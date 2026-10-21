"""Reviewer decisions and atomic publication of selected source editions."""

import json
import uuid

from ..db.database import get_db, get_supabase, is_sqlite_mode
from .source_service import decode_submission, submission_sources


class ReviewService:
    def inbox(self, status: str = "pending") -> list[dict]:
        if is_sqlite_mode():
            rows = get_db().execute(
                "SELECT s.*,u.display_name AS contributor FROM book_submissions s JOIN users u ON u.id=s.user_id ORDER BY s.created_at DESC LIMIT 200"
            ).fetchall()
        else:
            rows = get_supabase().table("book_submissions").select("*,users(display_name)").order("created_at", desc=True).limit(200).execute().data or []
        submissions = [decode_submission(row) for row in rows]
        for submission in submissions:
            submission.setdefault("contributor", (submission.get("users") or {}).get("display_name", "Reader"))
        return [row for row in submissions if status == "all" or row["status"] == status]

    def get(self, submission_id: str) -> dict | None:
        if is_sqlite_mode():
            row = get_db().execute(
                "SELECT s.*,u.display_name AS contributor FROM book_submissions s JOIN users u ON u.id=s.user_id WHERE s.id=?", (submission_id,)
            ).fetchone()
            submission = decode_submission(row) if row else None
            reviews = [dict(row) for row in get_db().execute(
                "SELECT decision,note,created_at FROM submission_reviews WHERE submission_id=? ORDER BY created_at DESC", (submission_id,)
            )]
        else:
            rows = get_supabase().table("book_submissions").select("*,users(display_name)").eq("id", submission_id).limit(1).execute().data or []
            submission = decode_submission(rows[0]) if rows else None
            reviews = get_supabase().table("submission_reviews").select("decision,note,created_at").eq("submission_id", submission_id).order("created_at", desc=True).execute().data or []
        if submission:
            submission.setdefault("contributor", (submission.get("users") or {}).get("display_name", "Reader"))
            submission["sources"] = submission_sources(submission)
            submission["reviews"] = reviews
        return submission

    def decide(self, submission_id: str, reviewer: dict, *, decision: str, title: str, author: str,
               note: str, source_ids: list[str]) -> None:
        if reviewer.get("role") != "admin":
            raise PermissionError("Reviewer access required")
        submission = self.get(submission_id)
        if not submission or submission["status"] != "pending":
            raise ValueError("This submission has already been reviewed or is unavailable.")
        title, author, note = title.strip(), author.strip(), note.strip()
        if decision not in {"approved", "declined"}:
            raise ValueError("Choose a review decision.")
        if not 1 <= len(title) <= 160 or not 1 <= len(author) <= 160:
            raise ValueError("Add the correct title and author before completing the review.")
        if not 1 <= len(note) <= 2000:
            raise ValueError("Record the source, edition, and sharing basis, or why publication was declined.")
        sources = {source["id"]: source for source in submission["sources"]}
        if any(source_id not in sources for source_id in source_ids):
            raise ValueError("A selected source does not belong to this submission.")
        if decision == "approved" and not source_ids:
            raise ValueError("Select at least one source to publish.")
        books = [{**sources[source_id], "title": title, "author": author,
                  "visibility": "public", "rights_status": "approved"}
                 for source_id in dict.fromkeys(source_ids)] if decision == "approved" else []
        review_id = f"review_{uuid.uuid4().hex}"
        if is_sqlite_mode():
            db = get_db()
            with db:
                changed = db.execute("UPDATE book_submissions SET status=?,title=?,author=? WHERE id=? AND status='pending'",
                                     (decision, title, author, submission_id))
                if changed.rowcount != 1:
                    raise ValueError("Another reviewer has already completed this submission.")
                for book in books:
                    db.execute("INSERT INTO community_editions(id,submission_id,book_json) VALUES(?,?,?)",
                               (book["id"], submission_id, json.dumps(book)))
                db.execute("INSERT INTO submission_reviews(id,submission_id,reviewer_id,decision,note,source_ids_json) VALUES(?,?,?,?,?,?)",
                           (review_id, submission_id, reviewer["id"], decision, note, json.dumps([book["id"] for book in books])))
        else:
            get_supabase().rpc("review_submission", {
                "p_submission_id": submission_id, "p_reviewer_id": reviewer["id"], "p_review_id": review_id,
                "p_decision": decision, "p_note": note, "p_title": title, "p_author": author, "p_books": books,
            }).execute()
