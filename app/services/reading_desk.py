"""Discovery desk for manually reviewing public book links.

Search engines supply candidates. This module checks whether a URL actually
returns a PDF, estimates book length where feasible, and records its evidence.
It never signs in, defeats a paywall, publishes files, or auto-opens tabs.
"""

from __future__ import annotations

import asyncio
import io
import ipaddress
import json
import logging
import re
import socket
import time
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urljoin, urlparse

import httpx
from ddgs import DDGS
from pypdf import PdfReader


logger = logging.getLogger(__name__)

MAX_BOOKS_PER_JOB = 500
ARCHIVE_ITEMS_PER_BOOK = 5
ARCHIVE_PDF_FORMATS = {"Text PDF", "Image Container PDF", "Additional Text PDF"}
MAX_CANDIDATES_PER_BOOK = 18
FULL_INSPECTIONS_PER_BOOK = 4
MAX_PDF_BYTES = 80 * 1024 * 1024
PROBE_BYTES = 96 * 1024
JOB_TTL_SECONDS = 60 * 60 * 8

# Rough length references for books where a search often returns a different
# volume or a collected series. Edition and PDF page counts can vary widely.
EXPECTED_PAGE_HINTS = {
    "harry potter and the philosopher's stone": 300,
    "the hobbit": 310,
    "the lord of the rings": 1190,
    "a game of thrones": 800,
    "dune": 500,
    "the hunger games": 390,
    "percy jackson and the lightning thief": 380,
    "the lion, the witch and the wardrobe": 200,
    "the three-body problem": 400,
    "project hail mary": 500,
    "the martian": 380,
    "the shining": 450,
    "it": 1100,
    "neuromancer": 270,
    "kindred": 280,
    "1984": 330,
    "animal farm": 110,
    "fahrenheit 451": 190,
    "brave new world": 270,
    "the handmaid's tale": 310,
    "don quixote": 950,
    "pride and prejudice": 400,
    "jane eyre": 500,
    "the great gatsby": 190,
    "crime and punishment": 650,
    "frankenstein": 280,
    "dracula": 400,
    "to kill a mockingbird": 280,
    "things fall apart": 210,
    "invisible man": 500,
    "one hundred years of solitude": 410,
    "their eyes were watching god": 220,
    "the remains of the day": 250,
    "the kite runner": 370,
    "the book thief": 550,
    "the song of achilles": 370,
    "the seven husbands of evelyn hugo": 390,
    "normal people": 270,
    "the silent patient": 330,
    "and then there were none": 260,
    "the adventures of sherlock holmes": 300,
    "meditations": 250,
    "the art of war": 110,
    "the analects": 250,
    "nicomachean ethics": 300,
    "critique of pure reason": 700,
    "the histories": 700,
    "history of the peloponnesian war": 650,
    "narrative of the life of frederick douglass": 130,
    "the structure of scientific revolutions": 220,
    "cosmos": 350,
    "silent spring": 370,
    "a brief history of time": 220,
    "the emperor of all maladies": 580,
    "sapiens": 440,
    "thinking, fast and slow": 500,
    "the body keeps the score": 450,
    "ways of seeing": 165,
    "atomic habits": 300,
    "the 48 laws of power": 450,
    "man's search for meaning": 165,
    "the psychology of money": 250,
    "how to win friends and influence people": 290,
    "the power of now": 230,
    "the subtle art of not giving a f*ck": 220,
    "deep work": 300,
    "can't hurt me": 360,
    "the four agreements": 150,
    "the creative act": 400,
    "on writing": 300,
}

SEARCH_ALIASES = {
    "harry potter and the philosopher's stone": "Harry Potter and the Sorcerer's Stone",
    "percy jackson and the lightning thief": "The Lightning Thief",
    "the poems of emily dickinson": "Collected Poems of Emily Dickinson",
}

# Repository hosts can help rank persistence and accessibility. Hosting alone
# does not establish that a particular uploaded book is licensed for sharing.
OPEN_REPOSITORIES = {
    "archive.org",
    "gutenberg.org",
    "www.gutenberg.org",
    "loc.gov",
    "www.loc.gov",
    "standardebooks.org",
    "www.standardebooks.org",
    "wikisource.org",
    "en.wikisource.org",
    "oapen.org",
    "library.oapen.org",
    "doabooks.org",
    "www.doabooks.org",
    "open.umn.edu",
    "openstax.org",
    "www.openstax.org",
}

GATED_DOMAINS = {
    # Summary and study-guide sellers: never the book itself, even when the file is a PDF.
    "bookey.app",
    "cdn.bookey.app",
    "blinkist.com",
    "shortform.com",
    "litcharts.com",
    "sparknotes.com",
    "gradesaver.com",
    "getabstract.com",
    "12min.com",
    "scribd.com",
    "www.scribd.com",
    "coursehero.com",
    "www.coursehero.com",
    "studocu.com",
    "www.studocu.com",
    "academia.edu",
    "www.academia.edu",
}

NEGATIVE_TERMS = {
    "preview": -22,
    "sample": -22,
    "excerpt": -24,
    "summary": -28,
    "study guide": -34,
    "login": -30,
    "sign in": -30,
    "subscribe": -30,
    "buy": -20,
    "audiobook": -22,
}


def parse_books(raw: str) -> list[dict[str, str]]:
    """Parse one title per line, optionally followed by an author."""
    books: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for raw_line in raw.splitlines():
        line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", raw_line).strip()
        if not line:
            continue

        title, author = line, ""
        for separator in (" — ", " – ", "\t", " | "):
            if separator in line:
                title, author = (part.strip() for part in line.split(separator, 1))
                break
        else:
            by_match = re.match(r"^(.+?)\s+by\s+([^,;]+)$", line, flags=re.IGNORECASE)
            if by_match:
                title, author = by_match.group(1).strip(), by_match.group(2).strip()

        if not title:
            continue
        key = (title.casefold(), author.casefold())
        if key not in seen:
            seen.add(key)
            books.append({"title": title[:240], "author": author[:160]})
        if len(books) >= MAX_BOOKS_PER_JOB:
            break
    return books


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").casefold().rstrip(".")


def _is_open_repository(host: str) -> bool:
    return any(host == domain or host.endswith(f".{domain}") for domain in OPEN_REPOSITORIES)


def _is_gated(host: str) -> bool:
    return any(host == domain or host.endswith(f".{domain}") for domain in GATED_DOMAINS)


def _institutional_host(host: str) -> bool:
    return host.endswith(".gov") or host.endswith(".edu") or ".ac." in host


def _token_overlap(needle: str, haystack: str) -> float:
    tokens = {token for token in re.findall(r"[a-z0-9]+", needle.casefold()) if len(token) > 2}
    if not tokens:
        return 0.0
    haystack_tokens = set(re.findall(r"[a-z0-9]+", haystack.casefold()))
    return len(tokens & haystack_tokens) / len(tokens)


def _title_overlap(book: dict[str, str], item: dict[str, Any]) -> float:
    return _token_overlap(book["title"], _identity_text(item["title"], item["url"]))


def _identity_text(result_title: str, url: str) -> str:
    """Favor the named file over enclosing folders, which may hold other books."""
    parsed = urlparse(url)
    filename = unquote(parsed.path.rsplit("/", 1)[-1])
    archived_file = " ".join(parse_qs(parsed.query).get("file", []))
    return f"{result_title} {filename} {archived_file}"


async def _expected_pages(book: dict[str, str], client: httpx.AsyncClient) -> int | None:
    """Use Open Library as a rough edition-length reference, when available."""
    hint = EXPECTED_PAGE_HINTS.get(book["title"].casefold())
    if hint:
        return hint
    query = f"{book['title']} {book['author']}"
    try:
        response = await client.get(
            "https://openlibrary.org/search.json",
            params={"q": query, "fields": "title,author_name,number_of_pages_median", "limit": 12},
        )
        response.raise_for_status()
        docs = response.json().get("docs", [])
    except (httpx.HTTPError, ValueError, json.JSONDecodeError):
        return EXPECTED_PAGE_HINTS.get(book["title"].casefold())
    for doc in docs:
        title = str(doc.get("title") or "")
        pages = doc.get("number_of_pages_median")
        authors = " ".join(doc.get("author_name") or [])
        if not isinstance(pages, int) or pages < 30:
            continue
        if _token_overlap(book["author"], authors) < 0.5:
            continue
        requested = book["title"].casefold()
        named = title.casefold()
        if _token_overlap(title, book["title"]) >= 0.8 and (requested == named or requested.endswith(named) or named.endswith(requested)):
            return pages
    return EXPECTED_PAGE_HINTS.get(book["title"].casefold())


def assess_edition(book: dict[str, str], item: dict[str, Any], expected_pages: int | None, *, force: bool = False) -> dict[str, Any]:
    """Rescore a checked result using title identity and plausible book length."""
    if item.get("quality_checked") and not force:
        return item
    if force and item.get("quality_checked"):
        previous_fit = item.get("edition_fit")
        if "pre_quality_score" in item:
            item["score"] = item["pre_quality_score"]
        else:
            # Checkpoints made before pre_quality_score was recorded.
            if previous_fit == "possible collection":
                item["score"] += 32
            elif previous_fit == "possible excerpt":
                item["score"] += 25
            elif previous_fit == "plausible length":
                item["score"] -= 6
            if "requested title absent from result" in item.get("reasons", []):
                item["score"] += 25
        item["reasons"] = [reason for reason in item.get("reasons", []) if reason not in {
            "requested title absent from result", "plausible edition length", "title and author on opening pages", "summary or guide on opening pages"
        } and not reason.endswith(" expected")]
    item["pre_quality_score"] = item["score"]
    source_label = f"{item.get('title', '')} {item.get('url', '')}".casefold()
    if "litcharts" in source_label or "bookey.app" in source_label:
        item["summary_warning"] = True
    item["expected_pages"] = expected_pages
    item["quality_checked"] = True
    item["edition_fit"] = "length unknown"
    if not item.get("viewable"):
        return item
    title_match = _title_overlap(book, item)
    if title_match < 0.45 and len(re.findall(r"\w+", book["title"])) > 1:
        item["score"] -= 25
        item["reasons"].append("requested title absent from result")
    pages = item.get("page_count")
    if expected_pages and pages:
        ratio = pages / expected_pages
        if ratio > 1.9:
            item["score"] -= 32
            item["edition_fit"] = "possible collection"
            item["reasons"].append(f"{pages} pages vs roughly {expected_pages} expected")
        elif ratio < 0.42:
            item["score"] -= 25
            item["edition_fit"] = "possible excerpt"
            item["reasons"].append(f"{pages} pages vs roughly {expected_pages} expected")
        elif 0.55 <= ratio <= 1.65:
            item["score"] += 6
            item["edition_fit"] = "plausible length"
            item["reasons"].append("plausible edition length")
        else:
            item["edition_fit"] = "check edition"
    if item.get("summary_warning"):
        item["score"] -= 38
        item["reasons"].append("summary or guide on opening pages")
    elif (item.get("title_page_match") or 0) >= 0.65 and (item.get("author_page_match") or 0) >= 0.5:
        item["score"] += 8
        item["reasons"].append("title and author on opening pages")
    item["score"] = max(0, min(99, item["score"]))
    return item


def _initial_candidate(result: dict[str, Any], book: dict[str, str], query: str, rank: int) -> dict[str, Any] | None:
    url = str(result.get("href") or result.get("url") or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None

    result_title = str(result.get("title") or "Untitled result").strip()
    snippet = str(result.get("body") or result.get("description") or "").strip()
    host = _host(url)
    identity_text = _identity_text(result_title, url)
    haystack = f"{identity_text} {snippet}"
    title_match = _token_overlap(book["title"], identity_text)
    snippet_match = _token_overlap(book["title"], snippet)
    author_match = _token_overlap(book["author"], haystack) if book["author"] else 0.0

    score = max(0, 22 - rank)
    reasons: list[str] = []
    if title_match >= 0.75:
        score += 24
        reasons.append("strong title match")
    elif title_match >= 0.45:
        score += 12
        reasons.append("partial title match")
    else:
        score -= 24
        reasons.append("title missing from link")
        if snippet_match >= 0.75:
            score += 4
            reasons.append("title only in search excerpt")
    if author_match >= 0.5:
        score += 10
        reasons.append("author match")
    if parsed.path.casefold().endswith(".pdf") or ".pdf?" in url.casefold():
        score += 18
        reasons.append("PDF-shaped URL")
    if _is_open_repository(host):
        score += 22
        reasons.append("archive host")
    elif _institutional_host(host):
        score += 10
        reasons.append("institutional host")
    if _is_gated(host):
        score -= 55
        reasons.append("known gated host")
    lowered = haystack.casefold()
    for term, penalty in NEGATIVE_TERMS.items():
        if term in lowered:
            score += penalty
            reasons.append(term)

    return {
        "title": result_title,
        "url": url,
        "final_url": url,
        "display_url": f"{host}{parsed.path[:110]}",
        "domain": host,
        "snippet": snippet[:360],
        "query": query,
        "search_rank": rank,
        "score": score,
        "confidence": "unverified",
        "state": "queued",
        "rights": "archive host; rights unverified" if _is_open_repository(host) else "rights unverified",
        "page_count": None,
        "size_bytes": None,
        "content_type": None,
        "viewable": False,
        "reasons": reasons,
        "error": None,
    }


def _search_queries(book: dict[str, str], *, broad: bool = False) -> list[str]:
    title = book["title"].replace('"', " ").strip()
    author = book["author"].replace('"', " ").strip()
    identity = f'"{title}" "{author}"' if author else f'"{title}"'
    if broad:
        alias = SEARCH_ALIASES.get(title.casefold(), title)
        return [
            f'"{alias}" pdf {author}',
            f"{alias} {author} complete book pdf",
        ]
    return [
        f"{identity} filetype:pdf",
        f"{identity} PDF full text",
        f'(site:gutenberg.org OR site:archive.org/download OR site:loc.gov OR site:oapen.org) {identity}',
    ]


def _archive_results(book: dict[str, str]) -> list[dict[str, Any]]:
    """Ask the Internet Archive directly for scanned or uploaded PDF editions.

    Web search engines rate-limit datacenter traffic, so this keyless catalog API is the
    finder's dependable backbone: it answers in about a second and names the exact files.
    """
    title = book["title"].replace('"', " ").strip()
    author_tokens = [token for token in re.findall(r"[A-Za-z][A-Za-z'\-]+", book["author"]) if len(token) > 2]
    query = f'title:("{title}") AND mediatype:texts AND format:(PDF)'
    if author_tokens:
        query += f' AND creator:({author_tokens[-1]})'
    results: list[dict[str, Any]] = []
    try:
        with httpx.Client(timeout=httpx.Timeout(8.0, connect=4.0), headers={"User-Agent": "WaleedsReadingDesk/1.0 (+public book discovery)"}) as client:
            response = client.get(
                "https://archive.org/advancedsearch.php",
                params={"q": query, "fl[]": ["identifier", "title", "creator", "downloads"], "rows": ARCHIVE_ITEMS_PER_BOOK,
                        "sort[]": "downloads desc", "output": "json"},
            )
            response.raise_for_status()
            docs = response.json().get("response", {}).get("docs", [])
            for doc in docs:
                identifier = str(doc.get("identifier") or "")
                if not identifier:
                    continue
                try:
                    files = client.get(f"https://archive.org/metadata/{identifier}/files").json().get("result", [])
                except (httpx.HTTPError, ValueError):
                    continue
                creator = doc.get("creator")
                creator_text = " ".join(creator) if isinstance(creator, list) else str(creator or "")
                for entry in files:
                    name = str(entry.get("name") or "")
                    fmt = str(entry.get("format") or "")
                    lowered = name.casefold()
                    if not (fmt in ARCHIVE_PDF_FORMATS or lowered.endswith(".pdf")):
                        continue
                    if "encrypted" in fmt.casefold() or "_encrypted" in lowered or lowered.endswith("_bw.pdf") or "/" in name:
                        continue
                    size = int(entry["size"]) if str(entry.get("size", "")).isdigit() else None
                    if size is not None and size < 200_000:
                        continue  # covers, excerpts, and metadata stubs
                    results.append({
                        "href": f"https://archive.org/download/{identifier}/{quote(name)}",
                        "title": f"{doc.get('title') or identifier} — {name}",
                        "body": f"{creator_text} · Internet Archive item {identifier}",
                        "archive_identifier": identifier,
                        "archive_downloads": int(doc.get("downloads") or 0),
                        "size_bytes": size,
                    })
    except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("Internet Archive search failed for %r: %s", title, exc)
    return results


def _search_web(book: dict[str, str], *, broad: bool = False) -> list[dict[str, Any]]:
    candidates: OrderedDict[str, dict[str, Any]] = OrderedDict()

    def run_query(query: str) -> tuple[str, list[dict[str, Any]]]:
        if query == "archive.org":
            return query, _archive_results(book)
        try:
            results = DDGS(timeout=10).text(query, region="us-en", safesearch="moderate", max_results=12)
        except Exception as exc:
            # Search engines throttle datacenter addresses; say so in the logs instead of hiding it.
            logger.warning("Web search returned nothing for %r: %s: %s", query, type(exc).__name__, str(exc)[:160])
            results = []
        return query, results

    queries = _search_queries(book, broad=broad)
    if not broad:
        queries = ["archive.org", *queries]
    with ThreadPoolExecutor(max_workers=len(queries), thread_name_prefix="PDFSearch") as executor:
        batches = executor.map(run_query, queries)
        for query, results in batches:
            for rank, result in enumerate(results, 1):
                candidate = _initial_candidate(result, book, query, rank)
                if not candidate:
                    continue
                if result.get("archive_identifier"):
                    candidate["archive_listed"] = True
                    candidate["size_bytes"] = result.get("size_bytes")
                    candidate["score"] += 14  # the archive's own catalog named this file as a PDF
                    candidate["reasons"].append("listed by the Internet Archive")
                    if (result.get("archive_downloads") or 0) >= 1000:
                        candidate["score"] += 6
                        candidate["reasons"].append("widely downloaded")
                normalized = candidate["url"].split("#", 1)[0].rstrip("/")
                current = candidates.get(normalized)
                if not current or candidate["score"] > current["score"]:
                    candidates[normalized] = candidate
    return sorted(candidates.values(), key=lambda item: item["score"], reverse=True)[:MAX_CANDIDATES_PER_BOOK]


async def _validate_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("unsupported URL")
    infos = await asyncio.to_thread(socket.getaddrinfo, parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_multicast or address.is_unspecified:
            raise ValueError("private network destination blocked")


async def _download_limited(
    client: httpx.AsyncClient,
    url: str,
    limit: int,
    *,
    range_probe: bool = False,
) -> tuple[bytes, httpx.Response, str]:
    current = url
    for _ in range(6):
        await _validate_public_url(current)
        headers = {"Range": f"bytes=0-{limit - 1}"} if range_probe else {}
        request = client.build_request("GET", current, headers=headers)
        response = await client.send(request, stream=True)
        if response.status_code in {301, 302, 303, 307, 308}:
            location = response.headers.get("location")
            await response.aclose()
            if not location:
                raise ValueError("redirect without destination")
            current = urljoin(current, location)
            continue

        chunks: list[bytes] = []
        size = 0
        async for chunk in response.aiter_bytes():
            next_size = size + len(chunk)
            if next_size > limit and range_probe:
                chunks.append(chunk[: limit - size])
                await response.aclose()
                return b"".join(chunks), response, current
            size = next_size
            if size > limit:
                await response.aclose()
                raise ValueError("file exceeds inspection limit")
            chunks.append(chunk)
        await response.aclose()
        return b"".join(chunks), response, current
    raise ValueError("too many redirects")


def _pdf_page_count(data: bytes) -> int | None:
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        return len(reader.pages)
    except Exception:
        # A conservative fallback for malformed but readable PDFs.
        count = len(re.findall(rb"/Type\s*/Page\b", data))
        return count or None


def pdf_book_evidence(data: bytes, book: dict[str, str]) -> dict[str, Any]:
    """Extract a small identity fingerprint without retaining copyrighted text."""
    evidence: dict[str, Any] = {"page_count": _pdf_page_count(data), "title_page_match": None, "author_page_match": None, "summary_warning": False}
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        front = " ".join((reader.pages[index].extract_text() or "")[:4000] for index in range(min(3, len(reader.pages))))
        if front.strip():
            evidence["title_page_match"] = round(_token_overlap(book["title"], front), 2)
            evidence["author_page_match"] = round(_token_overlap(book["author"], front), 2) if book["author"] else None
            lowered = front[:6000].casefold()
            evidence["summary_warning"] = any(marker in lowered for marker in (
                "bookey", "litcharts", "study guide", "study notes", "summary of the book", "book summary", "teaching guide", "reader resources"
            ))
    except Exception:
        pass
    return evidence


async def _probe_candidate(candidate: dict[str, Any], client: httpx.AsyncClient, book: dict[str, str], *, full_inspection: bool = False) -> dict[str, Any]:
    item = dict(candidate)
    try:
        probe, response, final_url = await _download_limited(client, item["url"], PROBE_BYTES, range_probe=True)
        item["final_url"] = final_url
        item["domain"] = _host(final_url)
        item["display_url"] = f"{item['domain']}{urlparse(final_url).path[:110]}"
        item["content_type"] = response.headers.get("content-type", "").split(";", 1)[0].casefold()
        item["state"] = "checked"

        if response.status_code in {401, 403}:
            item["score"] -= 45
            item["state"] = "gated"
            item["reasons"].append(f"HTTP {response.status_code}")
            return item
        if response.status_code == 429:
            item["score"] -= 15
            item["state"] = "rate limited"
            item["reasons"].append("source rate limited")
            return item
        if response.status_code >= 400:
            item["score"] -= 35
            item["state"] = "dead link"
            item["reasons"].append(f"HTTP {response.status_code}")
            return item

        is_pdf = probe.lstrip().startswith(b"%PDF-")
        if not is_pdf:
            item["score"] -= 38
            item["state"] = "not a PDF"
            item["reasons"].append("HTML or non-PDF response")
            return item

        item["score"] += 42
        item["confidence"] = "verified PDF"
        item["state"] = "PDF verified"
        item["viewable"] = True
        item["reasons"].append("PDF signature verified")

        trusted = _is_open_repository(item["domain"])
        institutional = _institutional_host(item["domain"])
        if trusted:
            item["rights"] = "archive host; rights unverified"
        elif institutional:
            item["rights"] = "institutional; verify rights"
            item["score"] += 6
        else:
            item["rights"] = "rights unverified"

        header_size = response.headers.get("content-range", "").split("/")[-1]
        if header_size.isdigit():
            item["size_bytes"] = int(header_size)
        elif response.headers.get("content-length", "").isdigit() and response.status_code == 200:
            item["size_bytes"] = int(response.headers["content-length"])

        # A few high-ranking PDFs get a complete local inspection so the page
        # count is real. Failure here does not erase a successful PDF probe.
        if full_inspection and (not item["size_bytes"] or item["size_bytes"] <= MAX_PDF_BYTES):
            try:
                data, full_response, final_url = await _download_limited(client, final_url, MAX_PDF_BYTES)
                if data.lstrip().startswith(b"%PDF-"):
                    item["final_url"] = final_url
                    item["size_bytes"] = len(data)
                    item.update(await asyncio.to_thread(pdf_book_evidence, data, book))
                    item["content_type"] = full_response.headers.get("content-type", item["content_type"]).split(";", 1)[0]
                    if item["page_count"]:
                        if item["page_count"] >= 40:
                            item["score"] += 18
                            item["reasons"].append("book-length PDF")
                        elif item["page_count"] < 16:
                            item["score"] -= 26
                            item["reasons"].append("likely excerpt or paper")
            except (httpx.HTTPError, OSError, ValueError) as exc:
                item["reasons"].append("page count unavailable")
                item["error"] = str(exc)[:180]
    except (httpx.HTTPError, OSError, ValueError) as exc:
        if item.get("archive_listed"):
            # The archive's catalog already told us this is a PDF; a slow mirror should not hide it.
            item["score"] += 20
            item["state"] = "PDF listed by archive"
            item["confidence"] = "archive-listed PDF"
            item["viewable"] = True
            item["rights"] = "archive host; rights unverified"
            item["reasons"].append("archive mirror slow to answer")
        else:
            item["score"] -= 28
            item["state"] = "unreachable"
            item["reasons"].append("probe failed")
        item["error"] = str(exc)[:180]
    return item


async def find_readings(title: str, author: str = "") -> list[dict[str, Any]]:
    book = {"title": title.strip(), "author": author.strip()}
    if not book["title"]:
        return []
    candidates = await asyncio.to_thread(_search_web, book)
    timeout = httpx.Timeout(14.0, connect=5.0)
    limits = httpx.Limits(max_connections=10, max_keepalive_connections=5)
    headers = {"User-Agent": "WaleedsReadingDesk/1.0 (+public book discovery)"}
    async with httpx.AsyncClient(timeout=timeout, limits=limits, headers=headers) as client:
        expected_task = asyncio.create_task(_expected_pages(book, client))
        semaphore = asyncio.Semaphore(9)

        async def inspect(index: int, item: dict[str, Any]) -> dict[str, Any]:
            async with semaphore:
                return await _probe_candidate(item, client, book, full_inspection=index < FULL_INSPECTIONS_PER_BOOK)

        checked = await asyncio.gather(*(inspect(index, item) for index, item in enumerate(candidates)))
        if not any(item["viewable"] for item in checked):
            broad_candidates = await asyncio.to_thread(_search_web, book, broad=True)
            known = {item["url"] for item in checked}
            extra = [item for item in broad_candidates if item["url"] not in known]
            checked.extend(await asyncio.gather(*(inspect(index, item) for index, item in enumerate(extra))))
        expected = await expected_task
    for item in checked:
        # Scale the unbounded evidence sum without flattening every strong
        # candidate to 100. This is a ranking score, not a legal-certainty claim.
        item["score"] = max(0, min(99, round(item["score"] * 0.55)))
        assess_edition(book, item, expected)
    checked.sort(key=lambda item: (item["viewable"], item["score"]), reverse=True)
    for index, item in enumerate(checked, 1):
        item["rank"] = index
    return checked


_JOBS: OrderedDict[str, dict[str, Any]] = OrderedDict()
_TASKS: dict[str, asyncio.Task[Any]] = {}


def _prune_jobs() -> None:
    cutoff = time.time() - JOB_TTL_SECONDS
    for job_id in list(_JOBS):
        if _JOBS[job_id]["created_at"] < cutoff and job_id not in _TASKS:
            _JOBS.pop(job_id, None)


def start_search(books: list[dict[str, str]]) -> str:
    _prune_jobs()
    job_id = uuid.uuid4().hex[:12]
    _JOBS[job_id] = {
        "id": job_id,
        "status": "queued",
        "created_at": time.time(),
        "total": len(books),
        "completed": 0,
        "current": None,
        "books": [],
        "error": None,
        "cancel_requested": False,
    }
    task = asyncio.create_task(_run_search(job_id, books))
    _TASKS[job_id] = task
    task.add_done_callback(lambda _: _TASKS.pop(job_id, None))
    return job_id


async def _run_search(job_id: str, books: list[dict[str, str]]) -> None:
    job = _JOBS[job_id]
    job["status"] = "running"
    try:
        for book in books:
            if job["cancel_requested"]:
                job["status"] = "cancelled"
                break
            job["current"] = book
            started = time.monotonic()
            try:
                results = await find_readings(book["title"], book["author"])
                error = None
            except Exception as exc:  # one failed title should not kill a long batch
                results = []
                error = str(exc)[:240]
            job["books"].append(
                {
                    **book,
                    "results": results,
                    "error": error,
                    "elapsed": round(time.monotonic() - started, 1),
                }
            )
            job["completed"] += 1
        else:
            job["status"] = "complete"
        job["current"] = None
    except asyncio.CancelledError:
        job["status"] = "cancelled"
        job["current"] = None
        raise
    except Exception as exc:
        job["status"] = "failed"
        job["error"] = str(exc)[:300]
        job["current"] = None


def get_job(job_id: str) -> dict[str, Any] | None:
    job = _JOBS.get(job_id)
    if not job:
        return None
    return {key: value for key, value in job.items() if key not in {"created_at", "cancel_requested"}}


def stop_job(job_id: str) -> bool:
    job = _JOBS.get(job_id)
    if not job or job["status"] in {"complete", "failed", "cancelled"}:
        return False
    job["cancel_requested"] = True
    task = _TASKS.get(job_id)
    if task:
        task.cancel()
    return True
