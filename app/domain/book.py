"""
Alexandria Library - Book Entity
Data shape for books. No DB calls.
"""

from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class Book:
    """
    A book in the canon.
    
    Books are immutable once ingested.
    Users cannot modify books.
    """
    id: str
    title: str
    author: str
    domain: Optional[str] = None
    subdomain: Optional[str] = None
    is_public: bool = True
    created_at: Optional[datetime] = None
    
    @classmethod
    def from_dict(cls, data: dict) -> "Book":
        """Create Book from dictionary (e.g., from DB row)."""
        return cls(
            id=data["id"],
            title=data["title"],
            author=data["author"],
            domain=data.get("domain"),
            subdomain=data.get("subdomain"),
            is_public=data.get("is_public", True),
            created_at=data.get("created_at")
        )
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "author": self.author,
            "domain": self.domain,
            "subdomain": self.subdomain,
            "is_public": self.is_public,
            "created_at": self.created_at
        }

