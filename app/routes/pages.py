"""Public pages for Waleed's Library."""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .. import templates
from ..config import settings
from ..services.catalog_service import CatalogService
from .auth import get_current_user_optional
from .library import render_shelf

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    domain: str | None = None,
    search: str | None = None,
    status: str | None = None,
    view: str | None = None,
    refresh: str | None = None,
    user=Depends(get_current_user_optional),
):
    return render_shelf(
        request,
        user,
        domain=domain,
        search=search,
        status=status,
        view=view,
        refresh=refresh,
    )


@router.get("/about", response_class=HTMLResponse)
async def about(request: Request, user=Depends(get_current_user_optional)):
    return templates.TemplateResponse("about.html", {"request": request, "user": user})


@router.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request, user=Depends(get_current_user_optional)):
    return templates.TemplateResponse("privacy.html", {"request": request, "user": user})


@router.get("/terms", response_class=HTMLResponse)
async def terms(request: Request, user=Depends(get_current_user_optional)):
    return templates.TemplateResponse("terms.html", {"request": request, "user": user})


@router.get("/design", response_class=HTMLResponse)
async def design_system(request: Request, user=Depends(get_current_user_optional)):
    """Unlinked review surface for the glyph set, loader, and components. Development only."""
    if settings.is_production:
        raise HTTPException(status_code=404, detail="Not found")
    sample = [book for book in CatalogService().get_books() if book.get("author")][:3]
    return templates.TemplateResponse("design.html", {"request": request, "user": user, "sample": sample})


@router.get("/device")
async def device_shortcut(code: str = ""):
    """The address printed on a Kindle screen. Short to type; the real page lives under the account."""
    return RedirectResponse(f"/account/devices{'?code=' + code if code else ''}", status_code=303)
