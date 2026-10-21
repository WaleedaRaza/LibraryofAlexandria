"""Private conversations attached to reader highlights."""

import uuid

from ..db.database import get_db, get_supabase, is_sqlite_mode


class ChatService:
    def get_messages(self, highlight_id: str) -> list[dict]:
        if is_sqlite_mode():
            rows = get_db().execute(
                "SELECT * FROM chat_messages WHERE highlight_id = ? ORDER BY created_at", (highlight_id,)
            ).fetchall()
            return [dict(row) for row in rows]
        return get_supabase().table("chat_messages").select("*").eq(
            "highlight_id", highlight_id
        ).order("created_at").execute().data or []

    def add_message(self, highlight_id: str, role: str, content: str) -> dict:
        if role not in {"user", "assistant"}:
            raise ValueError("Unknown chat role")
        record = {
            "id": f"msg_{uuid.uuid4().hex[:12]}",
            "highlight_id": highlight_id,
            "role": role,
            "content": content.strip(),
        }
        if is_sqlite_mode():
            db = get_db()
            db.execute(
                "INSERT INTO chat_messages (id, highlight_id, role, content) VALUES (:id, :highlight_id, :role, :content)",
                record,
            )
            db.commit()
        else:
            get_supabase().table("chat_messages").insert(record).execute()
        return record
