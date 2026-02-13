"""
Alexandria Library - Application Entry Point
FastAPI app bootstrap. SQLite. Artifact-first.
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
    version="2.0.0",
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
    start_time = time.time()
    response = await call_next(request)
    response.headers["X-Process-Time"] = str(time.time() - start_time)
    return response


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup_event():
    print("=" * 60)
    print("  ALEXANDRIA LIBRARY — Starting up...")
    print("=" * 60)

    # Force mock mode if no OpenAI key
    if not settings.OPENAI_API_KEY and not settings.USE_MOCK_AGENTS:
        import os
        os.environ["USE_MOCK_AGENTS"] = "true"
        print("  No OPENAI_API_KEY — mock agents enabled")

    print("  Database: SQLite")

    # Init DB (creates tables from schema.sql)
    init_db()

    # Show available artifacts
    from .services.artifact_loader import get_available_books
    books = get_available_books()
    print(f"  Artifacts: {len(books)} book(s) — {', '.join(books) if books else 'none'}")

    print("=" * 60)
    print("  Alexandria Library ready!")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

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
    try:
        from .db.database import get_db
        db = get_db()
        db.execute("SELECT 1").fetchone()
        return {"status": "ok", "db": "sqlite"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# Error Handlers
# ---------------------------------------------------------------------------

@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return templates.TemplateResponse(
        "errors/404.html",
        {"request": request},
        status_code=404
    )


@app.exception_handler(500)
async def server_error_handler(request: Request, exc):
    return templates.TemplateResponse(
        "errors/500.html",
        {"request": request},
        status_code=500
    )
