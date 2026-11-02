"""One key per book, shared with the catalog, so typed titles and library books match."""

from __future__ import annotations

import time

from ..catalog_normalization import canonicalize_book, clean_catalog_text

_INDEX: dict[str, dict] = {}
_INDEX_BUILT_AT = 0.0
_INDEX_TTL = 600  # seconds; the catalog changes when a submission is approved


def work_key(title: str, author: str = "") -> str:
    """The same hash the catalog uses for `work_id`."""
    return canonicalize_book({"title": title, "author": author})["work_id"]


def _library_index() -> dict[str, dict]:
    global _INDEX, _INDEX_BUILT_AT
    if not _INDEX or time.monotonic() - _INDEX_BUILT_AT > _INDEX_TTL:
        from ..catalog_service import CatalogService

        works = CatalogService().get_works()
        _INDEX = {
            work["id"]: {
                "book_id": (work.get("representative") or {}).get("id"),
                "title": work["title"],
                "author": work["author"],
                "readable": (work.get("representative") or {}).get("availability") != "external_link",
            }
            for work in works
        }
        _INDEX_BUILT_AT = time.monotonic()
    return _INDEX


def reset_index() -> None:
    global _INDEX, _INDEX_BUILT_AT
    _INDEX, _INDEX_BUILT_AT = {}, 0.0


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
    if found:
        return {"work_key": key, "title": found["title"], "author": found["author"],
                "book_id": found["book_id"], "status": "library"}
    return {"work_key": key, "title": title, "author": author, "book_id": None,
            "status": "finder" if verified else "unverified"}
