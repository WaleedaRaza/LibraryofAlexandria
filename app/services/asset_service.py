"""Resolve PDF assets locally or through private object storage."""

from __future__ import annotations

from pathlib import Path
from typing import Optional
from urllib.parse import quote

from ..config import settings
from ..db.database import get_supabase, is_sqlite_mode


class AssetService:
    def local_pdf(self, book: dict) -> Optional[Path]:
        if book.get("storage_key"):
            root = settings.DATA_DIR.resolve()
            candidate = (root / book["storage_key"]).resolve()
            return candidate if root in candidate.parents and candidate.is_file() else None
        if not settings.LOCAL_PDF_ROOT:
            return None
        root = settings.LOCAL_PDF_ROOT.resolve()
        candidate = (root / book["source_filename"]).resolve()
        if root not in candidate.parents or not candidate.is_file():
            return None
        return candidate

    def signed_pdf_url(self, book: dict) -> Optional[str]:
        if settings.GCS_LIBRARY_BUCKET and not book.get("submission_id"):
            key = quote(book["asset_key"], safe="/")
            return f"https://storage.googleapis.com/{settings.GCS_LIBRARY_BUCKET}/{key}"
        if is_sqlite_mode():
            return None
        response = get_supabase().storage.from_(settings.SUPABASE_STORAGE_BUCKET).create_signed_url(
            book["asset_key"],
            settings.PDF_SIGNED_URL_TTL,
        )
        if isinstance(response, dict):
            return response.get("signedURL") or response.get("signed_url")
        return getattr(response, "signed_url", None)

    def browser_pdf_url(self, book: dict) -> str:
        """Use GCS directly for the public collection and proxy private files."""
        if settings.GCS_LIBRARY_BUCKET and not book.get("submission_id"):
            return self.signed_pdf_url(book) or f"/read/{quote(book['id'], safe='')}/pdf"
        return f"/read/{quote(book['id'], safe='')}/pdf"

    def signed_cover_url(self, book: dict) -> Optional[str]:
        if is_sqlite_mode() or book.get("submission_id"):
            return None
        cover_key = f"covers/{book['id']}.jpg"
        response = get_supabase().storage.from_(settings.SUPABASE_STORAGE_BUCKET).create_signed_url(
            cover_key,
            settings.PDF_SIGNED_URL_TTL,
        )
        if isinstance(response, dict):
            return response.get("signedURL") or response.get("signed_url")
        return getattr(response, "signed_url", None)
