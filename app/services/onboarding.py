"""First run: doors into the collection, and the first steps a new reader has and hasn't taken.

Steps are read from what the reader has actually done (shelf, progress,
highlights, conversations, source runs), not from a "seen the tour" flag, so
the list stays honest and disappears on its own. The two steps that leave no
row in the database (asking a book, a quick search with the eye) are carried in
a small cookie.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

from ..db.database import get_db, get_supabase, is_sqlite_mode
from .catalog_service import CatalogService
from .user_service import UserService

logger = logging.getLogger(__name__)

DOORS_PATH = Path(__file__).resolve().parent.parent.parent / "library" / "onboarding" / "doors.json"
STEPS_COOKIE = "lx_steps"
WELCOMED_COOKIE = "lx_welcomed"
COOKIE_FLAGS = {"asked", "eye"}
STARTER_MAX = 8


@lru_cache(maxsize=1)
def _doors_file() -> list[dict]:
    try:
        return json.loads(DOORS_PATH.read_text(encoding="utf-8")).get("doors", [])
    except (OSError, ValueError):
        logger.warning("Onboarding doors file is missing or invalid")
        return []


def doors() -> list[dict]:
    """Doors with each book resolved against the live catalog; books that left the catalog are dropped."""
    catalog = CatalogService()
    out = []
    for door in _doors_file():
        books = []
        for entry in door.get("books", []):
            book = catalog.get_book(entry["id"])
            if not book or book.get("availability") == "external_link":
                continue
            books.append({
                "id": book["id"],
                "title": book.get("title") or "Untitled",
                "author": book.get("author") or "",
                "questions": entry.get("questions", [])[:3],
            })
        if books:
            out.append({"key": door["key"], "label": door["label"], "line": door.get("line", ""), "books": books})
    return out


def starter_ids() -> set[str]:
    return {book["id"] for door in doors() for book in door["books"]}


def suggested_questions(book_id: str) -> list[str]:
    for door in _doors_file():
        for entry in door.get("books", []):
            if entry["id"] == book_id:
                return entry.get("questions", [])[:3]
    return []


def save_starter_shelf(user_id: str, book_ids: list[str]) -> list[str]:
    allowed = starter_ids()
    chosen = [book_id for book_id in dict.fromkeys(book_ids) if book_id in allowed][:STARTER_MAX]
    service = UserService()
    for book_id in chosen:
        service.save_book(user_id, book_id)
    return chosen


# ---------------------------------------------------------------------------
# First steps
# ---------------------------------------------------------------------------

def read_flags(cookie_value: str | None) -> set[str]:
    return {flag for flag in (cookie_value or "").split(".") if flag in COOKIE_FLAGS}


def with_flag(cookie_value: str | None, flag: str) -> str:
    return ".".join(sorted(read_flags(cookie_value) | {flag}))


def _discussed(highlight_ids: list[str]) -> bool:
    if not highlight_ids:
        return False
    ids = highlight_ids[:200]
    if is_sqlite_mode():
        marks = ",".join("?" * len(ids))
        row = get_db().execute(f"SELECT 1 FROM chat_messages WHERE highlight_id IN ({marks}) LIMIT 1", ids).fetchone()
        return row is not None
    rows = get_supabase().table("chat_messages").select("id").in_("highlight_id", ids).limit(1).execute().data
    return bool(rows)


def _sent_the_eye(user_id: str) -> bool:
    from .finder_job_service import FinderJobService

    return bool(FinderJobService().list_for_user(user_id, limit=1))


def first_steps(user: dict, cookie_value: str | None = None) -> dict:
    """The six things that make LibXNDR click, each marked done from the reader's own data."""
    service = UserService()
    flags = read_flags(cookie_value)
    user_id = user["id"]

    def safe(check, default=False):
        try:
            return check()
        except Exception:
            logger.info("First-steps check failed", exc_info=True)
            return default

    saved = safe(lambda: len(service.get_saved_book_ids(user_id)), 0)
    progress = safe(lambda: service.get_progress_for_user(user_id), [])
    highlights = safe(lambda: service.get_highlights(user_id), [])
    opened = progress[0] if progress else None
    steps = [
        {
            "key": "shelf", "title": "Build a starter shelf", "done": saved >= 3,
            "line": "Pick three books you mean to read. They wait on your reading board.",
            "href": "/welcome", "action": "Pick books",
        },
        {
            "key": "ask", "title": "Ask a book a question", "done": "asked" in flags,
            "line": "Get an answer that is a passage from the book itself, with the page, not a summary from memory.",
            "href": "/welcome#ask", "action": "Ask one",
        },
        {
            "key": "open", "title": "Open a book", "done": bool(opened),
            "line": "Read in the browser. Your page follows you to every device.",
            "href": f"/read/{opened['book_id']}" if opened else "/library", "action": "Open one",
        },
        {
            "key": "keep", "title": "Keep a passage", "done": bool(highlights),
            "line": "Select a line in the reader and press Keep this passage. It goes into your notebook.",
            "href": f"/read/{opened['book_id']}" if opened else "/library", "action": "Go to the reader",
        },
        {
            "key": "discuss", "title": "Talk to a passage", "done": safe(lambda: _discussed([h["id"] for h in highlights])),
            "line": "Open Discuss this passage beside anything you kept. The companion reads the page with you.",
            "href": "/library/my/memory", "action": "Your passages",
        },
        {
            "key": "eye", "title": "Send the eye for a missing book", "done": "eye" in flags or safe(lambda: _sent_the_eye(user_id)),
            "line": "Name a book that isn't here. The eye searches the open web for a readable copy.",
            "href": "/welcome#eye", "action": "Try the eye",
        },
    ]
    done = sum(step["done"] for step in steps)
    next_step = next((step for step in steps if not step["done"]), None)
    return {"steps": steps, "done": done, "total": len(steps), "complete": next_step is None, "next": next_step}


def needs_welcome(user: dict, welcomed_cookie: str | None) -> bool:
    """Send a reader to /welcome once: when their shelf is empty and they haven't been through it on this device."""
    if welcomed_cookie:
        return False
    try:
        return not UserService().get_saved_book_ids(user["id"])
    except Exception:
        return False
