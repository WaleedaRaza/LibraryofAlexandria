"""
Alexandria Library - Application Factory
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from .config import settings
from .db.database import init_db


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    
    app = FastAPI(
        title="Alexandria Library",
        description="A constrained, agent-guided reading system",
        version="1.0.0",
        docs_url="/api/docs" if settings.DEBUG else None,
        redoc_url=None,
    )
    
    # Static files
    static_path = Path(__file__).parent.parent / "static"
    if static_path.exists():
        app.mount("/static", StaticFiles(directory=str(static_path)), name="static")
    
    # Initialize database
    init_db()
    
    # Register routes
    from .routes import pages, ask, reader, library, wishlist, auth
    
    app.include_router(pages.router)
    app.include_router(ask.router, prefix="/ask", tags=["ask"])
    app.include_router(reader.router, prefix="/read", tags=["reader"])
    app.include_router(library.router, prefix="/library", tags=["library"])
    app.include_router(wishlist.router, prefix="/wishlist", tags=["wishlist"])
    app.include_router(auth.router, prefix="/auth", tags=["auth"])
    
    return app


# Templates instance (shared across routes)
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

