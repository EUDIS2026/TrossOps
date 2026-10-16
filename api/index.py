"""Vercel entry point: serves the FastAPI app from backend/ as one Python serverless function.
Local development keeps using `uvicorn app.main:app` from backend/; this file only adds the import path."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.main import app  # noqa: E402  (ASGI app discovered by the Vercel Python runtime)
