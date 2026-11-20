"""Catalog, covers, personal shelf, and reading memory."""

import random
import re
import logging
import asyncio
import time
from collections import defaultdict
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response

from .. import templates
from ..config import settings
from ..services.asset_service import AssetService
from ..services.catalog_service import CatalogService
from ..services.catalog_normalization import canonicalize_book, group_editions
from ..services.chat_service import ChatService
from ..services.link_cover import render_link_cover
from ..services.memory_companion_service import MemoryCompanionService
from ..services.user_service import UserService
from ..services.source_service import readable_book
from .auth import get_current_user_optional, get_current_user_required

router = APIRouter()
logger = logging.getLogger(__name__)
_memory_chat_times: dict[str, list[float]] = defaultdict(list)
_memory_chat_slots = asyncio.Semaphore(3)


@router.get("/book/{book_id}/cover")
async def book_cover(book_id: str, user=Depends(get_current_user_optional)):
    book = readable_book(book_id, user) or CatalogService().get_book(book_id, include_drafts=not settings.is_production)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if book.get("availability") == "external_link" or book.get("submission_id"):
        return Response(
            render_link_cover(book),
            media_type="image/svg+xml",
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    cover_dir = settings.BASE_DIR / "library" / "covers"
    cover_path = cover_dir / f"{book_id}.jpg"
    if not cover_path.exists():
        pdf_path = AssetService().local_pdf(book)
        if pdf_path:
            try:
                import fitz

                cover_dir.mkdir(parents=True, exist_ok=True)
                document = fitz.open(str(pdf_path))
                page = document[0]
                pixmap = page.get_pixmap(matrix=fitz.Matrix(1.15, 1.15), alpha=False)
                pixmap.save(str(cover_path))
                document.close()
            except Exception as exc:
                raise HTTPException(status_code=503, detail="Cover is not ready") from exc
        else:
            # Covers are an enhancement, never a prerequisite for opening the
            # catalog. Older catalog rows can point at cover objects that were
            # never generated (or have since been removed). Storage clients
            # raise for those misses, so degrade to the deterministic SVG cover
            # instead of turning an ordinary image request into a 500.
            try:
                signed_url = AssetService().signed_cover_url(book)
            except Exception as exc:
                logger.info("Falling back to generated cover for %s (%s)", book_id, type(exc).__name__)
                signed_url = None
            if signed_url:
                return RedirectResponse(signed_url, status_code=307)
            return Response(
                render_link_cover(book), media_type="image/svg+xml",
                headers={"Cache-Control": "public, max-age=86400", "X-Content-Type-Options": "nosniff"},
            )
    return FileResponse(cover_path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


def reading_snapshot(user) -> dict[str, str]:
    if not user:
        return {}
    return UserService().get_shelf_statuses(user["id"])


def header_counts(user, *, include_drafts: bool = False) -> dict:
    catalog = CatalogService()
    total = len(catalog.get_books(include_drafts=include_drafts))
    snapshot = reading_snapshot(user)
    read = sum(status == "read" for status in snapshot.values())
    reading = sum(status == "reading" for status in snapshot.values())
    return {
        "total_books": total,
        "read": read,
        "reading": reading,
        "want": sum(status == "want_to_read" for status in snapshot.values()),
    }


def _href(base: dict, **overrides) -> str:
    params = {**base, **overrides}
    clean = {
        key: value
        for key, value in params.items()
        if value and not (key == "view" and value == "grid") and not (key == "status" and value == "all")
    }
    query = urlencode(clean)
    return "/library" + (f"?{query}" if query else "")


GUEST_PREVIEW_BOOKS = 30
GUEST_SEARCH_BOOKS = 12


def _discovery_pool(books: list[dict]) -> list[dict]:
    """Keep the prominent three-book window clear of obvious file-name metadata.

    The full vault is still browseable. This is a display-quality guard, not an
    editorial ranking or a rights assessment.
    """
    clean: list[dict] = []
    seen: set[str] = set()
    for book in books:
        title = (book.get("title") or "").strip()
        author = (book.get("author") or "").strip()
        key = title.casefold()
        if (
            not 4 <= len(title) <= 75
            or not author
            or not title[0].isupper()
            or re.search(r"(?i)\b(pdf|excerpt|chapter|full book|preview|www|unknown|z\s*lib|pdfdrive)\b|__|https?://|file [a-z]:", title)
            or re.search(r"(?i)\bv\s*\d+\b|__|\b(pdf|unknown|www|z\s*lib|pdfdrive|administrator|guest|user|ebook|cereal|text)\b|https?://|\d", author)
            or title.casefold() == author.casefold()
            or key in seen
        ):
            continue
        seen.add(key)
        clean.append(book)
    return clean or books


def _author_heading(raw: str) -> str:
    name = re.sub(r"(?i)(?:__dup\d+|\s+dup\s*\d+|\s+v\s*\d+|\s*\(\d+\))+$", "", raw.strip()).strip()
    if (
        len(name) < 3 or len(name) > 70 or not name[0].isupper()
        or re.search(r"(?i)\b(unknown|administrator|guest user|www|pdf|ebook|edition)\b|__|\d", name)
        or name.casefold() in {"user", "text", "a a"}
    ):
        return "Uncatalogued / needs review"
    return name


def _title_letter(title: str) -> str:
    """Return the reader-facing A-Z shelf for a title."""
    first = (title or "").strip()[:1].upper()
    if first.isalpha():
        return first
    if first.isdigit():
        return "0–9"
    return "#"


def render_shelf(
    request: Request,
    user,
    *,
    domain: str | None = None,
    search: str | None = None,
    status: str | None = None,
    view: str | None = None,
    refresh: str | None = None,
    preview_links: str | None = None,
    kind: str | None = None,
    browse: str | None = None,
):
    catalog = CatalogService()
    include_drafts = preview_links == "1" and not settings.is_production
    service = UserService()
    snapshot = reading_snapshot(user)
    note_counts: dict[str, int] = {}
    if user:
        for highlight in service.get_highlights(user["id"]):
            note_counts[highlight["book_id"]] = note_counts.get(highlight["book_id"], 0) + 1

    def decorate(book: dict) -> dict:
        return {
            **book,
            "reading_status": snapshot.get(book["id"]),
            "note_count": note_counts.get(book["id"], 0),
        }

    all_books = catalog.get_books(include_drafts=include_drafts)
    counts: dict[str, int] = {}
    for book in all_books:
        counts[book.get("domain") or "General"] = counts.get(book.get("domain") or "General", 0) + 1

    editions = [decorate(book) for book in catalog.get_books(domain=domain, search=search, include_drafts=include_drafts)]
    if kind == "links":
        editions = [book for book in editions if book.get("availability") == "external_link"]
    elif kind == "pdfs":
        editions = [book for book in editions if book.get("availability") != "external_link"]
    if status in {"want_to_read", "reading", "read"}:
        editions = [book for book in editions if book["reading_status"] == status]

    books = []
    status_rank = {None: 0, "want_to_read": 1, "reading": 2, "read": 3}
    for work in group_editions(editions):
        owned = [edition for edition in work["editions"] if edition.get("reading_status")]
        representative = (owned or [work["representative"]])[0]
        representative = {
            **representative,
            "edition_count": work["edition_count"],
            "editions": work["editions"],
            "note_count": sum(edition.get("note_count", 0) for edition in work["editions"]),
            "reading_status": max(
                (edition.get("reading_status") for edition in work["editions"]),
                key=lambda value: status_rank[value],
            ),
        }
        books.append(representative)
    books.sort(key=lambda item: ((item.get("title") or "").casefold(), (item.get("author") or "").casefold()))
    discovery_pool = _discovery_pool(books)
    random.shuffle(discovery_pool)
    discovery_books = discovery_pool[:1]
    vault_total = len(books)
    match_total = len(books)
    # Visitors without an account see a look inside, not the whole shelf: a changing handful of
    # covers, or the first few matches for a search. The full A-Z and by-author views open on sign-in.
    guest_preview = user is None and not include_drafts
    if guest_preview:
        browse = "books"
        books = sorted(books[:GUEST_SEARCH_BOOKS] if search else discovery_pool[1:1 + GUEST_PREVIEW_BOOKS],
                       key=lambda item: ((item.get("title") or "").casefold(), (item.get("author") or "").casefold()))
    alphabet_groups: list[dict] = []
    for book in (() if guest_preview else books):
        letter = _title_letter(book.get("title") or "")
        if not alphabet_groups or alphabet_groups[-1]["letter"] != letter:
            alphabet_groups.append({"letter": letter, "books": []})
        alphabet_groups[-1]["books"].append(book)
    authors: dict[str, list[dict]] = {}
    for book in (() if guest_preview else books):
        authors.setdefault(_author_heading(book.get("author") or ""), []).append(book)
    author_groups = [
        {"name": name, "books": sorted(group, key=lambda item: item["title"].casefold())}
        for name, group in sorted(authors.items(), key=lambda item: (item[0].startswith("Uncatalogued"), item[0].casefold()))
    ]

    filters = {
        "domain": domain or "", "search": search or "", "status": status or "", "view": view or "",
        "kind": kind or "", "preview_links": "1" if include_drafts else "", "browse": browse or "",
    }
    domains = [
        {"name": name, "count": counts[name], "href": _href(filters, domain=name)}
        for name in sorted(counts)
    ]
    shelf = header_counts(user, include_drafts=include_drafts)
    return templates.TemplateResponse(
        "library.html",
        {
            "request": request,
            "user": user,
            "books": books,
            "discovery_books": discovery_books,
            "discovery_data": [
                {key: book.get(key) for key in ("id", "title", "author", "domain", "availability")}
                for book in discovery_pool
            ],
            "grid_data": [
                {key: book.get(key) for key in ("id", "title", "author", "domain", "availability", "edition_count")}
                for book in books
            ],
            "author_groups": author_groups,
            "alphabet_groups": alphabet_groups,
            "browse": "authors" if browse == "authors" else "books",
            "guest_preview": guest_preview,
            "vault_total": vault_total,
            "match_total": match_total,
            "edition_count": len(editions),
            "shelf": shelf,
            "total_books": shelf["total_books"],
            "domains": domains,
            "current_domain": domain,
            "search": search or "",
            "status": status or "",
            "view": "kanban" if view == "kanban" else "grid",
            "kind": kind or "",
            "preview_links": include_drafts,
            "link_count": sum(book.get("availability") == "external_link" for book in all_books),
            "links": {
                "all": _href(filters, domain="", status=""),
                "want": _href(filters, status="want_to_read"),
                "reading": _href(filters, status="reading"),
                "read": _href(filters, status="read"),
                "grid": _href(filters, view="grid"),
                "kanban": _href(filters, view="kanban"),
                "domain_all": _href(filters, domain=""),
                "all_kinds": _href(filters, kind=""),
                "pdfs": _href(filters, kind="pdfs"),
                "external": _href(filters, kind="links"),
                "browse_books": _href(filters, browse="books"),
                "browse_authors": _href(filters, browse="authors"),
            },
            "show_shelf": True,
        },
    )


@router.get("/", response_class=HTMLResponse)
async def browse_library(
    request: Request,
    domain: str | None = None,
    search: str | None = None,
    status: str | None = None,
    view: str | None = None,
    refresh: str | None = None,
    preview_links: str | None = None,
    kind: str | None = None,
    browse: str | None = None,
    user=Depends(get_current_user_optional),
):
    return render_shelf(
        request,
        user,
        domain=domain,
        search=search,
        status=status,
        view=view,
        refresh=refresh,
        preview_links=preview_links,
        kind=kind,
        browse=browse,
    )


@router.get("/my", response_class=HTMLResponse)
async def my_library(request: Request, user=Depends(get_current_user_optional)):
    if not user:
        return RedirectResponse("/auth/login?next=/library/my", status_code=303)
    service = UserService()
    books = service.get_saved_books(user["id"])
    columns = [
        {"key": key, "label": label, "books": [book for book in books if book["reading_status"] == key]}
        for key, label in (
            ("want_to_read", "Want to read"),
            ("reading", "Reading"),
            ("read", "Read"),
        )
    ]
    shelf = header_counts(user)
    continue_book = next(
        (book for book in books
         if book["reading_status"] == "reading" and book.get("availability") != "external_link"),
        None,
    )
    return templates.TemplateResponse(
        "my_library.html",
        {
            "request": request,
            "user": user,
            "books": books,
            "columns": columns,
            "continue_book": continue_book,
            "stats": service.get_stats(user["id"]),
            "shelf": shelf,
            "total_books": shelf["total_books"],
        },
    )


@router.get("/my/runs")
async def my_runs():
    return RedirectResponse("/library/find/runs", status_code=303)


@router.get("/my/memory", response_class=HTMLResponse)
async def my_reading_memory(
    request: Request,
    q: str = "",
    book: str = "",
    user=Depends(get_current_user_optional),
):
    if not user:
        return RedirectResponse("/auth/login?next=/library/my/memory", status_code=303)
    service = UserService()
    highlights = service.get_highlights(user["id"])
    for highlight in highlights:
        highlight["book"] = readable_book(highlight["book_id"], user)
        highlight["messages"] = ChatService().get_messages(highlight["id"])
    memory_books = []
    seen_books = set()
    for highlight in highlights:
        source = highlight.get("book")
        if source and highlight["book_id"] not in seen_books:
            seen_books.add(highlight["book_id"])
            memory_books.append(source)
    memory_books.sort(key=lambda item: (item.get("title") or "").casefold())
    q = q.strip()[:160]
    if book:
        highlights = [highlight for highlight in highlights if highlight["book_id"] == book]
    if q:
        needle = q.casefold()
        highlights = [
            highlight for highlight in highlights
            if needle in " ".join(
                (
                    highlight.get("selected_text") or "",
                    highlight.get("note") or "",
                    (highlight.get("book") or {}).get("title") or "",
                    (highlight.get("book") or {}).get("author") or "",
                )
            ).casefold()
        ]
    shelf = header_counts(user)
    return templates.TemplateResponse(
        "reading_memory.html",
        {
            "request": request,
            "user": user,
            "highlights": highlights,
            "memory_books": memory_books,
            "memory_query": q,
            "memory_book": book,
            "companion_messages": MemoryCompanionService().get_messages(user["id"]),
            "companion_live": bool(settings.OPENAI_API_KEY and not settings.USE_MOCK_AGENTS),
            "stats": service.get_stats(user["id"]),
            "shelf": shelf,
            "total_books": shelf["total_books"],
        },
    )


@router.post("/my/memory/chat", response_class=JSONResponse)
async def reading_memory_chat(request: Request, user=Depends(get_current_user_required)):
    data = await request.json()
    now = time.monotonic()
    recent = [stamp for stamp in _memory_chat_times[user["id"]] if now - stamp < 900]
    if len(recent) >= 20:
        raise HTTPException(status_code=429, detail="Pause for a few minutes before asking again.")
    recent.append(now)
    _memory_chat_times[user["id"]] = recent
    try:
        async with _memory_chat_slots:
            message = await asyncio.to_thread(
                MemoryCompanionService().ask, user, str(data.get("question", ""))
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Reading memory companion failed")
        raise HTTPException(status_code=503, detail="The companion could not answer just now. Your reading memory is safe.") from exc
    return {"success": True, "message": message}


@router.get("/book/{book_id}", response_class=HTMLResponse)
async def book_detail(
    request: Request, book_id: str, preview_links: str | None = None,
    user=Depends(get_current_user_optional),
):
    include_drafts = preview_links == "1" and not settings.is_production
    book = readable_book(book_id, user) or CatalogService().get_book(book_id, include_drafts=include_drafts)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    book = canonicalize_book(book)
    other_editions = [
        edition for edition in CatalogService().get_books(include_drafts=include_drafts)
        if edition.get("work_id") == book.get("work_id") and edition["id"] != book_id
    ]
    service = UserService()
    progress = service.get_progress(user["id"], book_id) if user else None
    reading_status = service.get_reading_status(user["id"], book_id) if user else None
    shelf = header_counts(user, include_drafts=include_drafts)
    # A shelf click asks for the record alone and shows it in a dialog over the books;
    # a direct visit gets the same record inside the full page.
    partial = request.headers.get("x-partial") == "1"
    return templates.TemplateResponse(
        "partials/book_preview.html" if partial else "book_detail.html",
        {
            "request": request,
            "user": user,
            "book": book,
            "pdf_url": AssetService().browser_pdf_url(book) if book.get("availability") != "external_link" else None,
            "is_saved": service.is_book_saved(user["id"], book_id) if user else False,
            "progress": progress,
            "reading_status": reading_status,
            "highlights": service.get_highlights(user["id"], book_id) if user else [],
            "shelf": shelf,
            "total_books": shelf["total_books"],
            "source_url": book.get("source_url") if str(book.get("source_url", "")).startswith(("https://", "http://")) else None,
            "source_page": book.get("source_page") if str(book.get("source_page", "")).startswith(("https://", "http://")) else None,
            "original_url": book.get("original_url") if str(book.get("original_url", "")).startswith(("https://", "http://")) else None,
            "is_link": book.get("availability") == "external_link",
            "is_draft": book.get("visibility") == "draft",
            "preview_links": include_drafts,
            "other_editions": other_editions,
        },
    )


@router.post("/book/{book_id}/status")
async def set_book_status(
    book_id: str,
    status: str = Form(...),
    next: str = Form(""),
    user=Depends(get_current_user_required),
):
    if status not in {"want_to_read", "reading", "read"}:
        raise HTTPException(status_code=400, detail="Unknown status")
    if not readable_book(book_id, user):
        raise HTTPException(status_code=404, detail="Book not found")
    UserService().set_reading_status(user["id"], book_id, status)
    destination = "/library/my" if next == "/library/my" else f"/library/book/{book_id}"
    return RedirectResponse(destination, status_code=303)


@router.post("/save/{book_id}")
async def save_book(book_id: str, user=Depends(get_current_user_required)):
    if not readable_book(book_id, user):
        raise HTTPException(status_code=404, detail="Book not found")
    UserService().save_book(user["id"], book_id)
    return RedirectResponse(f"/library/book/{book_id}", status_code=303)


@router.post("/unsave/{book_id}")
async def unsave_book(book_id: str, user=Depends(get_current_user_required)):
    UserService().unsave_book(user["id"], book_id)
    return RedirectResponse(f"/library/book/{book_id}", status_code=303)
