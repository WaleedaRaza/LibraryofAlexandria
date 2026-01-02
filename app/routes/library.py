"""
Alexandria Library - Library Routes
Browse the canon and manage personal library.
"""

from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from .. import templates
from ..services.canon_service import CanonService
from ..services.user_service import UserService
from .auth import get_current_user_optional, get_current_user_required

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def browse_library(
    request: Request,
    domain: str = None,
    search: str = None,
    user=Depends(get_current_user_optional)
):
    """
    Browse the public library.
    Filter by domain or search.
    """
    canon = CanonService()
    
    # Get all public books (with optional filters)
    books = canon.get_books(domain=domain, search=search)
    
    # Get available domains for filter
    domains = canon.get_domains()
    
    # Get user's saved book IDs for showing saved indicators
    saved_book_ids = set()
    if user:
        user_service = UserService()
        saved_books = user_service.get_saved_books(user["id"])
        saved_book_ids = {b["id"] for b in saved_books}
    
    return templates.TemplateResponse(
        "library.html",
        {
            "request": request,
            "user": user,
            "books": books,
            "domains": domains,
            "current_domain": domain,
            "search": search,
            "saved_book_ids": saved_book_ids,
        }
    )


@router.get("/book/{book_id}", response_class=HTMLResponse)
async def book_detail(
    request: Request,
    book_id: str,
    user=Depends(get_current_user_optional)
):
    """Book detail page - info + link to reader."""
    canon = CanonService()
    
    book = canon.get_book(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    
    chapters = canon.get_chapters(book_id)
    
    # Check if user has saved this book
    is_saved = False
    if user:
        user_service = UserService()
        is_saved = user_service.is_book_saved(user["id"], book_id)
    
    return templates.TemplateResponse(
        "book_detail.html",
        {
            "request": request,
            "user": user,
            "book": book,
            "chapters": chapters,
            "is_saved": is_saved,
        }
    )


@router.get("/my", response_class=HTMLResponse)
async def my_library(
    request: Request,
    user=Depends(get_current_user_required)
):
    """Personal library - saved books."""
    user_service = UserService()
    
    saved_books = user_service.get_saved_books(user["id"])
    
    return templates.TemplateResponse(
        "my_library.html",
        {
            "request": request,
            "user": user,
            "books": saved_books,
        }
    )


@router.post("/save/{book_id}")
async def save_book(
    request: Request,
    book_id: str,
    user=Depends(get_current_user_required)
):
    """Save a book to personal library."""
    user_service = UserService()
    user_service.save_book(user["id"], book_id)
    
    return RedirectResponse(
        url=f"/library/book/{book_id}",
        status_code=303
    )


@router.post("/unsave/{book_id}")
async def unsave_book(
    request: Request,
    book_id: str,
    user=Depends(get_current_user_required)
):
    """Remove a book from personal library."""
    user_service = UserService()
    user_service.unsave_book(user["id"], book_id)
    
    return RedirectResponse(
        url=f"/library/book/{book_id}",
        status_code=303
    )

