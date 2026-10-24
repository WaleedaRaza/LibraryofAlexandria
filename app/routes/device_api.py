"""JSON API for reading devices (the Kindle plugin). Bearer tokens come from /device pairing."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from typing import Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.background import BackgroundTask

from ..config import settings
from ..services.asset_service import AssetService
from ..services.catalog_normalization import canonicalize_book
from ..services.catalog_service import CatalogService
from ..services.device_service import DeviceService
from ..services.reading_desk import _is_gated, _validate_public_url, find_readings
from ..services.session_service import SessionService
from ..services.source_service import readable_book
from ..services.submission_service import SubmissionService
from ..services.user_service import UserService

router = APIRouter()
logger = logging.getLogger(__name__)
_eye_times: dict[str, list[float]] = defaultdict(list)
_eye_slots = asyncio.Semaphore(2)
MAX_PROXY_BYTES = 200 * 1024 * 1024


def device_user(authorization: Optional[str] = Header(None)) -> dict:
    token = authorization.split(" ", 1)[1].strip() if authorization and authorization.lower().startswith("bearer ") else None
    user = SessionService().user(token) if token else None
    if not user:
        raise HTTPException(status_code=401, detail="Pair this device with your LibXNDR account")
    return user


def _public_book(book: dict, *, user_id: str | None = None, progress: dict | None = None, status: str | None = None) -> dict:
    book = canonicalize_book(book)
    item = {
        "id": book["id"],
        "title": book.get("title"),
        "author": book.get("author"),
        "domain": book.get("domain"),
        "availability": "link" if book.get("availability") == "external_link" else "pdf",
        "page_count": book.get("page_count"),
        "source_domain": book.get("source_domain"),
    }
    if progress:
        item["page_number"] = progress.get("page_number")
        item["percent"] = progress.get("percent")
    if status:
        item["reading_status"] = status
    return item


# Pairing (no auth) ------------------------------------------------------------

@router.post("/device/code", response_class=JSONResponse)
async def device_code(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    code = DeviceService().create_code(str(payload.get("device_name", "Kindle")))
    origin = settings.PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    return {**code, "claim_url": f"{origin}/device"}


@router.get("/device/poll", response_class=JSONResponse)
async def device_poll(code: str = "", secret: str = ""):
    return DeviceService().poll(code, secret)


# Reading (bearer token) -------------------------------------------------------

@router.get("/me", response_class=JSONResponse)
async def me(user=Depends(device_user)):
    service = UserService()
    statuses = service.get_shelf_statuses(user["id"])
    shown = {book_id: status for book_id, status in statuses.items()
             if not book_id.startswith("sub_") or status != "want_to_read"}
    return {
        "user": {"display_name": user["display_name"], "username": user.get("username")},
        "books": len(shown),
        "reading": sum(1 for value in shown.values() if value == "reading"),
        "collection": CatalogService().get_book_count(),
    }


@router.get("/search", response_class=JSONResponse)
async def search(q: str = "", limit: int = 24, user=Depends(device_user)):
    query = q.strip()[:160]
    if len(query) < 2:
        return {"query": query, "results": []}
    limit = max(1, min(limit, 60))
    seen: set[str] = set()
    results = []
    for book in CatalogService().get_books(search=query, limit=400):
        book = canonicalize_book(book)
        key = f"{(book.get('title') or '').casefold()}|{(book.get('author') or '').casefold()}"
        if key in seen:
            continue
        seen.add(key)
        results.append(_public_book(book))
        if len(results) >= limit:
            break
    return {"query": query, "results": results}


@router.get("/library", response_class=JSONResponse)
async def library(user=Depends(device_user)):
    """The reader's shelf for a device, built with a handful of queries rather than one per book.

    Submissions waiting in the review room also sit on their contributor's shelf. A device only shows
    them once they are actually being read, so a reviewer with hundreds of queued imports still gets
    a short, fast list.
    """
    service = UserService()
    statuses = service.get_shelf_statuses(user["id"])
    progress = {row["book_id"]: row for row in service.get_progress_for_user(user["id"])}
    catalog = {book["id"]: book for book in CatalogService().get_books(limit=100000)}
    wanted = [book_id for book_id in statuses
              if book_id in catalog or statuses[book_id] != "want_to_read" or book_id in progress]
    private_ids = [book_id for book_id in wanted if book_id not in catalog and book_id.startswith("sub_")]
    private = _private_sources(private_ids, user)
    books = []
    for book_id in wanted:
        item = catalog.get(book_id) or private.get(book_id)
        if item:
            books.append(_public_book(item, progress=progress.get(book_id), status=statuses[book_id]))
    order = {"reading": 0, "want_to_read": 1, "read": 2}
    books.sort(key=lambda item: (order.get(item.get("reading_status"), 3), (item.get("title") or "").casefold()))
    return {"books": books[:300], "total": len(books)}


def _private_sources(book_ids: list[str], user: dict) -> dict[str, dict]:
    """Resolve submission sources for many ids with one query."""
    import re
    from ..db.database import get_db, get_supabase, is_sqlite_mode
    from ..services.source_service import decode_submission, submission_sources

    submission_ids = sorted({match.group(1) for book_id in book_ids
                             if (match := re.fullmatch(r"(sub_[a-f0-9]{32})-(pdf|link)-(\d+)", book_id))})
    if not submission_ids:
        return {}
    if is_sqlite_mode():
        marks = ",".join("?" for _ in submission_ids)
        rows = [dict(row) for row in get_db().execute(f"SELECT * FROM book_submissions WHERE id IN ({marks})", submission_ids)]
    else:
        rows = get_supabase().table("book_submissions").select("*").in_("id", submission_ids).execute().data or []
    sources: dict[str, dict] = {}
    for row in rows:
        submission = decode_submission(row)
        if submission["user_id"] != user["id"] and user.get("role") != "admin":
            continue
        for source in submission_sources(submission):
            sources[source["id"]] = source
    return sources


@router.get("/books/{book_id}", response_class=JSONResponse)
async def book(book_id: str, user=Depends(device_user)):
    item = readable_book(book_id, user)
    if not item:
        raise HTTPException(status_code=404, detail="Book not found")
    service = UserService()
    return {"book": _public_book(item, progress=service.get_progress(user["id"], book_id),
                                 status=service.get_reading_status(user["id"], book_id))}


async def _close(response: httpx.Response, client: httpx.AsyncClient) -> None:
    await response.aclose()
    await client.aclose()


async def _stream_pdf(url: str, filename: str, *, headers: dict | None = None) -> StreamingResponse:
    client = httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(120, connect=15),
                               headers={"User-Agent": "LibXNDR-Device/1.0"})
    try:
        upstream = await client.send(client.build_request("GET", url, headers=headers or {}), stream=True)
    except Exception as exc:
        await client.aclose()
        raise HTTPException(status_code=503, detail="This PDF could not be fetched just now") from exc
    if upstream.status_code != 200:
        await upstream.aclose()
        await client.aclose()
        raise HTTPException(status_code=503, detail=f"The source answered {upstream.status_code}")
    length = upstream.headers.get("content-length")
    if length and length.isdigit() and int(length) > MAX_PROXY_BYTES:
        await upstream.aclose()
        await client.aclose()
        raise HTTPException(status_code=413, detail="This PDF is too large to send to a device")

    async def body():
        first = True
        sent = 0
        async for chunk in upstream.aiter_raw():
            if first:
                first = False
                if not chunk.lstrip().startswith(b"%PDF-"):
                    raise HTTPException(status_code=502, detail="The source did not return a PDF")
            sent += len(chunk)
            if sent > MAX_PROXY_BYTES:
                raise HTTPException(status_code=413, detail="This PDF is too large to send to a device")
            yield chunk

    forwarded = {"Content-Type": "application/pdf", "Content-Disposition": f'attachment; filename="{filename}"',
                 "Cache-Control": "private, no-store"}
    if length:
        forwarded["Content-Length"] = length
    return StreamingResponse(body(), headers=forwarded, background=BackgroundTask(_close, upstream, client))


@router.get("/books/{book_id}/file")
async def book_file(book_id: str, user=Depends(device_user)):
    item = readable_book(book_id, user)
    if not item:
        raise HTTPException(status_code=404, detail="Book not found")
    filename = f"{book_id}.pdf"
    if item.get("availability") == "external_link":
        source = item.get("source_url") or ""
        if not source.startswith(("https://", "http://")):
            raise HTTPException(status_code=404, detail="This book has no file to send")
        await _validate_public_url(source)
        return await _stream_pdf(source, filename)
    assets = AssetService()
    local = assets.local_pdf(item)
    if local:
        return FileResponse(local, media_type="application/pdf", filename=filename,
                            headers={"Cache-Control": "private, no-store"})
    try:
        signed_url = assets.signed_pdf_url(item)
    except Exception as exc:
        logger.warning("Device PDF lookup failed for %s (%s)", book_id, type(exc).__name__)
        signed_url = None
    if not signed_url:
        raise HTTPException(status_code=503, detail="This PDF has not been uploaded yet")
    return await _stream_pdf(signed_url, filename)


@router.post("/progress", response_class=JSONResponse)
async def progress(request: Request, user=Depends(device_user)):
    data = await request.json()
    book_id = str(data.get("book_id", ""))
    if not readable_book(book_id, user):
        raise HTTPException(status_code=404, detail="Book not found")
    try:
        page, count = int(data.get("page_number", 1)), int(data.get("page_count", 1))
        if not 1 <= page <= count <= 100000:
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Choose a valid page in this book")
    return {"progress": UserService().update_progress(user["id"], book_id, page, count)}


@router.post("/books/{book_id}/status", response_class=JSONResponse)
async def set_status(book_id: str, request: Request, user=Depends(device_user)):
    data = await request.json()
    status = str(data.get("status", ""))
    if status not in {"want_to_read", "reading", "read"}:
        raise HTTPException(status_code=400, detail="Unknown status")
    if not readable_book(book_id, user):
        raise HTTPException(status_code=404, detail="Book not found")
    UserService().set_reading_status(user["id"], book_id, status)
    return {"status": status}


# The Eye ----------------------------------------------------------------------

@router.post("/eye", response_class=JSONResponse)
async def eye(request: Request, user=Depends(device_user)):
    if not settings.SOURCE_FINDER_ENABLED:
        raise HTTPException(status_code=503, detail="The eye is turned off on this deployment")
    payload = await request.json()
    title = str(payload.get("title", "")).strip()[:160]
    author = str(payload.get("author", "")).strip()[:160]
    if len(title) < 2:
        raise HTTPException(status_code=400, detail="Enter a book title first")
    now = time.monotonic()
    recent = [stamp for stamp in _eye_times[user["id"]] if now - stamp < 900]
    if len(recent) >= 8:
        raise HTTPException(status_code=429, detail="Search limit reached. Try again in a little while")
    recent.append(now)
    _eye_times[user["id"]] = recent
    try:
        async with _eye_slots:
            rows = await asyncio.wait_for(find_readings(title, author), timeout=55)
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="That search took too long. Try it again") from exc
    except Exception as exc:
        logger.exception("Device eye search failed")
        raise HTTPException(status_code=503, detail="Search failed. Try again in a moment") from exc
    results = [
        {"title": row.get("title") or title, "url": row.get("final_url") or row.get("url"), "domain": row.get("domain"),
         "page_count": row.get("page_count"), "size_bytes": row.get("size_bytes"), "score": row.get("score")}
        for row in rows
        if row.get("viewable") and str(row.get("final_url") or row.get("url") or "").startswith(("https://", "http://"))
    ][:8]
    return {"title": title, "author": author, "results": results}


@router.get("/eye/fetch")
async def eye_fetch(url: str, user=Depends(device_user)):
    """Bring a PDF the eye found down to the device, through the server, with the same checks the finder uses."""
    if not url.startswith(("https://", "http://")):
        raise HTTPException(status_code=400, detail="Only web links can be fetched")
    host = (urlparse(url).hostname or "").casefold()
    if _is_gated(host):
        raise HTTPException(status_code=400, detail="That site does not serve the book itself")
    try:
        await _validate_public_url(url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    name = (urlparse(url).path.rsplit("/", 1)[-1] or "book.pdf")[:120]
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return await _stream_pdf(url, name)


@router.post("/contribute", response_class=JSONResponse)
async def contribute(request: Request, user=Depends(device_user)):
    data = await request.json()
    links = data.get("links") or []
    if isinstance(links, str):
        links = [links]
    try:
        record = await SubmissionService().create(
            user_id=user["id"], title=str(data.get("title", "")), author=str(data.get("author", "")),
            note=str(data.get("note", "Sent from a Kindle with the Eye."))[:800],
            links="\n".join(str(link) for link in links), files=[],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"submission_id": record["id"], "status": "pending"}
