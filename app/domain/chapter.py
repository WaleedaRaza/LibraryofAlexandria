"""
Alexandria Library - Chapter Entity
Data shape for chapters. No DB calls.

Chapters reference offsets into book_text.content.
They do NOT store text themselves - that would duplicate canon.
"""

from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class Chapter:
    """
    A chapter in a book.
    
    Chapters point to sections of text via offsets.
    The actual text lives in book_text.content.
    """
    id: str
    book_id: str
    number: int
    title: str
    start_offset: int
    end_offset: int
    created_at: Optional[datetime] = None
    
    @classmethod
    def from_dict(cls, data: dict) -> "Chapter":
        """Create Chapter from dictionary."""
        return cls(
            id=data["id"],
            book_id=data["book_id"],
            number=data["number"],
            title=data["title"],
            start_offset=data["start_offset"],
            end_offset=data["end_offset"],
            created_at=data.get("created_at")
        )
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "book_id": self.book_id,
            "number": self.number,
            "title": self.title,
            "start_offset": self.start_offset,
            "end_offset": self.end_offset,
            "created_at": self.created_at
        }
    
    @property
    def length(self) -> int:
        """Character length of this chapter."""
        return self.end_offset - self.start_offset

