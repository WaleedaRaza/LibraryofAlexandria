"""S0: confirm the PDF is the work the catalog says it is.

Rules only: the catalog's author surname (or, failing that, the main title word) must appear
in the first pages of text. The largest-font lines of the first text page become
`detected_title`. A mismatch is flagged, not fixed: a person (or a later model check) decides.
"""
from __future__ import annotations
import hashlib
import re
from pathlib import Path

import pymupdf

from .model import Edition

_GENERIC = {"the", "a", "an", "of", "and", "v", "dup", "by", "unknown", "pdf", "book", "full", "text"}


def _words(s: str) -> list[str]:
    return [w for w in re.findall(r"[a-z]+", s.lower()) if w not in _GENERIC and len(w) > 2]


def detect_title(doc: pymupdf.Document, max_pages: int = 6) -> str:
    for page in list(doc)[:max_pages]:
        lines = []
        for b in page.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                t = "".join(s["text"] for s in l["spans"]).strip()
                if t and l["spans"]:
                    lines.append((max(s["size"] for s in l["spans"]), t))
        if sum(len(t) for _, t in lines) < 20:
            continue
        top = max(sz for sz, _ in lines)
        big = []
        for sz, t in lines:
            if sz >= top * 0.75 and t not in big:
                big.append(t)
        return " ".join(big)[:160]
    return ""


def run(pdf_path: Path, edition_id: str, catalog_title: str = "", catalog_author: str = "") -> Edition:
    data = pdf_path.read_bytes()
    doc = pymupdf.open(stream=data, filetype="pdf")
    head = " ".join(p.get_text() for p in list(doc)[:6]).lower()
    ed = Edition(
        id=edition_id, path=str(pdf_path), sha256=hashlib.sha256(data).hexdigest(), pages=doc.page_count,
        producer=(doc.metadata or {}).get("producer", "") or "", has_outline=bool(doc.get_toc()),
        detected_title=detect_title(doc), catalog_title=catalog_title, catalog_author=catalog_author,
    )
    author_words = [w for w in _words(catalog_author) if not re.fullmatch(r"[ivx]+", w)]
    title_words = _words(catalog_title)
    if author_words:
        missing = [w for w in author_words if w not in head]
        if len(missing) == len(author_words):
            ed.identity_ok = False
            ed.identity_note = f"catalog author {catalog_author!r} not found in first pages; text starts {ed.detected_title!r}"
    elif title_words and not any(w in head for w in title_words):
        ed.identity_ok = False
        ed.identity_note = f"catalog title {catalog_title!r} not found in first pages"
    return ed
