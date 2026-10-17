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
    saved = {m: sys.modules.pop(m) for m in [m for m in list(sys.modules) if m.startswith("app.")]}
    import app as pkg
    saved_attrs = {k: v for k, v in vars(pkg).items() if f"app.{k}" in saved}
    from fastapi.testclient import TestClient
    from app.main import app
    try:
        with TestClient(app) as c:
            yield c
    finally:  # put the original modules back so module-level imports in other test files stay the live ones
        for mod in [m for m in list(sys.modules) if m.startswith("app.")]:
            del sys.modules[mod]
            if mod.count(".") == 1 and mod not in saved:  # imported only by the reload: unbind from the package too
                vars(pkg).pop(mod.split(".", 1)[1], None)
        sys.modules.update(saved)
        for k, v in saved_attrs.items():
            setattr(pkg, k, v)
