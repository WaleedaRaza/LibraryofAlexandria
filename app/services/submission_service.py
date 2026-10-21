"""Private, review-first reader book submissions."""

from __future__ import annotations

import ipaddress
import json
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import UploadFile

from ..config import settings
from ..db.database import get_db, get_supabase, is_sqlite_mode
from .source_service import submission_sources

MAX_FILES = 4
# Firebase Hosting forwards uploads to Cloud Run over HTTP/1. Keep the entire
# multipart request comfortably below Cloud Run's 32 MiB request ceiling.
MAX_UPLOAD_BYTES = 24 * 1024 * 1024
MAX_LINKS = 12


def clean_links(raw: str) -> list[str]:
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if len(lines) > MAX_LINKS:
        raise ValueError(f"Add at most {MAX_LINKS} links at a time.")
    links: list[str] = []
    for link in lines:
        if len(link) > 2048:
            raise ValueError("One of the links is too long.")
        parsed = urlsplit(link)
        hostname = parsed.hostname or ""
        if parsed.scheme not in {"http", "https"} or not hostname or parsed.username or parsed.password:
            raise ValueError("Use full public http:// or https:// links, one per line.")
        try:
            if not ipaddress.ip_address(hostname).is_global:
                raise ValueError("Local or private network links cannot be submitted.")
        except ValueError as exc:
            if "cannot be submitted" in str(exc):
                raise
            if hostname.casefold() in {"localhost", "localhost.localdomain"} or "." not in hostname:
                raise ValueError("Use a public website link, not a local address.") from exc
        if link not in links:
            links.append(link)
    return links


class SubmissionService:
    def for_user(self, user_id: str) -> list[dict]:
        if is_sqlite_mode():
            rows = get_db().execute(
                "SELECT * FROM book_submissions WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
            result = [dict(row) for row in rows]
        else:
            result = get_supabase().table("book_submissions").select("*").eq(
                "user_id", user_id
            ).order("created_at", desc=True).execute().data or []
        for row in result:
            for key in ("links_json", "files_json"):
                if isinstance(row[key], str):
                    row[key] = json.loads(row[key])
            row["sources"] = submission_sources(row)
        return result

    async def create(
        self,
        *,
        user_id: str,
        title: str,
        author: str,
        note: str,
        links: str,
        files: list[UploadFile],
    ) -> dict:
        title, author, note = title.strip(), author.strip(), note.strip()
        if not title or len(title) > 160 or len(author) > 160 or len(note) > 800:
            raise ValueError("Add a title, and keep the title, author, and note reasonably short.")
        clean = clean_links(links)
        files = [item for item in files if item.filename]
        if len(files) > MAX_FILES:
            raise ValueError(f"Add at most {MAX_FILES} PDF files at a time.")
        if not clean and not files:
            raise ValueError("Add at least one PDF file or public link.")

        submission_id = f"sub_{uuid.uuid4().hex}"
        stored: list[dict] = []
        uploaded_bytes = 0
        try:
            for file in files:
                content = await file.read(MAX_UPLOAD_BYTES + 1)
                uploaded_bytes += len(content)
                if len(content) > MAX_UPLOAD_BYTES or uploaded_bytes > MAX_UPLOAD_BYTES:
                    raise ValueError("PDF uploads are limited to 24 MB total. Submit smaller files or public links.")
                if not content.startswith(b"%PDF-"):
                    raise ValueError("Only valid PDF files can be submitted.")
                try:
                    import fitz

                    with fitz.open(stream=content, filetype="pdf") as document:
                        page_count = document.page_count
                except Exception as exc:
                    raise ValueError("A PDF could not be opened. Please check the file and try again.") from exc
                if page_count < 1:
                    raise ValueError("A submitted PDF has no pages.")
                original_name = Path(file.filename).name[:180]
                key = f"submissions/{user_id}/{submission_id}/{uuid.uuid4().hex}.pdf"
                if is_sqlite_mode():
                    destination = settings.DATA_DIR / key
                    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    destination.write_bytes(content)
                else:
                    get_supabase().storage.from_(settings.SUPABASE_STORAGE_BUCKET).upload(
                        path=key,
                        file=content,
                        file_options={"content-type": "application/pdf", "upsert": "false"},
                    )
                stored.append({"name": original_name, "storage_key": key, "page_count": page_count, "size": len(content)})

            record = {
                "id": submission_id,
                "user_id": user_id,
                "title": title,
                "author": author,
                "note": note,
                "links_json": clean,
                "files_json": stored,
                "status": "pending",
            }
            if is_sqlite_mode():
                get_db().execute(
                    """INSERT INTO book_submissions
                       (id, user_id, title, author, note, links_json, files_json, status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (submission_id, user_id, title, author, note, json.dumps(clean), json.dumps(stored), "pending"),
                )
                for source in submission_sources(record):
                    get_db().execute("INSERT INTO saved_books(id,user_id,book_id) VALUES(?,?,?)",
                                     (f"saved_{uuid.uuid4().hex}", user_id, source["id"]))
                get_db().commit()
            else:
                get_supabase().rpc("create_book_submission", {"p_record": record,
                    "p_source_ids": [source["id"] for source in submission_sources(record)]}).execute()
            return record
        except Exception:
            if is_sqlite_mode():
                get_db().rollback()
            if stored:
                if is_sqlite_mode():
                    for item in stored:
                        (settings.DATA_DIR / item["storage_key"]).unlink(missing_ok=True)
                else:
                    get_supabase().storage.from_(settings.SUPABASE_STORAGE_BUCKET).remove(
                        [item["storage_key"] for item in stored]
                    )
            raise
