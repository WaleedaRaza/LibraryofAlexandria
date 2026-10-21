"""Source-focused review room. Never exposes another reader's annotations."""

import logging

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .. import templates
from ..services.review_service import ReviewService
from .auth import get_current_user_required

router = APIRouter()
logger = logging.getLogger(__name__)


def reviewer_required(user=Depends(get_current_user_required)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="This room is for library reviewers")
    return user


@router.get("", response_class=HTMLResponse)
async def review_inbox(request: Request, status: str = "pending", user=Depends(reviewer_required)):
    if status not in {"pending", "approved", "declined", "all"}:
        status = "pending"
    all_submissions = ReviewService().inbox("all")
    counts = {
        "all": len(all_submissions),
        "pending": sum(item["status"] == "pending" for item in all_submissions),
        "approved": sum(item["status"] == "approved" for item in all_submissions),
        "declined": sum(item["status"] == "declined" for item in all_submissions),
    }
    return templates.TemplateResponse("review/inbox.html", {"request": request, "user": user,
        "submissions": all_submissions if status == "all" else [item for item in all_submissions if item["status"] == status],
        "status": status, "counts": counts})


@router.get("/{submission_id}", response_class=HTMLResponse)
async def review_detail(request: Request, submission_id: str, error: str = "", user=Depends(reviewer_required)):
    submission = ReviewService().get(submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    return templates.TemplateResponse("review/detail.html", {"request": request, "user": user, "submission": submission,
                                                             "error": error[:160] or None})


@router.post("/{submission_id}/decision", response_class=HTMLResponse)
async def review_decision(request: Request, submission_id: str, decision: str = Form(""),
                          title: str = Form(""), author: str = Form(""), note: str = Form(""),
                          source_ids: list[str] = Form(default=[]), user=Depends(reviewer_required)):
    try:
        ReviewService().decide(submission_id, user, decision=decision, title=title, author=author,
                               note=note, source_ids=source_ids)
    except ValueError as exc:
        submission = ReviewService().get(submission_id)
        if not submission:
            raise HTTPException(status_code=404, detail="Submission not found")
        return templates.TemplateResponse("review/detail.html", {"request": request, "user": user,
            "submission": submission, "error": str(exc), "form_title": title, "form_author": author,
            "form_note": note, "selected_ids": source_ids}, status_code=400)
    except Exception:
        logger.exception("Review decision failed")
        raise HTTPException(status_code=503, detail="The review could not be saved. Reload this submission before trying again.")
    return RedirectResponse(f"/review/{submission_id}", status_code=303)


@router.post("/{submission_id}/quick")
async def review_quick(submission_id: str, decision: str = Form(""), status: str = Form("pending"),
                       user=Depends(reviewer_required)):
    """Approve every source as submitted, or decline, straight from the list.

    The full form stays available for anything that needs its title or author fixed first.
    """
    submission = ReviewService().get(submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    try:
        if decision == "approved":
            ReviewService().decide(submission_id, user, decision="approved", title=submission["title"],
                                   author=submission["author"] or "Unknown author",
                                   note="Approved from the review list with every submitted source, as catalogued by the contributor.",
                                   source_ids=[source["id"] for source in submission["sources"]])
        elif decision == "declined":
            ReviewService().decide(submission_id, user, decision="declined", title=submission["title"],
                                   author=submission["author"] or "Unknown author",
                                   note="Declined from the review list.", source_ids=[])
        else:
            raise ValueError("Choose a decision.")
    except ValueError as exc:
        return RedirectResponse(f"/review/{submission_id}?error={str(exc)[:160]}", status_code=303)
    except Exception:
        logger.exception("Quick review failed")
        raise HTTPException(status_code=503, detail="The review could not be saved. Reload before trying again.")
    return RedirectResponse(f"/review?status={status}", status_code=303)
