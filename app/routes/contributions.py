"""Reader submissions stay private until Waleed reviews them.

Contributing lives inside Find books (/library/find#contribute). The old /library/contribute
page redirects there; its POST endpoints remain so saved forms, tests, and bookmarks keep working.
"""

from __future__ import annotations

import logging
import asyncio
import time
from collections import defaultdict
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from .. import templates
from ..config import settings
from ..services.finder_job_service import FinderJobService
from ..services.reading_desk import find_readings
from ..services.submission_service import SubmissionService
from .auth import get_current_user_optional, get_current_user_required

router = APIRouter()
logger = logging.getLogger(__name__)
_find_times: dict[str, list[float]] = defaultdict(list)
_find_slots = asyncio.Semaphore(2)

CONTRIBUTE_URL = "/library/find#contribute"


def finder_context(request: Request, user, **extra) -> dict:
    """Everything finder.html needs, so the contribute form can re-render inside it."""
    return {
        "request": request,
        "user": user,
        "source_finder_enabled": settings.SOURCE_FINDER_ENABLED,
        "jobs": FinderJobService().list_for_user(user["id"]) if user else [],
        "submissions": SubmissionService().for_user(user["id"]) if user else [],
        **extra,
    }


@router.get("/contribute")
async def contribute(submitted: str | None = None):
    destination = "/library/find?submitted=1#contribute" if submitted == "1" else CONTRIBUTE_URL
    return RedirectResponse(destination, status_code=303)


@router.post("/contribute", response_class=HTMLResponse)
async def create_contribution(
    request: Request,
    title: str = Form(""),
    author: str = Form(""),
    note: str = Form(""),
    links: str = Form(""),
    files: list[UploadFile] = File(default=[]),
    user=Depends(get_current_user_optional),
):
    if not user:
        return RedirectResponse(
            "/auth/register?" + urlencode({"next": CONTRIBUTE_URL}), status_code=303
        )
    try:
        await SubmissionService().create(
            user_id=user["id"], title=title, author=author, note=note,
            links=links, files=files or [],
        )
    except ValueError as exc:
        return templates.TemplateResponse(
            "finder.html",
            finder_context(request, user, contribute_error=str(exc), title=title, author=author, note=note, links=links),
            status_code=400,
        )
    except Exception:
        logger.exception("Book submission failed")
        return templates.TemplateResponse(
            "finder.html",
            finder_context(request, user, contribute_error="We could not save this submission. Please try again.",
                           title=title, author=author, note=note, links=links),
            status_code=503,
        )
    return RedirectResponse("/library/find?submitted=1#contribute", status_code=303)


@router.post("/contribute/find", response_class=JSONResponse)
async def find_source(request: Request, user=Depends(get_current_user_required)):
    if not settings.SOURCE_FINDER_ENABLED:
        raise HTTPException(status_code=503, detail="Source finding is not enabled on this deployment yet.")
    payload = await request.json()
    title = str(payload.get("title", "")).strip()[:160]
    author = str(payload.get("author", "")).strip()[:160]
    if len(title) < 2:
        raise HTTPException(status_code=400, detail="Enter a book title first.")
    now = time.monotonic()
    recent = [stamp for stamp in _find_times[user["id"]] if now - stamp < 900]
    if len(recent) >= 6:
        raise HTTPException(status_code=429, detail="Search limit reached. Please try again in a little while.")
    recent.append(now)
    _find_times[user["id"]] = recent
    try:
        async with _find_slots:
            results = await asyncio.wait_for(find_readings(title, author), timeout=55)
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="This search took too long. Please try again.") from exc
    except Exception as exc:
        logger.exception("Reader source search failed")
        raise HTTPException(status_code=503, detail="Source search is temporarily unavailable.") from exc
    return {"results": [
        {"title": row.get("title"), "url": row.get("final_url") or row.get("url"), "page_count": row.get("page_count"),
         "score": row.get("score"), "source_domain": row.get("domain"),
         "viewable": row.get("viewable"), "edition_fit": row.get("edition_fit")}
        for row in results if row.get("viewable") and str(row.get("url", "")).startswith(("https://", "http://"))
    ][:10]}
