"""Fusion and deception: independent sources counted once, dependent indicators discounted, corroboration bounded in
time and space, every number explained."""
import math
from datetime import timedelta

from app import deception, rules
from app.engine import Engine
from tests.test_rules_core import report


def test_fused_track_is_not_counted_next_to_its_own_sensor_report(engine: Engine):
    ev = engine.evaluate(1000)
    fz = ev.fx.fusion["unk-air-03"]  # one sensor report (Sensor Site Syd) and the fused track from the same radars
    assert fz["corroboration"] == 1 and fz["independentSources"] == ["sensor:Sensor Site Syd"]
    track = next(s for s in fz["sources"] if s["channel"] == "sensor_track")
    assert "not counted separately" in track["gradingBasis"]
    assert all(s.get("gradingBasis") and s.get("independence") for s in fz["sources"])


def test_independent_confirmation_is_shown_as_credibility_1(engine: Engine):
    fz = engine.evaluate(1400).fx.fusion["unk-sea-03"]
    assert fz["corroboration"] >= 2
    graded = [s for s in fz["sources"] if s["inputId"]]
    assert graded and all(s["grading"].endswith("1") and "confirmed by" in s["gradingBasis"] for s in graded)


def test_real_ais_is_graded_as_self_reported(engine: Engine):
    report(engine, "in-t-ais", "sensor_detection", "VESSEL slow over cable", refs=("unk-sea-03",), tags=("ais", "cable", "real"))
    fz = engine.evaluate(1400).fx.fusion["unk-sea-03"]
    src = next(s for s in fz["sources"] if s["inputId"] == "in-t-ais")
    assert src["gradingBasis"].startswith("C3") and src["confidence"] == round(0.6 * 0.6, 2)


def test_dependent_indicators_are_discounted_and_the_sum_is_exact(engine: Engine):
    d = engine.evaluate(1400).fx.deception["unk-sea-03"]
    by = {i["id"]: i for i in d["indicators"]}
    assert by["D5"]["group"] == by["D7"]["group"] == "slow_over_cable"
    assert by["D7"]["weight"] == round(by["D7"]["rawWeight"] * deception.DEPENDENCE_DISCOUNT, 3) and by["D5"]["weight"] == by["D5"]["rawWeight"]
    assert abs(math.log(d["prior"] / (1 - d["prior"])) + sum(i["weight"] for i in d["indicators"]) - d["logOdds"]) < 0.02


def test_coordinated_orbit_needs_more_than_one_track(engine: Engine):
    ev = engine.evaluate(1400)
    d9 = next(i for i in ev.fx.deception["unk-uas-01"]["indicators"] if i["id"] == "D9")
    assert d9["evidence"].startswith("3 small UAS tracks")
    keep = {k: v for k, v in ev.entities.items() if not (k.startswith("unk-uas") and k != "unk-uas-01")}
    ctx = rules.Context(t=ev.t, now_iso=engine.iso_at(ev.t), revision=1, entities=keep, inputs=ev.inputs, areas=engine.world.areas, committed={}, acknowledged=set(),
                        cables=engine.world.cables, sites=engine.world.sites)
    alone = rules.evaluate(ctx).deception["unk-uas-01"]
    assert not any(i["id"] == "D9" for i in alone["indicators"])


def test_sensor_corroboration_must_be_close_in_time(engine: Engine):
    # in-015: sensor detection in the Öresund approaches at 430 s
    near = report(engine, "in-t-c1", "public_news", "Strange ship seen off Helsingborg", pos=(12.45, 55.97), radius=10_000, at_s=500, severity="advisory")
    late = report(engine, "in-t-c2", "public_news", "Strange ship seen off Helsingborg again", pos=(12.45, 55.97), radius=10_000, at_s=0, severity="advisory")
    late.effectiveAt = (engine.epoch + timedelta(seconds=430) + timedelta(hours=3)).isoformat()
    dec = engine.evaluate(1010).fx.deception
    assert any(i["id"] == "N3" for i in dec[near.id]["indicators"])
    ids = {i["id"] for i in dec[late.id]["indicators"]}
    assert "N3" not in ids and "D10" in ids


def test_official_channel_corroborates_a_public_report(engine: Engine):
    r = report(engine, "in-t-c3", "public_news", "Big crash on the E4 near Njurunda", pos=(17.31, 62.26), radius=10_000, at_s=140, severity="advisory")
    d = engine.evaluate(1010).fx.deception[r.id]
    n4 = next(i for i in d["indicators"] if i["id"] == "N4")
    assert "in-005" in n4["evidence"] and d["probability"] < 0.2


def test_coverage_contradiction_needs_coverage(engine: Engine):
    p = (14.6, 63.2)  # inland Jämtland, outside every modelled radar coverage circle
    ctx_areas = type("C", (), {"areas": engine.world.areas})()
    assert deception._covered(ctx_areas, p) is None and deception._covered(ctx_areas, (13.95, 55.40)) is not None
    r = report(engine, "in-t-c4", "public_news", "Landing claimed on Storsjön", pos=p, radius=10_000, at_s=10, tags=("hostile_claim", "social_media"))
    ids = {i["id"] for i in engine.evaluate(1010).fx.deception[r.id]["indicators"]}
    assert "D12" not in ids
