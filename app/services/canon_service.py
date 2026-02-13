"""
Alexandria Library - Canon Service
Artifact-first. No Supabase. No mock books.
All book data comes from taxonomy-pipeline artifacts on disk.
"""

from typing import Optional, List
from .artifact_loader import (
    get_book,
    get_all_books,
    get_books_by_domain,
    get_sections_as_chapters,
    get_section_by_number,
    get_section_text,
    get_full_text,
    is_artifact_book,
    get_available_books,
)


class CanonService:
    """
    Read-only access to books and sections.
    Everything comes from artifact JSON files.
    """

    def get_books(
        self,
        domain: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 100
    ) -> List[dict]:
        """Get all public books, optionally filtered."""
        if domain:
            books = get_books_by_domain(domain)
        else:
            books = get_all_books()

        if search:
            q = search.lower()
            books = [
                b for b in books
                if q in b.get("title", "").lower()
                or q in b.get("author", "").lower()
            ]

        return books[:limit]

    def get_book(self, book_id: str) -> Optional[dict]:
        return get_book(book_id)

    def get_domains(self) -> List[str]:
        """Unique domains from all available artifacts."""
        domains = set()
        for b in get_all_books():
            d = b.get("domain")
            if d:
                domains.add(d)
        return sorted(domains)

    def get_book_count(self) -> int:
        return len(get_available_books())

    def get_chapters(self, book_id: str) -> List[dict]:
        """Sections formatted as chapters."""
        return get_sections_as_chapters(book_id)

    def get_chapter(self, chapter_id: str) -> Optional[dict]:
        """Find a section/chapter by id across all books."""
        for bid in get_available_books():
            for ch in get_sections_as_chapters(bid):
                if ch["id"] == chapter_id:
                    return ch
        return None

    def get_chapter_by_number(self, book_id: str, number: int) -> Optional[dict]:
        return get_section_by_number(book_id, number)

    def get_chapter_text(self, book_id: str, chapter_id: str) -> str:
        return get_section_text(book_id, chapter_id) or ""

    def get_full_text(self, book_id: str) -> str:
        return get_full_text(book_id) or ""

    def get_books_by_domain(self, domain: str) -> List[dict]:
        return get_books_by_domain(domain)

    def search_books(self, query: str) -> List[dict]:
        return self.get_books(search=query)
