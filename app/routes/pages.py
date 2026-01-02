"""
Alexandria Library - Page Routes
Renders HTML pages. No business logic here.
"""

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse

from .. import templates
from ..services.canon_service import CanonService
from ..services.user_service import UserService
from .auth import get_current_user_optional

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, user=Depends(get_current_user_optional)):
    """
    Landing page with the Ask prompt and book previews.
    This is the spine of the app.
    """
    canon = CanonService()
    
    # Get featured books (limit to 12 for preview)
    books = canon.get_books(limit=12)
    
    # Get total count for display
    total_books = canon.get_book_count()
    
    # Get domains for filtering
    domains = canon.get_domains()
    
    # Get user's saved book IDs for showing saved indicators
    saved_book_ids = set()
    if user:
        user_service = UserService()
        saved_books = user_service.get_saved_books(user["id"])
        saved_book_ids = {b["id"] for b in saved_books}
    
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "user": user,
            "books": books,
            "total_books": total_books,
            "domains": domains,
            "saved_book_ids": saved_book_ids,
        }
    )


@router.get("/about", response_class=HTMLResponse)
async def about(request: Request, user=Depends(get_current_user_optional)):
    """About page - what this is and isn't."""
    return templates.TemplateResponse(
        "about.html",
        {
            "request": request,
            "user": user,
        }
    )

