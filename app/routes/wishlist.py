"""
Alexandria Library - Wishlist Routes
Book requests - the growth loop.
"""

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from .. import templates
from ..services.request_service import RequestService
from .auth import get_current_user_required

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def view_wishlist(
    request: Request,
    user=Depends(get_current_user_required)
):
    """View user's book requests."""
    request_service = RequestService()
    
    requests = request_service.get_user_requests(user["id"])
    
    return templates.TemplateResponse(
        "wishlist.html",
        {
            "request": request,
            "user": user,
            "book_requests": requests,
        }
    )


@router.post("/request")
async def request_book(
    request: Request,
    title: str = Form(...),
    author: str = Form(None),
    reason: str = Form(None),
    user=Depends(get_current_user_required)
):
    """Submit a book request."""
    request_service = RequestService()
    
    request_service.create_request(
        user_id=user["id"],
        title=title,
        author=author,
        reason=reason
    )
    
    return RedirectResponse(url="/wishlist", status_code=303)


@router.post("/cancel/{request_id}")
async def cancel_request(
    request: Request,
    request_id: str,
    user=Depends(get_current_user_required)
):
    """Cancel a pending book request."""
    request_service = RequestService()
    
    # Only allow canceling own requests
    request_service.cancel_request(request_id, user["id"])
    
    return RedirectResponse(url="/wishlist", status_code=303)

