"""
Alexandria Library - User Service
Highlights, annotations. SQLite-only. New schema (book_id + section_id).
"""

from typing import Optional, List
import uuid
from ..db.database import get_db


class UserService:
    """User-specific mutable data: highlights and annotations."""

    # -------------------------------------------------------------------------
    # Highlights (new schema: book_id + section_id, no FK to chapters)
    # -------------------------------------------------------------------------

    def get_highlights(self, user_id: str, section_id: str) -> List[dict]:
        """Get all highlights for a user in a specific section."""
        db = get_db()
        rows = db.execute(
            """
            SELECT id, user_id, book_id, section_id, selected_text, color, created_at
            FROM highlights
            WHERE user_id = ? AND section_id = ?
            ORDER BY created_at DESC
            """,
            (user_id, section_id)
        ).fetchall()
        return [dict(row) for row in rows]

    def get_all_highlights(self, user_id: str, book_id: str) -> List[dict]:
        """Get all highlights for a user in a book."""
        db = get_db()
        rows = db.execute(
            """
            SELECT id, book_id, section_id, selected_text, color, created_at
            FROM highlights
            WHERE user_id = ? AND book_id = ?
            ORDER BY created_at DESC
            """,
            (user_id, book_id)
        ).fetchall()
        return [dict(row) for row in rows]

    def create_highlight(
        self,
        user_id: str,
        book_id: str,
        section_id: str,
        selected_text: str,
        color: str = "yellow"
    ) -> dict:
        """Create a new highlight."""
        highlight_id = f"hl_{uuid.uuid4().hex[:12]}"
        db = get_db()
        db.execute(
            """
            INSERT INTO highlights (id, user_id, book_id, section_id, selected_text, color)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (highlight_id, user_id, book_id, section_id, selected_text, color)
        )
        db.commit()
        return {
            "id": highlight_id,
            "user_id": user_id,
            "book_id": book_id,
            "section_id": section_id,
            "selected_text": selected_text,
            "color": color,
        }

    def delete_highlight(self, highlight_id: str, user_id: str) -> bool:
        db = get_db()
        cursor = db.execute(
            "DELETE FROM highlights WHERE id = ? AND user_id = ?",
            (highlight_id, user_id)
        )
        db.commit()
        return cursor.rowcount > 0

    # -------------------------------------------------------------------------
    # Annotations
    # -------------------------------------------------------------------------

    def get_annotation(self, highlight_id: str) -> Optional[dict]:
        db = get_db()
        row = db.execute(
            """
            SELECT id, highlight_id, text, created_at, updated_at
            FROM annotations
            WHERE highlight_id = ?
            """,
            (highlight_id,)
        ).fetchone()
        return dict(row) if row else None

    def create_annotation(self, highlight_id: str, text: str) -> dict:
        annotation_id = f"ann_{uuid.uuid4().hex[:12]}"
        db = get_db()
        db.execute(
            """
            INSERT INTO annotations (id, highlight_id, text)
            VALUES (?, ?, ?)
            ON CONFLICT(highlight_id) DO UPDATE SET
                text = excluded.text,
                updated_at = CURRENT_TIMESTAMP
            """,
            (annotation_id, highlight_id, text)
        )
        db.commit()
        return {"id": annotation_id, "highlight_id": highlight_id, "text": text}

    def delete_annotation(self, annotation_id: str) -> bool:
        db = get_db()
        cursor = db.execute(
            "DELETE FROM annotations WHERE id = ?",
            (annotation_id,)
        )
        db.commit()
        return cursor.rowcount > 0
