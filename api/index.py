"""Vercel entry point: serves the FastAPI app from backend/ as one Python serverless function.
Local development keeps using `uvicorn app.main:app` from backend/; this file only adds the import path."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import time  # noqa: E402

_t0 = time.perf_counter()
from app.main import BOOT, app  # noqa: E402  (ASGI app discovered by the Vercel Python runtime)

BOOT["importS"] = round(time.perf_counter() - _t0, 2)  # whole backend import incl. FastAPI and the world build
