"""
Alexandria Library - Configuration
All settings in one place. No magic.
"""

import os
from pathlib import Path
from typing import Optional

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
    APP_NAME: str = "Alexandria Library"
    ENV: str = os.getenv("ENV", "development")  # development or production
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    
    @property
    def is_production(self) -> bool:
        return self.ENV == "production"
    
    # Paths
    BASE_DIR: Path = Path(__file__).parent.parent
    DB_PATH: Path = BASE_DIR / "data" / "alexandria.db"
    CANON_DIR: Path = BASE_DIR / "canon"  # Where book texts live
    
    # ==========================================================================
    # SUPABASE
    # ==========================================================================
    # Get these from: Supabase Dashboard → Settings → API
    SUPABASE_URL: Optional[str] = os.getenv("SUPABASE_URL")
    SUPABASE_ANON_KEY: Optional[str] = os.getenv("SUPABASE_ANON_KEY")  # For auth
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = os.getenv("SUPABASE_SERVICE_ROLE_KEY")  # For admin ops
    
    # Legacy - kept for reference but no longer used
    # DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")
    
    # LLM
    USE_MOCK_AGENTS: bool = os.getenv("USE_MOCK_AGENTS", "true").lower() == "true"
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    
    # Auth
    SESSION_COOKIE_NAME: str = "alexandria_session"
    SESSION_MAX_AGE: int = 60 * 60 * 24 * 7  # 7 days
    
    def __init__(self):
        # Ensure data directory exists (for local SQLite fallback)
        self.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.CANON_DIR.mkdir(parents=True, exist_ok=True)


settings = Settings()

