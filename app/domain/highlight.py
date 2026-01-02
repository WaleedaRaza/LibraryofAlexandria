"""
Alexandria Library - Highlight Entity
Data shape for highlights. No DB calls.

Highlights are user-owned, mutable data.
They reference offsets within a chapter.
"""

from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class Highlight:
    """
    A text highlight created by a user.
    
    Highlights are personal. They don't affect canon.
    """
    id: str
    user_id: str
    chapter_id: str
    start_offset: int  # Offset within the chapter
    end_offset: int
    color: str = "yellow"
    created_at: Optional[datetime] = None
    
    @classmethod
    def from_dict(cls, data: dict) -> "Highlight":
        """Create Highlight from dictionary."""
        return cls(
            id=data["id"],
            user_id=data["user_id"],
            chapter_id=data["chapter_id"],
            start_offset=data["start_offset"],
            end_offset=data["end_offset"],
            color=data.get("color", "yellow"),
            created_at=data.get("created_at")
        )
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "chapter_id": self.chapter_id,
            "start_offset": self.start_offset,
            "end_offset": self.end_offset,
            "color": self.color,
            "created_at": self.created_at
        }
    
    @property
    def length(self) -> int:
        """Character length of this highlight."""
        return self.end_offset - self.start_offset


VALID_COLORS = ["yellow", "green", "blue", "pink", "orange"]


def validate_color(color: str) -> bool:
    """Check if highlight color is valid."""
    return color in VALID_COLORS

