"""Cross-cutting contracts: the API, the frontend type mirror, the view model, the renderer's layer maps and the docs
must agree. These tests parse frontend sources with regexes on purpose (no Node needed for the backend suite)."""
from __future__ import annotations

import re
import sys
import typing
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TYPES_TS = ROOT / "frontend" / "src" / "contracts" / "types.ts"
OVERLAYS_TS = ROOT / "frontend" / "src" / "scene" / "overlays.ts"
API_DOC = ROOT / "docs" / "geospatial" / "api-contracts.md"
VOCAB = {"working", "partial", "simulated", "adapter-only", "planned", "blocked"}
LANTMATERIET_ENV = ("LANTMATERIET_TOKEN", "LANTMATERIET_CLIENT_ID", "LANTMATERIET_CLIENT_SECRET", "LANTMATERIET_USERNAME", "LANTMATERIET_PASSWORD")


@pytest.fixture(autouse=True)
def restore_app_modules():
    """The conftest `client` re-imports `app.*` with test settings. Put the original modules (and the package
    attributes that `from app import feeds` resolves) back afterwards, so suites that imported `app.feeds` at
    collection time (test_feeds) keep patching the same feed singletons the router uses."""
    saved = {k: v for k, v in sys.modules.items() if k == "app" or k.startswith("app.")}
    yield
    for k in [k for k in sys.modules if k.startswith("app.")]:
        parent, _, child = k.rpartition(".")
        if k not in saved and parent in saved and getattr(saved[parent], child, None) is sys.modules[k]:
            delattr(saved[parent], child)
        del sys.modules[k]
    sys.modules.update(saved)
    for name, mod in saved.items():
        parent, _, child = name.rpartition(".")
        if parent in saved:
            setattr(saved[parent], child, mod)


def ts_union(name: str) -> set[str]:
    m = re.search(rf"export type {name} =([^\n]*(?:\n\s*\|[^\n]*)*)", TYPES_TS.read_text(encoding="utf-8"))
    assert m, f"type {name} not found in types.ts"
    return set(re.findall(r"'([^']+)'", m.group(1)))


def ts_record_keys(const: str) -> set[str]:
    text = OVERLAYS_TS.read_text(encoding="utf-8")
    m = re.search(rf"export const {const}[^=]*=\s*\{{(.*?)\n\}}", text, re.S)
    assert m, f"{const} not found in overlays.ts"
    return set(re.findall(r"^\s*'([a-z_]+\.[a-z_]+)'\s*:", m.group(1), re.M))


# ---- regression: real police events used to crash every evaluation ----------------------------------------------------

def test_police_event_inputs_validate_and_reach_the_engine(client):
    """`feed_inputs` emits channel `police_event`; the InputReport model must accept it (it raised ValidationError, which
    took down every snapshot while a matching polisen.se event was cached)."""
    from datetime import datetime, timezone

    from app import feed_inputs
    feeds = feed_inputs.feeds  # the module feed_inputs reads (the client fixture may have reloaded app.feeds)
    now = datetime.now(timezone.utc).isoformat()
    feeds.POLISEN._data = {"items": [{"id": 9001, "datetime": now, "name": "Drönare observerad, Luleå", "summary": "Drönare över flygplatsen.",
                                      "keywords": ["drone"], "lng": 22.12, "lat": 65.58, "precision": "municipality"}]}
    try:
        ins = feed_inputs.inputs_for_engine(0)
        pol = [i for i in ins if i.channel == "police_event"]
        assert len(pol) == 1 and "drone" in pol[0].tags and pol[0].sourceKind == "public"
        r = client.get("/api/inputs", params={"channel": "police_event"})
        assert r.status_code == 200 and r.json()["count"] == 1
        assert client.get("/api/scene/snapshot").status_code == 200
    finally:
        feeds.POLISEN._data = None


def test_channel_unions_match_the_frontend():
    from app import models
    from app.inputs import CHANNEL_META
    backend = set(typing.get_args(models.Channel))
    assert ts_union("Channel") == backend
    assert set(CHANNEL_META) == set(typing.get_args(models.Channel))


def test_status_vocabulary_matches_agents_md():
    assert ts_union("FeedStatus") == VOCAB


# ---- /api/sources -------------------------------------------------------------------------------------------------------

def test_sources_lists_every_feed_with_an_honest_status(client):
    from app import feeds
    body = client.get("/api/sources").json()
    rows = {s["id"]: s for s in body["sources"]}
    assert set(rows) == set(feeds.FEEDS) and len(body["sources"]) == len(feeds.FEEDS)
    assert {"firms", "lm-markhojd", "trafikverket", "aisstream"} <= set(rows)
    for s in body["sources"]:
        assert s["status"] in VOCAB, s
        assert {"label", "category", "licence", "attribution", "url", "note", "stale", "lastOkAt", "count"} <= set(s), s["id"]
    assert len(body["attribution"]) == len(feeds.FEEDS)


@pytest.mark.parametrize("path", ["/api/env/fires", "/api/civil/traffic"])
def test_new_feed_endpoints_follow_the_feed_contract(client, path):
    payload = client.get(path).json()
    assert {"status", "source", "licence", "attribution", "fetchedAt", "stale", "items", "count"} <= set(payload)
    assert payload["status"] == "blocked" and payload["items"] == []


# ---- terrain ---------------------------------------------------------------------------------------------------------

def test_terrain_without_credentials_is_503_not_a_fake_answer(client, monkeypatch):
    for name in LANTMATERIET_ENV:
        monkeypatch.delenv(name, raising=False)
    for feeds_env in ("off", ""):
        monkeypatch.setenv("TROSSOPS_FEEDS", feeds_env)
        r = client.get("/api/terrain/elevation", params={"at": "18.07,59.33"})
        assert r.status_code == 503 and "terrain not configured" in r.json()["detail"], r.text
        r = client.get("/api/terrain/los", params={"a": "18.0,59.3", "b": "18.2,59.4"})
        assert r.status_code == 503
    assert "LANTMATERIET_USERNAME" in client.get("/api/terrain/elevation", params={"at": "18.07,59.33"}).json()["detail"]


@pytest.mark.parametrize("query", [{"at": "nonsense"}, {"at": "18.0"}, {"at": "2.35,48.86"}])
def test_terrain_rejects_bad_or_foreign_points_before_any_lookup(client, query):
    r = client.get("/api/terrain/elevation", params=query)
    assert r.status_code == 422


def test_terrain_los_validates_heights(client):
    assert client.get("/api/terrain/los", params={"a": "18.0,59.3", "b": "18.2,59.4", "ha": -1}).status_code == 422
    assert client.get("/api/terrain/los", params={"a": "18.0,59.3"}).status_code == 422


# ---- view model ↔ renderer ---------------------------------------------------------------------------------------------

def test_views_reference_only_existing_layers():
    from app import views
    ids = [l.id for l in views.LAYERS]
    assert len(ids) == len(set(ids)), "duplicate layer ids"
    groups = {i.split(".")[0] for i in ids}
    assert set(views.EXCLUSIVE_GROUPS) <= groups
    role_ids = {r.id for r in views.ROLES}
    assert set(views.REGION_SCOPE) <= role_ids
    for r in views.ROLES:
        modes = [m.id for m in r.modes]
        assert len(modes) == len(set(modes)) and r.defaultModeId in modes, r.id
        for m in r.modes:
            missing = set(m.layers) - set(ids)
            assert not missing, f"{r.id}/{m.id} references unknown layers {missing}"
            assert sum(1 for l in m.layers if l.split(".")[0] in views.EXCLUSIVE_GROUPS) <= 1, f"{r.id}/{m.id} turns on two analysis surfaces"


def test_every_layer_has_a_render_path_in_the_frontend(engine):
    """A layer is drawn by a native overlay (OVERLAY_LAYERS), a site-detail layer (DETAIL_LAYERS), the entity renderer
    (catalog entities carry `layer`), a dedicated scene renderer switched by id (`on.has('picture.labels')`), the
    live-traffic renderer (`live.*`), the analysis surface (`analysis.*`) or the unknown-track filter (`track.unknown`).
    Anything else is a switch that does nothing."""
    from app import views
    overlay, detail = ts_record_keys("OVERLAY_LAYERS"), ts_record_keys("DETAIL_LAYERS")
    assert overlay and detail
    ids = {l.id for l in views.LAYERS}
    assert overlay <= ids, f"OVERLAY_LAYERS has keys the API does not define: {overlay - ids}"
    assert detail <= ids, f"DETAIL_LAYERS has keys the API does not define: {detail - ids}"
    entity_layers = {e["layer"] for e in engine.catalog()["entities"] if e.get("layer")}
    # layers with a dedicated renderer that the scene switches by id, e.g. `on.has('picture.labels')` (GPU text layer)
    scene_src = "\n".join(f.read_text(encoding="utf-8") for f in (ROOT / "frontend" / "src" / "scene").glob("*.ts"))
    switched = set(re.findall(r"\.has\('([a-z_]+\.[a-z_]+)'\)", scene_src))
    orphans = sorted(i for i in ids if i not in overlay | detail | entity_layers | switched and not i.startswith(("live.", "analysis.")) and i != "track.unknown")
    assert not orphans, f"layers with no renderer: {orphans}"


# ---- docs ------------------------------------------------------------------------------------------------------------

def test_every_route_is_documented(client):
    from app.main import app
    doc = API_DOC.read_text(encoding="utf-8")
    paths = sorted(p for p in app.openapi()["paths"] if p.startswith("/api/"))
    undocumented = [p for p in paths if p not in doc]
    assert not undocumented, f"routes missing from docs/geospatial/api-contracts.md: {undocumented}"
