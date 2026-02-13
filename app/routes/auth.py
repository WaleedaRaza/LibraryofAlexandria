"""
Alexandria Library - Authentication
POC mode: No Supabase auth. Anonymous users only.
Preserves route structure so login/register pages still render.
"""

from fastapi import APIRouter, Request, Depends, Form, HTTPException, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from typing import Optional
import logging

from .. import templates
from ..config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


# =============================================================================
# AUTH DEPENDENCIES (used by all routes)
# =============================================================================

def get_current_user_optional(request: Request) -> Optional[dict]:
    """
    POC: Always returns None (anonymous).
    Routes fall back to anon_test_user.
    """
    return None


def get_current_user_required(
    user: Optional[dict] = Depends(get_current_user_optional)
) -> dict:
    """Require authenticated user. In POC, always 401."""
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


# =============================================================================
# STUB ROUTES (so the app doesn't 404 on /auth/*)
# =============================================================================

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("auth/login.html", {"request": request})


@router.post("/login")
async def login(request: Request, email: str = Form(...), password: str = Form(...)):
    return templates.TemplateResponse(
        "auth/login.html",
        {"request": request, "error": "Auth disabled in POC mode. You are anonymous."}
    )


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("auth/register.html", {"request": request})


@router.post("/register")
async def register(request: Request, email: str = Form(...), password: str = Form(...)):
    return templates.TemplateResponse(
        "auth/register.html",
        {"request": request, "error": "Auth disabled in POC mode."}
    )


@router.post("/logout")
async def logout(request: Request):
    return RedirectResponse(url="/", status_code=303)
