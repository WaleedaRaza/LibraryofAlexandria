"""
Alexandria Library - Taxonomy Gate V2 (Artifact-based)
Maps domain_id/subdomain_id to candidate book_ids using artifact files.

This replaces the hardcoded taxonomy.py with a scalable artifact-based approach.

INVARIANT: All book_ids must exist in book_index artifact.
MAINTENANCE: Regenerate artifacts when books change (admin/build_artifacts.py)
"""

import json
from pathlib import Path
from typing import List, Set, Optional, Dict, Any
from dataclasses import dataclass


# Paths
BASE_DIR = Path(__file__).parent.parent.parent
ARTIFACTS_DIR = BASE_DIR / "artifacts"


@dataclass
class TaxonomyArtifacts:
    """Loaded taxonomy artifacts."""
    taxonomy: Dict[str, Any]
    book_index: Dict[str, Any]
    chapter_index: Dict[str, Any]
    
    # Lookup caches
    books_by_id: Dict[str, Dict]
    chapters_by_book: Dict[str, List[Dict]]
    books_by_domain: Dict[str, Set[str]]
    books_by_subdomain: Dict[str, Set[str]]


class TaxonomyGateV2:
    """
    Artifact-based taxonomy gate.
    
    Loads taxonomy, book_index, and chapter_index from JSON artifacts.
    Provides deterministic routing from domain_id → candidate books/chapters.
    """
    
    def __init__(self, version: Optional[int] = None):
        """
        Initialize taxonomy gate.
        
        Args:
            version: Artifact version to load (None = latest)
        """
        self.version = version or self._find_latest_version()
        self.artifacts = self._load_artifacts()
    
    def _find_latest_version(self) -> int:
        """Find the latest artifact version."""
        versions = []
        for path in ARTIFACTS_DIR.glob("book_index.v*.json"):
            try:
                version_str = path.stem.split(".v")[1]
                versions.append(int(version_str))
            except (IndexError, ValueError):
                continue
        
        if not versions:
            raise FileNotFoundError(f"No book_index artifacts found in {ARTIFACTS_DIR}")
        
        return max(versions)
    
    def _load_artifacts(self) -> TaxonomyArtifacts:
        """Load all artifacts and build lookup indexes."""
        # Load taxonomy
        taxonomy_path = ARTIFACTS_DIR / "taxonomy.v1.json"
        if not taxonomy_path.exists():
            raise FileNotFoundError(f"Taxonomy not found: {taxonomy_path}")
        
        with open(taxonomy_path) as f:
            taxonomy = json.load(f)
        
        # Load book index
        book_index_path = ARTIFACTS_DIR / f"book_index.v{self.version}.json"
        if not book_index_path.exists():
            raise FileNotFoundError(f"Book index not found: {book_index_path}")
        
        with open(book_index_path) as f:
            book_index = json.load(f)
        
        # Load chapter index
        chapter_index_path = ARTIFACTS_DIR / f"chapter_index.v{self.version}.json"
        if not chapter_index_path.exists():
            raise FileNotFoundError(f"Chapter index not found: {chapter_index_path}")
        
        with open(chapter_index_path) as f:
            chapter_index = json.load(f)
        
        # Build lookup indexes
        books_by_id = {
            book["book_id"]: book 
            for book in book_index["books"]
        }
        
        chapters_by_book = {}
        for chapter in chapter_index["chapters"]:
            book_id = chapter["book_id"]
            if book_id not in chapters_by_book:
                chapters_by_book[book_id] = []
            chapters_by_book[book_id].append(chapter)
        
        # Build domain → books index
        books_by_domain = {}
        for book in book_index["books"]:
            for domain_id in book["domain_ids"]:
                if domain_id not in books_by_domain:
                    books_by_domain[domain_id] = set()
                books_by_domain[domain_id].add(book["book_id"])
        
        # Build subdomain → books index
        books_by_subdomain = {}
        for book in book_index["books"]:
            for subdomain_id in book["subdomain_ids"]:
                if subdomain_id not in books_by_subdomain:
                    books_by_subdomain[subdomain_id] = set()
                books_by_subdomain[subdomain_id].add(book["book_id"])
        
        return TaxonomyArtifacts(
            taxonomy=taxonomy,
            book_index=book_index,
            chapter_index=chapter_index,
            books_by_id=books_by_id,
            chapters_by_book=chapters_by_book,
            books_by_domain=books_by_domain,
            books_by_subdomain=books_by_subdomain
        )
    
    def get_candidate_books(
        self,
        domain_id: str,
        subdomain_id: Optional[str] = None,
        max_books: int = 12
    ) -> List[str]:
        """
        Get candidate book IDs for a domain/subdomain.
        
        Lookup strategy:
        1. If subdomain_id provided, get books for that subdomain
        2. Also get books for the domain
        3. Return union, capped at max_books
        
        Args:
            domain_id: Primary domain ID (lowercase)
            subdomain_id: Optional subdomain ID (lowercase)
            max_books: Cap on number of books returned
            
        Returns:
            List of book_ids (max 12)
        """
        candidates: Set[str] = set()
        
        # Add books from subdomain
        if subdomain_id and subdomain_id in self.artifacts.books_by_subdomain:
            candidates.update(self.artifacts.books_by_subdomain[subdomain_id])
        
        # Add books from domain
        if domain_id in self.artifacts.books_by_domain:
            candidates.update(self.artifacts.books_by_domain[domain_id])
        
        # Cap at max_books
        return list(candidates)[:max_books]
    
    def get_candidate_chapters(
        self,
        book_ids: List[str],
        max_chapters_per_book: int = 8
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get candidate chapters for a list of book IDs.
        
        Returns dict mapping book_id → list of chapter dicts.
        Each chapter dict contains: chapter_id, number, title, word_count.
        
        Args:
            book_ids: List of book IDs
            max_chapters_per_book: Max chapters to return per book
            
        Returns:
            Dict of book_id → chapters
        """
        result = {}
        for book_id in book_ids:
            chapters = self.artifacts.chapters_by_book.get(book_id, [])
            # Return up to max_chapters_per_book
            result[book_id] = chapters[:max_chapters_per_book]
        return result
    
    def get_book_metadata(self, book_id: str) -> Optional[Dict[str, Any]]:
        """Get book metadata from book_index."""
        return self.artifacts.books_by_id.get(book_id)
    
    def validate_book_id(self, book_id: str) -> bool:
        """Check if a book_id exists in the book_index."""
        return book_id in self.artifacts.books_by_id
    
    def validate_chapter_id(self, chapter_id: str, book_id: str) -> bool:
        """Check if a chapter_id exists for a given book."""
        chapters = self.artifacts.chapters_by_book.get(book_id, [])
        return any(ch["chapter_id"] == chapter_id for ch in chapters)
    
    def get_taxonomy_version(self) -> int:
        """Get taxonomy version (for cache invalidation)."""
        return self.artifacts.taxonomy["version"]
    
    def get_artifact_version(self) -> int:
        """Get artifact version (book/chapter index)."""
        return self.version
    
    def get_domain_info(self, domain_id: str) -> Optional[Dict[str, Any]]:
        """Get domain information from taxonomy."""
        domains = self.artifacts.taxonomy.get("domains", {})
        return domains.get(domain_id)
    
    def get_subdomain_info(
        self,
        domain_id: str,
        subdomain_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get subdomain information from taxonomy."""
        domain = self.get_domain_info(domain_id)
        if not domain:
            return None
        subdomains = domain.get("subdomains", {})
        return subdomains.get(subdomain_id)
    
    def get_all_domain_ids(self) -> List[str]:
        """Get list of all domain IDs."""
        return list(self.artifacts.taxonomy.get("domains", {}).keys())
    
    def get_all_subdomain_ids(self, domain_id: str) -> List[str]:
        """Get list of all subdomain IDs for a domain."""
        domain = self.get_domain_info(domain_id)
        if not domain:
            return []
        return list(domain.get("subdomains", {}).keys())
    
    def get_stats(self) -> Dict[str, Any]:
        """Get taxonomy statistics."""
        return {
            "artifact_version": self.version,
            "taxonomy_version": self.get_taxonomy_version(),
            "total_domains": len(self.artifacts.taxonomy.get("domains", {})),
            "total_books": len(self.artifacts.books_by_id),
            "total_chapters": len(self.artifacts.chapter_index["chapters"]),
            "books_by_domain": {
                domain_id: len(book_ids)
                for domain_id, book_ids in self.artifacts.books_by_domain.items()
            }
        }


# =============================================================================
# SINGLETON & COMPATIBILITY LAYER
# =============================================================================

_gate: Optional[TaxonomyGateV2] = None


def get_taxonomy_gate() -> TaxonomyGateV2:
    """Get or create the global taxonomy gate instance."""
    global _gate
    if _gate is None:
        _gate = TaxonomyGateV2()
    return _gate


def reset_taxonomy_gate():
    """Reset gate (useful for testing or reloading artifacts)."""
    global _gate
    _gate = None


# Compatibility functions for existing code
def get_candidate_books(
    domain_id: str,
    subdomain_id: Optional[str] = None,
    max_books: int = 12
) -> List[str]:
    """Compatibility wrapper for existing code."""
    gate = get_taxonomy_gate()
    return gate.get_candidate_books(domain_id, subdomain_id, max_books)


def validate_book_id(book_id: str) -> bool:
    """Compatibility wrapper for existing code."""
    gate = get_taxonomy_gate()
    return gate.validate_book_id(book_id)


def get_taxonomy_version() -> int:
    """Compatibility wrapper for existing code."""
    gate = get_taxonomy_gate()
    return gate.get_taxonomy_version()
