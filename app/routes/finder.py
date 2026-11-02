"""Signed-in, durable one-or-many book source finder."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from .. import templates
from ..config import settings
from ..services.finder_job_service import FinderJobService
from ..services.reading_desk import find_readings, parse_books
from ..services.submission_service import SubmissionService
from .auth import get_current_user_optional, get_current_user_required

router = APIRouter()
logger = logging.getLogger(__name__)
_quick_find_times: dict[str, list[float]] = defaultdict(list)
_quick_find_slots = asyncio.Semaphore(2)


@router.get("", response_class=HTMLResponse)
async def finder_home(request: Request, submitted: str = "", title: str = "", author: str = "",
                      user=Depends(get_current_user_optional)):
    from .contributions import finder_context

    return templates.TemplateResponse("finder.html", finder_context(
        request, user, submitted=submitted == "1", title=title.strip()[:160], author=author.strip()[:160]))


@router.post("/quick", response_class=JSONResponse)
async def quick_find(request: Request, user=Depends(get_current_user_required)):
    """One title, searched on the open web. Signed-in readers only; the eye is not a public tool."""
    if not settings.SOURCE_FINDER_ENABLED:
        raise HTTPException(status_code=503, detail="The source finder is temporarily unavailable.")
    payload = await request.json()
    title = str(payload.get("title", "")).strip()[:160]
    author = str(payload.get("author", "")).strip()[:160]
    if len(title) < 2:
        raise HTTPException(status_code=400, detail="Enter a book title first.")
    identity = user["id"] if user else f"guest:{request.client.host if request.client else 'unknown'}"
    now = time.monotonic()
    recent = [stamp for stamp in _quick_find_times[identity] if now - stamp < 900]
    limit = 8 if user else 4
    if len(recent) >= limit:
        raise HTTPException(status_code=429, detail="Search limit reached. Try again in a little while.")
    recent.append(now)
    _quick_find_times[identity] = recent
    try:
        async with _quick_find_slots:
            rows = await asyncio.wait_for(find_readings(title, author), timeout=55)
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="That search took too long. Try it again.") from exc
    except Exception as exc:
        logger.exception("Quick source search failed")
        raise HTTPException(status_code=503, detail="The source finder could not search just now.") from exc
    results = [
        {
            "title": row.get("title") or title,
            "url": row.get("final_url") or row.get("url"),
            "page_count": row.get("page_count"),
            "size_bytes": row.get("size_bytes"),
            "score": row.get("score"),
            "domain": row.get("domain"),
            "edition_fit": row.get("edition_fit"),
            "reasons": row.get("reasons") or [],
        }
        for row in rows
        if row.get("viewable") and str(row.get("final_url") or row.get("url") or "").startswith(("https://", "http://"))
    ][:8]
    return {"title": title, "author": author, "results": results}


@router.post("")
async def create_job(request: Request, books: str = Form(""), user=Depends(get_current_user_required)):
    from .contributions import finder_context

    if not settings.SOURCE_FINDER_ENABLED:
        raise HTTPException(status_code=503, detail="Source finding is temporarily unavailable.")
    parsed = parse_books(books)
    if not parsed:
        return templates.TemplateResponse("finder.html", finder_context(request, user, books=books,
            error="Enter at least one book title."), status_code=400)
    try:
        job_id = FinderJobService().create(user["id"], parsed)
    except ValueError as exc:
        return templates.TemplateResponse("finder.html", finder_context(request, user, books=books, error=str(exc)), status_code=400)
    except Exception:
        logger.exception("Finder job creation failed")
        return templates.TemplateResponse("finder.html", finder_context(request, user, books=books,
            error="This search could not be started. Please try again."), status_code=503)
    return RedirectResponse(f"/library/find/{job_id}", status_code=303)


@router.get("/runs", response_class=HTMLResponse)
async def finder_runs(request: Request, user=Depends(get_current_user_optional)):
    if not user:
        return RedirectResponse("/auth/login?next=/library/find/runs", status_code=303)
    return templates.TemplateResponse("finder_runs.html", {"request": request, "user": user,
        "jobs": FinderJobService().list_for_user(user["id"])})


@router.get("/{job_id}", response_class=HTMLResponse)
async def finder_job(request: Request, job_id: str, saved: str = "", error: str = "",
                     user=Depends(get_current_user_required)):
    job = FinderJobService().get(job_id, user["id"])
    if not job:
        raise HTTPException(status_code=404, detail="Finder job not found")
    return templates.TemplateResponse("finder_job.html", {"request": request, "user": user,
        "job": job, "saved": saved == "1", "error": error[:180]})


@router.post("/{job_id}/next", response_class=JSONResponse)
async def work_next(job_id: str, user=Depends(get_current_user_required)):
    if not settings.SOURCE_FINDER_ENABLED:
        raise HTTPException(status_code=503, detail="Source finding is temporarily unavailable.")
    job = await FinderJobService().work_next(job_id, user["id"])
    if not job:
        raise HTTPException(status_code=404, detail="Finder job not found")
    return {"status": job["status"], "completed": job["completed"], "total": job["total"]}


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str, user=Depends(get_current_user_required)):
    if not FinderJobService().cancel(job_id, user["id"]):
        raise HTTPException(status_code=404, detail="Active finder job not found")
    return RedirectResponse(f"/library/find/{job_id}", status_code=303)


@router.post("/{job_id}/save")
async def save_results(job_id: str, item_id: str = Form(...), urls: list[str] = Form(default=[]),
                       credit_mode: str = Form("credited"),
                       user=Depends(get_current_user_required)):
    try:
        item, selected = FinderJobService().candidate_urls(job_id, item_id, user["id"], urls)
        credit = "anonymous" if credit_mode == "anonymous" else f"credited to {user['display_name']}"
        await SubmissionService().create(user_id=user["id"], title=item["title"], author=item["author"],
                                         note=f"Found with the LibXNDR source finder. Publication credit: {credit}.",
                                         links="\n".join(selected), files=[])
    except ValueError as exc:
        return RedirectResponse(f"/library/find/{job_id}?error={str(exc)}", status_code=303)
    except Exception:
        logger.exception("Finder result save failed")
        return RedirectResponse(f"/library/find/{job_id}?error=Those+links+could+not+be+saved.", status_code=303)
    return RedirectResponse(f"/library/find/{job_id}?saved=1", status_code=303)
