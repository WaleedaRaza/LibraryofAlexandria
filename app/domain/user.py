"""
Alexandria Library - User Entity
Data shape for users. No DB calls.

Users are minimal in V1:
- No profiles
- No public identity
- Just auth and data ownership
"""

from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class User:
    """
    A user of the system.
    
    Minimal for V1. No social features.
    """
    id: str
    email: str
    display_name: Optional[str] = None
    role: str = "user"  # "user" or "admin"
    created_at: Optional[datetime] = None
    
    @classmethod
    def from_dict(cls, data: dict) -> "User":
        """Create User from dictionary."""
        return cls(
            id=data["id"],
            email=data["email"],
            display_name=data.get("display_name"),
            role=data.get("role", "user"),
            created_at=data.get("created_at")
        )
    
    def to_dict(self) -> dict:
        """Convert to dictionary (excludes password)."""
        return {
            "id": self.id,
            "email": self.email,
            "display_name": self.display_name,
            "role": self.role,
            "created_at": self.created_at
        }
    
    @property
    def is_admin(self) -> bool:
        """Check if user is admin."""
        return self.role == "admin"
    
    @property
    def name(self) -> str:
        """Display name or email prefix."""
        if self.display_name:
            return self.display_name
        return self.email.split("@")[0]


VALID_ROLES = ["user", "admin"]


def validate_role(role: str) -> bool:
    """Check if role is valid."""
    return role in VALID_ROLES

