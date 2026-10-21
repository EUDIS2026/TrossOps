"""Load `backend/.env` (gitignored) into the environment for local runs. Real environment variables win, so a
deployment's settings (Vercel project env) are never overridden by a stray local file."""
from __future__ import annotations

import os
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def load(path: Path = ENV_FILE) -> list[str]:
    loaded: list[str] = []
    if not path.exists():
        return loaded
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return loaded



def public_mode() -> bool:
    """TROSSOPS_PUBLIC=1: the deployment is an open public demo. The API is read-only for visitors, the terrain proxy
    (the operator's Lantmäteriet account) is rate-limited per client, and real vessels are not named in pattern
    indicators."""
    return os.environ.get("TROSSOPS_PUBLIC", "").strip().lower() in ("1", "true", "yes")


load()
