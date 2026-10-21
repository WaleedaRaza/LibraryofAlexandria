"""Read-only catalog for Waleed's Library.

The catalog is deliberately separate from taxonomy artifacts. A PDF can be
readable before its text has been extracted or enriched for LLM navigation.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from ..config import settings
from .catalog_normalization import canonicalize_book, group_editions


@lru_cache(maxsize=1)
def _catalog() -> dict[str, Any]:
    path = Path(settings.LIBRARY_CATALOG_PATH)
    if not path.exists():
        return {"version": 1, "books": []}
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    data.setdefault("books", [])
    return data


@lru_cache(maxsize=1)
def _link_catalog(*, drafts: bool = False) -> list[dict[str, Any]]:
    """Only explicitly approved links enter the public catalog.

    The unreviewed sourcing run is kept in ignored data/ and can only be
    included by a local preview route.
    """
    path = settings.BASE_DIR / ("data/link_books_staged.json" if drafts else "library/link_catalog.json")
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    books = data.get("books", [])
    if drafts:
        return [book for book in books if book.get("visibility") == "draft"]
    return [
        book for book in books
        if book.get("visibility") == "public" and book.get("rights_status") == "approved"
    ]


def _books(*, include_drafts: bool = False) -> list[dict[str, Any]]:
    from .source_service import published_editions
    books = list(_catalog()["books"])
    books.extend(_link_catalog())
    books.extend(published_editions())
    if include_drafts and not settings.is_production:
        books.extend(_link_catalog(drafts=True))
    return [canonicalize_book(book) for book in books]


class CatalogService:
    """Search and retrieve deployable book records."""

    def get_books(
        self,
        *,
        domain: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 1000,
        offset: int = 0,
        include_drafts: bool = False,
    ) -> list[dict[str, Any]]:
        books = _books(include_drafts=include_drafts)
        if domain:
            wanted = domain.casefold()
            books = [b for b in books if b.get("domain", "").casefold() == wanted]
        if search:
            terms = search.casefold().split()
            books = [
                book
                for book in books
                if all(
                    term in " ".join(
                        [
                            book.get("title", ""),
                            book.get("author", ""),
                            book.get("domain", ""),
                        ]
                    ).casefold()
                    for term in terms
                )
            ]
        return books[offset : offset + limit]

    def get_book(self, book_id: str, *, include_drafts: bool = False) -> Optional[dict[str, Any]]:
        return next((book for book in _books(include_drafts=include_drafts) if book["id"] == book_id), None)

    def get_domains(self) -> list[str]:
        return sorted({b.get("domain", "General") for b in _books()})

    def get_book_count(self) -> int:
        return len(_books())

    def get_works(self, *, include_drafts: bool = False) -> list[dict[str, Any]]:
        """Return canonical works with every source edition still attached."""
        return group_editions(_books(include_drafts=include_drafts))

    def get_featured_books(self, limit: int = 14) -> list[dict[str, Any]]:
        books = _books()
        featured = [book for book in books if book.get("featured")]
        return (featured or books)[:limit]

    def reload(self) -> None:
        _catalog.cache_clear()
        _link_catalog.cache_clear()
