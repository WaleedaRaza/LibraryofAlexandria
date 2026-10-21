"""Reader profiles and normalized, private profile photos."""

import io
import logging
import re
import uuid
import warnings

from PIL import Image, ImageOps

from ..config import settings
from ..db.database import get_db, get_supabase, is_sqlite_mode

logger = logging.getLogger(__name__)
MAX_AVATAR_BYTES = 5 * 1024 * 1024


def normalize_avatar(content: bytes) -> bytes:
    if len(content) > MAX_AVATAR_BYTES:
        raise ValueError("Choose a photo smaller than 5 MB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as source:
                if source.format not in {"JPEG", "PNG", "WEBP"} or source.width * source.height > 20_000_000:
                    raise ValueError("Choose a JPG, PNG, or WebP photo under 20 megapixels.")
                source.load()
                portrait = ImageOps.fit(ImageOps.exif_transpose(source).convert("RGB"), (512, 512),
                                        method=Image.Resampling.LANCZOS)
                output = io.BytesIO()
                portrait.save(output, format="JPEG", quality=85)
                return output.getvalue()
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("That image could not be opened. Try a JPG, PNG, or WebP photo.") from exc


class ProfileService:
    def _remove_avatar(self, key: str | None, user_id: str) -> None:
        if not key or not key.startswith(f"avatars/{user_id}/") or ".." in key:
            return
        try:
            if is_sqlite_mode():
                (settings.DATA_DIR / key).unlink(missing_ok=True)
            else:
                get_supabase().storage.from_(settings.SUPABASE_STORAGE_BUCKET).remove([key])
        except Exception:
            logger.warning("Old profile photo cleanup failed for user %s", user_id)

    def update(self, user: dict, *, display_name: str, username: str, photo: bytes | None = None,
               remove_photo: bool = False) -> None:
        display_name, username = display_name.strip(), username.strip().casefold()
        if not 1 <= len(display_name) <= 80:
            raise ValueError("Use a display name between 1 and 80 characters.")
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,23}", username):
            raise ValueError("Use 3–24 letters, numbers, dots, hyphens, or underscores for your username.")
        if is_sqlite_mode():
            existing = get_db().execute("SELECT id FROM users WHERE username=? AND id<>?", (username, user["id"])).fetchone()
        else:
            existing = get_supabase().table("users").select("id").eq("username", username).neq("id", user["id"]).limit(1).execute().data
        if existing:
            raise ValueError("That username is already taken. Try another one.")
        new_key = None
        avatar_key = None if remove_photo else user.get("avatar_key")
        try:
            if photo is not None:
                content = normalize_avatar(photo)
                new_key = f"avatars/{user['id']}/{uuid.uuid4().hex}.jpg"
                if is_sqlite_mode():
                    destination = settings.DATA_DIR / new_key
                    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    destination.write_bytes(content)
                else:
                    get_supabase().storage.from_(settings.SUPABASE_STORAGE_BUCKET).upload(
                        new_key, content, file_options={"content-type": "image/jpeg", "upsert": "false"}
                    )
                avatar_key = new_key
            record = {"display_name": display_name, "username": username, "avatar_key": avatar_key}
            if is_sqlite_mode():
                db = get_db()
                db.execute("UPDATE users SET display_name=:display_name,username=:username,avatar_key=:avatar_key WHERE id=:id",
                           {**record, "id": user["id"]})
                db.commit()
            else:
                get_supabase().table("users").update(record).eq("id", user["id"]).execute()
        except Exception:
            self._remove_avatar(new_key, user["id"])
            raise
        if avatar_key != user.get("avatar_key"):
            self._remove_avatar(user.get("avatar_key"), user["id"])
