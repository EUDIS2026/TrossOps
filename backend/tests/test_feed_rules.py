"""Real road situations (Trafikverket) and thermal anomalies (NASA FIRMS) as rule inputs: translation, relevance
filtering, rules R21/R22 and the deception layer's thermal corroboration. Feeds are off; every test injects cached
feed payloads, so the results are deterministic."""
from datetime import datetime, timedelta, timezone

import pytest

from app import geo
from app.engine import Engine
from app.models import GeoPosition, InputIn, InputReport


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def point_along(coords, dist_m: float) -> tuple[float, float]:
    run = 0.0
    for a, b in zip(coords, coords[1:]):
        seg = geo.haversine_m(a, b)
        if run + seg >= dist_m:
            f = (dist_m - run) / (seg or 1)
            return a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f
        run += seg
    return coords[-1]


def offset(p: tuple[float, float], east_m: float = 0.0, north_m: float = 0.0) -> tuple[float, float]:
    return geo.destination(geo.destination(p, 90, east_m), 0, north_m) if east_m or north_m else p


@pytest.fixture()
def feeds_cache(monkeypatch):
    """Empty caches for every feed the engine reads, then the test fills Trafikverket / FIRMS."""
    from app import feed_inputs, feeds as F
    for f in (F.SMHI_WARNINGS, F.POLISEN, F.ADSB, F.AIS, F.TRAFIKVERKET, F.FIRMS):
        monkeypatch.setattr(f, "_data", {"items": []}, raising=False)
    monkeypatch.setattr(F.ADSB, "gnss", lambda: [])
    feed_inputs._MEMO.clear()

    def fill(road=None, fires=None):
        if road is not None:
            monkeypatch.setattr(F.TRAFIKVERKET, "_data", {"items": road}, raising=False)
        if fires is not None:
            monkeypatch.setattr(F.FIRMS, "_data", {"items": fires}, raising=False)
        feed_inputs._MEMO.clear()
    return fill


def wire(engine: Engine) -> None:
    from app import feed_inputs
    engine.external_inputs = feed_inputs.inputs_for_engine
    engine._cache = None


def road(rid, kind, p, *, start=None, end=None, code=2, road_no="E4", msg="Vägen är avstängd."):
    return {"id": rid, "type": kind, "severity": "Stor påverkan" if code >= 4 else "Liten påverkan", "severityCode": code, "message": msg, "roadNumber": road_no,
            "location": "Testby", "lng": p[0], "lat": p[1], "start": start, "end": end}


def fire(fid, p, when: datetime, *, frp=25.0, conf="n", dn="D", sat="N20"):
    return {"id": fid, "lng": p[0], "lat": p[1], "frpMw": frp, "brightnessK": 340.0, "confidence": conf, "acquired": when.strftime("%Y-%m-%dT%H:%M:00Z"),
            "satellite": sat, "daynight": dn, "source": "VIIRS_NOAA20_NRT"}


# ---- translation -------------------------------------------------------------------------------------------------------
def test_road_situations_respect_time_validity_and_grade(feeds_cache):
    from app import feed_inputs
    n = now_utc()
    iso = lambda d: d.isoformat()  # noqa: E731
    feeds_cache(road=[
        road("live", "Hinder", (15.0, 58.0), start=iso(n - timedelta(hours=1)), end=iso(n + timedelta(hours=2))),
        road("ended", "Hinder", (15.0, 58.0), start=iso(n - timedelta(hours=3)), end=iso(n - timedelta(minutes=5))),
        road("later", "Restriktion", (15.0, 58.0), start=iso(n + timedelta(hours=10))),
        road("soon", "Restriktion", (15.0, 58.0), start=iso(n + timedelta(hours=2)), code=5),
        road("stale-acc", "Olycka", (15.0, 58.0), start=iso(n - timedelta(hours=20))),
        road("local-time", "Olycka", (15.0, 58.0), start=(n - timedelta(hours=1)).astimezone(timezone(timedelta(hours=2))).isoformat()),
        {"id": "nopos", "type": "Hinder", "lng": None, "lat": None},
        {"id": "other", "type": "Vägarbete", "lng": 15.0, "lat": 58.0},
    ])
    ins = {i.id: i for i in feed_inputs.inputs_for_engine(0)}
    assert set(ins) == {"in-x-tv-live", "in-x-tv-soon", "in-x-tv-local-time"}
    live = ins["in-x-tv-live"]
    assert live.channel == "road_situation" and live.severity == "advisory" and live.sourceKind == "public" and "obstruction" in live.tags
    assert any(t.startswith("valid_to:") for t in live.tags) and "until" in live.text
    assert ins["in-x-tv-soon"].severity == "advisory"  # restriction (info) raised one step by Trafikverket impact 5
    assert ins["in-x-tv-local-time"].effectiveAt.endswith("+00:00")  # instants normalised to UTC


def test_firms_detections_cluster_per_heat_source_with_stable_ids_and_caveat(feeds_cache):
    from app import feed_inputs
    n = now_utc()
    p = (16.5, 59.5)
    feeds_cache(fires=[
        fire("a", p, n - timedelta(hours=10), dn="N", sat="N"),
        fire("b", offset(p, 400), n - timedelta(hours=2), frp=40.0),
        fire("c", offset(p, 0, 700), n - timedelta(hours=2), sat="N21"),
        fire("low", (18.0, 60.0), n - timedelta(hours=1), conf="l"),
        fire("old", (18.5, 60.5), n - timedelta(hours=30)),
        fire("far", (20.0, 63.0), n - timedelta(hours=1), frp=3.0),
    ])
    ins = {i.id: i for i in feed_inputs.inputs_for_engine(0) if i.channel == "thermal_anomaly"}
    assert set(ins) == {"in-x-firms-a", "in-x-firms-far"}  # low confidence and > 24 h dropped; three detections are one source
    src = ins["in-x-firms-a"]
    assert "3 VIIRS detection(s)" in src.text and "40" in src.title and src.severity == "advisory" and "persistent" in src.tags
    assert "not fire" in src.text and "flares" in src.text
    assert ins["in-x-firms-far"].severity == "info"  # < 10 MW


def test_parse_input_tags_explosion_and_fire_claims_but_not_negations():
    from app.inputs import parse_input
    when = now_utc()

    def tags(text):
        return parse_input(InputIn(channel="field_report", authorLevel="soldier", author="t", title="Report", text=text), set(), when).tags
    assert "explosion" in tags("Loud explosion heard near the depot")
    assert "fire" in tags("Building on fire, flames visible")
    assert "fire" not in tags("No fire reported. Weapon fired twice at the range.")
    assert "fire" not in tags("Firewall alarm on the comms node")


# ---- relevance ---------------------------------------------------------------------------------------------------------
def test_unrelated_nationwide_items_are_dropped_before_they_reach_the_picture(engine: Engine, feeds_cache):
    site, sp = lonely_site(engine)
    n = now_utc()
    feeds_cache(road=[road("near-site", "Olycka", offset(sp, 2_000), start=n.isoformat()), road("nowhere", "Hinder", (14.0, 68.3), start=n.isoformat())],
                fires=[fire("site-fire", offset(sp, 0, 6_000), n - timedelta(hours=1)), fire("arctic", (24.0, 68.9), n - timedelta(hours=1))])
    wire(engine)
    ev = engine.evaluate(engine.now_s())
    ids = {i.id for i in ev.inputs}
    assert {"in-x-tv-near-site", "in-x-firms-site-fire"} <= ids
    assert "in-x-tv-nowhere" not in ids and "in-x-firms-arctic" not in ids


# ---- R21 ---------------------------------------------------------------------------------------------------------------
def line_length(coords) -> float:
    return sum(geo.haversine_m(a, b) for a, b in zip(coords, coords[1:]))


def column(engine: Engine):
    """The moving own column with the longest route ahead (at least 45 km beyond its lead)."""
    t = engine.now_s()
    cols = engine.columns_at(engine.entities_at(t), t)
    best = max(cols, key=lambda c: line_length(c["ahead"]) - c["lengthM"])
    assert line_length(best["ahead"]) - best["lengthM"] > 45_000, "the scenario has own road marches in motion"
    return best


def lonely_site(engine: Engine):
    """An own facility with no other own site within 20 km, so 'nearest site' is unambiguous."""
    ents = engine.entities_at(engine.now_s())
    sites = [e for e in ents.values() if e.affiliation == "own" and e.kind in ("facility", "infrastructure") and e.position]
    for s in sites:
        sp = (s.position.longitudeDeg, s.position.latitudeDeg)
        if s.kind == "facility" and all(o is s or geo.haversine_m(sp, (o.position.longitudeDeg, o.position.latitudeDeg)) > 20_000 for o in sites):
            return s, sp
    raise AssertionError("no isolated own site")


def test_r21_obstruction_ahead_of_a_column_proposes_a_reroute(engine: Engine, feeds_cache):
    col = column(engine)
    ahead = point_along(col["ahead"], col["lengthM"] + 8_000)
    n = now_utc()
    off = next(q for q in (offset(ahead, e, nn) for e, nn in ((1_500, 0), (-1_500, 0), (0, 1_500), (0, -1_500), (1_100, 1_100)))
               if all(geo.project_on_line(q, c["ahead"])[0] > 1_000 for c in engine.columns_at(engine.entities_at(engine.now_s()), engine.now_s())))
    feeds_cache(road=[road("block", "Hinder", offset(ahead, 120), start=(n - timedelta(hours=1)).isoformat(), end=(n + timedelta(hours=3)).isoformat()),
                      road("off-route", "Hinder", off, start=n.isoformat())])
    wire(engine)
    ev = engine.evaluate(engine.now_s())
    a = next(a for a in ev.fx.alerts if a.ruleId == "R21" and a.id.startswith("al-R21-") and "in-x-tv-block" in a.inputIds)
    assert a.severity == "warning" and "blocks the march route" in a.detail and "500 m" in a.detail and "Re-plan the march" in a.detail
    assert "in-x-tv-off-route" not in a.inputIds  # 1.5 km from the road: a different road
    assert set(a.entityIds) & set(col["entityIds"])
    iv = next(i for i in ev.fx.interventions if i.alertId == a.id)
    titles = [o.title for o in iv.options]
    assert any(t.startswith("Re-route") for t in titles) and any(t.startswith("Hold") for t in titles)
    hold = next(o for o in iv.options if o.title.startswith("Hold"))
    assert "expects it to end" in hold.rationale and all(o.id.startswith(f"opt-{o.assignedEntityIds[0]}") for o in iv.options)
    tr = next(t for t in ev.fx.traces if t["rule"] == "R21" and "in-x-tv-block" in t["inputs"])
    assert tr["thresholdM"] == 500 and tr["distancesM"][0] < 500


def test_r21_respects_time_validity_against_the_column_arrival(engine: Engine, feeds_cache):
    col = column(engine)
    n = now_utc()
    far = point_along(col["ahead"], col["lengthM"] + 40_000)  # ~45 min ahead at march speed
    feeds_cache(road=[road("clears", "Hinder", far, start=(n - timedelta(hours=1)).isoformat(), end=(n + timedelta(minutes=5)).isoformat()),
                      road("restr", "Restriktion", point_along(col["ahead"], col["lengthM"] + 20_000), start=n.isoformat())])
    wire(engine)
    ev = engine.evaluate(engine.now_s())
    a = next(a for a in ev.fx.alerts if a.ruleId == "R21" and "in-x-tv-clears" in a.inputIds)
    assert a.severity == "advisory" and "expected clear" in a.detail and "may restrict heavy or tracked vehicles" in a.detail
    assert not any(i.alertId == a.id for i in ev.fx.interventions)  # nothing blocking: no re-route proposal


def test_r21_accident_near_an_own_site_is_context(engine: Engine, feeds_cache):
    site, sp = lonely_site(engine)
    feeds_cache(road=[road("acc", "Olycka", offset(sp, 3_000), start=now_utc().isoformat(), code=4)])
    wire(engine)
    ev = engine.evaluate(engine.now_s())
    a = next(a for a in ev.fx.alerts if a.id == "al-R21-in-x-tv-acc")
    assert a.severity == "advisory" and site.id in a.entityIds and "km from" in a.detail and "within 5 km" in a.detail


# ---- R22 ---------------------------------------------------------------------------------------------------------------
def test_r22_heat_source_near_a_site_is_a_warning_with_the_flare_caveat(engine: Engine, feeds_cache):
    site, sp = lonely_site(engine)
    n = now_utc()
    feeds_cache(fires=[fire("near", offset(sp, 1_500), n - timedelta(hours=1)), fire("mid", offset(sp, 0, -8_000), n - timedelta(hours=1)),
                       fire("mid-n", offset(sp, 0, -8_200), n - timedelta(hours=9), dn="N")])
    wire(engine)
    ev = engine.evaluate(engine.now_s())
    near = next(a for a in ev.fx.alerts if a.id == "al-R22-in-x-firms-near")
    assert near.severity == "warning" and "< 3 km: warning" in near.detail and "VIIRS detects heat, not fire" in near.detail and site.id in near.entityIds
    mid = next(a for a in ev.fx.alerts if a.id.startswith("al-R22-in-x-firms-mid"))
    assert mid.severity == "info" and "persistent heat" in mid.detail  # 10 km band advisory, day+night persistent: one step lower


def test_r22_heat_on_a_column_route_is_an_advisory(engine: Engine, feeds_cache):
    col = column(engine)
    p = point_along(col["ahead"], col["lengthM"] + 15_000)
    feeds_cache(fires=[fire("route", offset(p, 800), now_utc() - timedelta(hours=1))])
    wire(engine)
    ev = engine.evaluate(engine.now_s())
    a = next(a for a in ev.fx.alerts if a.id == "al-R22-in-x-firms-route")
    assert a.severity in ("advisory", "warning") and "km from the route of" in a.detail and "(< 2 km)" in a.detail
    assert set(a.entityIds) & set(col["entityIds"])


# ---- deception: thermal corroboration ------------------------------------------------------------------------------------
def claim(engine: Engine, rid: str, p, hours_ago: float, title="Explosion reported at the harbour") -> InputReport:
    ts = (now_utc() - timedelta(hours=hours_ago)).isoformat()
    r = InputReport(id=rid, channel="public_news", authorLevel="media", author="test", receivedAt=ts, effectiveAt=ts, severity="warning", title=title,
                    text="Social media posts describe a large explosion.", position=GeoPosition(longitudeDeg=p[0], latitudeDeg=p[1]), radiusM=3_000,
                    tags=["explosion"], sourceKind="simulated")
    engine.posted.append(r)
    engine._cache = None
    return r


def test_thermal_anomaly_corroborates_or_weakly_contradicts_an_explosion_report(engine: Engine, feeds_cache):
    n = now_utc()
    hit_p, miss_p, pre_p = (12.2, 57.9), (13.6, 55.7), (16.9, 58.6)
    claim(engine, "in-t-boom", hit_p, 3)
    claim(engine, "in-t-nothing", miss_p, 3)
    claim(engine, "in-t-preexisting", pre_p, 3)
    feeds_cache(fires=[fire("hit", offset(hit_p, 1_200), n - timedelta(hours=2)),
                       fire("pre", offset(pre_p, 900), n - timedelta(hours=9)), fire("pre2", offset(pre_p, 950), n - timedelta(hours=1)),
                       fire("elsewhere", (25.0, 65.0), n - timedelta(hours=1), frp=2.0)])  # evidences a later overpass, then dropped as irrelevant
    wire(engine)
    ev = engine.evaluate(engine.now_s())
    assert "in-x-firms-elsewhere" not in {i.id for i in ev.inputs}
    boom = {i["id"]: i for i in ev.fx.deception["in-t-boom"]["indicators"]}
    assert boom["N6"]["weight"] == -1.0 and "in-x-firms-hit" in boom["N6"]["evidence"] and "D15" not in boom
    nothing = {i["id"]: i for i in ev.fx.deception["in-t-nothing"]["indicators"]}
    assert nothing["D15"]["weight"] == 0.4 and "Weak evidence" in nothing["D15"]["evidence"] and "N6" not in nothing
    pre = {i["id"]: i for i in ev.fx.deception["in-t-preexisting"]["indicators"]}
    assert "N6" not in pre and "pre-existing" in pre["D15"]["evidence"]
    assert ev.fx.deception["in-t-boom"]["probability"] < ev.fx.deception["in-t-nothing"]["probability"]
    assert "check NASA FIRMS after the next VIIRS overpass" in ev.fx.deception["in-t-nothing"]["wouldChange"]


def test_no_thermal_verdict_without_a_later_overpass_or_with_feeds_off(engine: Engine, feeds_cache):
    p = (12.2, 57.9)
    claim(engine, "in-t-fresh", p, 0.1)
    feeds_cache(fires=[fire("earlier", (25.0, 65.0), now_utc() - timedelta(hours=2))])  # last pass before the claim
    wire(engine)
    ind = {i["id"] for i in engine.evaluate(engine.now_s()).fx.deception["in-t-fresh"]["indicators"]}
    assert not {"N6", "D15"} & ind
    feeds_cache(fires=[])
    engine._cache = None
    ind = {i["id"] for i in engine.evaluate(engine.now_s()).fx.deception["in-t-fresh"]["indicators"]}
    assert not {"N6", "D15"} & ind


def test_new_channels_are_graded_and_broken_feed_items_never_break_evaluation(engine: Engine, feeds_cache):
    from app.fusion import grade
    from app.inputs import CHANNEL_META
    assert {"road_situation", "thermal_anomaly"} <= set(CHANNEL_META)
    assert grade("road_situation", ["real"]) == ("A", 2) and grade("thermal_anomaly", ["real"]) == ("B", 3)
    feeds_cache(road=[{"id": "x", "type": "Hinder", "lng": "not-a-number", "lat": 58.0, "start": "garbage"}], fires=[{"id": "y", "lng": 15.0, "lat": 58.0, "acquired": "bad"}])
    wire(engine)
    assert engine.evaluate(engine.now_s()).fx.alerts
