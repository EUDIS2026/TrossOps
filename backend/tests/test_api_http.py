"""HTTP behaviour of the API: caching validators, compression, security headers, and clear 4xx (never 5xx) on bad input."""

import json



BAD_GETS = [
    # time parameters: negative, non-finite, absurd, not a number
    "/api/scene/snapshot?at=-1", "/api/scene/snapshot?at=nan", "/api/scene/snapshot?at=inf", "/api/scene/snapshot?at=1e308",
    "/api/scene/snapshot?at=abc", "/api/scene/snapshot?role=nope", "/api/scene/snapshot?role=" + "x" * 500,
    "/api/scene/entities?at=nan", "/api/scene/entities?at=-5",
    "/api/scene/attention?at=nan", "/api/scene/attention?resolution=galactic", "/api/scene/attention?role=nope",
    "/api/scene/predictions?at=inf", "/api/scene/predictions?at=-1e9",
    "/api/alerts?at=nan", "/api/interventions?at=1e300", "/api/inputs?at=-inf", "/api/inputs?channel=" + "c" * 200,
    "/api/entities/depot-mitt?at=nan", "/api/entities/nope", "/api/entities/" + "e" * 300,
    "/api/scene/tracks/nope", "/api/scene/tracks/aw-s-03?step=0", "/api/scene/tracks/aw-s-03?step=nan",
    "/api/scene/tracks/aw-s-03?from=-1e12&to=100", "/api/scene/tracks/aw-s-03?from=0&to=1e9&step=1", "/api/scene/tracks/aw-s-03?from=x",
    "/api/sites/nope/layout", "/api/environment/forecast/atlantis", "/api/stream?interval=0", "/api/stream?interval=nan",
    "/api/live/vessels/notanumber/history", "/api/live/aircraft/zzz/trail", "/api/sources?probe=maybe", "/api/does-not-exist",
]

BAD_POSTS = [
    ("/api/inputs", None), ("/api/inputs", "not json"), ("/api/inputs", {}), ("/api/inputs", []),
    ("/api/inputs", {"channel": "field_report", "authorLevel": "soldier", "author": "a", "title": "t", "text": "x" * 20_000}),
    ("/api/inputs", {"channel": "nope", "authorLevel": "soldier", "author": "a", "title": "t", "text": "x"}),
    ("/api/inputs", {"channel": "field_report", "authorLevel": "soldier", "author": "a", "title": "t", "text": "x", "radiusM": -1}),
    ("/api/inputs", {"channel": "field_report", "authorLevel": "soldier", "author": "a", "title": "t", "text": "x",
                     "position": {"longitudeDeg": 500, "latitudeDeg": 59}}),
    ("/api/events", {"assetId": "coy-s1a-02", "kind": "explode", "expectedRevision": 1}), ("/api/events", {"assetId": "nope", "kind": "fault", "expectedRevision": 0}),
    ("/api/interventions/nope/commit", {"optionId": "x", "expectedRevision": 1}), ("/api/interventions/nope/commit", {"optionId": 3}),
    ("/api/interventions/nope/abort", None), ("/api/plan/nope/cancel", None),
    ("/api/plan/route", {"entityId": "coy-s1a-02", "to": [14.5]}), ("/api/plan/route", {"entityId": "coy-s1a-02", "to": [500, 59]}),
    ("/api/plan/route", {"entityId": "coy-s1a-02", "to": ["a", "b"]}), ("/api/plan/route", {"entityId": "nope", "to": [14.5, 56.4]}),
    ("/api/plan/route", {"entityId": "coy-s1a-02", "to": [14.5, 56.4, 3]}),
    ("/api/plan/commit", {"entityId": "coy-s1a-02", "path": [[14.5, 56.4]], "speeds": [], "expectedRevision": 1}),
    ("/api/plan/commit", {"entityId": "coy-s1a-02", "path": [[14.5], [14.6]], "speeds": [10], "expectedRevision": 1}),
    ("/api/plan/commit", {"entityId": "coy-s1a-02", "path": [[14.5, 56.4], [999, 56.5]], "speeds": [10], "expectedRevision": 1}),
    ("/api/plan/commit", {"entityId": "coy-s1a-02", "path": [[14.5, 56.4], [14.6, 56.5]], "speeds": [-3], "expectedRevision": 1}),
    ("/api/plan/commit", {"entityId": "coy-s1a-02", "path": [[14.5, 56.4], [14.6, 56.5]], "speeds": [10, 10], "expectedRevision": 1}),
    ("/api/plan/commit", {"entityId": "coy-s1a-02", "path": [[None, 56.4], [14.6, 56.5]], "speeds": [10], "expectedRevision": 1}),
    ("/api/plan/commit", {"entityId": "nope", "path": [[14.5, 56.4], [14.6, 56.5]], "speeds": [10], "expectedRevision": 1}),
    ("/api/scenario/inject", {"preset": "nope"}), ("/api/scenario/inject", {"preset": ""}), ("/api/strategy/optimize?at=nan", None),
]


def _post(client, path, body):
    if body is None:
        return client.post(path)
    if isinstance(body, str):
        return client.post(path, content=body, headers={"content-type": "application/json"})
    return client.post(path, json=body)


def test_bad_input_is_a_clear_4xx_and_never_mutates(client):
    before = client.get("/api/clock").json()["worldRevision"]
    for path in BAD_GETS:
        r = client.get(path)
        assert 400 <= r.status_code < 500, (path, r.status_code, r.text[:200])
        assert isinstance(r.json()["detail"], str), path
    for path, body in BAD_POSTS:
        r = _post(client, path, body)
        assert 400 <= r.status_code < 500, (path, body, r.status_code, r.text[:200])
        assert isinstance(r.json()["detail"], str), (path, body)
    assert client.get("/api/clock").json()["worldRevision"] == before  # nothing reached the mutation log


def test_non_json_float_literals_are_rejected(client):
    """Python's json parser accepts NaN/Infinity; they must not reach the planner or the mutation log."""
    r = client.post("/api/plan/route", content='{"entityId": "coy-s1a-02", "to": [NaN, Infinity]}', headers={"content-type": "application/json"})
    assert r.status_code == 422
    body = '{"entityId": "coy-s1a-02", "path": [[14.5, 56.4], [NaN, 56.5]], "speeds": [10], "expectedRevision": 1}'
    assert client.post("/api/plan/commit", content=body, headers={"content-type": "application/json"}).status_code == 422


def test_validation_errors_are_structured(client):
    r = client.get("/api/scene/snapshot", params={"at": "nan"})
    assert r.status_code == 422
    j = r.json()
    assert "at" in j["detail"] and j["errors"][0]["loc"] == ["query", "at"] and "input" not in j["errors"][0]


def test_world_is_encoded_once_with_etag_and_gzip(client):
    r = client.get("/api/world")
    assert r.status_code == 200 and r.headers["content-encoding"] == "gzip" and "Accept-Encoding" in r.headers["vary"]
    etag = r.headers["etag"]
    assert etag.startswith('W/"') and r.headers["cache-control"] == "no-cache"
    plain = client.get("/api/world", headers={"accept-encoding": "identity"})
    assert "content-encoding" not in plain.headers and plain.headers["etag"] == etag
    assert plain.json() == r.json() and r.json()["catalogRevision"] >= 1
    assert int(r.headers["content-length"]) < len(plain.content) / 4  # wire size: gzip of ~2 MB JSON
    nm = client.get("/api/world", headers={"if-none-match": etag})
    assert nm.status_code == 304 and nm.content == b"" and nm.headers["etag"] == etag
    assert client.get("/api/world", headers={"if-none-match": 'W/"other", ' + etag.removeprefix("W/")}).status_code == 304
    assert client.get("/api/world", headers={"if-none-match": 'W/"other"'}).status_code == 200


def test_world_etag_changes_with_the_catalog(client):
    etag = client.get("/api/world").headers["etag"]
    rev = client.get("/api/clock").json()["worldRevision"]
    r = client.post("/api/plan/commit", json={"entityId": "coy-s1a-02", "path": [[14.5, 56.4], [14.6, 56.5]], "speeds": [10], "expectedRevision": rev})
    assert r.status_code == 200
    after = client.get("/api/world", headers={"if-none-match": etag})
    assert after.status_code == 200 and after.headers["etag"] != etag
    assert after.json()["catalogRevision"] == r.json()["catalogRevision"]
    assert any(p["entityId"] == "coy-s1a-02" for p in after.json()["plans"])


def test_layout_and_views_are_cacheable(client):
    lay = client.get("/api/sites/airbase-syd/layout")
    assert lay.status_code == 200 and lay.json()["siteId"] == "airbase-syd" and "max-age" in lay.headers["cache-control"]
    assert client.get("/api/sites/airbase-syd/layout", headers={"if-none-match": lay.headers["etag"]}).status_code == 304
    v = client.get("/api/views")
    assert v.status_code == 200 and v.json()["roles"] and v.headers["etag"]
    assert client.get("/api/views", headers={"if-none-match": v.headers["etag"]}).status_code == 304


def test_snapshot_and_attention_reuse_one_evaluation(client):
    a = client.get("/api/scene/snapshot", params={"at": 700}).json()
    b = client.get("/api/scene/snapshot", params={"at": 700}).json()
    for k in ("serverNow", "nowS", "live", "future"):
        a.pop(k), b.pop(k)
    assert a == b
    s = client.get("/api/scene/snapshot", params={"at": 700, "role": "regional_south"}).json()
    assert s["role"] == "regional_south" and s["scope"] and len(s["status"]) < len(a["status"])
    live = client.get("/api/scene/snapshot").json()
    assert live["live"] is True and live["future"] is False
    future = client.get("/api/scene/snapshot", params={"at": live["nowS"] + 3600}).json()
    assert future["future"] is True and future["live"] is True
    past = client.get("/api/scene/snapshot", params={"at": 0}).json()
    assert past["live"] is False and past["future"] is False
    att = client.get("/api/scene/attention", params={"at": 699.5, "resolution": "national"}).json()
    att2 = client.get("/api/scene/attention", params={"at": 700, "resolution": "national"}).json()
    assert att["atS"] == 699.5 and att2["atS"] == 700 and att["cells"] == att2["cells"] and att["resolution"] == "national"
    # a mutation invalidates the cached evaluation
    rev = a["worldRevision"]
    alert = a["alerts"][0]["id"] if a["alerts"] else None
    if alert:
        client.post(f"/api/alerts/{alert}/ack")
        c = client.get("/api/scene/snapshot", params={"at": 700}).json()
        assert c["worldRevision"] == rev + 1 and next(x for x in c["alerts"] if x["id"] == alert)["acknowledged"]


def test_security_headers_and_cors(client):
    r = client.get("/api/clock")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer"
    pre = client.options("/api/inputs", headers={"origin": "http://localhost:5173", "access-control-request-method": "POST",
                                                 "access-control-request-headers": "content-type"})
    assert pre.status_code == 200 and pre.headers["access-control-allow-origin"] == "http://localhost:5173"
    evil = client.get("/api/clock", headers={"origin": "https://evil.example"})
    assert "access-control-allow-origin" not in evil.headers


def test_forecast_respects_feeds_off(client):
    r = client.get("/api/environment/forecast/stockholm").json()
    assert r["status"] == "unavailable" and "disabled" in r["reason"]


def test_large_payloads_are_gzipped(client):
    for path in ["/api/scene/snapshot", "/api/scene/attention", "/api/alerts", "/api/inputs", "/api/interventions"]:
        r = client.get(path)
        assert r.status_code == 200
        if len(json.dumps(r.json())) > 4096:
            assert r.headers.get("content-encoding") == "gzip", path
