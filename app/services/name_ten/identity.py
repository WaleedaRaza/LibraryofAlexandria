"""One key per book, loose enough that the same book typed or catalogued differently matches.

The catalog's own work ids are exact (title and author as written), so it
holds "Brothers Karamazov", "The Brothers Karamazov" and "The Brothers
Karamazov Book Pdf" as three works. A taste game that counted those as three
books would split one book's numbers and let a player name it twice. The game
key drops articles, subtitles and file junk from the title and keeps only the
first letters of the author's surname, so spelling variants (Dostoevsky,
Dostoyevsky) and particles (Mc Carthy, McCarthy) agree.
"""

from __future__ import annotations

import hashlib
import re
import time

from ..catalog_normalization import clean_catalog_text, normalized_identity

_INDEX: dict[str, dict] = {}
_BY_TITLE: dict[str, list[str]] = {}
_INDEX_BUILT_AT = 0.0
_INDEX_TTL = 600  # seconds; the catalog changes when a submission is approved

_ARTICLES = {"the", "a", "an"}
_FILE_WORDS = {"pdf", "epub", "mobi", "ebook"}
_PARTICLES = {"mc", "mac", "o", "de", "di", "du", "da", "van", "von", "le", "la", "del", "der", "st"}
_UNKNOWN_AUTHORS = {"", "unknown", "anonymous", "various", "n a"}


def title_key(title: str) -> str:
    title = re.split(r"[:;(\[]", str(title or ""), maxsplit=1)[0]
    words = normalized_identity(title).split()
    if any(word in _FILE_WORDS for word in words):
        words = [word for word in words if word not in _FILE_WORDS]
        if words and words[-1] == "book":
            words = words[:-1]
    if len(words) > 1 and words[0] in _ARTICLES:
        words = words[1:]
    return " ".join(words)


def author_key(author: str) -> str:
    name = normalized_identity(author)
    if name in _UNKNOWN_AUTHORS:
        return ""
    words = name.split()
    surname = words[-1]
    if len(words) > 1 and words[-2] in _PARTICLES:
        surname = words[-2] + surname
    return surname[:4]


def work_key(title: str, author: str = "") -> str:
    identity = f"{title_key(title)}\n{author_key(author)}"
    return "work_" + hashlib.sha256(identity.encode()).hexdigest()[:16]


def tidy(title: str, author: str) -> tuple[str, str]:
    """Undo a common filename-to-catalog slip: "Prince by Nicolo Machiavelli" with author "The"."""
    match = re.match(r"^(.+?)\s+by\s+(.+)$", title, flags=re.IGNORECASE)
    if not match:
        return title, author
    head, named = match.group(1).strip(), match.group(2).strip()
    article = normalized_identity(author) in _ARTICLES
    if article:
        return f"{author.strip().capitalize()} {head}", named
    if not author_key(author):
        return head, named
    if author_key(named) == author_key(author):
        return head, author
    return title, author


def _library_index() -> dict[str, dict]:
    global _INDEX, _BY_TITLE, _INDEX_BUILT_AT
    if not _INDEX or time.monotonic() - _INDEX_BUILT_AT > _INDEX_TTL:
        from ..catalog_service import CatalogService

        index: dict[str, dict] = {}
        for work in CatalogService().get_works():
            representative = work.get("representative") or {}
            title, author = tidy(work["title"], work["author"])
            entry = {
                "book_id": representative.get("id"),
                "title": title,
                "author": author,
                "readable": representative.get("availability") != "external_link",
                "title_key": title_key(title),
            }
            key = work_key(title, author)
            current = index.get(key)
            # Several catalog works can be one book: keep a readable copy with the cleanest title.
            if current is None or (not current["readable"], len(current["title"])) > (
                    not entry["readable"], len(entry["title"])):
                index[key] = entry
        by_title: dict[str, list[str]] = {}
        for key, entry in index.items():
            by_title.setdefault(entry["title_key"], []).append(key)
        _INDEX, _BY_TITLE = index, by_title
        _INDEX_BUILT_AT = time.monotonic()
    return _INDEX


def reset_index() -> None:
    global _INDEX, _BY_TITLE, _INDEX_BUILT_AT
    _INDEX, _BY_TITLE, _INDEX_BUILT_AT = {}, {}, 0.0


def library_book(key: str) -> dict | None:
    return _library_index().get(key)


def resolve(title: str, author: str = "", *, verified: bool = False) -> dict:
    """Turn a typed or picked book into a list item.

    status is `library` when the catalog holds the work, `finder` when an
    external source (Open Library) confirmed the book exists so the Finder can
    look for it, and `unverified` when it is only what the player typed.
    """
    title = clean_catalog_text(title)[:300]
    author = clean_catalog_text(author)[:200]
    if not title:
        raise ValueError("Every slot needs a title.")
    key = work_key(title, author)
    found = library_book(key)
    if not found and not author_key(author):
        # "The Republic" with no author: take the library's copy when only one book has that title.
        matches = _BY_TITLE.get(title_key(title), [])
        if len(matches) == 1:
            key, found = matches[0], _INDEX[matches[0]]
    if found:
        return {"work_key": key, "title": found["title"], "author": found["author"],
                "book_id": found["book_id"], "status": "library"}
    return {"work_key": key, "title": title, "author": author, "book_id": None,
            "status": "finder" if verified else "unverified"}
