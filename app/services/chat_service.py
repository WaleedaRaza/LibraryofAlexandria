"""
Alexandria Library - Chat Service
Conversation threads tied to highlights. SQLite-only.
"""

from typing import List
import uuid
from ..db.database import get_db


# =============================================================================
# COLOR SYSTEM
# =============================================================================

HIGHLIGHT_COLORS = {
    "yellow": {"label": "Important", "hex": "#fef08a"},
    "green": {"label": "Agree", "hex": "#86efac"},
    "blue": {"label": "Question", "hex": "#93c5fd"},
    "purple": {"label": "Insight", "hex": "#d8b4fe"},
    "red": {"label": "Disagree", "hex": "#fca5a5"},
}

def get_color_info(color: str) -> dict:
    return HIGHLIGHT_COLORS.get(color, HIGHLIGHT_COLORS["yellow"])


class ChatService:
    """Chat messages tied to highlights. 1 highlight = 1 thread."""

    def get_messages(self, highlight_id: str) -> List[dict]:
        db = get_db()
        rows = db.execute(
            """
            SELECT id, highlight_id, role, content, created_at
            FROM chat_messages
            WHERE highlight_id = ?
            ORDER BY created_at ASC
            """,
            (highlight_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    def get_message_count(self, highlight_id: str) -> int:
        db = get_db()
        row = db.execute(
            "SELECT COUNT(*) as count FROM chat_messages WHERE highlight_id = ?",
            (highlight_id,)
        ).fetchone()
        return row["count"] if row else 0

    def add_message(self, highlight_id: str, role: str, content: str) -> dict:
        if role not in ("user", "assistant"):
            raise ValueError(f"Invalid role: {role}")

        message_id = f"msg_{uuid.uuid4().hex[:12]}"
        db = get_db()
        db.execute(
            """
            INSERT INTO chat_messages (id, highlight_id, role, content)
            VALUES (?, ?, ?, ?)
            """,
            (message_id, highlight_id, role, content)
        )
        db.commit()
        return {
            "id": message_id,
            "highlight_id": highlight_id,
            "role": role,
            "content": content,
        }

    def delete_messages(self, highlight_id: str) -> bool:
        db = get_db()
        cursor = db.execute(
            "DELETE FROM chat_messages WHERE highlight_id = ?",
            (highlight_id,)
        )
        db.commit()
        return cursor.rowcount > 0
