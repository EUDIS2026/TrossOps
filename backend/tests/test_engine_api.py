from app import geo, planner
from app.engine import Engine


def test_revision_checked_events_and_persistence(tmp_path):
    e = Engine(tmp_path / "w.sqlite")
    assert e.revision == 1
    try:
        e.apply_event(type("E", (), {"expectedRevision": 5, "assetId": "coy-s1a-02", "kind": "fault"})())
        assert False
    except ValueError:
        pass
    from app.models import EventIn
    e.apply_event(EventIn(assetId="coy-s1a-02", kind="fault", expectedRevision=1))
    assert e.revision == 2 and e.entities_at(e.now_s() + 1)["coy-s1a-02"].condition == "unavailable"
    again = Engine(tmp_path / "w.sqlite")
    assert again.revision == 2 and again.events[0]["assetId"] == "coy-s1a-02"


def test_commit_progress_and_monitoring(tmp_path):
    e = Engine(tmp_path / "c.sqlite", start_s=1000)
    ev = e.evaluate(e.now_s())
    iv = next(i for i in ev.fx.interventions if i.id == "iv-R01-unk-sea-01")
    e.commit(iv.id, iv.recommendedOptionId, e.revision)
    later = e.evaluate(e.now_s() + 3600 * 5)
    iv2 = next(i for i in later.fx.interventions if i.id == iv.id)
    assert iv2.status == "completed" and iv2.progress == 1.0 and iv2.committedOptionId == iv.recommendedOptionId


def test_optimiser_never_double_books(tmp_path):
    e = Engine(tmp_path / "o.sqlite")
    result = e.optimise(1400)
    units = [p["unit"] for p in result["plan"] if p["unit"] and p["unit"] != "__external__"]
    assert len(units) == len(set(units))
    assert result["method"] == "hungarian" and result["alternatives"][0]["objective"] >= result["objective"] - 1e-9


def test_plan_and_commit_moves_the_unit(tmp_path):
    e = Engine(tmp_path / "p.sqlite", start_s=1000)
    ev = e.evaluate(e.now_s())
    ship = ev.entities["fl-s-cor3"]
    result = planner.plan(ship, (18.2, 57.3), ev.fx.predictions, [], [])
    opt = result["options"][0]
    assert opt["distanceKm"] > 50 and opt["etaMin"] > 0 and opt["basedOn"]
    e.commit_plan("fl-s-cor3", {"path": opt["path"], "speeds": opt["speeds"], "startS": e.now_s(), "label": "test"}, e.revision)
    cat = e.catalog()
    assert cat["catalogRevision"] == 2 and any(p["entityId"] == "fl-s-cor3" for p in cat["plans"])
    later = e.evaluate(e.now_s() + opt["etaMin"] * 60 + 60).entities["fl-s-cor3"].position
    assert geo.haversine_m((later.longitudeDeg, later.latitudeDeg), (18.2, 57.3)) < 8000


def test_api_snapshot_views_and_inputs(client):
    views = client.get("/api/views").json()
    assert len(views["roles"]) >= 9 and len(views["layers"]) >= 50 and len(views["channels"]) >= 14
    layer_ids = {l["id"] for l in views["layers"]}
    assert all(set(m["layers"]) <= layer_ids for r in views["roles"] for m in r["modes"])
    world = client.get("/api/world").json()
    assert len(world["entities"]) > 1000 and world["routes"] and world["sites"]
    snap = client.get("/api/scene/snapshot", params={"at": 700, "role": "national_commander"}).json()
    assert snap["worldRevision"] == 1 and len(snap["status"]) > 900 and snap["layerAttention"]
    south = client.get("/api/scene/snapshot", params={"at": 700, "role": "regional_south"}).json()
    assert 0 < len(south["status"]) < len(snap["status"])
    posted = client.post("/api/inputs", json={"channel": "field_report", "authorLevel": "soldier", "author": "Pvt Test", "title": "Drone over depot-mitt", "text": "Unknown drone observed over depot-mitt perimeter"}).json()
    assert posted["worldRevision"] == 2 and posted["input"]["entityRefs"] == ["depot-mitt"]
    detail = client.get("/api/entities/depot-mitt").json()
    assert any(i["id"] == posted["input"]["id"] for i in detail["inputs"]) and detail["layout"]["features"]
    formation = client.get("/api/entities/fm-bde-s").json()
    assert formation["platforms"] > 100 and formation["byPlatform"]
    assert len(client.get("/api/scene/tracks/aw-s-03", params={"from": 0, "to": 120, "step": 30}).json()["samples"]) == 5
    lay = client.get("/api/sites/airbase-syd/layout").json()
    assert lay["runway"] and len(lay["spots"]["shelter"]) == 24
    assert {f["properties"]["layer"] for f in lay["features"]["features"]} >= {"infra", "logistics", "defence", "personnel"}
    assert client.get("/api/scene/attention", params={"at": 700, "resolution": "national"}).json()["cells"]
    assert client.post("/api/events", json={"assetId": "coy-s1a-02", "kind": "fault", "expectedRevision": 1}).status_code == 409
    assert client.get("/api/entities/nope").status_code == 404
