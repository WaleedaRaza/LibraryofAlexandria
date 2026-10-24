"""
Alexandria Library - Configuration
All settings in one place. No magic.
"""

import os
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

# Load .env file for local development
# In production, env vars are set directly (Render, Fly.io, etc.)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, rely on system env vars


class Settings:
    """Application settings. Environment variables override defaults."""
    
    # Core
    APP_NAME: str = "LibXNDR"
    ENV: str = os.getenv("ENV", "development")  # development or production
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    PUBLIC_BASE_URL: Optional[str] = os.getenv("PUBLIC_BASE_URL")
    GOOGLE_AUTH_ENABLED: bool = os.getenv("GOOGLE_AUTH_ENABLED", "false").lower() == "true"
    ASSET_VERSION: str = os.getenv("ASSET_VERSION", "42")
    
    @property
    def is_production(self) -> bool:
        return self.ENV == "production"

    def production_errors(self) -> list[str]:
        errors = []
        for name in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY"):
            value = getattr(self, name)
            if not value or value.startswith("your-") or "your-project" in value:
                errors.append(f"Set {name}")
        if len(self.SECRET_KEY) < 32 or self.SECRET_KEY in {"dev-secret-key-change-in-production", "your-secret-key-change-in-production"}:
            errors.append("Set a unique SECRET_KEY of at least 32 characters")
        origin = urlsplit(self.PUBLIC_BASE_URL or "")
        if origin.scheme != "https" or not origin.hostname or origin.path not in {"", "/"} or origin.query or origin.fragment or origin.username:
            errors.append("Set PUBLIC_BASE_URL to the exact HTTPS site origin")
        if self.DEBUG:
            errors.append("Set DEBUG=false")
        if self.LOCAL_PDF_ROOT:
            errors.append("Unset LOCAL_PDF_ROOT so production uses cloud storage")
        if not self.GCS_LIBRARY_BUCKET:
            errors.append("Set GCS_LIBRARY_BUCKET for the public founding collection")
        return errors
    
    # Paths
    BASE_DIR: Path = Path(__file__).parent.parent
    DATA_DIR: Path = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
    DB_PATH: Path = Path(os.getenv("DB_PATH", str(DATA_DIR / "alexandria.db")))
    CANON_DIR: Path = BASE_DIR / "canon"  # Where book texts live
    LIBRARY_CATALOG_PATH: Path = Path(
        os.getenv("LIBRARY_CATALOG_PATH", str(BASE_DIR / "library" / "catalog.json"))
    )
    LOCAL_PDF_ROOT: Optional[Path] = (
        Path(os.environ["LOCAL_PDF_ROOT"]).expanduser()
        if os.getenv("LOCAL_PDF_ROOT")
        else None
    )
    
    # ==========================================================================
    # SUPABASE
    # ==========================================================================
    # Get these from: Supabase Dashboard → Settings → API
    SUPABASE_URL: Optional[str] = os.getenv("SUPABASE_URL")
    SUPABASE_ANON_KEY: Optional[str] = os.getenv("SUPABASE_ANON_KEY")  # For auth
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = os.getenv("SUPABASE_SERVICE_ROLE_KEY")  # For admin ops
    SUPABASE_STORAGE_BUCKET: str = os.getenv("SUPABASE_STORAGE_BUCKET", "waleeds-library")
    GCS_LIBRARY_BUCKET: Optional[str] = os.getenv("GCS_LIBRARY_BUCKET")
    PDF_SIGNED_URL_TTL: int = int(os.getenv("PDF_SIGNED_URL_TTL", "900"))
    SOURCE_FINDER_ENABLED: bool = os.getenv("SOURCE_FINDER_ENABLED", "true").lower() == "true"
    
    # Legacy - kept for reference but no longer used
    # DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")
    
    # LLM
    USE_MOCK_AGENTS: bool = os.getenv("USE_MOCK_AGENTS", "true").lower() == "true"
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    
    # Auth
    SESSION_COOKIE_NAME: str = "__session"  # Firebase Hosting forwards this cookie.
    SESSION_MAX_AGE: int = 60 * 60 * 24 * 7  # 7 days
    
    def __init__(self):
        # Ensure data directory exists (for local SQLite fallback)
        self.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.CANON_DIR.mkdir(parents=True, exist_ok=True)


settings = Settings()
