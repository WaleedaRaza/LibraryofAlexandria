"""
Alexandria Library - Application Entry Point

FastAPI app bootstrap. Middleware. Nothing else.
"""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
import time

from .config import settings
from .db.database import init_db


# Create app
app = FastAPI(
    title="Alexandria Library",
    description="A constrained, agent-guided reading system",
    version="1.0.0",
    docs_url="/api/docs" if settings.DEBUG else None,
    redoc_url=None,
)

# Templates
templates_path = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_path))

# Static files
static_path = Path(__file__).parent.parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Track request processing time."""
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response


# ---------------------------------------------------------------------------
# Startup / Shutdown
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup_event():
    """Initialize database and validate environment on startup."""
    print("=" * 60)
    print("🏛️  ALEXANDRIA LIBRARY - Starting up...")
    print("=" * 60)
    
    # Validate required env vars
    if settings.is_production:
        if settings.SECRET_KEY == "dev-secret-key-change-in-production":
            raise RuntimeError("SECRET_KEY must be set in production")
    
    # Force mock mode if no OpenAI key
    if not settings.OPENAI_API_KEY and not settings.USE_MOCK_AGENTS:
        import os
        os.environ["USE_MOCK_AGENTS"] = "true"
        print("⚠️  OPENAI_API_KEY not set, forcing mock mode")
    
    # Show database mode
    from .db.database import is_sqlite_mode
    if is_sqlite_mode():
        print("📁 Database: SQLite (local development)")
    else:
        print("☁️  Database: Supabase REST API")
    
    # Initialize database connection
    init_db()
    
    print("=" * 60)
    print("✅ Alexandria Library ready!")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

# Import and include routers
from .routes import pages, ask, reader, library, wishlist, auth, admin

app.include_router(pages.router)
app.include_router(ask.router, prefix="/ask", tags=["ask"])
app.include_router(reader.router, prefix="/read", tags=["reader"])
app.include_router(library.router, prefix="/library", tags=["library"])
app.include_router(wishlist.router, prefix="/wishlist", tags=["wishlist"])
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    from .db.database import is_sqlite_mode, get_supabase
    
    try:
        if is_sqlite_mode():
            from .db.database import get_db
            db = get_db()
            db.execute("SELECT 1").fetchone()
            return {"status": "ok", "db": "sqlite", "mode": "local"}
        else:
            client = get_supabase()
            # Quick ping - select from users table
            result = client.table("users").select("id").limit(1).execute()
            return {"status": "ok", "db": "supabase", "mode": "rest_api"}
    except Exception as e:
        return {"status": "error", "db": "disconnected", "error": str(e)}


# ---------------------------------------------------------------------------
# Error Handlers
# ---------------------------------------------------------------------------

@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """Custom 404 page."""
    return templates.TemplateResponse(
        "errors/404.html",
        {"request": request},
        status_code=404
    )


@app.exception_handler(500)
async def server_error_handler(request: Request, exc):
    """Custom 500 page."""
    return templates.TemplateResponse(
        "errors/500.html",
        {"request": request},
        status_code=500
    )
