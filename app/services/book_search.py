"""Ask one book a question and get back the passage that answers it.

The answer is always a real passage from the PDF the reader opens, with its
page number, so the reader can jump straight to it. The model (when one is
configured) only does two things: rewrite the question into the vocabulary of
the book, and choose among passages that retrieval already found and quote
from the one it picks. Quotes are checked against the passage text; a quote
that is not in the book is replaced with one that is.

Text comes from the same PDF the reader shows. Extraction runs once per book
and is cached on disk, so the first question about a book costs a download and
a few seconds of PyMuPDF, and later questions cost milliseconds.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
import math
import re
import unicodedata
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote as url_quote

import httpx

from ..config import settings
from .asset_service import AssetService

logger = logging.getLogger(__name__)

MAX_PDF_BYTES = 90 * 1024 * 1024
MIN_PASSAGE_WORDS = 40
MAX_PASSAGE_WORDS = 190
_MEMORY: "OrderedDict[str, list[Passage]]" = OrderedDict()
_MEMORY_BOOKS = 12
_load_slots = asyncio.Semaphore(2)
_book_locks: dict[str, asyncio.Lock] = {}

STOP = set("""a about above after again against all am an and any are as at be because been before being below
between both but by can could did do does doing down during each few for from further had has have having he her
here hers herself him himself his how i if in into is it its itself just me more most my myself no nor not now of
off on once only or other our ours ourselves out over own same she should so some such than that the their theirs
them themselves then there these they this those through to too under until up very was we were what when where
which while who whom why will with would you your yours yourself yourselves thee thou thy thine hath doth shall
unto upon also may might must one ones us said say says""".split())

# Older books name things differently. A model rewrite covers this properly; this
# short table keeps the commonest gaps closed when no model is configured.
RELATED = {
    "luck": "fortune chance", "lucky": "fortune", "promise": "faith word keep faith", "promises": "faith word",
    "anger": "angry wrath rage", "angry": "anger wrath", "die": "death dying", "death": "die dying mortal",
    "ruler": "prince king sovereign", "leader": "prince ruler", "government": "state commonwealth",
    "happy": "happiness happier blessed", "happiness": "happy good life", "money": "wealth riches gold",
    "love": "loved loving", "fear": "feared afraid", "god": "gods divine", "soul": "mind spirit",
    "morning": "bed sleep", "work": "labour labor", "freedom": "liberty free", "people": "men mankind",
    "cave": "den prisoners shadows", "hatred": "hostility hostilities hate", "hate": "hatred hostility", "lying": "lie falsehood deceive", "friends": "friendship friend",
}

# Lines that belong to the edition, not the book.
FURNITURE = re.compile(
    r"project gutenberg|gutenberg\.org|www\.|https?://|all rights reserved|isbn|copyright ©|"
    r"this ebook is for the use|produced by|transcriber'?s note|table of contents|\.{5,}",
    re.I,
)


@dataclass
class Passage:
    page: int  # 1-based, the page number the reader shows
    text: str
    terms: Counter = field(default_factory=Counter, repr=False)
    weight: float = 1.0  # below 1 for headings, contents pages and other furniture


@dataclass
class Answer:
    page: int
    quote: str
    passage: str
    answer: str
    grounded_by_model: bool
    alternates: list[dict]


class BookTextUnavailable(Exception):
    """The book's text cannot be read (no PDF, scanned images only, or too large)."""


# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------

def _stem(word: str) -> str:
    for suffix in ("ingly", "edly", "ness", "ments", "ment", "ings", "ing", "ies", "ied", "es", "ed", "ly", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def expand_related(question: str) -> str:
    words = re.findall(r"[a-z]+", question.lower())
    extra = [RELATED[w] for w in words if w in RELATED]
    return question + (" " + " ".join(extra) if extra else "")


def tokens(text: str) -> list[str]:
    text = unicodedata.normalize("NFKC", text)
    return [_stem(w) for w in re.findall(r"[a-z][a-z']+", text.lower().replace("’", "'")) if w not in STOP and len(w) > 2]


def _clean_page(text: str) -> str:
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or FURNITURE.search(stripped):
            lines.append("")
            continue
        if re.fullmatch(r"(page\s*)?[\divxlcdmIVXLCDM.\-–— ]{1,12}", stripped, re.I):  # running page numbers
            continue
        lines.append(stripped)
    text = "\n".join(lines)
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # rejoin hyphenated line breaks
    text = re.sub(r"\bPage \d{1,4}\b", " ", text)  # page stamps printed inside the text block
    return text


def page_passages(page_number: int, text: str) -> list[Passage]:
    """Split one page into passages of roughly paragraph size, keeping sentences whole."""
    text = _clean_page(text)
    paragraphs = [re.sub(r"\s+", " ", block).strip() for block in re.split(r"\n\s*\n", text)]
    paragraphs = [p for p in paragraphs if p]
    if len(paragraphs) <= 1:
        # Many PDFs have no blank lines; fall back to sentence windows.
        flat = re.sub(r"\s+", " ", text).strip()
        paragraphs = re.split(r"(?<=[.!?;])\s+(?=[A-Z“\"'‘])", flat) if flat else []
    out: list[Passage] = []
    buffer: list[str] = []
    words = 0
    for paragraph in paragraphs:
        size = len(paragraph.split())
        if buffer and words + size > MAX_PASSAGE_WORDS:
            out.append(" ".join(buffer))
            buffer, words = [], 0
        buffer.append(paragraph)
        words += size
        if words >= MIN_PASSAGE_WORDS * 2:
            out.append(" ".join(buffer))
            buffer, words = [], 0
    if buffer:
        if out and words < MIN_PASSAGE_WORDS:
            out[-1] = out[-1] + " " + " ".join(buffer)
        else:
            out.append(" ".join(buffer))
    passages = []
    for chunk in out:
        if len(chunk.split()) < MIN_PASSAGE_WORDS // 2:
            continue
        letters = sum(c.isalpha() for c in chunk)
        if letters < 0.6 * len(chunk):  # tables, indexes, numerals
            continue
        upper = sum(c.isupper() for c in chunk)
        weight = 0.5 if upper > 0.25 * letters else 1.0  # running heads, contents, lecture synopses
        passages.append(Passage(page_number, chunk, Counter(tokens(chunk)), weight))
    return passages


def passages_from_pages(pages: list[str]) -> list[Passage]:
    out: list[Passage] = []
    for index, text in enumerate(pages):
        out.extend(page_passages(index + 1, text))
    return out


def extract_pages(pdf_bytes: bytes) -> list[str]:
    import fitz

    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        return [unicodedata.normalize("NFKC", page.get_text("text")) for page in document]


def _cache_path(book_id: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_.-]", "_", book_id)[:120]
    return Path(settings.DATA_DIR) / "text_cache" / f"{safe}.json.gz"


async def _pdf_bytes(book: dict) -> bytes:
    assets = AssetService()
    local = assets.local_pdf(book)
    if local:
        if local.stat().st_size > MAX_PDF_BYTES:
            raise BookTextUnavailable("This PDF is too large to search.")
        return await asyncio.to_thread(local.read_bytes)
    url = await asyncio.to_thread(assets.signed_pdf_url, book)
    if not url:
        raise BookTextUnavailable("This book has no readable file yet.")
    async with httpx.AsyncClient(timeout=httpx.Timeout(40.0), follow_redirects=False) as client:
        async with client.stream("GET", url) as response:
            if response.status_code != 200:
                raise BookTextUnavailable("The book's file could not be fetched.")
            chunks, size = [], 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > MAX_PDF_BYTES:
                    raise BookTextUnavailable("This PDF is too large to search.")
                chunks.append(chunk)
    return b"".join(chunks)


async def book_passages(book: dict) -> list[Passage]:
    book_id = book["id"]
    if book_id in _MEMORY:
        _MEMORY.move_to_end(book_id)
        return _MEMORY[book_id]
    lock = _book_locks.setdefault(book_id, asyncio.Lock())
    async with lock:
        if book_id in _MEMORY:
            return _MEMORY[book_id]
        path = _cache_path(book_id)
        pages: list[str] | None = None
        if path.is_file():
            try:
                pages = json.loads(gzip.decompress(path.read_bytes()))["pages"]
            except Exception:
                pages = None
        if pages is None:
            async with _load_slots:
                data = await _pdf_bytes(book)
                try:
                    pages = await asyncio.to_thread(extract_pages, data)
                except Exception as exc:
                    raise BookTextUnavailable("This PDF's text could not be read.") from exc
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(gzip.compress(json.dumps({"pages": pages}).encode("utf-8")))
            except OSError:
                logger.info("Could not cache text for %s", book_id)
        passages = passages_from_pages(pages)
        if len(passages) < 5:
            raise BookTextUnavailable("This edition is scanned images, so its text cannot be searched yet.")
        _MEMORY[book_id] = passages
        while len(_MEMORY) > _MEMORY_BOOKS:
            _MEMORY.popitem(last=False)
        return passages


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

def bm25(passages: list[Passage], queries: list[str], k1: float = 1.2, b: float = 0.75) -> list[tuple[float, int]]:
    """Score every passage against several phrasings of the question; a passage keeps its best phrasing."""
    n = len(passages)
    if not n:
        return []
    avg = sum(sum(p.terms.values()) for p in passages) / n or 1.0
    df: Counter = Counter()
    for passage in passages:
        df.update(passage.terms.keys())
    best = [0.0] * n
    last_page = max(p.page for p in passages)
    for query in queries:
        terms = set(tokens(query))
        if not terms:
            continue
        idf = {t: math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5)) for t in terms if df[t]}
        for index, passage in enumerate(passages):
            length = sum(passage.terms.values())
            score = 0.0
            matched = 0
            for term, weight in idf.items():
                tf = passage.terms.get(term, 0)
                if tf:
                    matched += 1
                    score += weight * tf * (k1 + 1) / (tf + k1 * (1 - b + b * length / avg))
            # Reward passages that answer more of the question, not one word many times.
            score *= (1 + 0.15 * max(0, matched - 1)) * passage.weight
            # Editors' introductions sit in the first pages; the reader asked the author.
            if passage.page <= max(3, last_page // 10):
                score *= 0.8
            if score > best[index]:
                best[index] = score
    ranked = sorted(((score, index) for index, score in enumerate(best) if score > 0), reverse=True)
    return ranked


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?;:])\s+", text) if len(s.split()) >= 4]


def best_quote(passage: str, queries: list[str], max_words: int = 60) -> str:
    """The run of up to three sentences in the passage that shares the most with the question."""
    sentences = _sentences(passage) or [passage]
    wanted = set()
    for query in queries:
        wanted.update(tokens(query))
    best, best_score = sentences[0], -1.0
    for start in range(len(sentences)):
        for span in (1, 2, 3):
            window = sentences[start:start + span]
            if len(window) < span:
                break
            text = " ".join(window)
            if len(text.split()) > max_words and span > 1:
                break
            hits = len(wanted & set(tokens(text)))
            score = hits - 0.01 * len(text.split())
            if score > best_score:
                best, best_score = text, score
    words = best.split()
    return " ".join(words[:max_words]) + ("…" if len(words) > max_words else "")


def _normal(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower().replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def quote_in(quote: str, passage: str) -> bool:
    q = _normal(quote.rstrip("…"))
    return len(q.split()) >= 4 and q in _normal(passage)


def find_phrase(quote: str, words: int = 9) -> str:
    """A short, distinctive run from the start of the quote, used by the reader to light it up on the page."""
    return " ".join(quote.rstrip("…").split()[:words])


def open_url(book_id: str, page: int, quote: str) -> str:
    return f"/read/{url_quote(book_id, safe='')}?page={page}&find={url_quote(find_phrase(quote))}"


# ---------------------------------------------------------------------------
# Model steps (optional)
# ---------------------------------------------------------------------------

EXPAND_SYSTEM = (
    "You help search inside one book. Rewrite the reader's question into three short search phrasings that use the "
    "words this author and this translation would actually use (period vocabulary, the book's own terms, likely "
    "synonyms). Return JSON: {\"queries\": [\"...\", \"...\", \"...\"]}."
)

CHOOSE_SYSTEM = (
    "You answer a reader's question using ONLY passages from one book. You are shown numbered passages that a search "
    "found. Pick the single passage that best answers the question. Quote it exactly: copy one to three consecutive "
    "sentences verbatim from that passage, no more than 60 words. Prefer the author's own text over an editor's "
    "introduction, preface or notes. Then answer in two to four plain sentences that say "
    "what the author says, not what you know about the book. If no passage answers it, pick the closest and say "
    "plainly what it does and does not settle. Return JSON: {\"passage\": <number>, \"quote\": \"...\", \"answer\": \"...\"}."
)


def _llm():
    if settings.USE_MOCK_AGENTS or not settings.OPENAI_API_KEY:
        return None
    try:
        from ..agents.llm_provider import LLMProvider

        return LLMProvider(timeout=25, max_retries=1)
    except Exception:
        return None


def _call(llm, system: str, user: str, agent: str, max_tokens: int) -> dict:
    result = llm.call(system, user, agent_name=agent, temperature=0.2, max_tokens=max_tokens, response_format="json")
    if isinstance(result, dict) and isinstance(result.get("content"), dict):
        return result["content"]
    if isinstance(result, dict) and isinstance(result.get("content"), str):
        try:
            return json.loads(result["content"])
        except ValueError:
            return {}
    return result if isinstance(result, dict) else {}


def expand_question(llm, book: dict, question: str) -> list[str]:
    if not llm:
        related = expand_related(question)
        return [question] if related == question else [question, related]
    try:
        data = _call(llm, EXPAND_SYSTEM, f"Book: {book.get('title')} by {book.get('author')}\nQuestion: {question}",
                     "book_search.expand", 200)
        extra = [str(q)[:200] for q in data.get("queries", []) if isinstance(q, str) and q.strip()][:3]
    except Exception:
        logger.info("Question expansion failed; searching the question as written")
        extra = []
    return [question, *extra]


def choose_and_answer(llm, book: dict, question: str, candidates: list[Passage]) -> dict | None:
    if not llm or not candidates:
        return None
    listing = "\n\n".join(f"[{i + 1}] (page {p.page}) {p.text}" for i, p in enumerate(candidates))
    try:
        data = _call(llm, CHOOSE_SYSTEM,
                     f"Book: {book.get('title')} by {book.get('author')}\nQuestion: {question}\n\nPassages:\n{listing}",
                     "book_search.choose", 450)
    except Exception:
        logger.info("Passage choice failed; using the search order")
        return None
    try:
        choice = int(data.get("passage", 0)) - 1
    except (TypeError, ValueError):
        return None
    if not 0 <= choice < len(candidates):
        return None
    return {"index": choice, "quote": str(data.get("quote") or ""), "answer": str(data.get("answer") or "").strip()}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def ask_book(book: dict, question: str) -> Answer | None:
    passages = await book_passages(book)
    llm = _llm()
    queries = await asyncio.to_thread(expand_question, llm, book, question)
    ranked = bm25(passages, queries)
    if not ranked:
        return None
    candidates = [passages[index] for _, index in ranked[:6]]
    picked = await asyncio.to_thread(choose_and_answer, llm, book, question, candidates)
    chosen = candidates[picked["index"]] if picked else candidates[0]
    quote = picked["quote"] if picked else ""
    if not quote_in(quote, chosen.text):
        quote = best_quote(chosen.text, queries)
    answer = picked["answer"] if picked else ""
    alternates = [
        {"page": p.page, "quote": best_quote(p.text, queries, max_words=32)}
        for p in candidates if p is not chosen
    ][:3]
    return Answer(page=chosen.page, quote=quote, passage=chosen.text, answer=answer,
                  grounded_by_model=bool(picked and answer), alternates=alternates)
