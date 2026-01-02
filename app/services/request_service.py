"""
Alexandria Library - Request Service
Book request lifecycle - the growth loop.
Users request books, admins approve, canon grows.
"""

from typing import Optional, List
import uuid
from datetime import datetime

from ..db.database import get_supabase, is_sqlite_mode


class RequestService:
    """
    Service for book requests.
    This is how the canon grows - deliberately, not automatically.
    """
    
    def get_user_requests(self, user_id: str) -> List[dict]:
        """Get all book requests by a user."""
        if is_sqlite_mode():
            from ..db.database import get_db
            db = get_db()
            rows = db.execute(
                """
                SELECT id, title, author, reason, status, admin_notes, created_at, resolved_at
                FROM book_requests
                WHERE user_id = ?
                ORDER BY created_at DESC
                """,
                (user_id,)
            ).fetchall()
            return [dict(row) for row in rows]
        
        # Supabase REST API
        client = get_supabase()
        result = client.table("book_requests").select(
            "id, title, author, reason, status, admin_notes, created_at, resolved_at"
        ).eq("user_id", user_id).order("created_at", desc=True).execute()
        
        return result.data or []
    
    def get_pending_requests(self) -> List[dict]:
        """Get all pending requests (admin view)."""
        return self.get_requests_by_status("PENDING")
    
    def get_all_requests(self) -> List[dict]:
        """Get all requests (admin view)."""
        if is_sqlite_mode():
            from ..db.database import get_db
            db = get_db()
            rows = db.execute(
                """
                SELECT br.id, br.title, br.author, br.reason, br.status, br.created_at,
                       br.admin_notes, br.resolved_at,
                       u.email as requester_email, u.display_name as requester_name
                FROM book_requests br
                JOIN users u ON br.user_id = u.id
                ORDER BY br.created_at DESC
                """
            ).fetchall()
            return [dict(row) for row in rows]
        
        # Supabase REST API - use foreign key relationship
        client = get_supabase()
        result = client.table("book_requests").select(
            "id, title, author, reason, status, created_at, admin_notes, resolved_at, "
            "users(email, display_name)"
        ).order("created_at", desc=True).execute()
        
        # Flatten the nested user data
        requests = []
        for row in result.data or []:
            user = row.pop("users", {}) or {}
            row["requester_email"] = user.get("email")
            row["requester_name"] = user.get("display_name")
            requests.append(row)
        
        return requests
    
    def get_requests_by_status(self, status: str) -> List[dict]:
        """Get requests filtered by status (admin view)."""
        if is_sqlite_mode():
            from ..db.database import get_db
            db = get_db()
            rows = db.execute(
                """
                SELECT br.id, br.title, br.author, br.reason, br.status, br.created_at,
                       br.admin_notes, br.resolved_at,
                       u.email as requester_email, u.display_name as requester_name
                FROM book_requests br
                JOIN users u ON br.user_id = u.id
                WHERE br.status = ?
                ORDER BY br.created_at DESC
                """,
                (status,)
            ).fetchall()
            return [dict(row) for row in rows]
        
        # Supabase REST API
        client = get_supabase()
        result = client.table("book_requests").select(
            "id, title, author, reason, status, created_at, admin_notes, resolved_at, "
            "users(email, display_name)"
        ).eq("status", status).order("created_at", desc=True).execute()
        
        # Flatten the nested user data
        requests = []
        for row in result.data or []:
            user = row.pop("users", {}) or {}
            row["requester_email"] = user.get("email")
            row["requester_name"] = user.get("display_name")
            requests.append(row)
        
        return requests
    
    def get_request(self, request_id: str) -> Optional[dict]:
        """Get a single request by ID."""
        if is_sqlite_mode():
            from ..db.database import get_db
            db = get_db()
            row = db.execute(
                """
                SELECT id, user_id, title, author, reason, status, admin_notes, 
                       created_at, resolved_at
                FROM book_requests
                WHERE id = ?
                """,
                (request_id,)
            ).fetchone()
            return dict(row) if row else None
        
        # Supabase REST API
        client = get_supabase()
        result = client.table("book_requests").select(
            "id, user_id, title, author, reason, status, admin_notes, created_at, resolved_at"
        ).eq("id", request_id).execute()
        
        return result.data[0] if result.data else None
    
    def create_request(
        self,
        user_id: str,
        title: str,
        author: Optional[str] = None,
        reason: Optional[str] = None
    ) -> dict:
        """Create a new book request."""
        request_id = f"req_{uuid.uuid4().hex[:12]}"
        
        if is_sqlite_mode():
            from ..db.database import get_db
            db = get_db()
            db.execute(
                """
                INSERT INTO book_requests (id, user_id, title, author, reason, status)
                VALUES (?, ?, ?, ?, ?, 'PENDING')
                """,
                (request_id, user_id, title, author, reason)
            )
            db.commit()
        else:
            # Supabase REST API
            client = get_supabase()
            client.table("book_requests").insert({
                "id": request_id,
                "user_id": user_id,
                "title": title,
                "author": author,
                "reason": reason,
                "status": "PENDING"
            }).execute()
        
        return {
            "id": request_id,
            "user_id": user_id,
            "title": title,
            "author": author,
            "reason": reason,
            "status": "PENDING"
        }
    
    def cancel_request(self, request_id: str, user_id: str) -> bool:
        """
        Cancel a pending request.
        Only the requester can cancel, and only if still pending.
        """
        if is_sqlite_mode():
            from ..db.database import get_db
            db = get_db()
            cursor = db.execute(
                """
                DELETE FROM book_requests
                WHERE id = ? AND user_id = ? AND status = 'PENDING'
                """,
                (request_id, user_id)
            )
            db.commit()
            return cursor.rowcount > 0
        
        # Supabase REST API
        client = get_supabase()
        result = client.table("book_requests").delete().eq(
            "id", request_id
        ).eq("user_id", user_id).eq("status", "PENDING").execute()
        
        return len(result.data or []) > 0
    
    # -------------------------------------------------------------------------
    # Admin actions
    # -------------------------------------------------------------------------
    
    def approve_request(self, request_id: str, admin_notes: Optional[str] = None) -> bool:
        """Approve a book request (admin only)."""
        if is_sqlite_mode():
            from ..db.database import get_db
            db = get_db()
            cursor = db.execute(
                """
                UPDATE book_requests
                SET status = 'APPROVED',
                    admin_notes = ?,
                    resolved_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'PENDING'
                """,
                (admin_notes, request_id)
            )
            db.commit()
            return cursor.rowcount > 0
        
        # Supabase REST API
        client = get_supabase()
        result = client.table("book_requests").update({
            "status": "APPROVED",
            "admin_notes": admin_notes,
            "resolved_at": datetime.utcnow().isoformat()
        }).eq("id", request_id).eq("status", "PENDING").execute()
        
        return len(result.data or []) > 0
    
    def reject_request(self, request_id: str, admin_notes: Optional[str] = None) -> bool:
        """Reject a book request (admin only)."""
        if is_sqlite_mode():
            from ..db.database import get_db
            db = get_db()
            cursor = db.execute(
                """
                UPDATE book_requests
                SET status = 'REJECTED',
                    admin_notes = ?,
                    resolved_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'PENDING'
                """,
                (admin_notes, request_id)
            )
            db.commit()
            return cursor.rowcount > 0
        
        # Supabase REST API
        client = get_supabase()
        result = client.table("book_requests").update({
            "status": "REJECTED",
            "admin_notes": admin_notes,
            "resolved_at": datetime.utcnow().isoformat()
        }).eq("id", request_id).eq("status", "PENDING").execute()
        
        return len(result.data or []) > 0
    
    def mark_added(self, request_id: str, book_id: str = None) -> bool:
        """Mark a request as fulfilled (book added to canon)."""
        note = f"Added as {book_id}" if book_id else "Added to library"
        
        if is_sqlite_mode():
            from ..db.database import get_db
            db = get_db()
            cursor = db.execute(
                """
                UPDATE book_requests
                SET status = 'ADDED',
                    admin_notes = COALESCE(admin_notes || ' | ', '') || ?,
                    resolved_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (note, request_id)
            )
            db.commit()
            return cursor.rowcount > 0
        
        # Supabase REST API - need to read first to append notes
        client = get_supabase()
        
        # Get existing notes
        existing = client.table("book_requests").select("admin_notes").eq("id", request_id).execute()
        if not existing.data:
            return False
        
        current_notes = existing.data[0].get("admin_notes") or ""
        new_notes = f"{current_notes} | {note}" if current_notes else note
        
        result = client.table("book_requests").update({
            "status": "ADDED",
            "admin_notes": new_notes,
            "resolved_at": datetime.utcnow().isoformat()
        }).eq("id", request_id).execute()
        
        return len(result.data or []) > 0
