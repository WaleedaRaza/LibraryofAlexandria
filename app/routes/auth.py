"""Friction-light email/password authentication.

Supabase Auth verifies production sign-ins. Opaque, revocable server sessions
work through Firebase Hosting and also support local SQLite development.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
import uuid
from typing import Optional
from urllib.parse import unquote

import bcrypt
from fastapi import APIRouter, Cookie, Depends, Form, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from .. import templates
from ..config import settings
from ..db.database import get_db, get_supabase, is_sqlite_mode
from ..services.session_service import SessionService

router = APIRouter()
logger = logging.getLogger(__name__)
RECOVERY_COOKIE_NAME = "__libxndr_recovery"
RECOVERY_MAX_AGE = 15 * 60


def _safe_next(value: Optional[str]) -> str:
    decoded = unquote(value or "")
    if not decoded.startswith("/") or decoded.startswith("//") or "\\" in decoded or any(ord(c) < 32 for c in decoded):
        return "/library/my"
    return value


def _set_cookie(response: Response, name: str, value: str) -> None:
    response.set_cookie(
        name,
        value,
        max_age=settings.SESSION_MAX_AGE,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
    )


def _start_session(response: Response, user_id: str) -> None:
    _set_cookie(response, settings.SESSION_COOKIE_NAME, SessionService().create(user_id))


def _oauth_cookie(verifier: str, destination: str) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({
        "verifier": verifier, "next": _safe_next(destination), "exp": int(time.time()) + 600,
    }).encode()).decode().rstrip("=")
    signature = hmac.new(settings.SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"oauth.{payload}.{signature}"


def _read_oauth_cookie(token: str) -> Optional[dict]:
    try:
        if not token.startswith("oauth."):
            return None
        token = token.removeprefix("oauth.")
        payload, signature = token.rsplit(".", 1)
        expected = hmac.new(settings.SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if data["exp"] < time.time() or not isinstance(data["verifier"], str):
            return None
        return {"verifier": data["verifier"], "next": _safe_next(data["next"])}
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def _recovery_cookie(user_id: str) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({
        "user_id": user_id, "purpose": "password-recovery",
        "exp": int(time.time()) + RECOVERY_MAX_AGE,
    }).encode()).decode().rstrip("=")
    signature = hmac.new(settings.SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"recovery.{payload}.{signature}"


def _read_recovery_cookie(token: str) -> Optional[dict]:
    try:
        if not token.startswith("recovery."):
            return None
        payload, signature = token.removeprefix("recovery.").rsplit(".", 1)
        expected = hmac.new(settings.SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if (
            data.get("purpose") != "password-recovery"
            or data.get("exp", 0) < time.time()
            or not isinstance(data.get("user_id"), str)
        ):
            return None
        return {"user_id": data["user_id"], "exp": data["exp"]}
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def _auth_error_code(exc: Exception) -> str:
    code = getattr(exc, "code", "")
    return str(getattr(code, "value", code) or "").casefold()


def _base_url(request: Request) -> str:
    return (settings.PUBLIC_BASE_URL or str(request.base_url)).rstrip("/")


def get_supabase_auth_client():
    from supabase import ClientOptions, create_client

    if not settings.SUPABASE_URL or not settings.SUPABASE_ANON_KEY:
        raise RuntimeError("Supabase authentication is not configured")
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY,
                         options=ClientOptions(auto_refresh_token=False, persist_session=False, flow_type="implicit"))


def _public_user(auth_user) -> dict:
    database = get_supabase()
    rows = database.table("users").select("id,email,display_name,username,avatar_key,role").eq(
        "id", str(auth_user.id)
    ).limit(1).execute().data or []
    if rows:
        return rows[0]
    email = auth_user.email or ""
    record = {
        "id": str(auth_user.id), "email": email,
        "display_name": (auth_user.user_metadata or {}).get("display_name") or (auth_user.user_metadata or {}).get("full_name") or email.split("@")[0] or "Reader",
        "role": "user",
    }
    try:
        database.table("users").insert(record).execute()
    except Exception:
        # A legacy profile row can hold this email under an older auth id. Map
        # the verified identity to that stable application profile instead of
        # rewriting its primary key: shelves, highlights, submissions, and
        # sessions intentionally continue to reference the established id.
        legacy = database.table("users").select("id,email,display_name,username,avatar_key,role").eq(
            "email", email
        ).limit(1).execute().data or []
        if not legacy:
            raise
        logger.info("Mapped auth user %s to legacy profile %s", auth_user.id, legacy[0]["id"])
        return legacy[0]
    return {**record, "username": None, "avatar_key": None}


def get_current_user_optional(
    request: Request,
    session: Optional[str] = Cookie(None, alias="__session"),
) -> Optional[dict]:
    try:
        return SessionService().user(session)
    except Exception as exc:
        logger.debug("Session lookup failed: %s", exc)
        return None


def get_current_user_required(user: Optional[dict] = Depends(get_current_user_optional)) -> dict:
    if not user:
        raise HTTPException(status_code=401, detail="Sign in to use your reading tools")
    return user


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = "/library/my"):
    return templates.TemplateResponse("auth/login.html", {"request": request, "next": _safe_next(next),
                                                     "google_auth_enabled": settings.GOOGLE_AUTH_ENABLED and not is_sqlite_mode()})


@router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form("/library/my"),
):
    destination = _safe_next(next)
    try:
        if is_sqlite_mode():
            row = get_db().execute(
                "SELECT id, password_hash FROM users WHERE lower(email) = lower(?)", (email.strip(),)
            ).fetchone()
            if not row or not bcrypt.checkpw(password.encode(), row["password_hash"].encode()):
                raise ValueError("Email or password did not match")
            response = RedirectResponse(destination, status_code=303)
            _start_session(response, row["id"])
            return response

        auth = get_supabase_auth_client().auth.sign_in_with_password(
            {"email": email.strip(), "password": password}
        )
        if not auth.session or not auth.user:
            raise ValueError("Email or password did not match")
        response = RedirectResponse(destination, status_code=303)
        _start_session(response, _public_user(auth.user)["id"])
        return response
    except Exception as exc:
        logger.exception("Sign-in failed")
        code = _auth_error_code(exc)
        if code == "email_not_confirmed":
            message = "Confirm your email first, then come back here to sign in."
        elif code in {"over_request_rate_limit", "over_email_send_rate_limit"}:
            message = "Too many attempts at once. Wait a moment, then try again."
        else:
            message = "We couldn't sign you in. Check your email and password, or reset your password."
        return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "next": destination, "email": email,
             "error": message,
             "google_auth_enabled": settings.GOOGLE_AUTH_ENABLED and not is_sqlite_mode()},
            status_code=400,
        )


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, next: str = "/library/my"):
    return templates.TemplateResponse("auth/register.html", {"request": request, "next": _safe_next(next),
                                                        "google_auth_enabled": settings.GOOGLE_AUTH_ENABLED and not is_sqlite_mode()})


@router.post("/register")
async def register(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    display_name: str = Form(""),
    next: str = Form("/library/my"),
):
    destination = _safe_next(next)
    email = email.strip().casefold()
    display_name = display_name.strip() or email.split("@")[0]
    if len(password) < 8:
        return templates.TemplateResponse(
            "auth/register.html",
            {"request": request, "next": destination, "email": email, "display_name": display_name,
             "error": "Use at least 8 characters for your password.",
             "google_auth_enabled": settings.GOOGLE_AUTH_ENABLED and not is_sqlite_mode()},
            status_code=400,
        )
    try:
        if is_sqlite_mode():
            user_id = f"usr_{uuid.uuid4().hex[:16]}"
            password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
            database = get_db()
            database.execute(
                "INSERT INTO users (id, email, password_hash, display_name) VALUES (?, ?, ?, ?)",
                (user_id, email, password_hash, display_name),
            )
            database.commit()
            response = RedirectResponse(destination, status_code=303)
            _start_session(response, user_id)
            return response

        base_url = _base_url(request)
        auth = get_supabase_auth_client().auth.sign_up(
            {"email": email, "password": password, "options": {
                "email_redirect_to": f"{base_url}/auth/confirm",
                "data": {"display_name": display_name},
            }}
        )
        if not auth.user:
            raise ValueError("Account was not created")
        if auth.session:
            profile = _public_user(auth.user)
            response = RedirectResponse(destination, status_code=303)
            _start_session(response, profile["id"])
            return response
        # With email confirmation enabled, Supabase may intentionally return a
        # synthetic user for an address that already exists. Do not mirror that
        # unverified identity into the profile table; the real profile is made
        # only after confirmation or a successful sign-in.
        return templates.TemplateResponse("auth/verify_email.html", {"request": request, "email": email})
    except Exception as exc:
        logger.error("Registration failed", exc_info=exc)
        code = _auth_error_code(exc)
        if code in {"user_already_exists", "email_exists"}:
            message = "That email already has an account. Sign in or reset the password instead."
        elif code in {"over_email_send_rate_limit", "over_request_rate_limit"}:
            message = "Email is temporarily rate-limited. Wait a moment, then try again."
        else:
            message = "We couldn't finish that signup. If this email already has an account, sign in or reset its password."
        return templates.TemplateResponse(
            "auth/register.html",
            {"request": request, "next": destination, "email": email, "display_name": display_name,
             "error": message,
             "google_auth_enabled": settings.GOOGLE_AUTH_ENABLED and not is_sqlite_mode()},
            status_code=400,
        )


@router.get("/google")
async def google_sign_in(request: Request, next: str = "/library/my", user=Depends(get_current_user_optional)):
    if user:
        return RedirectResponse(_safe_next(next), status_code=303)
    if not settings.GOOGLE_AUTH_ENABLED or is_sqlite_mode():
        raise HTTPException(status_code=404, detail="Google sign-in is not configured")
    from supabase import ClientOptions, create_client
    from supabase_auth._sync.storage import SyncMemoryStorage

    storage = SyncMemoryStorage()
    client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY,
                           options=ClientOptions(flow_type="pkce", storage=storage, persist_session=False))
    base_url = _base_url(request)
    callback_url = f"{base_url}/auth/google/callback"
    oauth = client.auth.sign_in_with_oauth({"provider": "google", "options": {"redirect_to": callback_url}})
    verifier = [value for key, value in storage.storage.items() if key.endswith("-code-verifier")]
    verifier = verifier[0] if verifier else None
    if not verifier or not oauth.url:
        raise HTTPException(status_code=503, detail="Google sign-in could not start")
    response = RedirectResponse(oauth.url, status_code=302)
    response.set_cookie(settings.SESSION_COOKIE_NAME, _oauth_cookie(verifier, next), max_age=600,
                        httponly=True, secure=settings.is_production, samesite="lax")
    return response


@router.get("/google/callback")
async def google_callback(request: Request, code: str = "", libxndr_oauth: Optional[str] = Cookie(None, alias="__session")):
    saved = _read_oauth_cookie(libxndr_oauth or "")
    def sign_in_error(message: str):
        response = templates.TemplateResponse("auth/login.html", {"request": request,
            "next": saved["next"] if saved else "/library/my", "error": message,
            "google_auth_enabled": settings.GOOGLE_AUTH_ENABLED and not is_sqlite_mode()}, status_code=400)
        if libxndr_oauth and libxndr_oauth.startswith("oauth."):
            response.delete_cookie(settings.SESSION_COOKIE_NAME)
        return response
    if not settings.GOOGLE_AUTH_ENABLED or is_sqlite_mode() or not code or not saved:
        return sign_in_error("Google sign-in expired. Please try again.")
    try:
        from supabase import ClientOptions, create_client

        client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY,
                               options=ClientOptions(flow_type="pkce", persist_session=False))
        auth = client.auth.exchange_code_for_session({"auth_code": code, "code_verifier": saved["verifier"]})
        if not auth.session or not auth.user:
            raise ValueError("Missing authenticated session")
        profile = _public_user(auth.user)
    except Exception as exc:
        logger.warning("Google sign-in callback failed: %s", type(exc).__name__)
        return sign_in_error("Google sign-in could not be completed. Please try again.")
    response = RedirectResponse(saved["next"], status_code=303)
    _start_session(response, profile["id"])
    return response


@router.post("/logout")
async def logout(request: Request):
    SessionService().revoke(request.cookies.get(settings.SESSION_COOKIE_NAME))
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(settings.SESSION_COOKIE_NAME)
    response.delete_cookie("alexandria-session")
    response.delete_cookie("sb-access-token")
    response.delete_cookie("sb-refresh-token")
    return response


@router.get("/confirm", response_class=HTMLResponse)
async def confirm(
    request: Request,
    token_hash: str = "",
    confirmation_type: str = Query("email", alias="type"),
    next: str = "/library/my",
):
    destination = _safe_next(next)
    if token_hash:
        try:
            verification_type = confirmation_type if confirmation_type in {"email", "signup", "invite", "magiclink"} else "email"
            auth = get_supabase_auth_client().auth.verify_otp({
                "token_hash": token_hash,
                "type": verification_type,
            })
            if not auth.user:
                raise ValueError("Missing confirmed user")
            response = RedirectResponse(destination, status_code=303)
            _start_session(response, _public_user(auth.user)["id"])
            return response
        except Exception as exc:
            logger.warning("Server confirmation failed: %s", _auth_error_code(exc) or type(exc).__name__)
            return templates.TemplateResponse("auth/confirm_callback.html", {
                "request": request,
                "confirmation_error": "That confirmation link is invalid or has expired. You can still sign in or reset your password.",
            }, status_code=400)
    return templates.TemplateResponse("auth/confirm_callback.html", {"request": request, "next": destination})


@router.post("/set-session")
async def set_session(request: Request):
    data = await request.json()
    access_token = data.get("access_token")
    destination = _safe_next(data.get("next"))
    if not access_token:
        return JSONResponse({"error": "Confirmation tokens were missing"}, status_code=400)
    try:
        result = get_supabase_auth_client().auth.get_user(access_token)
        if not result.user:
            raise ValueError("Unverified session")
        profile = _public_user(result.user)
    except Exception:
        logger.exception("Email confirmation session failed")
        return JSONResponse({"error": "That sign-in link could not be verified. Please sign in again."}, status_code=400)
    response = JSONResponse({"success": True, "redirect": destination})
    _start_session(response, profile["id"])
    return response


@router.post("/resend")
async def resend_confirmation(email: str = Form(...)):
    if is_sqlite_mode():
        return {"success": True}
    try:
        get_supabase_auth_client().auth.resend({"type": "signup", "email": email.strip()})
        return {"success": True}
    except Exception:
        return JSONResponse({"success": False, "error": "We could not resend that email yet."}, status_code=400)


@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    return templates.TemplateResponse("auth/forgot_password.html", {"request": request})


@router.post("/forgot-password", response_class=HTMLResponse)
async def forgot_password(request: Request, email: str = Form(...)):
    email = email.strip().casefold()
    # Always show the same result so this endpoint cannot enumerate accounts.
    if not is_sqlite_mode():
        try:
            get_supabase_auth_client().auth.reset_password_for_email(
                email,
                {"redirect_to": f"{_base_url(request)}/auth/reset-password"},
            )
        except Exception as exc:
            logger.warning("Password recovery request failed: %s", _auth_error_code(exc) or type(exc).__name__)
    return templates.TemplateResponse("auth/forgot_password.html", {
        "request": request,
        "email": email,
        "sent": True,
    })


@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(
    request: Request,
    token_hash: str = "",
    recovery_type: str = Query("recovery", alias="type"),
    recovery_state: Optional[str] = Cookie(None, alias=RECOVERY_COOKIE_NAME),
):
    if token_hash and not is_sqlite_mode():
        try:
            auth = get_supabase_auth_client().auth.verify_otp({
                "token_hash": token_hash,
                "type": "recovery",
            })
            if not auth.user:
                raise ValueError("Missing recovery user")
            profile = _public_user(auth.user)
            response = RedirectResponse("/auth/reset-password", status_code=303)
            response.set_cookie(
                RECOVERY_COOKIE_NAME,
                _recovery_cookie(profile["id"]),
                max_age=RECOVERY_MAX_AGE,
                httponly=True,
                secure=settings.is_production,
                samesite="lax",
            )
            return response
        except Exception as exc:
            logger.warning("Recovery token verification failed: %s", _auth_error_code(exc) or type(exc).__name__)
            return templates.TemplateResponse("auth/reset_password.html", {
                "request": request,
                "ready": False,
                "error": "That password-reset link is invalid or has expired.",
            }, status_code=400)
    return templates.TemplateResponse("auth/reset_password.html", {
        "request": request,
        "ready": bool(_read_recovery_cookie(recovery_state or "")),
    })


@router.post("/recovery-session")
async def recovery_session(request: Request):
    data = await request.json()
    access_token = data.get("access_token")
    if not access_token or is_sqlite_mode():
        return JSONResponse({"error": "Recovery tokens were missing"}, status_code=400)
    try:
        result = get_supabase_auth_client().auth.get_user(access_token)
        if not result.user:
            raise ValueError("Unverified recovery session")
        profile = _public_user(result.user)
    except Exception as exc:
        logger.warning("Recovery session failed: %s", _auth_error_code(exc) or type(exc).__name__)
        return JSONResponse({"error": "That password-reset link is invalid or has expired."}, status_code=400)
    response = JSONResponse({"success": True})
    response.set_cookie(
        RECOVERY_COOKIE_NAME,
        _recovery_cookie(profile["id"]),
        max_age=RECOVERY_MAX_AGE,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
    )
    return response


@router.post("/reset-password")
async def reset_password(
    request: Request,
    password: str = Form(...),
    confirm_password: str = Form(...),
    recovery_state: Optional[str] = Cookie(None, alias=RECOVERY_COOKIE_NAME),
):
    state = _read_recovery_cookie(recovery_state or "")
    if not state:
        return templates.TemplateResponse("auth/reset_password.html", {
            "request": request,
            "ready": False,
            "error": "That password-reset link is invalid or has expired.",
        }, status_code=400)
    if len(password) < 8 or password != confirm_password:
        message = "Use at least 8 characters." if len(password) < 8 else "The two passwords do not match."
        return templates.TemplateResponse("auth/reset_password.html", {
            "request": request,
            "ready": True,
            "error": message,
        }, status_code=400)
    try:
        get_supabase().auth.admin.update_user_by_id(state["user_id"], {"password": password})
        response = RedirectResponse("/library/my?password=changed", status_code=303)
        _start_session(response, state["user_id"])
        response.delete_cookie(RECOVERY_COOKIE_NAME)
        return response
    except Exception as exc:
        logger.error("Password reset failed", exc_info=exc)
        return templates.TemplateResponse("auth/reset_password.html", {
            "request": request,
            "ready": True,
            "error": "We couldn't save the new password. Please request another reset link.",
        }, status_code=400)
