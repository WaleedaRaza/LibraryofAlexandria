"""First run (/welcome) and "ask this book" (a question answered with a passage and its page)."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from .. import templates
from ..config import settings
from ..services import onboarding
from ..services.book_search import BookTextUnavailable, ask_book, open_url
from ..services.source_service import readable_book
from .auth import get_current_user_optional, get_current_user_required

router = APIRouter()
logger = logging.getLogger(__name__)
_ask_times: dict[str, list[float]] = defaultdict(list)
COOKIE_AGE = 60 * 60 * 24 * 365


def _cookie(response, name: str, value: str) -> None:
    response.set_cookie(name, value, max_age=COOKIE_AGE, httponly=True, samesite="lax",
                        secure=settings.is_production)


@router.get("/welcome", response_class=HTMLResponse)
async def welcome(request: Request, user=Depends(get_current_user_optional)):
    if not user:
        return RedirectResponse("/auth/register?next=/welcome", status_code=303)
    steps = onboarding.first_steps(user, request.cookies.get(onboarding.STEPS_COOKIE))
    response = templates.TemplateResponse("welcome.html", {
        "request": request,
        "user": user,
        "doors": onboarding.doors(),
        "first_steps": steps,
        "finder_enabled": settings.SOURCE_FINDER_ENABLED,
    })
    # Seen once is enough: the reading board stops sending this reader here.
    _cookie(response, onboarding.WELCOMED_COOKIE, "1")
    return response


@router.post("/welcome/shelf", response_class=JSONResponse)
async def welcome_shelf(request: Request, user=Depends(get_current_user_required)):
    payload = await request.json()
    ids = payload.get("book_ids") if isinstance(payload, dict) else None
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        raise HTTPException(status_code=400, detail="Choose at least one book.")
    saved = onboarding.save_starter_shelf(user["id"], ids)
    if not saved:
        raise HTTPException(status_code=400, detail="Choose at least one book.")
    return {"saved": saved}


@router.post("/welcome/eye-tried", response_class=JSONResponse)
async def welcome_eye_tried(request: Request, user=Depends(get_current_user_required)):
    response = JSONResponse({"ok": True})
    _cookie(response, onboarding.STEPS_COOKIE,
            onboarding.with_flag(request.cookies.get(onboarding.STEPS_COOKIE), "eye"))
    return response


@router.post("/library/book/{book_id}/ask", response_class=JSONResponse)
async def ask_this_book(request: Request, book_id: str, user=Depends(get_current_user_optional)):
    """Answer with a passage from this book and the page it is on. Open to visitors: it is the best preview we have."""
    book = readable_book(book_id, user)
    if not book or book.get("availability") == "external_link":
        raise HTTPException(status_code=404, detail="This book can't be searched here.")
    try:
        payload = await request.json()
    except ValueError:
        payload = {}
    question = str((payload or {}).get("question", "")).strip()[:300]
    if len(question) < 4:
        raise HTTPException(status_code=400, detail="Ask a full question.")

    identity = user["id"] if user else f"guest:{request.client.host if request.client else 'unknown'}"
    now = time.monotonic()
    recent = [stamp for stamp in _ask_times[identity] if now - stamp < 600]
    if len(recent) >= (20 if user else 5):
        raise HTTPException(status_code=429, detail="That's a lot of questions at once. Try again in a few minutes.")
    _ask_times[identity] = [*recent, now]

    try:
        result = await ask_book(book, question)
    except BookTextUnavailable as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Asking %s failed", book_id)
        raise HTTPException(status_code=503, detail="The book couldn't be searched just now.") from exc
    if not result:
        raise HTTPException(status_code=404, detail="Nothing in this book matches that. Try different words.")

    target = open_url(book["id"], result.page, result.quote)
    body = {
        "book": {"id": book["id"], "title": book.get("title"), "author": book.get("author")},
        "question": question,
        "page": result.page,
        "quote": result.quote,
        "answer": result.answer,
        "open_url": target if user else f"/auth/register?next={quote(target, safe='/')}",
        "signed_in": bool(user),
        "alternates": [
            {**alt, "open_url": open_url(book["id"], alt["page"], alt["quote"])} for alt in result.alternates
        ] if user else [],
    }
    response = JSONResponse(body)
    if user:
        _cookie(response, onboarding.STEPS_COOKIE,
                onboarding.with_flag(request.cookies.get(onboarding.STEPS_COOKIE), "asked"))
    return response


@router.get("/welcome/lookup", response_class=JSONResponse)
async def welcome_lookup(q: str = "", user=Depends(get_current_user_required)):
    """Is this book already in the collection? Checked before the eye goes out to the web."""
    from ..services.catalog_service import CatalogService

    q = " ".join(q.split())[:120]
    if len(q) < 2:
        return {"matches": []}
    books = CatalogService().get_books(search=q, limit=4)
    return {"matches": [
        {"id": b["id"], "title": b.get("title"), "author": b.get("author"), "href": f"/library/book/{b['id']}"}
        for b in books if b.get("availability") != "external_link"
    ][:3]}
