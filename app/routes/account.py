"""Personal account settings. Profiles do not expose a reader's private activity."""

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from .. import templates
from ..config import settings
from ..db.database import get_supabase, is_sqlite_mode
from ..services.profile_service import MAX_AVATAR_BYTES, ProfileService
from .auth import get_current_user_optional, get_current_user_required

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("", response_class=HTMLResponse)
async def account(request: Request, saved: str = "", user=Depends(get_current_user_optional)):
    if not user:
        return RedirectResponse("/auth/login?next=/account", status_code=303)
    return templates.TemplateResponse("account.html", {"request": request, "user": user, "saved": saved == "1"})


@router.post("", response_class=HTMLResponse)
async def update_account(request: Request, display_name: str = Form(""), username: str = Form(""),
                         remove_photo: bool = Form(False), photo: UploadFile | None = File(None),
                         user=Depends(get_current_user_required)):
    try:
        content = await photo.read(MAX_AVATAR_BYTES + 1) if photo and photo.filename else None
        ProfileService().update(user, display_name=display_name, username=username,
                                photo=content, remove_photo=remove_photo)
    except ValueError as exc:
        return templates.TemplateResponse("account.html", {"request": request, "user": user,
            "form_name": display_name, "form_username": username, "error": str(exc)}, status_code=400)
    except Exception:
        logger.exception("Profile update failed")
        return templates.TemplateResponse("account.html", {"request": request, "user": user,
            "form_name": display_name, "form_username": username,
            "error": "Your profile could not be saved. Please try again."}, status_code=503)
    return RedirectResponse("/account?saved=1", status_code=303)


@router.get("/avatar")
async def avatar(user=Depends(get_current_user_required)):
    key = user.get("avatar_key")
    if not key or not key.startswith(f"avatars/{user['id']}/") or ".." in key:
        raise HTTPException(status_code=404, detail="No profile photo")
    if is_sqlite_mode():
        path = settings.DATA_DIR / key
        if path.is_file():
            return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=300"})
    else:
        result = get_supabase().storage.from_(settings.SUPABASE_STORAGE_BUCKET).create_signed_url(key, 300)
        url = result.get("signedURL") or result.get("signed_url")
        if url:
            return RedirectResponse(url, headers={"Cache-Control": "private, no-store"})
    raise HTTPException(status_code=404, detail="Profile photo unavailable")
