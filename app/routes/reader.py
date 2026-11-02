"""Authenticated PDF reader and passage-level reading tools."""

import asyncio
import logging
import time
from collections import defaultdict

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from starlette.background import BackgroundTask

from .. import templates
from ..agents import passage_companion
from ..agents.passage_companion import MAX_PAGE_TEXT, PassageContext
from ..services.asset_service import AssetService
from ..services.catalog_service import CatalogService
from ..services.chat_service import ChatService
from ..services.user_service import UserService
from ..services.source_service import readable_book
from .auth import get_current_user_optional, get_current_user_required

router = APIRouter()
logger = logging.getLogger(__name__)
_passage_chat_times: dict[str, list[float]] = defaultdict(list)
_passage_chat_slots = asyncio.Semaphore(3)


@router.get("/{book_id}", response_class=HTMLResponse)
async def read_book(request: Request, book_id: str, user=Depends(get_current_user_optional)):
    book = readable_book(book_id, user)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    if book.get("availability") == "external_link":
        return RedirectResponse(f"/library/book/{book_id}", status_code=303)
    if not user:
        # Reading is for members. Visitors see the preview and a sign-in prompt instead.
        return RedirectResponse(f"/auth/login?next=/read/{book_id}", status_code=303)
    service = UserService()
    service.save_book(user["id"], book_id)
    highlights = service.get_highlights(user["id"], book_id) if user else []
    for highlight in highlights:
        highlight["messages"] = ChatService().get_messages(highlight["id"])
    return templates.TemplateResponse(
        "reader.html",
        {
            "request": request,
            "user": user,
            "book": book,
            "pdf_url": AssetService().browser_pdf_url(book),
            "progress": (service.get_progress(user["id"], book_id) if user else None) or {"page_number": 1, "percent": 0},
            "highlights": highlights,
        },
    )


async def _close_pdf_proxy(response: httpx.Response, client: httpx.AsyncClient) -> None:
    await response.aclose()
    await client.aclose()


@router.get("/{book_id}/pdf")
async def pdf_asset(request: Request, book_id: str, user=Depends(get_current_user_required)):
    book = readable_book(book_id, user)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    if book.get("availability") == "external_link":
        raise HTTPException(status_code=404, detail="This is a source link, not a hosted PDF")
    assets = AssetService()
    local = assets.local_pdf(book)
    if local:
        return FileResponse(local, media_type="application/pdf", filename=f"{book['title']}.pdf",
                            content_disposition_type="inline", headers={"Cache-Control": "private, no-store"})
    try:
        signed_url = assets.signed_pdf_url(book)
    except Exception as exc:
        logger.warning("PDF asset lookup failed for %s (%s)", book_id, type(exc).__name__)
        signed_url = None
    if signed_url:
        # Keep the browser on LibXNDR while it negotiates byte ranges. PDF.js
        # and iOS Safari otherwise follow a cross-origin storage redirect whose
        # CORS/range behaviour varies by device and often surfaces as a vague
        # "PDF not available" error even when the object exists.
        range_header = request.headers.get("range")
        upstream_headers = {"Range": range_header} if range_header else {}
        client = httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(65, connect=15))
        try:
            upstream = await client.send(
                client.build_request("GET", signed_url, headers=upstream_headers), stream=True
            )
        except Exception as exc:
            await client.aclose()
            logger.warning("PDF proxy connection failed for %s (%s)", book_id, type(exc).__name__)
            raise HTTPException(status_code=503, detail="This PDF could not be opened just now") from exc
        if upstream.status_code not in {200, 206}:
            status_code = upstream.status_code
            await upstream.aclose()
            await client.aclose()
            logger.warning("PDF proxy returned %s for %s", status_code, book_id)
            raise HTTPException(status_code=503, detail="This PDF could not be opened just now")
        forwarded = {
            "Content-Type": upstream.headers.get("content-type", "application/pdf"),
            "Content-Disposition": f'inline; filename="{book_id}.pdf"',
            "Accept-Ranges": upstream.headers.get("accept-ranges", "bytes"),
            "Cache-Control": "private, no-store",
        }
        for name in ("content-length", "content-range", "etag", "last-modified"):
            if upstream.headers.get(name):
                forwarded[name.title()] = upstream.headers[name]
        return StreamingResponse(
            upstream.aiter_raw(),
            status_code=upstream.status_code,
            headers=forwarded,
            background=BackgroundTask(_close_pdf_proxy, upstream, client),
        )
    raise HTTPException(status_code=503, detail="This PDF has not been uploaded yet")


@router.post("/{book_id}/progress", response_class=JSONResponse)
async def update_progress(request: Request, book_id: str, user=Depends(get_current_user_required)):
    if not readable_book(book_id, user):
        raise HTTPException(status_code=404, detail="Book not found")
    data = await request.json()
    try:
        page, count = int(data.get("page_number", 1)), int(data.get("page_count", 1))
        if not 1 <= page <= count <= 100000:
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Choose a valid page in this book")
    record = UserService().update_progress(
        user["id"], book_id, page, count
    )
    return {"success": True, "progress": record}


@router.post("/{book_id}/highlights", response_class=JSONResponse)
async def create_highlight(request: Request, book_id: str, user=Depends(get_current_user_required)):
    if not readable_book(book_id, user):
        raise HTTPException(status_code=404, detail="Book not found")
    data = await request.json()
    selected_text = str(data.get("selected_text", "")).strip()
    if not selected_text or len(selected_text) > 20000:
        raise HTTPException(status_code=400, detail="Select between 1 and 20,000 characters to highlight")
    try:
        page = int(data.get("page_number", 1))
        start, end = data.get("text_start"), data.get("text_end")
        if not 1 <= page <= 100000:
            raise ValueError()
        if start is not None or end is not None:
            start, end = int(start), int(end)
            if not 0 <= start <= end <= 10000000:
                raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Choose a valid page and text selection")
    highlight = UserService().create_highlight(
        user["id"],
        book_id,
        page,
        selected_text,
        str(data.get("color", "gold")),
        start,
        end,
    )
    return {"success": True, "highlight": highlight}


@router.post("/{book_id}/highlights/{highlight_id}/note", response_class=JSONResponse)
async def save_note(
    request: Request,
    book_id: str,
    highlight_id: str,
    user=Depends(get_current_user_required),
):
    highlight = UserService().get_highlight(user["id"], highlight_id)
    if not highlight or highlight["book_id"] != book_id:
        raise HTTPException(status_code=404, detail="Passage not found")
    data = await request.json()
    text = str(data.get("text", ""))
    if len(text) > 20_000:
        raise HTTPException(status_code=400, detail="Keep a private note under 20,000 characters")
    try:
        note = UserService().save_note(user["id"], highlight_id, text)
    except PermissionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"success": True, "note": note}


@router.delete("/{book_id}/highlights/{highlight_id}", response_class=JSONResponse)
async def delete_highlight(book_id: str, highlight_id: str, user=Depends(get_current_user_required)):
    highlight = UserService().get_highlight(user["id"], highlight_id)
    if not highlight or highlight["book_id"] != book_id:
        raise HTTPException(status_code=404, detail="Passage not found")
    deleted = UserService().delete_highlight(highlight_id, user["id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Highlight not found")
    return {"success": True}


@router.post("/{book_id}/highlights/{highlight_id}/chat", response_class=JSONResponse)
async def passage_chat(
    request: Request,
    book_id: str,
    highlight_id: str,
    user=Depends(get_current_user_required),
):
    service = UserService()
    highlight = service.get_highlight(user["id"], highlight_id)
    book = readable_book(book_id, user)
    if not highlight or highlight["book_id"] != book_id or not book:
        raise HTTPException(status_code=404, detail="Passage not found")
    data = await request.json()
    question = str(data.get("question", "")).strip()
    if not 2 <= len(question) <= 2_000:
        raise HTTPException(status_code=400, detail="Ask a question between 2 and 2,000 characters")
    now = time.monotonic()
    recent = [stamp for stamp in _passage_chat_times[user["id"]] if now - stamp < 900]
    if len(recent) >= 20:
        raise HTTPException(status_code=429, detail="Pause for a few minutes before asking again.")
    recent.append(now)
    _passage_chat_times[user["id"]] = recent
    page_text = data.get("page_text") or ""
    if not isinstance(page_text, str):
        page_text = ""
    chat = ChatService()
    history = chat.get_messages(highlight_id)
    others = [
        item for item in service.get_highlights(user["id"], book_id)
        if item["id"] != highlight_id
    ]
    others.sort(key=lambda item: abs(int(item["page_number"]) - int(highlight["page_number"])))
    board = [
        book_row for book_row in service.get_saved_books(user["id"])
        if book_row.get("reading_status") in {"reading", "read"} and book_row.get("id") != book_id
    ]
    context = PassageContext(
        book_title=book["title"],
        book_author=book.get("author") or "",
        passage=highlight["selected_text"],
        page_number=int(highlight["page_number"]),
        page_text=page_text[:MAX_PAGE_TEXT],
        note=highlight.get("note") or "",
        other_passages=others,
        board=board,
        history=history,
    )
    chat.add_message(highlight_id, "user", question)
    try:
        async with _passage_chat_slots:
            explanation = await asyncio.to_thread(passage_companion.answer, context, question)
    except Exception as exc:
        logger.exception("Passage companion failed")
        raise HTTPException(
            status_code=503,
            detail="The companion could not answer just now. Your passage and note are safe.",
        ) from exc
    assistant_message = chat.add_message(highlight_id, "assistant", explanation)
    return {"success": True, "message": assistant_message, "messages": chat.get_messages(highlight_id)}
