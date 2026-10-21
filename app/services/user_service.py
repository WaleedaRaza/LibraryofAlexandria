"""Private reader state: shelf, progress, highlights, notes, and memory."""

from __future__ import annotations

import uuid
from typing import Optional

from ..db.database import get_db, get_supabase, is_sqlite_mode
from .catalog_service import CatalogService


class UserService:
    def save_book(self, user_id: str, book_id: str) -> None:
        record = {"id": f"saved_{uuid.uuid4().hex[:12]}", "user_id": user_id, "book_id": book_id}
        if is_sqlite_mode():
            db = get_db()
            db.execute(
                "INSERT OR IGNORE INTO saved_books (id, user_id, book_id) VALUES (?, ?, ?)",
                tuple(record.values()),
            )
            db.commit()
        else:
            get_supabase().table("saved_books").upsert(
                record, on_conflict="user_id,book_id", ignore_duplicates=True
            ).execute()

    def unsave_book(self, user_id: str, book_id: str) -> None:
        if is_sqlite_mode():
            db = get_db()
            db.execute("DELETE FROM saved_books WHERE user_id = ? AND book_id = ?", (user_id, book_id))
            db.commit()
        else:
            get_supabase().table("saved_books").delete().eq("user_id", user_id).eq("book_id", book_id).execute()

    def is_book_saved(self, user_id: str, book_id: str) -> bool:
        if is_sqlite_mode():
            return get_db().execute(
                "SELECT 1 FROM saved_books WHERE user_id = ? AND book_id = ?", (user_id, book_id)
            ).fetchone() is not None
        return bool(
            get_supabase().table("saved_books").select("id").eq("user_id", user_id).eq("book_id", book_id).limit(1).execute().data
        )

    def get_saved_book_ids(self, user_id: str) -> list[str]:
        if is_sqlite_mode():
            rows = get_db().execute(
                "SELECT book_id FROM saved_books WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
            ).fetchall()
            return [row["book_id"] for row in rows]
        rows = get_supabase().table("saved_books").select("book_id").eq("user_id", user_id).order("created_at", desc=True).execute().data
        return [row["book_id"] for row in rows or []]

    def get_shelf_statuses(self, user_id: str) -> dict[str, str]:
        if is_sqlite_mode():
            rows = get_db().execute(
                "SELECT book_id, status FROM saved_books WHERE user_id = ?", (user_id,)
            ).fetchall()
        else:
            rows = get_supabase().table("saved_books").select("book_id,status").eq(
                "user_id", user_id
            ).execute().data or []
        return {row["book_id"]: row["status"] for row in rows}

    def get_reading_status(self, user_id: str, book_id: str) -> str | None:
        return self.get_shelf_statuses(user_id).get(book_id)

    def get_saved_books(self, user_id: str) -> list[dict]:
        from .source_service import private_source
        catalog = CatalogService()
        progress = {row["book_id"]: row for row in self.get_progress_for_user(user_id)}
        statuses = self.get_shelf_statuses(user_id)
        books = []
        for book_id in self.get_saved_book_ids(user_id):
            book = catalog.get_book(book_id) or private_source(book_id, {"id": user_id, "role": "user"})
            if book:
                books.append({
                    **book,
                    **progress.get(book_id, {"percent": 0, "page_number": 1}),
                    "reading_status": statuses.get(book_id, "want_to_read"),
                })
        return books

    def update_progress(self, user_id: str, book_id: str, page_number: int, page_count: int) -> dict:
        percent = round(min(100, max(0, page_number / max(page_count, 1) * 100)), 1)
        record = {
            "user_id": user_id,
            "book_id": book_id,
            "page_number": page_number,
            "page_count": page_count,
            "percent": percent,
        }
        if is_sqlite_mode():
            db = get_db()
            db.execute(
                """INSERT INTO reading_progress (user_id, book_id, page_number, page_count, percent)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(user_id, book_id) DO UPDATE SET
                     page_number=excluded.page_number, page_count=excluded.page_count,
                     percent=excluded.percent, updated_at=CURRENT_TIMESTAMP""",
                (user_id, book_id, page_number, page_count, percent),
            )
            db.commit()
        else:
            get_supabase().table("reading_progress").upsert(record, on_conflict="user_id,book_id").execute()
        self.save_book(user_id, book_id)
        if page_number > 1 and self.get_reading_status(user_id, book_id) == "want_to_read":
            self.set_reading_status(user_id, book_id, "reading")
        return record

    def get_progress(self, user_id: str, book_id: str) -> Optional[dict]:
        if is_sqlite_mode():
            row = get_db().execute(
                "SELECT * FROM reading_progress WHERE user_id = ? AND book_id = ?", (user_id, book_id)
            ).fetchone()
            return dict(row) if row else None
        rows = get_supabase().table("reading_progress").select("*").eq("user_id", user_id).eq("book_id", book_id).limit(1).execute().data
        return rows[0] if rows else None

    def set_reading_status(self, user_id: str, book_id: str, status: str) -> None:
        if status not in {"want_to_read", "reading", "read"}:
            raise ValueError("Unknown reading status")
        self.save_book(user_id, book_id)
        if is_sqlite_mode():
            db = get_db()
            db.execute(
                "UPDATE saved_books SET status = ? WHERE user_id = ? AND book_id = ?",
                (status, user_id, book_id),
            )
            db.commit()
        else:
            get_supabase().table("saved_books").update({"status": status}).eq(
                "user_id", user_id
            ).eq("book_id", book_id).execute()

    def clear_progress(self, user_id: str, book_id: str) -> None:
        if is_sqlite_mode():
            db = get_db()
            db.execute(
                "DELETE FROM reading_progress WHERE user_id = ? AND book_id = ?",
                (user_id, book_id),
            )
            db.commit()
            return
        get_supabase().table("reading_progress").delete().eq("user_id", user_id).eq("book_id", book_id).execute()

    def get_progress_for_user(self, user_id: str) -> list[dict]:
        if is_sqlite_mode():
            return [dict(row) for row in get_db().execute(
                "SELECT * FROM reading_progress WHERE user_id = ? ORDER BY updated_at DESC", (user_id,)
            ).fetchall()]
        return get_supabase().table("reading_progress").select("*").eq("user_id", user_id).order("updated_at", desc=True).execute().data or []

    def create_highlight(
        self,
        user_id: str,
        book_id: str,
        page_number: int,
        selected_text: str,
        color: str = "gold",
        text_start: Optional[int] = None,
        text_end: Optional[int] = None,
    ) -> dict:
        record = {
            "id": f"hl_{uuid.uuid4().hex[:12]}",
            "user_id": user_id,
            "book_id": book_id,
            "page_number": page_number,
            "selected_text": selected_text,
            "text_start": text_start,
            "text_end": text_end,
            "color": color,
        }
        if is_sqlite_mode():
            db = get_db()
            db.execute(
                """INSERT INTO highlights
                   (id, user_id, book_id, page_number, selected_text, text_start, text_end, color)
                   VALUES (:id, :user_id, :book_id, :page_number, :selected_text, :text_start, :text_end, :color)""",
                record,
            )
            db.commit()
        else:
            get_supabase().table("highlights").insert(record).execute()
        self.save_book(user_id, book_id)
        return record

    def get_highlights(self, user_id: str, book_id: Optional[str] = None) -> list[dict]:
        if is_sqlite_mode():
            sql = """SELECT h.*, a.id annotation_id, a.text note
                     FROM highlights h LEFT JOIN annotations a ON a.highlight_id = h.id
                     WHERE h.user_id = ?"""
            params: list = [user_id]
            if book_id:
                sql += " AND h.book_id = ?"
                params.append(book_id)
            sql += " ORDER BY h.created_at DESC"
            return [dict(row) for row in get_db().execute(sql, params).fetchall()]
        query = get_supabase().table("highlights").select("*,annotations(id,text)").eq("user_id", user_id)
        if book_id:
            query = query.eq("book_id", book_id)
        rows = query.order("created_at", desc=True).execute().data or []
        for row in rows:
            # PostgREST returns a to-one relationship as an object on newer
            # releases and as a one-item list on older ones. Accept both so a
            # saved note can never take down the reader.
            related = row.pop("annotations", None)
            if isinstance(related, list):
                annotation = related[0] if related else None
            elif isinstance(related, dict):
                annotation = related
            else:
                annotation = None
            row["annotation_id"] = annotation.get("id") if annotation else None
            row["note"] = annotation.get("text") if annotation else None
        return rows

    def get_highlight(self, user_id: str, highlight_id: str) -> Optional[dict]:
        return next((h for h in self.get_highlights(user_id) if h["id"] == highlight_id), None)

    def delete_highlight(self, highlight_id: str, user_id: str) -> bool:
        if is_sqlite_mode():
            db = get_db()
            cursor = db.execute("DELETE FROM highlights WHERE id = ? AND user_id = ?", (highlight_id, user_id))
            db.commit()
            return cursor.rowcount > 0
        result = get_supabase().table("highlights").delete().eq("id", highlight_id).eq("user_id", user_id).execute()
        return bool(result.data)

    def save_note(self, user_id: str, highlight_id: str, text: str) -> dict:
        highlight = self.get_highlight(user_id, highlight_id)
        if not highlight:
            raise PermissionError("Highlight does not belong to this reader")
        record = {"id": highlight.get("annotation_id") or f"ann_{uuid.uuid4().hex[:12]}", "highlight_id": highlight_id, "text": text.strip()}
        if is_sqlite_mode():
            db = get_db()
            db.execute(
                """INSERT INTO annotations (id, highlight_id, text) VALUES (:id, :highlight_id, :text)
                   ON CONFLICT(highlight_id) DO UPDATE SET text=excluded.text, updated_at=CURRENT_TIMESTAMP""",
                record,
            )
            db.commit()
        else:
            get_supabase().table("annotations").upsert(record, on_conflict="highlight_id").execute()
        return record

    def get_stats(self, user_id: str) -> dict:
        highlights = self.get_highlights(user_id)
        return {
            "books": len(self.get_saved_book_ids(user_id)),
            "highlights": len(highlights),
            "notes": sum(bool(h.get("note")) for h in highlights),
        }
