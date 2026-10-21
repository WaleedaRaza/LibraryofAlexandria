"""Turn a submission into readable sources without publishing private material."""

import hashlib
import json
import re
from urllib.parse import urlsplit

from ..db.database import get_db, get_supabase, is_sqlite_mode


def decode_submission(row: dict) -> dict:
    row = dict(row)
    for key in ("links_json", "files_json"):
        if isinstance(row.get(key), str):
            row[key] = json.loads(row[key])
    return row


def submission_sources(submission: dict) -> list[dict]:
    base = {"title": submission["title"], "author": submission["author"], "domain": "Community",
            "submission_id": submission["id"], "visibility": "private",
            "rights_status": {"pending": "pending", "approved": "not_selected", "declined": "declined"}.get(submission["status"], "pending"),
            "text_status": "pending", "file_size": 0,
            "cover_tone": int(hashlib.sha256(submission["id"].encode()).hexdigest()[:2], 16) % 6}
    sources = []
    for index, file in enumerate(submission.get("files_json") or []):
        sources.append({**base, "id": f"{submission['id']}-pdf-{index}", "availability": "pdf_ready",
                        "source_filename": file["name"], "storage_key": file["storage_key"],
                        "asset_key": file["storage_key"], "page_count": file["page_count"], "file_size": file["size"]})
    for index, url in enumerate(submission.get("links_json") or []):
        sources.append({**base, "id": f"{submission['id']}-link-{index}", "availability": "external_link",
                        "source_url": url, "original_url": url, "source_domain": urlsplit(url).hostname, "page_count": None})
    return sources


def private_source(book_id: str, user: dict | None) -> dict | None:
    if not user:
        return None
    match = re.fullmatch(r"(sub_[a-f0-9]{32})-(pdf|link)-(\d+)", book_id)
    if not match:
        return None
    submission_id = match.group(1)
    if is_sqlite_mode():
        row = get_db().execute("SELECT * FROM book_submissions WHERE id=?", (submission_id,)).fetchone()
        submission = decode_submission(row) if row else None
    else:
        rows = get_supabase().table("book_submissions").select("*").eq("id", submission_id).limit(1).execute().data or []
        submission = decode_submission(rows[0]) if rows else None
    if not submission or (submission["user_id"] != user["id"] and user.get("role") != "admin"):
        return None
    return next((source for source in submission_sources(submission) if source["id"] == book_id), None)


def readable_book(book_id: str, user: dict | None) -> dict | None:
    from .catalog_service import CatalogService
    return CatalogService().get_book(book_id) or private_source(book_id, user)


def published_editions() -> list[dict]:
    if is_sqlite_mode():
        rows = get_db().execute("SELECT book_json FROM community_editions ORDER BY published_at DESC").fetchall()
    else:
        rows = get_supabase().table("community_editions").select("book_json").order("published_at", desc=True).execute().data or []
    return [json.loads(row["book_json"]) if isinstance(row["book_json"], str) else row["book_json"] for row in rows]
