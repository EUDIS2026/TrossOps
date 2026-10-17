import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture()
def engine(tmp_path):
    from app.engine import Engine
    return Engine(tmp_path / "t.sqlite", start_s=1000)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TROSSOPS_DB_PATH", str(tmp_path / "api.sqlite"))
    monkeypatch.setenv("TROSSOPS_START_S", "1000")
    monkeypatch.setenv("TROSSOPS_FEEDS", "off")
    for mod in [m for m in list(sys.modules) if m.startswith("app.")]:
        del sys.modules[mod]
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c
