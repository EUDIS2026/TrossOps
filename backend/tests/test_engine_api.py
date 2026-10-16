import json

from app.engine import Engine


def test_revision_checked_events_and_persistence(tmp_path):
    e = Engine(tmp_path / "w.sqlite")
    assert e.revision == 1
    try:
        e.apply_event(type("E", (), {"expectedRevision": 5, "assetId": "gv-02", "kind": "fault"})())
        assert False
    except ValueError:
        pass
    from app.models import EventIn
    e.apply_event(EventIn(assetId="gv-02", kind="fault", expectedRevision=1))
    assert e.revision == 2 and e.entities_at(e.now_s() + 1)["gv-02"].condition == "unavailable"
    again = Engine(tmp_path / "w.sqlite")
    assert again.revision == 2 and again.events[0]["assetId"] == "gv-02"


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
    result = e.optimise(700)
    units = [p["unit"] for p in result["plan"] if p["unit"] and p["unit"] != "__external__"]
    assert len(units) == len(set(units))
    assert result["method"] == "hungarian" and result["alternatives"][0]["objective"] >= result["objective"] - 1e-9


def test_api_snapshot_views_and_inputs(client):
    views = client.get("/api/views").json()
    assert len(views["roles"]) >= 7 and len(views["layers"]) >= 14 and len(views["channels"]) == 14
    snap = client.get("/api/scene/snapshot", params={"at": 700, "role": "national_commander"}).json()
    assert snap["worldRevision"] == 1 and len(snap["entities"]) > 100 and snap["layerAttention"]
    south = client.get("/api/scene/snapshot", params={"at": 700, "role": "regional_south"}).json()
    assert 0 < len(south["entities"]) < len(snap["entities"])
    posted = client.post("/api/inputs", json={"channel": "field_report", "authorLevel": "soldier", "author": "Pvt Test", "title": "Drone over depot-mitt", "text": "Unknown drone observed over depot-mitt perimeter"}).json()
    assert posted["worldRevision"] == 2 and posted["input"]["entityRefs"] == ["depot-mitt"]
    detail = client.get("/api/entities/depot-mitt").json()
    assert any(i["id"] == posted["input"]["id"] for i in detail["inputs"])
    assert client.get("/api/scene/tracks/fw-01", params={"from": 0, "to": 120, "step": 30}).json()["samples"].__len__() == 5
    assert client.get("/api/scene/attention", params={"at": 700, "resolution": "national"}).json()["cells"]
    assert client.post("/api/events", json={"assetId": "gv-02", "kind": "fault", "expectedRevision": 1}).status_code == 409
    assert client.get("/api/entities/nope").status_code == 404
