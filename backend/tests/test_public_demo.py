"""TROSSOPS_PUBLIC=1 (the open demo at trossops.se): visitors read but never change the shared world, the terrain proxy
(the operator's Lantmäteriet account) is rate-limited per client, and real vessels are not named next to cables."""
import time as _t


def test_public_demo_is_read_only_but_computes(client, monkeypatch):
    monkeypatch.setenv("TROSSOPS_PUBLIC", "1")
    report = {"channel": "field_report", "authorLevel": "soldier", "author": "Visitor", "title": "Test", "text": "Test"}
    for path, body in [("/api/inputs", report), ("/api/scenario/inject", {"preset": "drone_swarm"}), ("/api/alerts/x/ack", None),
                       ("/api/interventions/x/commit", {"optionId": "a", "expectedRevision": 1}), ("/api/plan/x/cancel", None)]:
        r = client.post(path, json=body)
        assert r.status_code == 403 and "Read-only public demo" in r.json()["detail"], path
    assert client.get("/api/health").status_code == 200
    assert client.post("/api/strategy/optimize").status_code == 200  # computes, changes nothing
    monkeypatch.delenv("TROSSOPS_PUBLIC")
    assert client.post("/api/inputs", json=report).status_code == 201  # local/dev behaviour unchanged


def test_public_demo_rate_limits_the_terrain_proxy(client, monkeypatch):
    from app import main
    monkeypatch.setenv("TROSSOPS_PUBLIC", "1")
    codes = [client.get("/api/terrain/elevation", params={"at": "18.07,59.33"}, headers={"x-forwarded-for": "203.0.113.7"}).status_code
             for _ in range(main.TERRAIN_PER_MIN + 3)]
    assert 429 not in codes[:main.TERRAIN_PER_MIN] and codes[-1] == 429
    other = client.get("/api/terrain/elevation", params={"at": "18.07,59.33"}, headers={"x-forwarded-for": "198.51.100.2"})
    assert other.status_code != 429  # limited per client


def test_public_demo_does_not_name_real_vessels_over_cables(monkeypatch):
    from app import feed_inputs, feeds as F
    from app.orbat import CABLES
    mid = CABLES[3]["coords"][2]
    now_ms = _t.time() * 1000
    vessel = {"id": 230000001, "name": "TEST VESSEL", "lng": mid[0], "lat": mid[1], "speedMps": 0.4, "navStatusLabel": "at anchor", "shipTypeLabel": "cargo"}
    hist = [{"timestampMs": now_ms - k * 60_000, "lng": mid[0], "lat": mid[1], "speedMps": 0.4} for k in range(30, -1, -1)]
    monkeypatch.setattr(F.AIS, "_data", {"items": [vessel]}, raising=False)
    monkeypatch.setattr(F.AIS, "history", lambda mmsi: hist)
    monkeypatch.setenv("TROSSOPS_PUBLIC", "1")
    cable = [i for i in feed_inputs._ais_cable_loiter("2026-10-21T00:00:00Z")]
    assert cable and all("TEST VESSEL" not in i.title and "230000001" not in i.id + i.title + i.text for i in cable)
    assert cable[0].title.startswith("A vessel slow over")
