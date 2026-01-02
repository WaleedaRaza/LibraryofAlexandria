"""
Alexandria Library - Admin Routes
Request management and book operations.
"""

from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from .. import templates
from ..services.request_service import RequestService
from .auth import get_current_user_optional

router = APIRouter()


def require_admin(user=Depends(get_current_user_optional)):
    """Require admin role for access."""
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@router.get("/requests", response_class=HTMLResponse)
async def list_requests(
    request: Request,
    status: str = None,
    user=Depends(require_admin)
):
    """View all book requests."""
    service = RequestService()
    
    if status and status != "all":
        requests = service.get_requests_by_status(status.upper())
    else:
        requests = service.get_all_requests()
    
    # Count by status
    counts = {
        "all": len(service.get_all_requests()),
        "pending": len(service.get_requests_by_status("PENDING")),
        "approved": len(service.get_requests_by_status("APPROVED")),
        "rejected": len(service.get_requests_by_status("REJECTED")),
        "added": len(service.get_requests_by_status("ADDED")),
    }
    
    return templates.TemplateResponse(
        "admin/requests.html",
        {
            "request": request,
            "user": user,
            "requests": requests,
            "current_status": status or "all",
            "counts": counts,
        }
    )


@router.get("/requests/{request_id}", response_class=HTMLResponse)
async def request_detail(
    request: Request,
    request_id: str,
    user=Depends(require_admin)
):
    """View single request detail."""
    service = RequestService()
    req = service.get_request(request_id)
    
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    
    return templates.TemplateResponse(
        "admin/request_detail.html",
        {
            "request": request,
            "user": user,
            "req": req,
        }
    )


@router.post("/requests/{request_id}/approve")
async def approve_request(
    request_id: str,
    admin_notes: str = Form(""),
    user=Depends(require_admin)
):
    """Approve a book request."""
    service = RequestService()
    service.approve_request(request_id, admin_notes or None)
    return RedirectResponse(url="/admin/requests", status_code=303)


@router.post("/requests/{request_id}/reject")
async def reject_request(
    request_id: str,
    admin_notes: str = Form(...),
    user=Depends(require_admin)
):
    """Reject a book request (note required)."""
    service = RequestService()
    service.reject_request(request_id, admin_notes)
    return RedirectResponse(url="/admin/requests", status_code=303)


@router.post("/requests/{request_id}/mark-added")
async def mark_added(
    request_id: str,
    user=Depends(require_admin)
):
    """Mark request as added to library."""
    service = RequestService()
    service.mark_added(request_id)
    return RedirectResponse(url="/admin/requests", status_code=303)
