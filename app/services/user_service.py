"""
Alexandria Library - User Service
Manages user data: saved books, highlights, annotations.
This is mutable data, unlike canon.
"""

from typing import Optional, List
import uuid
from ..db.database import get_supabase, is_sqlite_mode


class UserService:
    """
    Service for user-specific data.
    This is where highlights, saved books, and annotations live.
    """
    
    # -------------------------------------------------------------------------
    # Saved Books
    # -------------------------------------------------------------------------
    
    def get_saved_books(self, user_id: str) -> List[dict]:
        """Get all books saved by a user."""
        if is_sqlite_mode():
            from ..db.database import get_db
            db = get_db()
            rows = db.execute(
                """
                SELECT b.id, b.title, b.author, b.domain, sb.created_at as saved_at
                FROM saved_books sb
                JOIN books b ON sb.book_id = b.id
                WHERE sb.user_id = ?
                ORDER BY sb.created_at DESC
                """,
                (user_id,)
            ).fetchall()
            return [dict(row) for row in rows]
        
        # Supabase REST API - use foreign key relationship
        client = get_supabase()
        result = client.table("saved_books").select(
            "created_at, books(id, title, author, domain)"
        ).eq("user_id", user_id).order("created_at", desc=True).execute()
        
        # Flatten the nested book data
        saved = []
        for row in result.data or []:
            book = row.get("books", {}) or {}
            saved.append({
                "id": book.get("id"),
                "title": book.get("title"),
                "author": book.get("author"),
                "domain": book.get("domain"),
                "saved_at": row.get("created_at")
            })
        
        return saved
    
    def is_book_saved(self, user_id: str, book_id: str) -> bool:
        """Check if a user has saved a book."""
        if is_sqlite_mode():
            from ..db.database import get_db
            db = get_db()
            row = db.execute(
                "SELECT 1 FROM saved_books WHERE user_id = ? AND book_id = ?",
                (user_id, book_id)
            ).fetchone()
            return row is not None
        
        # Supabase REST API
        client = get_supabase()
        result = client.table("saved_books").select("id").eq(
            "user_id", user_id
        ).eq("book_id", book_id).execute()
        
        return len(result.data or []) > 0
    
    def save_book(self, user_id: str, book_id: str) -> dict:
        """Save a book to user's library."""
        save_id = f"save_{uuid.uuid4().hex[:12]}"
        
        if is_sqlite_mode():
            from ..db.database import get_db
            db = get_db()
            db.execute(
                """
                INSERT OR IGNORE INTO saved_books (id, user_id, book_id)
                VALUES (?, ?, ?)
                """,
                (save_id, user_id, book_id)
            )
            db.commit()
        else:
            # Supabase REST API - use upsert to handle duplicates
            client = get_supabase()
            try:
                client.table("saved_books").insert({
                    "id": save_id,
                    "user_id": user_id,
                    "book_id": book_id
                }).execute()
            except Exception:
                # Already exists - that's fine
                pass
        
        return {"id": save_id, "user_id": user_id, "book_id": book_id}
    
    def unsave_book(self, user_id: str, book_id: str) -> bool:
        """Remove a book from user's library."""
        if is_sqlite_mode():
            from ..db.database import get_db
            db = get_db()
            cursor = db.execute(
                "DELETE FROM saved_books WHERE user_id = ? AND book_id = ?",
                (user_id, book_id)
            )
            db.commit()
            return cursor.rowcount > 0
        
        # Supabase REST API
        client = get_supabase()
        result = client.table("saved_books").delete().eq(
            "user_id", user_id
        ).eq("book_id", book_id).execute()
        
        return len(result.data or []) > 0
    
    # -------------------------------------------------------------------------
    # Highlights
    # -------------------------------------------------------------------------
    
    def get_highlights(self, user_id: str, chapter_id: str) -> List[dict]:
        """Get all highlights for a user in a specific chapter."""
        if is_sqlite_mode():
            from ..db.database import get_db
            db = get_db()
            rows = db.execute(
                """
                SELECT id, user_id, chapter_id, start_offset, end_offset, color, created_at
                FROM highlights
                WHERE user_id = ? AND chapter_id = ?
                ORDER BY start_offset
                """,
                (user_id, chapter_id)
            ).fetchall()
            return [dict(row) for row in rows]
        
        # Supabase REST API
        client = get_supabase()
        result = client.table("highlights").select(
            "id, user_id, chapter_id, start_offset, end_offset, color, created_at"
        ).eq("user_id", user_id).eq("chapter_id", chapter_id).order("start_offset").execute()
        
        return result.data or []
    
    def get_all_highlights(self, user_id: str, book_id: str) -> List[dict]:
        """Get all highlights for a user across all chapters of a book."""
        if is_sqlite_mode():
            from ..db.database import get_db
            db = get_db()
            rows = db.execute(
                """
                SELECT h.id, h.chapter_id, h.start_offset, h.end_offset, h.color,
                       c.number as chapter_number, c.title as chapter_title
                FROM highlights h
                JOIN chapters c ON h.chapter_id = c.id
                WHERE h.user_id = ? AND c.book_id = ?
                ORDER BY c.number, h.start_offset
                """,
                (user_id, book_id)
            ).fetchall()
            return [dict(row) for row in rows]
        
        # Supabase REST API - need to filter by book through chapters
        client = get_supabase()
        
        # First get chapter IDs for the book
        chapters_result = client.table("chapters").select("id, number, title").eq("book_id", book_id).execute()
        if not chapters_result.data:
            return []
        
        chapter_ids = [c["id"] for c in chapters_result.data]
        chapter_map = {c["id"]: c for c in chapters_result.data}
        
        # Get highlights for those chapters
        result = client.table("highlights").select(
            "id, chapter_id, start_offset, end_offset, color"
        ).eq("user_id", user_id).in_("chapter_id", chapter_ids).execute()
        
        # Merge with chapter info and sort
        highlights = []
        for h in result.data or []:
            chapter = chapter_map.get(h["chapter_id"], {})
            highlights.append({
                "id": h["id"],
                "chapter_id": h["chapter_id"],
                "start_offset": h["start_offset"],
                "end_offset": h["end_offset"],
                "color": h["color"],
                "chapter_number": chapter.get("number"),
                "chapter_title": chapter.get("title")
            })
        
        # Sort by chapter number then start offset
        highlights.sort(key=lambda x: (x.get("chapter_number") or 0, x.get("start_offset") or 0))
        return highlights
    
    def create_highlight(
        self,
        user_id: str,
        chapter_id: str,
        start_offset: int,
        end_offset: int,
        color: str = "yellow"
    ) -> dict:
        """Create a new highlight."""
        highlight_id = f"hl_{uuid.uuid4().hex[:12]}"
        
        if is_sqlite_mode():
            from ..db.database import get_db
            db = get_db()
            db.execute(
                """
                INSERT INTO highlights (id, user_id, chapter_id, start_offset, end_offset, color)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (highlight_id, user_id, chapter_id, start_offset, end_offset, color)
            )
            db.commit()
        else:
            # Supabase REST API
            client = get_supabase()
            client.table("highlights").insert({
                "id": highlight_id,
                "user_id": user_id,
                "chapter_id": chapter_id,
                "start_offset": start_offset,
                "end_offset": end_offset,
                "color": color
            }).execute()
        
        return {
            "id": highlight_id,
            "user_id": user_id,
            "chapter_id": chapter_id,
            "start_offset": start_offset,
            "end_offset": end_offset,
            "color": color
        }
    
    def delete_highlight(self, highlight_id: str, user_id: str) -> bool:
        """Delete a highlight (only if owned by user)."""
        if is_sqlite_mode():
            from ..db.database import get_db
            db = get_db()
            cursor = db.execute(
                "DELETE FROM highlights WHERE id = ? AND user_id = ?",
                (highlight_id, user_id)
            )
            db.commit()
            return cursor.rowcount > 0
        
        # Supabase REST API
        client = get_supabase()
        result = client.table("highlights").delete().eq(
            "id", highlight_id
        ).eq("user_id", user_id).execute()
        
        return len(result.data or []) > 0
    
    # -------------------------------------------------------------------------
    # Annotations
    # -------------------------------------------------------------------------
    
    def get_annotation(self, highlight_id: str) -> Optional[dict]:
        """Get annotation for a highlight."""
        if is_sqlite_mode():
            from ..db.database import get_db
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
        
        # Supabase REST API
        client = get_supabase()
        result = client.table("annotations").select(
            "id, highlight_id, text, created_at, updated_at"
        ).eq("highlight_id", highlight_id).execute()
        
        return result.data[0] if result.data else None
    
    def create_annotation(self, highlight_id: str, text: str) -> dict:
        """Create or update annotation for a highlight."""
        annotation_id = f"ann_{uuid.uuid4().hex[:12]}"
        
        if is_sqlite_mode():
            from ..db.database import get_db
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
        else:
            # Supabase REST API - use upsert
            client = get_supabase()
            client.table("annotations").upsert({
                "id": annotation_id,
                "highlight_id": highlight_id,
                "text": text
            }, on_conflict="highlight_id").execute()
        
        return {"id": annotation_id, "highlight_id": highlight_id, "text": text}
    
    def delete_annotation(self, annotation_id: str) -> bool:
        """Delete an annotation."""
        if is_sqlite_mode():
            from ..db.database import get_db
            db = get_db()
            cursor = db.execute(
                "DELETE FROM annotations WHERE id = ?",
                (annotation_id,)
            )
            db.commit()
            return cursor.rowcount > 0
        
        # Supabase REST API
        client = get_supabase()
        result = client.table("annotations").delete().eq("id", annotation_id).execute()
        
        return len(result.data or []) > 0
