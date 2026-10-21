"""Non-destructive work identity and display metadata for catalog editions."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import OrderedDict


_COPY_SUFFIX = re.compile(
    r"(?i)(?:__dup\s*\d+|\s+dup\s*\d+|\s+v(?:ersion)?\s*\d+|\s*\(\d+\))+$"
)


def clean_catalog_text(value: str) -> str:
    """Remove filename copy/version markers without mutating source evidence."""
    cleaned = re.sub(r"\s+", " ", str(value or "")).strip()
    cleaned = _COPY_SUFFIX.sub("", cleaned).strip(" -_")
    return cleaned


def normalized_identity(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.casefold()).strip()


def canonicalize_book(book: dict) -> dict:
    """Add a stable work ID and clean visible metadata while preserving raw fields."""
    raw_title = str(book.get("source_title") or book.get("title") or "").strip()
    raw_author = str(book.get("source_author") or book.get("author") or "").strip()
    title = clean_catalog_text(raw_title) or raw_title or "Untitled"
    author = clean_catalog_text(raw_author) or raw_author or "Unknown"
    identity = f"{normalized_identity(title)}\n{normalized_identity(author)}"
    work_id = "work_" + hashlib.sha256(identity.encode()).hexdigest()[:16]
    return {
        **book,
        "title": title,
        "author": author,
        "source_title": raw_title,
        "source_author": raw_author,
        "work_id": work_id,
    }


def group_editions(books: list[dict]) -> list[dict]:
    """Group records into works while keeping every inspectable edition."""
    grouped: OrderedDict[str, list[dict]] = OrderedDict()
    for original in books:
        book = canonicalize_book(original)
        grouped.setdefault(book["work_id"], []).append(book)
    works = []
    for work_id, editions in grouped.items():
        # Prefer a hosted PDF and then a featured record as the work's visual
        # representative. Edition IDs and source provenance remain untouched.
        representative = sorted(
            editions,
            key=lambda item: (
                item.get("availability") == "external_link",
                not bool(item.get("featured")),
                item.get("id") or "",
            ),
        )[0]
        works.append({
            "id": work_id,
            "title": representative["title"],
            "author": representative["author"],
            "domain": representative.get("domain") or "General",
            "representative": representative,
            "editions": editions,
            "edition_count": len(editions),
        })
    return works
