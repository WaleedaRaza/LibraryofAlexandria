"""
Alexandria Library - Authentication Routes
Uses Supabase Auth (their built-in auth service with email provider)
"""

from fastapi import APIRouter, Request, Depends, Form, HTTPException, Cookie, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from typing import Optional
from datetime import datetime
import logging

from .. import templates
from ..config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


def get_supabase_auth_client():
    """Get Supabase client for auth operations."""
    from supabase import create_client
    
    url = settings.SUPABASE_URL
    # Use anon key for auth, fall back to service role key
    key = settings.SUPABASE_ANON_KEY or settings.SUPABASE_SERVICE_ROLE_KEY
    
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_ANON_KEY (or SERVICE_ROLE_KEY) required")
    
    return create_client(url, key)


def get_current_user_optional(
    request: Request,
    access_token: Optional[str] = Cookie(None, alias="sb-access-token"),
    refresh_token: Optional[str] = Cookie(None, alias="sb-refresh-token")
) -> Optional[dict]:
    """
    Get current user from Supabase session cookies.
    Returns None if not logged in.
    """
    if not access_token:
        return None
    
    try:
        client = get_supabase_auth_client()
        
        # Set the session from cookies
        client.auth.set_session(access_token, refresh_token or "")
        
        # Get user
        user_response = client.auth.get_user()
        
        if user_response and user_response.user:
            user = user_response.user
            return {
                "id": user.id,
                "email": user.email,
                "display_name": user.user_metadata.get("display_name") or user.email.split("@")[0],
                "role": user.user_metadata.get("role", "user"),
            }
        return None
        
    except Exception as e:
        logger.debug(f"Auth check failed: {e}")
        return None


def get_current_user_required(
    user: Optional[dict] = Depends(get_current_user_optional)
) -> dict:
    """
    Require authenticated user.
    Raises 401 if not logged in.
    """
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Authentication required"
        )
    return user


def set_auth_cookies(response: Response, session) -> Response:
    """Set Supabase auth cookies on response."""
    max_age = 60 * 60 * 24 * 7  # 7 days
    
    response.set_cookie(
        key="sb-access-token",
        value=session.access_token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=settings.is_production
    )
    response.set_cookie(
        key="sb-refresh-token", 
        value=session.refresh_token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=settings.is_production
    )
    return response


def ensure_user_record(user_id: str, email: str, display_name: str = None):
    """
    Ensure a user record exists in our users table.
    Supabase Auth stores users separately - we need a record
    in our table for foreign keys (highlights, saved_books, etc.)
    """
    try:
        from ..db.database import get_supabase
        client = get_supabase()
        
        # Check if user exists
        result = client.table("users").select("id").eq("id", user_id).execute()
        
        if not result.data:
            # Create user record
            client.table("users").insert({
                "id": user_id,
                "email": email,
                "password_hash": "supabase_auth",  # Placeholder - auth handled by Supabase
                "display_name": display_name or email.split("@")[0],
                "role": "user"
            }).execute()
            logger.info(f"Created user record for {email}")
    except Exception as e:
        logger.error(f"Failed to ensure user record: {e}")


def clear_auth_cookies(response: Response) -> Response:
    """Clear Supabase auth cookies."""
    response.delete_cookie("sb-access-token")
    response.delete_cookie("sb-refresh-token")
    return response


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page."""
    return templates.TemplateResponse(
        "auth/login.html",
        {"request": request}
    )


@router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...)
):
    """Process login with Supabase Auth."""
    try:
        client = get_supabase_auth_client()
        
        # Sign in with Supabase Auth
        auth_response = client.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        
        if not auth_response.session:
            return templates.TemplateResponse(
                "auth/login.html",
                {"request": request, "error": "Invalid email or password"}
            )
        
        # Ensure user record exists in our table (for foreign keys)
        user = auth_response.user
        ensure_user_record(
            user_id=user.id,
            email=user.email,
            display_name=user.user_metadata.get("display_name")
        )
        
        # Success - set cookies and redirect
        response = RedirectResponse(url="/", status_code=303)
        set_auth_cookies(response, auth_response.session)
        return response
        
    except Exception as e:
        logger.error(f"Login error: {e}")
        error_msg = str(e)
        if "Invalid login credentials" in error_msg:
            error_msg = "Invalid email or password"
        elif "Email not confirmed" in error_msg:
            error_msg = "Please check your email to confirm your account"
        else:
            error_msg = "Login failed. Please try again."
            
        return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "error": error_msg}
        )


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """Registration page."""
    return templates.TemplateResponse(
        "auth/register.html",
        {"request": request}
    )


@router.post("/register")
async def register(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    display_name: str = Form(None)
):
    """Process registration with Supabase Auth."""
    try:
        client = get_supabase_auth_client()
        
        # Get the base URL for the confirmation redirect
        base_url = str(request.base_url).rstrip("/")
        
        # Sign up with Supabase Auth
        auth_response = client.auth.sign_up({
            "email": email,
            "password": password,
            "options": {
                "email_redirect_to": f"{base_url}/auth/confirm",
                "data": {
                    "display_name": display_name or email.split("@")[0],
                    "role": "user"
                }
            }
        })
        
        if auth_response.user and auth_response.session:
            # User created and logged in (email confirmation disabled)
            # Ensure user record exists in our table
            user = auth_response.user
            ensure_user_record(
                user_id=user.id,
                email=user.email,
                display_name=display_name
            )
            
            response = RedirectResponse(url="/", status_code=303)
            set_auth_cookies(response, auth_response.session)
            return response
        elif auth_response.user:
            # User created but needs email confirmation - show verify page
            return templates.TemplateResponse(
                "auth/verify_email.html",
                {"request": request, "email": email}
            )
        else:
            return templates.TemplateResponse(
                "auth/register.html",
                {"request": request, "error": "Registration failed. Please try again."}
            )
            
    except Exception as e:
        logger.error(f"Registration error: {e}")
        error_msg = str(e)
        if "already registered" in error_msg.lower() or "already been registered" in error_msg.lower():
            error_msg = "This email is already registered. Try logging in."
        elif "password" in error_msg.lower():
            error_msg = "Password must be at least 6 characters"
        else:
            error_msg = "Registration failed. Please try again."
            
        return templates.TemplateResponse(
            "auth/register.html",
            {"request": request, "error": error_msg}
        )


@router.post("/resend")
async def resend_confirmation(
    request: Request,
    email: str = Form(...)
):
    """Resend confirmation email."""
    try:
        client = get_supabase_auth_client()
        base_url = str(request.base_url).rstrip("/")
        
        # Resend confirmation email
        client.auth.resend({
            "type": "signup",
            "email": email,
            "options": {
                "email_redirect_to": f"{base_url}/auth/confirm"
            }
        })
        
        return JSONResponse({"success": True})
        
    except Exception as e:
        logger.error(f"Resend error: {e}")
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)


@router.post("/set-session")
async def set_session(request: Request):
    """
    Set session cookies from tokens (called by JS after email confirmation).
    Also ensures user record exists in our table.
    """
    try:
        data = await request.json()
        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        
        if not access_token or not refresh_token:
            return JSONResponse({"error": "Missing tokens"}, status_code=400)
        
        # Get user info from the token to ensure user record
        try:
            client = get_supabase_auth_client()
            client.auth.set_session(access_token, refresh_token)
            user_response = client.auth.get_user()
            if user_response and user_response.user:
                user = user_response.user
                ensure_user_record(
                    user_id=user.id,
                    email=user.email,
                    display_name=user.user_metadata.get("display_name")
                )
        except Exception as e:
            logger.warning(f"Could not ensure user record: {e}")
        
        response = JSONResponse({"success": True})
        
        class Session:
            pass
        session = Session()
        session.access_token = access_token
        session.refresh_token = refresh_token
        set_auth_cookies(response, session)
        
        return response
        
    except Exception as e:
        logger.error(f"Set session error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/logout")
async def logout(request: Request):
    """Log out - clear session."""
    try:
        # Try to sign out from Supabase
        client = get_supabase_auth_client()
        client.auth.sign_out()
    except Exception as e:
        logger.debug(f"Logout signout error (ok if not logged in): {e}")
    
    response = RedirectResponse(url="/", status_code=303)
    clear_auth_cookies(response)
    return response


@router.get("/confirm")
async def confirm_email(
    request: Request,
    access_token: str = None,
    refresh_token: str = None,
    token_hash: str = None,
    type: str = None
):
    """
    Handle email confirmation callback from Supabase.
    User clicks link in email → lands here → auto-logged in.
    """
    # Supabase sends tokens as fragment (#) but also supports query params
    if access_token and refresh_token:
        response = RedirectResponse(url="/", status_code=303)
        
        class Session:
            pass
        session = Session()
        session.access_token = access_token
        session.refresh_token = refresh_token
        set_auth_cookies(response, session)
        return response
    
    # If tokens in fragment, we need JS to extract them
    # Render a page that does this
    return templates.TemplateResponse(
        "auth/confirm_callback.html",
        {"request": request}
    )


@router.get("/callback")
async def auth_callback(
    request: Request,
    access_token: str = None,
    refresh_token: str = None
):
    """
    Generic auth callback - redirects to confirm handler.
    """
    if access_token and refresh_token:
        response = RedirectResponse(url="/", status_code=303)
        
        class Session:
            pass
        session = Session()
        session.access_token = access_token
        session.refresh_token = refresh_token
        set_auth_cookies(response, session)
        return response
    
    return RedirectResponse(url="/auth/login", status_code=303)
