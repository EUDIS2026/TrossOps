"""Live public-data feeds: parsers against trimmed REAL payloads (tests/fixtures/feeds), cache/stale/kill-switch
semantics, and the /api router. No test touches the network: every feed gets an httpx.MockTransport."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import feeds
from app.feeds import adsb, ais, aisstream, krisinfo, openmeteo, polisen, smhi, swpc
from app.feeds.base import FT_TO_M, KT_TO_MPS

FIX = Path(__file__).parent / "fixtures" / "feeds"


def fixture(name: str):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def mock(routes, calls: list | None = None) -> httpx.MockTransport:
    """routes: list of (substring-of-url, response factory | fixture name | int status)."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if calls is not None:
            calls.append(url)
        for needle, target in routes:
            if needle in url:
                if callable(target):
                    return target(request)
                if isinstance(target, int):
                    return httpx.Response(target, text="upstream says no")
                return httpx.Response(200, json=fixture(target))
        raise AssertionError(f"unexpected request {url}")

    return httpx.MockTransport(handler)


def explode(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"network call while it should be impossible: {request.url}")


@pytest.fixture(autouse=True)
def clean_feeds(monkeypatch):
    for name in ("TROSSOPS_FEEDS", "VERCEL", "AISSTREAM_API_KEY", "TRAFIKVERKET_API_KEY", "OPENSKY_CLIENT_ID",
                 "OPENSKY_CLIENT_SECRET", "FIRMS_MAP_KEY", "LANTMATERIET_TOKEN", "LANTMATERIET_CLIENT_ID", "LANTMATERIET_CLIENT_SECRET", "LANTMATERIET_USERNAME", "LANTMATERIET_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    for f in feeds.FEEDS.values():
        f.reset()
        f.transport = httpx.MockTransport(explode)
    yield
    for f in feeds.FEEDS.values():
        f.reset()
        f.transport = None


# ---- kill switch / contract ---------------------------------------------------------------------------------------------
def test_kill_switch_blocks_every_feed_without_network(monkeypatch):
    monkeypatch.setenv("TROSSOPS_FEEDS", "off")
    for f in feeds.FEEDS.values():
        body = f.get()
        assert body["status"] == "blocked", f.id
        assert "disabled by configuration" in body["note"]
        assert body["stale"] is False and body["fetchedAt"] is None
        st = f.status()
        assert set(st) >= {"id", "label", "category", "status", "lastOkAt", "lastError", "count", "licence", "url", "note", "stale"}
        assert st["category"] in {"air", "sea", "weather", "civil", "space", "terrain"}


def test_status_before_first_fetch_is_not_presented_as_working():
    assert feeds.POLISEN.status()["status"] == "adapter-only"
    assert "not fetched" in feeds.POLISEN.status()["note"]


def test_stale_on_error_serves_last_good_data():
    state = {"fail": False}

    def respond(request):
        return httpx.Response(500, text="boom") if state["fail"] else httpx.Response(200, json=fixture("polisen.json"))

    feed = feeds.POLISEN
    feed.transport = mock([("polisen.se/api/events", respond)])
    good = feed.get()
    assert good["status"] == "working" and good["stale"] is False and good["count"] == 6
    state["fail"] = True
    feed.ttl_s = 0  # expire immediately
    try:
        bad = feed.get()
    finally:
        feed.ttl_s = polisen.PolisenFeed.ttl_s
    assert bad["stale"] is True
    assert bad["status"] == "partial"
    assert "HTTP 500" in bad["lastError"]
    assert [i["id"] for i in bad["items"]] == [i["id"] for i in good["items"]]
    assert bad["fetchedAt"] == good["fetchedAt"]
    assert feed.status()["lastOkAt"] == good["fetchedAt"]


def test_error_without_data_is_blocked():
    feeds.SWPC.transport = mock([("swpc.noaa.gov", 503)])
    body = feeds.SWPC.get()
    assert body["status"] == "blocked" and body["stale"] is False
    assert "HTTP 503" in body["lastError"] and body["kp"] is None


def test_error_backoff_does_not_hammer_upstream():
    calls: list = []
    feeds.SWPC.transport = mock([("swpc.noaa.gov", 503)], calls)
    for _ in range(5):
        feeds.SWPC.get()
    assert len(calls) == 1


def test_concurrent_requests_do_not_stampede_upstream():
    calls: list = []

    def slow(request):
        time.sleep(0.2)
        return httpx.Response(200, json=fixture("swpc_kp.json"))

    feeds.SWPC.transport = mock([("swpc.noaa.gov", slow)], calls)
    results = []
    threads = [threading.Thread(target=lambda: results.append(feeds.SWPC.get()["status"])) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == ["working"] * 6
    assert len(calls) == 1


# ---- ADS-B -----------------------------------------------------------------------------------------------------------------
def test_adsb_lol_parser_units_and_flags():
    raw = {a["hex"]: a for a in fixture("adsb_lol.json")["ac"]}
    jet = adsb.normalise_adsb_lol(raw["7809aa"])
    assert jet["altM"] == round(31500 * FT_TO_M, 1) and jet["altSource"] == "geometric" and jet["altDatum"] == "MSL"
    assert jet["speedMps"] == round(577.0 * KT_TO_MPS, 2)
    assert jet["callsign"] == "CCA856" and jet["registration"] == "B-2038" and jet["type"] == "B77W"
    assert jet["category"] == "A5" and jet["emergency"] is None and jet["military"] is False
    ground = adsb.normalise_adsb_lol(raw["478899"])
    assert ground["onGround"] is True and ground["altM"] == 0.0
    baro_only = adsb.normalise_adsb_lol({"hex": "ABC123", "lat": 59.0, "lon": 18.0, "alt_baro": 10000, "baro_rate": 1000,
                                         "gs": 100, "dbFlags": 1, "emergency": "general"})
    assert baro_only["altM"] == 3048.0 and baro_only["altSource"] == "baro"
    assert baro_only["verticalRateMps"] == 5.08 and baro_only["speedMps"] == 51.44
    assert baro_only["military"] is True and baro_only["emergency"] == "general" and baro_only["id"] == "abc123"
    assert adsb.normalise_adsb_lol({"hex": "x", "alt_baro": 1000}) is None  # no position


def test_adsb_feed_merges_circles_and_classifies_gnss():
    calls: list = []
    feeds.ADSB.transport = mock([("api.adsb.lol", "adsb_lol.json")], calls)
    body = feeds.ADSB.get()
    assert body["status"] == "working" and body["primary"] == "adsb.lol"
    assert len(calls) == len(adsb.CIRCLES)  # cold start fetches every circle once
    ids = [a["id"] for a in body["items"]]
    assert len(ids) == len(set(ids)) == 7  # the same fixture served for every circle merges by hex
    samples = {s["hex"]: s for s in feeds.ADSB.gnss()}
    assert "478899" not in samples  # on ground: excluded
    assert samples["4d200e"]["degraded"] is True  # NIC 5 < 7
    assert samples["7809aa"]["degraded"] is False  # NIC 8, NACp 9
    assert not any(s["degraded"] for h, s in samples.items() if h != "4d200e")


def test_gnss_degraded_thresholds():
    base = {"source": "adsb.lol", "onGround": False, "positionType": "adsb_icao", "nic": 8, "nacp": 9}
    assert adsb.is_gnss_sample(base) and not adsb.is_degraded(base)
    assert adsb.is_degraded({**base, "nic": 6})
    assert adsb.is_degraded({**base, "nacp": 7})
    assert not adsb.is_gnss_sample({**base, "positionType": "mlat"})
    assert not adsb.is_gnss_sample({**base, "source": "opensky"})


def test_adsb_staggers_circles_after_cold_start_and_reports_rate_limit():
    calls: list = []
    feeds.ADSB.transport = mock([("api.adsb.lol", "adsb_lol.json")], calls)
    feeds.ADSB.get()
    calls.clear()
    feeds.ADSB.transport = mock([("api.adsb.lol", 429)], calls)
    feeds.ADSB.refresh(force=True)
    assert len(calls) == 1  # only the stalest circle
    body = feeds.ADSB.get()
    assert body["status"] == "partial" and "429" in body["lastError"]
    assert body["count"] == 7  # other circles' snapshots still published
    calls.clear()
    feeds.ADSB.refresh(force=True)
    assert calls == []  # cooling down after the 429: no request sent
    assert "paused" in feeds.ADSB.get()["lastError"]


def test_adsb_rate_limit_pause_doubles_with_jitter_and_resets(monkeypatch):
    clock = {"t": 1_000_000.0}
    monkeypatch.setattr(adsb.time, "time", lambda: clock["t"])
    monkeypatch.setattr(adsb.random, "uniform", lambda lo, hi: hi)  # worst-case jitter: +25 %
    state = {"code": 429}
    calls: list = []
    feeds.ADSB.transport = mock([("api.adsb.lol", lambda r: httpx.Response(state["code"], json=fixture("adsb_lol.json")))], calls)
    pauses = []
    for _ in range(5):
        feeds.ADSB.refresh(force=True)
        pauses.append(round(feeds.ADSB._cooldown_until - clock["t"], 1))
        clock["t"] = feeds.ADSB._cooldown_until + 0.1
    assert pauses == [37.5, 75.0, 150.0, 300.0, 300.0]  # 30 s doubling, capped at 240 s, x1.25 jitter
    state["code"] = 200
    feeds.ADSB.refresh(force=True)
    assert feeds.ADSB._rate_limit_strikes == 0 and feeds.ADSB.get()["status"] == "working"
    state["code"] = 420
    feeds.ADSB.refresh(force=True)
    assert feeds.ADSB._cooldown_until - clock["t"] == 37.5  # back to the first step after a success


def test_opensky_cloud_block_is_detected_fast_and_explained(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("OPENSKY_CLIENT_ID", "id")
    monkeypatch.setenv("OPENSKY_CLIENT_SECRET", "secret")
    timeouts: list = []
    calls: list = []

    def lol(request):
        if "/lat/60.5/" in str(request.url):
            return httpx.Response(420, text="slow down")
        return httpx.Response(200, json=fixture("adsb_lol.json"))

    def dropped(request):
        timeouts.append(request.extensions["timeout"]["connect"])
        raise httpx.ConnectTimeout("timed out", request=request)

    feeds.ADSB.transport = mock([("api.adsb.lol", lol), ("opensky-network.org", dropped)], calls)
    body = feeds.ADSB.get()
    assert timeouts == [3.0]  # short connect timeout, not the 8 s client default
    assert body["status"] == "partial" and body["count"] == 7
    assert "connect timeout after 3 s from auth.opensky-network.org" in body["lastError"]
    assert "blocks many cloud-provider address ranges" in body["lastError"]
    calls.clear()
    feeds.ADSB._snapshots.pop(1, None)
    feeds.ADSB._cooldown_until = 0.0
    feeds.ADSB.refresh(force=True)
    assert not [c for c in calls if "opensky" in c]  # paused for 10 min: no second wait on a blocked upstream
    assert "opensky gap fill: paused 6" in feeds.ADSB.get()["lastError"] and "cloud-provider" in feeds.ADSB.get()["lastError"]


def test_describe_reports_timeout_phase_limit_and_host():
    from app.feeds.base import describe
    req = httpx.Request("GET", "https://example.org/x", extensions={"timeout": {"connect": 2.5, "read": 8, "write": 8, "pool": 8}})
    assert describe(httpx.ConnectTimeout("t", request=req)) == "connect timeout after 2.5 s from example.org"
    assert describe(httpx.ReadTimeout("t", request=req)) == "read timeout after 8 s from example.org"
    assert describe(httpx.ReadTimeout("t")) == "read timeout after 8 s"


def test_adsb_falls_back_to_opensky():
    feeds.ADSB.transport = mock([("api.adsb.lol", 429), ("opensky-network.org/api/states/all", "opensky.json")])
    body = feeds.ADSB.get()
    assert body["primary"] == "opensky" and body["status"] == "partial"
    raw = {s[0]: s for s in fixture("opensky.json")["states"]}
    items = {a["id"]: a for a in body["items"]}
    assert set(items) <= set(raw)
    air = items["4aca84"]
    assert air["source"] == "opensky" and air["altM"] == 10401.3 and air["speedMps"] == 269.93
    assert air["verticalRateMps"] == -9.1 and air["squawk"] == "2327"
    assert items["478899"]["onGround"] is True and items["478899"]["altM"] == 0.0


def test_adsb_keyed_opensky_fills_only_rate_limited_circles(monkeypatch):
    monkeypatch.setenv("OPENSKY_CLIENT_ID", "id")
    monkeypatch.setenv("OPENSKY_CLIENT_SECRET", "secret")

    def lol(request):  # the central circle is rate-limited, the others answer
        if "/lat/60.5/" in str(request.url):
            return httpx.Response(420, text="slow down")
        return httpx.Response(200, json=fixture("adsb_lol.json"))

    feeds.ADSB.transport = mock([("api.adsb.lol", lol), ("auth.opensky-network.org", lambda r: httpx.Response(200, json={"access_token": "t", "expires_in": 1800})),
                                 ("opensky-network.org/api/states/all", lambda r: httpx.Response(200, json=sky))])
    sky = fixture("opensky.json")
    inside = list(sky["states"][3])
    inside[0], inside[5], inside[6] = "aaaaaa", 18.4, 60.6  # in the rate-limited circle, unknown to adsb.lol
    sky["states"].append(inside)
    sky["states"].append(["4acac6"] + list(sky["states"][1][1:]))  # also seen by adsb.lol: adsb.lol wins
    body = feeds.ADSB.get()
    items = {a["id"]: a for a in body["items"]}
    assert body["primary"] == "adsb.lol+opensky" and body["status"] == "working"
    assert "filled by OpenSky" in body["gapFill"]
    assert items["aaaaaa"]["source"] == "opensky" and items["4acac6"]["source"] != "opensky"
    assert "4bb4ee" not in items  # 54.8 N 25.1 E, outside the missing circle


def test_adsb_trail_ring_respects_gap(monkeypatch):
    clock = {"t": 1_000_000.0}
    monkeypatch.setattr(adsb.time, "time", lambda: clock["t"])
    ac = {"id": "abc123", "lng": 18.0, "lat": 59.0, "altM": 1000.0, "seenS": 0.0}
    for step in range(30):
        clock["t"] += 5.0  # every 5 s: only samples at least TRAIL_MIN_GAP_S apart are kept
        feeds.ADSB.on_success({"items": [{**ac, "lng": 18.0 + step * 0.01}]})
    trail = feeds.ADSB.trail("ABC123")
    assert len(trail) == len(range(0, 150, int(adsb.TRAIL_MIN_GAP_S)))
    assert all(b["t"] - a["t"] >= adsb.TRAIL_MIN_GAP_S for a, b in zip(trail, trail[1:]))
    for step in range(adsb.TRAIL_LEN + 10):
        clock["t"] += adsb.TRAIL_MIN_GAP_S
        feeds.ADSB.on_success({"items": [ac]})
    assert len(feeds.ADSB.trail("abc123")) == adsb.TRAIL_LEN


# ---- AIS --------------------------------------------------------------------------------------------------------------------
def test_digitraffic_parser_bbox_heading_and_metadata():
    calls: list = []
    feeds.AIS.transport = mock([("/api/ais/v1/locations", "digitraffic_locations.json"),
                                ("/api/ais/v1/vessels", "digitraffic_vessels.json")], calls)
    body = feeds.AIS.get()
    assert body["status"] == "working"
    items = {v["id"]: v for v in body["items"]}
    assert 273611990 not in items  # lng 32.5: outside the box
    assert len(items) == 5
    assert items[273358970]["headingDeg"] is None  # 511 = not available
    assert items[230174300]["headingDeg"] == 312
    linea = items[230174300]
    meta = {v["mmsi"]: v for v in fixture("digitraffic_vessels.json")}[230174300]
    assert linea["name"] == meta["name"].strip() and linea["shipType"] == meta["shipType"]
    assert linea["draughtM"] == round(meta["draught"] / 10, 1)
    assert items[636025365]["speedMps"] == round(8.5 * KT_TO_MPS, 2)
    assert all(v["source"] == "digitraffic" for v in items.values())
    # metadata is cached for an hour: a second (expired) fetch only asks for locations
    calls.clear()
    feeds.AIS.refresh(force=True)
    assert all("/locations" in c for c in calls)


def test_digitraffic_requires_headers():
    seen = {}

    def respond(request):
        seen.update(request.headers)
        return httpx.Response(200, json=fixture("digitraffic_locations.json") if "locations" in str(request.url)
                              else fixture("digitraffic_vessels.json"))

    feeds.AIS.transport = mock([("meri.digitraffic.fi", respond)])
    feeds.AIS.get()
    assert seen["digitraffic-user"] == "TrossOps/1.0" and "gzip" in seen["accept-encoding"]
    assert seen["user-agent"].startswith("TrossOps/1.0")


def test_ais_labels_and_sentinels():
    assert ais.ship_type_label(35) == "Military ops" and ais.ship_type_label(55) == "Law enforcement"
    assert ais.ship_type_label(64) == "Passenger" and ais.ship_type_label(79) == "Cargo" and ais.ship_type_label(84) == "Tanker"
    assert ais.ship_type_label(0) is None and ais.ship_type_label(None) is None
    assert ais.heading(511) is None and ais.heading(0) == 0 and ais.course(360) is None
    assert ais.speed_mps(102.3) is None and ais.nav_status_label(5) == "Moored"


def test_ais_history_keeps_distinct_timestamps():
    item = {"id": 123, "lng": 18.0, "lat": 59.0, "speedMps": 1.0, "courseDeg": 90.0, "headingDeg": None, "navStatus": 0,
            "timestampMs": 1000, "source": "digitraffic"}
    for ts in (1000, 1000, 2000, 1500, 3000):
        feeds.AIS.record({**item, "timestampMs": ts})
    assert [p["timestampMs"] for p in feeds.AIS.history(123)] == [1000, 2000, 3000]
    for ts in range(4000, 4000 + 100 * 1000, 1000):
        feeds.AIS.record({**item, "timestampMs": ts})
    assert len(feeds.AIS.history(123)) == ais.HISTORY_LEN


def test_merge_vessels_prefers_newest_and_fills_metadata():
    a = {"id": 1, "name": "ALFA", "lng": 18.0, "lat": 59.0, "timestampMs": 1000, "destination": None, "source": "digitraffic"}
    b = {"id": 1, "name": None, "lng": 18.1, "lat": 59.1, "timestampMs": 2000, "destination": "VISBY", "source": "aisstream"}
    merged = ais.merge_vessels([a], [b, {"id": 2, "lng": 1, "lat": 2, "timestampMs": 5}])
    one = next(v for v in merged if v["id"] == 1)
    assert one["lng"] == 18.1 and one["name"] == "ALFA" and one["destination"] == "VISBY" and one["source"] == "aisstream"
    assert len(merged) == 2


def test_aisstream_adapter_only_without_key_and_message_parsing(monkeypatch):
    st = feeds.AISSTREAM.get()
    assert st["status"] == "adapter-only" and "aisstream.io" in st["note"]
    # documented AISStream message shape (https://aisstream.io/documentation)
    msg = {"MessageType": "PositionReport",
           "MetaData": {"MMSI": 265000001, "ShipName": "TESTSHIP ", "latitude": 59.3, "longitude": 18.9,
                        "time_utc": "2026-10-17 06:00:00.123456789 +0000 UTC"},
           "Message": {"PositionReport": {"Cog": 120.5, "Sog": 10.0, "TrueHeading": 511, "NavigationalStatus": 0,
                                          "Latitude": 59.3, "Longitude": 18.9, "UserID": 265000001}}}
    stream = aisstream.AisStreamFeed(history_sink=feeds.AIS.record)
    item = stream.handle_message(msg)
    assert item["headingDeg"] is None and item["courseDeg"] == 120.5 and item["speedMps"] == round(10 * KT_TO_MPS, 2)
    assert item["name"] == "TESTSHIP" and item["source"] == "aisstream" and item["navStatusLabel"] == "Under way using engine"
    assert item["timestampMs"] == aisstream.parse_time_utc("2026-10-17 06:00:00.123456 +0000 UTC")
    assert feeds.AIS.history(265000001)[0]["source"] == "aisstream"
    outside = {**msg, "MetaData": {**msg["MetaData"]},
               "Message": {"PositionReport": {**msg["Message"]["PositionReport"], "Longitude": 40.0}}}
    assert stream.handle_message(outside) is None
    # with a key but on Vercel: no thread, a short burst per refresh instead (stubbed: no network in tests)
    monkeypatch.setenv("AISSTREAM_API_KEY", "k")
    monkeypatch.setenv("VERCEL", "1")
    bursts = []

    def fake_burst(key, seconds=aisstream.BURST_S):
        bursts.append(key)
        stream._fetched_at = stream._last_ok = time.time()

    monkeypatch.setattr(stream, "_burst", fake_burst)
    st = stream.get()
    assert bursts == ["k"] and stream._thread is None
    assert st["status"] == "working" and "serverless" in st["note"] and len(st["items"]) == 1
    stream.refresh()
    assert bursts == ["k"]  # rate-limited to one burst per BURST_EVERY_S


class FakeWebSocket:
    """Stands in for websockets.sync.client.connect(): yields scripted messages, then times out like a quiet stream."""

    def __init__(self, messages: list[dict], log: list):
        self.messages, self.log = list(messages), log

    def __call__(self, url, **kwargs):
        self.log.append(("connect", url))
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def send(self, text):
        self.log.append(("send", json.loads(text)))

    def recv(self, timeout=None):
        if not self.messages:
            raise TimeoutError
        return json.dumps(self.messages.pop(0))


def ais_position(mmsi: int, lng: float, lat: float, when: str) -> dict:
    return {"MessageType": "PositionReport",
            "MetaData": {"MMSI": mmsi, "ShipName": f"SHIP{mmsi}", "latitude": lat, "longitude": lng, "time_utc": f"{when} +0000 UTC"},
            "Message": {"PositionReport": {"Cog": 90.0, "Sog": 5.0, "TrueHeading": 90, "NavigationalStatus": 0,
                                           "Latitude": lat, "Longitude": lng, "UserID": mmsi}}}


def test_aisstream_serverless_bursts_merge_vessels_and_report_honestly(monkeypatch):
    monkeypatch.setenv("AISSTREAM_API_KEY", "k")
    monkeypatch.setenv("VERCEL", "1")
    stream = aisstream.AisStreamFeed()
    log: list = []
    seconds: list = []
    real_burst = stream._burst
    monkeypatch.setattr(stream, "_burst", lambda key, s=aisstream.BURST_S: (seconds.append(s), real_burst(key, s)))
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    earlier = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() - 120))
    stream.ws_connect = FakeWebSocket([ais_position(1, 18.0, 59.0, now), ais_position(2, 19.0, 58.0, now)], log)
    body = stream.get()
    assert seconds == [aisstream.BURST_FIRST_S]  # cold instance: longer first burst
    assert log[1][1]["APIKey"] == "k" and log[1][1]["BoundingBoxes"]
    assert body["status"] == "working" and body["count"] == 2
    assert "2 vessels held by this instance from 1 burst(s)" in body["note"] and "do not share" in body["note"]
    # second burst: a new vessel plus an OUT-OF-ORDER older report for vessel 1, which must not move it back
    stream.ws_connect = FakeWebSocket([ais_position(3, 20.0, 60.0, now), ais_position(1, 10.0, 55.0, earlier)], log)
    body = stream.get()
    assert seconds == [aisstream.BURST_FIRST_S]  # at most one burst per BURST_EVERY_S
    stream._last_burst = 0.0
    body = stream.get()
    assert seconds == [aisstream.BURST_FIRST_S, aisstream.BURST_S]
    by_id = {v["id"]: v for v in body["items"]}
    assert set(by_id) == {1, 2, 3} and by_id[1]["lng"] == 18.0
    assert "from 2 burst(s)" in body["note"]
    # a failing burst keeps the merged vessels but downgrades to partial and says why
    stream.ws_connect = FakeWebSocket([{"error": "Api Key Is Not Valid"}], log)
    stream._last_burst = 0.0
    body = stream.get()
    assert body["status"] == "partial" and body["count"] == 3 and "Api Key Is Not Valid" in body["note"]


# ---- SMHI ---------------------------------------------------------------------------------------------------------------------
def smhi_obs_routes(fail_param: int | None = None):
    def respond(request):
        p = int(str(request.url).split("/parameter/")[1].split("/")[0])
        if p == fail_param:
            return httpx.Response(500)
        return httpx.Response(200, json=fixture(f"smhi_obs_p{p}.json"))
    return mock([("opendata-download-metobs.smhi.se", respond)])


def test_smhi_observations_join_per_station():
    feeds.SMHI_OBS.transport = smhi_obs_routes()
    body = feeds.SMHI_OBS.get()
    assert body["status"] == "working"
    rows = {r["id"]: r for r in body["items"]}
    abisko = rows["188790"]
    assert abisko["name"] == "Abisko Aut" and abisko["airTempC"] == 2.9 and abisko["lat"] == 68.3538
    raw4 = {s["key"]: s for s in fixture("smhi_obs_p4.json")["station"]}
    assert abisko["windMps"] == float(raw4["188790"]["value"][0]["value"])
    assert abisko["observedAt"].endswith("Z")
    assert set(abisko) >= {"id", "name", "lng", "lat", "airTempC", "windMps", "windDirDeg", "gustMps", "visibilityM",
                           "cloudPct", "precipMm", "observedAt"}
    assert all(any(r[f] is not None for f in smhi.PARAMETERS.values()) for r in rows.values())


def test_smhi_observations_partial_when_a_parameter_fails():
    feeds.SMHI_OBS.transport = smhi_obs_routes(fail_param=12)
    body = feeds.SMHI_OBS.get()
    assert body["status"] == "partial" and body["stale"] is False and "parameter 12" in body["lastError"]
    assert all(r["visibilityM"] is None for r in body["items"]) and body["count"] > 0


def test_smhi_warnings():
    raw = fixture("smhi_warnings.json")
    feeds.SMHI_WARNINGS.transport = mock([("opendata-download-warnings.smhi.se", "smhi_warnings.json")])
    body = feeds.SMHI_WARNINGS.get()
    assert body["count"] == sum(len(e["warningAreas"]) for e in raw)
    levels = {w["level"] for w in body["items"]}
    assert levels <= {"yellow", "orange", "red", "message"} and "yellow" in levels
    wind = next(w for w in body["items"] if w["eventCode"] == "WIND_SEA")
    assert wind["validFrom"] and wind["validTo"] and wind["headline"] and wind["areaName"]
    assert wind["geometry"]["type"] in {"Polygon", "MultiPolygon", "LineString"}
    water = next(w for w in body["items"] if w["eventCode"] == "WATER_SHORTAGE")
    assert water["level"] == "message" and water["validTo"] is None and water["description"]


# ---- Open-Meteo --------------------------------------------------------------------------------------------------------------
def test_open_meteo_grid_and_parser():
    sample = fixture("openmeteo.json")
    pts = [(17.0, 59.0), (18.0, 60.0), (19.0, 61.0)]
    rows = openmeteo.normalise(pts, sample)
    assert rows[0]["lng"] == 17.0 and rows[0]["windMps"] == sample[0]["current"]["wind_speed_10m"]
    assert rows[0]["visibilityM"] == sample[0]["current"]["visibility"] and isinstance(rows[0]["weatherCode"], int)
    with pytest.raises(Exception):
        openmeteo.normalise(pts[:2], sample)
    grid = openmeteo.grid_points()
    assert len(grid) == 16 * 18 and grid[0] == (10.0, 55.0) and grid[-1] == (25.0, 68.6)

    def respond(request):
        n = len(request.url.params["latitude"].split(","))
        assert n <= openmeteo.BATCH and request.url.params["wind_speed_unit"] == "ms"
        assert request.url.params["models"] == "icon_seamless"
        return httpx.Response(200, json=[sample[i % 3] for i in range(n)])

    feeds.OPEN_METEO.transport = mock([("api.open-meteo.com", respond)])
    body = feeds.OPEN_METEO.get()
    assert body["status"] == "working" and len(body["points"]) == len(grid) and body["lngStep"] == openmeteo.LNG_STEP


# ---- RainViewer / SWPC ---------------------------------------------------------------------------------------------------
def test_rainviewer_frames():
    feeds.RAINVIEWER.transport = mock([("api.rainviewer.com", "rainviewer.json")])
    body = feeds.RAINVIEWER.get()
    raw = fixture("rainviewer.json")
    assert body["maxZoom"] == 7 and body["host"] == raw["host"]
    assert len(body["frames"]) == len(raw["radar"]["past"])
    first = body["frames"][0]
    assert first["tileUrl"] == f"{raw['host']}{raw['radar']['past'][0]['path']}/256/{{z}}/{{x}}/{{y}}/2/1_1.png"
    assert body["latest"]["time"] == raw["radar"]["past"][-1]["time"]


def test_swpc_kp_current_and_legacy_format():
    body = swpc.normalise(fixture("swpc_kp.json"))
    raw = fixture("swpc_kp.json")
    assert body["kp"] == raw[-1]["Kp"] and len(body["series24h"]) == 8
    assert body["time"].endswith("Z")
    legacy = [["time_tag", "Kp", "a_running", "station_count"], ["2026-10-16 18:00:00.000", "5.67", "48", "8"]]
    storm = swpc.normalise(legacy)
    assert storm["kp"] == 5.67 and storm["stormScale"] == "G1"
    assert "HF and GNSS degradation likely at high latitudes" in storm["impact"]


# ---- Civil -------------------------------------------------------------------------------------------------------------------
def test_polisen_parsing():
    assert polisen.parse_gps("59.602496,18.138438") == (18.138438, 59.602496)
    assert polisen.parse_gps("garbage") == (None, None) and polisen.parse_gps(None) == (None, None)
    assert polisen.parse_datetime("2026-09-30 0:00:12 +02:00") == "2026-09-30T00:00:12+02:00"
    assert polisen.parse_datetime("2026-1-6 9:05:00 +01:00") == "2026-01-06T09:05:00+01:00"
    feeds.POLISEN.transport = mock([("polisen.se/api/events", "polisen.json")])
    items = {e["id"]: e for e in feeds.POLISEN.get()["items"]}
    murder = items[656506]
    assert murder["url"].startswith("https://polisen.se/aktuellt/handelser/")
    assert murder["lng"] == 18.138438 and murder["lat"] == 59.602496
    assert murder["precision"] == "county" and murder["placeName"] == "Stockholm"
    assert "shooting" in murder["keywords"]
    assert "fire" in items[656391]["keywords"]
    assert polisen.keywords("Drönare observerad över hamnen") == ["drone"]
    assert polisen.normalise({"id": 1, "location": {"name": "Ronneby", "gps": "56.2,15.3"}})["precision"] == "municipality"


def test_krisinformation_news_and_vma():
    feeds.KRISINFO.transport = mock([("/v3/news", "krisinfo_news.json"), ("/v3/vmas", "krisinfo_vmas.json")])
    body = feeds.KRISINFO.get()
    assert body["status"] == "working" and body["vmaCount"] == 0 and body["newsCount"] == 1
    news = body["items"][0]
    raw = fixture("krisinfo_news.json")[0]
    assert news["kind"] == "news" and news["headline"] == raw["headline"] and news["url"] == raw["web"]
    assert news["areas"] == ["Sverige"] and news["lng"] is None
    # VMA in the documented v3 shape with coordinates (no live VMA was active when fixtures were captured)
    vma = krisinfo.normalise({"Identifier": "vma-1", "Headline": "VMA", "Area": [
        {"Type": "County", "Description": "Stockholms län", "Coordinate": "59.33,18.06 0"},
        {"type": "Municipality", "description": "Nacka", "coordinateObject": {"latitude": 59.31, "longitude": 18.16}}]}, "vma")
    assert vma["kind"] == "vma" and vma["areas"] == ["Stockholms län", "Nacka"]
    assert vma["lng"] == pytest.approx(18.11) and vma["lat"] == pytest.approx(59.32)
    assert krisinfo.area_point({"coordinate": "18.06 59.33"}) == (18.06, 59.33)


def test_krisinformation_partial_when_vma_fails():
    feeds.KRISINFO.transport = mock([("/v3/news", "krisinfo_news.json"), ("/v3/vmas", 502)])
    body = feeds.KRISINFO.get()
    assert body["status"] == "partial" and "vmas" in body["lastError"] and body["count"] == 1


def test_trafikverket_adapter_only_then_parses(monkeypatch):
    body = feeds.TRAFIKVERKET.get()
    assert body["status"] == "adapter-only" and "TRAFIKVERKET_API_KEY" in body["note"] and body["items"] == []
    monkeypatch.setenv("TRAFIKVERKET_API_KEY", "secret")
    seen = {}

    def respond(request):
        seen["body"] = request.content.decode()
        return httpx.Response(200, json=fixture("trafikverket_documented_shape.json"))

    feeds.TRAFIKVERKET.transport = mock([("api.trafikinfo.trafikverket.se", respond)])
    body = feeds.TRAFIKVERKET.get()
    assert 'authenticationkey="secret"' in seen["body"] and 'objecttype="Situation"' in seen["body"]
    items = {i["id"]: i for i in body["items"]}
    acc = items["SE_STA_TRISSID_1_0000001"]
    assert acc["type"] == "Olycka" and acc["lng"] == 18.0123 and acc["lat"] == 59.3456 and acc["roadNumber"] == "E4"
    closure = items["SE_STA_TRISSID_1_0000002"]
    assert closure["message"] == "Vägen avstängd" and closure["lng"] == 18.1 and closure["end"] is None


def test_trafikverket_invalid_key_is_blocked(monkeypatch):
    monkeypatch.setenv("TRAFIKVERKET_API_KEY", "bad")
    feeds.TRAFIKVERKET.transport = mock([("api.trafikinfo.trafikverket.se",
                                          lambda r: httpx.Response(401, json=fixture("trafikverket_401.json")))])
    body = feeds.TRAFIKVERKET.get()
    assert body["status"] == "blocked" and "Invalid authentication" in body["lastError"]


# ---- Router -------------------------------------------------------------------------------------------------------------------
@pytest.fixture()
def api():
    from app.routes_live import router
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as c:
        yield c


def test_router_sources_with_kill_switch(api, monkeypatch):
    monkeypatch.setenv("TROSSOPS_FEEDS", "off")
    body = api.get("/api/sources").json()
    assert body["disabled"] is True and len(body["sources"]) == len(feeds.FEEDS)
    assert {s["status"] for s in body["sources"]} == {"blocked"}
    assert any("Källa: SMHI" in line for line in body["attribution"])
    for path in ("/api/live/aircraft", "/api/live/gnss", "/api/live/vessels", "/api/env/observations", "/api/env/warnings",
                 "/api/env/grid", "/api/env/radar", "/api/env/space", "/api/civil/police", "/api/civil/crisis",
                 "/api/civil/traffic"):
        r = api.get(path)
        assert r.status_code == 200, path
        payload = r.json()
        assert {"status", "source", "licence", "fetchedAt", "stale"} <= set(payload), path
        assert payload["status"] == "blocked", path
    assert api.get("/api/live/aircraft/abc123/trail").status_code == 404
    assert api.get("/api/live/vessels/123/history").status_code == 404


def fresh_locations(request):
    """Digitraffic fixture shifted so its newest position is 'now' (history forgets positions older than 3 h)."""
    body = fixture("digitraffic_locations.json")
    shift = time.time() * 1000 - max(f["properties"]["timestampExternal"] for f in body["features"])
    for f in body["features"]:
        f["properties"]["timestampExternal"] += shift
    return httpx.Response(200, json=body)


def test_router_live_payloads(api):
    feeds.ADSB.transport = mock([("api.adsb.lol", "adsb_lol.json")])
    feeds.AIS.transport = mock([("/api/ais/v1/locations", fresh_locations),
                                ("/api/ais/v1/vessels", "digitraffic_vessels.json")])
    feeds.POLISEN.transport = mock([("polisen.se/api/events", "polisen.json")])
    aircraft = api.get("/api/live/aircraft").json()
    assert aircraft["status"] == "working" and aircraft["count"] == 7 and aircraft["fetchedAt"]
    assert api.get("/api/live/aircraft/7809AA/trail").json()["points"]
    gnss = api.get("/api/live/gnss").json()
    assert gnss["degradedCount"] == 1 and gnss["count"] == len(gnss["samples"])
    vessels = api.get("/api/live/vessels").json()
    assert vessels["count"] == 5 and vessels["streams"]["aisstream"]["status"] == "adapter-only"
    assert api.get("/api/live/vessels/230174300/history").json()["points"]
    police = api.get("/api/civil/police").json()
    assert police["status"] == "working" and police["attribution"] == "Källa: Polisen (polisen.se)"
    sources = api.get("/api/sources?probe=false").json()["sources"]
    by_id = {s["id"]: s for s in sources}
    assert by_id["adsb"]["status"] == "working" and by_id["smhi-obs"]["status"] == "adapter-only"


def test_real_traffic_pattern_indicators(monkeypatch):
    """A real vessel loitering over a cable corridor and an orbiting aircraft become neutral R19 indicators."""
    import math
    import time as _t

    from app import feed_inputs, feeds as F
    from app.orbat import CABLES
    mid = CABLES[3]["coords"][2]  # a vertex of the Finland-Germany corridor, far from its landing points
    now_ms = _t.time() * 1000
    vessel = {"id": 230000001, "name": "TEST VESSEL", "lng": mid[0], "lat": mid[1], "speedMps": 0.4, "navStatusLabel": "at anchor", "shipTypeLabel": "cargo"}
    hist = [{"timestampMs": now_ms - k * 60_000, "lng": mid[0], "lat": mid[1], "speedMps": 0.4} for k in range(30, -1, -1)]
    trail = [{"t": _t.time() - 900 + k * 30, "lng": 20.0 + 0.2 * math.cos(k / 5), "lat": 57.0 + 0.1 * math.sin(k / 5), "altM": 9000} for k in range(31)]
    monkeypatch.setattr(F.AIS, "_data", {"items": [vessel]}, raising=False)
    monkeypatch.setattr(F.AIS, "history", lambda mmsi: hist)
    monkeypatch.setattr(F.ADSB, "_data", {"items": [{"id": "abc123", "callsign": "TEST01", "type": "E3TF", "military": True, "onGround": False, "altM": 9000, "lng": 20.0, "lat": 57.0}]}, raising=False)
    monkeypatch.setattr(F.ADSB, "trail", lambda h: trail)
    monkeypatch.setattr(F.ADSB, "gnss", lambda: [])
    ins = feed_inputs.inputs_for_engine(0)
    titles = [i.title for i in ins]
    assert any("TEST VESSEL slow over" in t for t in titles) and any("TEST01 flying an orbit" in t for t in titles)
    assert all("not an assessment" in i.text for i in ins if {"cable", "orbit"} & set(i.tags))


def test_krisinfo_decodes_mislabelled_latin1():
    from app.feeds.krisinfo import decode_json
    assert decode_json('[{"Headline": "Här ska vården stärkas"}]'.encode("cp1252"))[0]["Headline"] == "Här ska vården stärkas"
    assert decode_json('[{"Headline": "Här"}]'.encode("utf-8"))[0]["Headline"] == "Här"


def test_firms_csv_parsing_and_errors():
    from app.feeds.base import FeedError
    from app.feeds.firms import parse_csv
    rows = parse_csv("latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight\n"
                     "59.1,17.2,330.1,0.4,0.4,2026-10-16,0130,N20,VIIRS,n,2.0NRT,280.0,4.2,N\n", "VIIRS_NOAA20_NRT")
    assert rows[0]["lng"] == 17.2 and rows[0]["frpMw"] == 4.2 and rows[0]["acquired"] == "2026-10-16T01:30:00Z"
    try:
        parse_csv("Invalid MAP_KEY.", "VIIRS_NOAA20_NRT")
        assert False
    except FeedError:
        pass


# ---- Lantmäteriet Markhöjd ---------------------------------------------------------------------------------------------------
def test_markhojd_projection_and_resample():
    from app.feeds.markhojd import resample, to_sweref99tm
    assert to_sweref99tm(15.0, 0.0) == pytest.approx((500_000.0, 0.0), abs=1e-6)
    e, n = to_sweref99tm(18.0686, 59.3293)  # central Stockholm
    assert e == pytest.approx(674_571.9, abs=1.0) and n == pytest.approx(6_580_743.0, abs=1.0)
    pts, dist = resample([(15.0, 60.0), (15.0, 60.1), (15.2, 60.1)], 11)
    assert len(pts) == 11 and dist[0] == 0 and pts[0] == (15.0, 60.0) and pts[-1] == pytest.approx((15.2, 60.1))


def markhojd_routes(ground):
    """Mock API: ground(e, n) -> elevation; token endpoint answers client credentials."""
    def hojd(request):
        if request.method == "GET":
            e, n = float(request.url.params["e"]), float(request.url.params["n"])
            return httpx.Response(200, json={"type": "Feature", "geometry": {"type": "Point", "coordinates": [e, n, ground(e, n)]}, "properties": {"nodatavalue": -9999}})
        body = json.loads(request.content)
        assert body["crs"]["properties"]["name"] == "urn:ogc:def:crs:EPSG::3006" and len(body["coordinates"]) <= 1000
        assert request.headers["Authorization"] == "Bearer tok"
        return httpx.Response(200, json={"type": "Feature", "geometry": {"type": body["type"], "coordinates": [[e, n, ground(e, n)] for e, n in body["coordinates"]]},
                                         "properties": {"nodatavalue": -9999}})
    token = lambda r: httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})  # noqa: E731
    return [("oauth2/token", token), ("markhojd/v1/hojd", hojd)]


def test_markhojd_adapter_only_then_working(monkeypatch):
    st = feeds.MARKHOJD.status()
    assert st["status"] == "adapter-only" and "LANTMATERIET_PASSWORD" in st["note"] and st["category"] == "terrain"
    monkeypatch.setenv("LANTMATERIET_CLIENT_ID", "id")
    monkeypatch.setenv("LANTMATERIET_CLIENT_SECRET", "secret")
    feeds.MARKHOJD.transport = mock(markhojd_routes(lambda e, n: 21.5))
    body = feeds.MARKHOJD.get()
    assert body["status"] == "working" and body["probe"]["elevationM"] == 21.5
    assert feeds.MARKHOJD.elevations([(18.0, 59.3), (18.1, 59.3)]) == [21.5, 21.5]


def test_markhojd_line_of_sight_finds_a_ridge(monkeypatch):
    from app.feeds.markhojd import to_sweref99tm
    monkeypatch.setenv("LANTMATERIET_TOKEN", "tok")
    ridge_e = to_sweref99tm(15.5, 62.0)[0]
    feeds.MARKHOJD.transport = mock(markhojd_routes(lambda e, n: 300.0 if abs(e - ridge_e) < 400 else (-9999 if e < 0 else 100.0)))
    los = feeds.MARKHOJD.line_of_sight((15.3, 62.0), (15.7, 62.0), 2, 2)
    assert los["visible"] is False and los["obstruction"]["groundM"] == 300.0
    assert abs(los["obstruction"]["lng"] - 15.5) < 0.02
    high = feeds.MARKHOJD.line_of_sight((15.3, 62.0), (15.7, 62.0), 600, 600)
    assert high["visible"] is True and high["minClearanceM"] > 0


def test_planner_terrain_annotation_flags_low_clearance():
    from app import planner

    class FakeTerrain:
        def elevations(self, pts):
            return [900.0 for _ in pts]

        def profile(self, coords, samples):
            return {"distanceM": [0, 1], "groundM": [10.0, 50.0], "minM": 10.0, "maxM": 50.0, "climbM": 40}

    air = {"id": "direct", "airborne": True, "path": [[15, 60, 30], [15.5, 60, 1000], [16, 60, 30]], "notes": [], "basedOn": [], "risk": 0.0, "etaMin": 10, "feasible": True}
    land = {"id": "fastest", "airborne": False, "path": [[15, 60, None], [15.1, 60, None]], "notes": [], "basedOn": [], "risk": 0.0, "etaMin": 30, "feasible": True}
    result = {"options": [air, land], "recommended": "direct"}
    planner.annotate_terrain(result, FakeTerrain())
    assert air["terrain"]["minClearanceM"] == 100 and air["risk"] == 0.25 and "Terrain clearance only 100 m" in air["notes"][0]
    assert land["terrain"]["climbM"] == 40 and "total climb 40 m" in land["basedOn"][0]


def test_markhojd_basic_auth_with_geotorget_account(monkeypatch):
    import base64
    monkeypatch.setenv("LANTMATERIET_USERNAME", "user@example.org")
    monkeypatch.setenv("LANTMATERIET_PASSWORD", "pw")
    seen = []

    def hojd(request):
        seen.append(request.headers["Authorization"])
        return httpx.Response(200, json={"type": "Feature", "geometry": {"type": "Point", "coordinates": [1, 2, 33.3]}, "properties": {}})

    feeds.MARKHOJD.transport = mock([("markhojd/v1/hojd", hojd)])
    assert feeds.MARKHOJD.get()["status"] == "working"
    assert seen == ["Basic " + base64.b64encode(b"user@example.org:pw").decode()]


# ---- Edge cache headers -------------------------------------------------------------------------------------------------------
def test_edge_cache_policy_follows_feed_ttl_and_status():
    from app.feeds.base import edge_cache_header
    assert edge_cache_header(10, "working") == "max-age=5, stale-while-revalidate=10"  # ADS-B: floor of 5 s fresh
    assert edge_cache_header(30, "partial") == "max-age=15, stale-while-revalidate=30"
    assert edge_cache_header(600, "working") == "max-age=300, stale-while-revalidate=600"
    assert edge_cache_header(3600, "working") == "max-age=300, stale-while-revalidate=3600"  # capped at 5 min fresh
    for status in ("blocked", "adapter-only", ""):
        assert edge_cache_header(600, status) == "max-age=5"  # no data: brief, no stale serving


def test_router_feed_endpoints_set_edge_and_browser_cache_headers(api):
    feeds.ADSB.transport = mock([("api.adsb.lol", "adsb_lol.json")])
    feeds.SWPC.transport = mock([("swpc.noaa.gov", 503)])
    r = api.get("/api/live/aircraft")
    assert r.headers["vercel-cdn-cache-control"] == "max-age=5, stale-while-revalidate=10"
    assert r.headers["cache-control"] == "public, max-age=0, must-revalidate"  # browsers always revalidate
    body = r.json()
    assert body["generatedAt"] and body["ttlS"] == 10.0 and body["fetchedAt"] <= body["generatedAt"]
    assert api.get("/api/live/gnss").headers["vercel-cdn-cache-control"].startswith("max-age=5,")
    assert api.get("/api/env/space").headers["vercel-cdn-cache-control"] == "max-age=5"  # blocked: short, no SWR
    assert api.get("/api/live/aircraft/7809aa/trail").status_code == 200
    assert "vercel-cdn-cache-control" not in api.get("/api/live/aircraft/7809aa/trail").headers  # per-instance history
    assert "vercel-cdn-cache-control" not in api.get("/api/sources?probe=false").headers
