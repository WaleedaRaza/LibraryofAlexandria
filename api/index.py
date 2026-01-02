"""
Vercel Entry Point

This file is the entry point for Vercel deployment.
It imports the FastAPI app from the main module.
"""

import sys
from pathlib import Path

# Add app directory to path
app_dir = Path(__file__).parent.parent
sys.path.insert(0, str(app_dir))

from app.main import app

# Vercel expects the app to be named 'app' or 'handler'
handler = app

