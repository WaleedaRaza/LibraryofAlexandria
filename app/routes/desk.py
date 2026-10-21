"""Local PDF discovery desk. Not linked publicly and disabled in production."""

import json

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from .. import templates
from ..config import settings
from ..services.reading_desk import get_job, parse_books, start_search, stop_job

router = APIRouter()


def _local_only() -> None:
    if settings.is_production:
        raise HTTPException(status_code=404, detail="Not found")


@router.get("/desk", response_class=HTMLResponse)
async def reading_desk(request: Request):
    _local_only()
    return templates.TemplateResponse(
        "desk.html",
        {
            "request": request,
            "user": None,
        },
    )


@router.get("/desk/lists/essential-50")
async def essential_fifty():
    _local_only()
    path = settings.BASE_DIR / "library" / "reading_lists" / "essential_50.json"
    return JSONResponse(json.loads(path.read_text(encoding="utf-8")))


@router.get("/desk/lists/launch-72")
async def launch_seventy_two():
    _local_only()
    path = settings.BASE_DIR / "library" / "reading_lists" / "launch_72.json"
    return JSONResponse(json.loads(path.read_text(encoding="utf-8")))


@router.get("/desk/lists/launch-72/results")
async def launch_seventy_two_results():
    _local_only()
    path = settings.BASE_DIR / "data" / "launch_72_sourcing.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="No sourcing run yet")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["status"] = "complete" if payload["completed"] == payload["total"] else "running"
    payload["current"] = None
    return JSONResponse(payload)


@router.post("/desk/search")
async def search_reading_list(books: str = Form("")):
    _local_only()
    parsed = parse_books(books)
    if not parsed:
        raise HTTPException(status_code=422, detail="Enter at least one title")
    job_id = start_search(parsed)
    return JSONResponse({"job_id": job_id, "total": len(parsed)})


@router.get("/desk/jobs/{job_id}")
async def reading_list_status(job_id: str):
    _local_only()
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Search job not found")
    return JSONResponse(job)


@router.post("/desk/jobs/{job_id}/stop")
async def stop_reading_list(job_id: str):
    _local_only()
    return JSONResponse({"stopped": stop_job(job_id)})
