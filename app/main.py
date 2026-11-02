"""
Alexandria Library - Application Entry Point
FastAPI app bootstrap. SQLite. Artifact-first.
"""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
from urllib.parse import urlsplit
import time
import logging

from .config import settings
from .db.database import init_db


# Create app
app = FastAPI(
    title="LibXNDR",
    description="A constrained, agent-guided reading system",
    version="2.0.0",
    docs_url="/api/docs" if settings.DEBUG else None,
    redoc_url=None,
)

# Templates
templates_path = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_path))
templates.env.globals["asset_version"] = settings.ASSET_VERSION
templates.env.globals["name_ten_enabled"] = lambda: settings.NAME_TEN_ENABLED

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
    # A session cookie cannot follow a reader from libxndr.com onto one of the
    # generated Cloud Run / Firebase preview hostnames.  Those URLs sometimes
    # escape from deployment previews and make a healthy session look signed
    # out.  Treat PUBLIC_BASE_URL as the one public origin and bring safe page
    # requests back to it before rendering anything.
    if settings.is_production and settings.PUBLIC_BASE_URL and request.url.path != "/health":
        canonical = urlsplit(settings.PUBLIC_BASE_URL)
        forwarded_host = request.headers.get("x-forwarded-host", "").split(",", 1)[0].strip()
        visible_host = (forwarded_host or request.headers.get("host", "")).split(":", 1)[0].lower()
        is_deployment_host = (
            visible_host.endswith(".run.app")
            or visible_host.endswith(".web.app")
            or visible_host.endswith(".firebaseapp.com")
        )
        if is_deployment_host and visible_host != (canonical.hostname or "").lower():
            if request.method in {"GET", "HEAD"}:
                destination = f"{settings.PUBLIC_BASE_URL.rstrip('/')}{request.url.path}"
                if request.url.query:
                    destination = f"{destination}?{request.url.query}"
                return RedirectResponse(destination, status_code=308)
            return JSONResponse(
                {"detail": "Please submit this request from libxndr.com."},
                status_code=421,
            )
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        expected_origin = (settings.PUBLIC_BASE_URL or str(request.base_url)).rstrip("/")
        request_origin = f"{request.url.scheme}://{request.url.netloc}".rstrip("/")
        allowed_origins = {expected_origin, request_origin}
        if request.headers.get("sec-fetch-site") == "cross-site" or (origin and origin.rstrip("/") not in allowed_origins):
            return JSONResponse({"detail": "Please submit this request from the library."}, status_code=403)
    response = await call_next(request)
    response.headers["X-Process-Time"] = str(time.time() - start_time)
    if not request.url.path.startswith("/static/"):
        response.headers.setdefault("Cache-Control", "private, no-store")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    csp = ("default-src 'self'; script-src 'self' https://cdnjs.cloudflare.com; "
           "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
           "font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https://*.supabase.co; "
           "connect-src 'self' https://*.supabase.co https://storage.googleapis.com; "
           "worker-src 'self' blob: https://cdnjs.cloudflare.com; "
           "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'")
    response.headers.setdefault("Content-Security-Policy", csp)
    if settings.is_production:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup_event():
    if settings.is_production:
        errors = settings.production_errors()
        if errors:
            raise RuntimeError("; ".join(errors))
    print("=" * 60)
    print("  LIBXNDR — Starting up...")
    print("=" * 60)

    # Force mock mode if no OpenAI key
    if not settings.OPENAI_API_KEY and not settings.USE_MOCK_AGENTS:
        import os
        os.environ["USE_MOCK_AGENTS"] = "true"
        print("  No OPENAI_API_KEY — mock agents enabled")

    from .db.database import is_sqlite_mode
    print(f"  Database: {'SQLite' if is_sqlite_mode() else 'Supabase'}")

    # Init DB (creates tables from schema.sql)
    init_db()

    from .services.catalog_service import CatalogService
    print(f"  Catalog: {CatalogService().get_book_count()} book files")

    print("=" * 60)
    print("  LibXNDR ready!")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

from .routes import pages, reader, library, auth, desk, contributions, account, review, finder, device_api, name_ten

app.include_router(pages.router)
app.include_router(reader.router, prefix="/read", tags=["reader"])
app.include_router(library.router, prefix="/library", tags=["library"])
app.include_router(contributions.router, prefix="/library", tags=["contributions"])
app.include_router(finder.router, prefix="/library/find", tags=["finder"])
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(account.router, prefix="/account", tags=["account"])
app.include_router(review.router, prefix="/review", tags=["review"])
app.include_router(device_api.router, prefix="/api/v1", tags=["device api"])
app.include_router(name_ten.router, prefix="/ten", tags=["name ten"])
app.include_router(desk.router, tags=["local desk"])


# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health_check():
    try:
        from .db.database import get_db, is_sqlite_mode
        if is_sqlite_mode():
            get_db().execute("SELECT 1").fetchone()
        else:
            get_db().table("users").select("id").limit(1).execute()
        from .services.catalog_service import CatalogService
        return {
            "status": "ok",
            "db": "sqlite" if is_sqlite_mode() else "supabase",
            "books": CatalogService().get_book_count(),
        }
    except Exception as e:
        logging.getLogger(__name__).error("Health check failed: %s", type(e).__name__)
        return JSONResponse({"status": "error"}, status_code=503)


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
