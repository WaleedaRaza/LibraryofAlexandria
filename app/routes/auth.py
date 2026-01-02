"""
Alexandria Library - Authentication Routes
Minimal auth: sessions via signed cookies.
No OAuth in V1. No profiles.
"""

from fastapi import APIRouter, Request, Depends, Form, HTTPException, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse
from typing import Optional
import bcrypt
import secrets
import uuid
from datetime import datetime, timedelta

from .. import templates
from ..config import settings
from ..db.database import get_supabase, is_sqlite_mode

router = APIRouter()


def hash_password(password: str) -> str:
    """Hash password with bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against bcrypt hash."""
    # Handle legacy SHA256 hashes during migration
    if not password_hash.startswith('$2'):
        import hashlib
        return hashlib.sha256(password.encode()).hexdigest() == password_hash
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def get_current_user_optional(
    request: Request,
    session_id: Optional[str] = Cookie(None, alias=settings.SESSION_COOKIE_NAME)
) -> Optional[dict]:
    """
    Get current user from session cookie.
    Returns None if not logged in.
    """
    if not session_id:
        return None
    
    if is_sqlite_mode():
        # SQLite fallback
        from ..db.database import get_db
        db = get_db()
        session = db.execute(
            """
            SELECT s.user_id, u.id, u.email, u.display_name, u.role
            FROM sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.id = ? AND s.expires_at > datetime('now')
            """,
            (session_id,)
        ).fetchone()
        return dict(session) if session else None
    
    # Supabase REST API
    client = get_supabase()
    
    # Get session with user info (using foreign key relationship)
    result = client.table("sessions").select(
        "user_id, expires_at, users(id, email, display_name, role)"
    ).eq("id", session_id).execute()
    
    if not result.data:
        return None
    
    session = result.data[0]
    
    # Check if session is expired
    expires_at = datetime.fromisoformat(session["expires_at"].replace("Z", "+00:00"))
    if expires_at < datetime.now(expires_at.tzinfo):
        return None
    
    user = session.get("users")
    if not user:
        return None
    
    return {
        "id": user["id"],
        "email": user["email"],
        "display_name": user["display_name"],
        "role": user["role"],
        "user_id": user["id"]
    }


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
    """Process login."""
    if is_sqlite_mode():
        # SQLite fallback
        from ..db.database import get_db
        db = get_db()
        user = db.execute(
            "SELECT id, email, password_hash FROM users WHERE email = ?",
            (email,)
        ).fetchone()
        
        if not user or not verify_password(password, user["password_hash"]):
            return templates.TemplateResponse(
                "auth/login.html",
                {"request": request, "error": "Invalid email or password"}
            )
        
        session_id = secrets.token_urlsafe(32)
        db.execute(
            """
            INSERT INTO sessions (id, user_id, expires_at)
            VALUES (?, ?, datetime('now', '+7 days'))
            """,
            (session_id, user["id"])
        )
        db.commit()
    else:
        # Supabase REST API
        client = get_supabase()
        
        # Find user
        result = client.table("users").select(
            "id, email, password_hash"
        ).eq("email", email).execute()
        
        if not result.data:
            return templates.TemplateResponse(
                "auth/login.html",
                {"request": request, "error": "Invalid email or password"}
            )
        
        user = result.data[0]
        
        if not verify_password(password, user["password_hash"]):
            return templates.TemplateResponse(
                "auth/login.html",
                {"request": request, "error": "Invalid email or password"}
            )
        
        # Create session
        session_id = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(days=7)
        
        client.table("sessions").insert({
            "id": session_id,
            "user_id": user["id"],
            "expires_at": expires_at.isoformat()
        }).execute()
    
    # Set cookie and redirect
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=session_id,
        max_age=settings.SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=settings.is_production
    )
    return response


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
    """Process registration."""
    if is_sqlite_mode():
        # SQLite fallback
        from ..db.database import get_db
        db = get_db()
        
        existing = db.execute(
            "SELECT id FROM users WHERE email = ?",
            (email,)
        ).fetchone()
        
        if existing:
            return templates.TemplateResponse(
                "auth/register.html",
                {"request": request, "error": "Email already registered"}
            )
        
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        db.execute(
            """
            INSERT INTO users (id, email, password_hash, display_name, role)
            VALUES (?, ?, ?, ?, 'user')
            """,
            (user_id, email, hash_password(password), display_name)
        )
        db.commit()
        
        session_id = secrets.token_urlsafe(32)
        db.execute(
            """
            INSERT INTO sessions (id, user_id, expires_at)
            VALUES (?, ?, datetime('now', '+7 days'))
            """,
            (session_id, user_id)
        )
        db.commit()
    else:
        # Supabase REST API
        client = get_supabase()
        
        # Check if email exists
        result = client.table("users").select("id").eq("email", email).execute()
        
        if result.data:
            return templates.TemplateResponse(
                "auth/register.html",
                {"request": request, "error": "Email already registered"}
            )
        
        # Create user
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        client.table("users").insert({
            "id": user_id,
            "email": email,
            "password_hash": hash_password(password),
            "display_name": display_name,
            "role": "user"
        }).execute()
        
        # Auto-login: create session
        session_id = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(days=7)
        
        client.table("sessions").insert({
            "id": session_id,
            "user_id": user_id,
            "expires_at": expires_at.isoformat()
        }).execute()
    
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=session_id,
        max_age=settings.SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=settings.is_production
    )
    return response


@router.post("/logout")
async def logout(
    request: Request,
    session_id: Optional[str] = Cookie(None, alias=settings.SESSION_COOKIE_NAME)
):
    """Log out - clear session."""
    if session_id:
        if is_sqlite_mode():
            from ..db.database import get_db
            db = get_db()
            db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            db.commit()
        else:
            client = get_supabase()
            client.table("sessions").delete().eq("id", session_id).execute()
    
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(key=settings.SESSION_COOKIE_NAME)
    return response
