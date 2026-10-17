from app.engine import Engine
from app.inputs import SCRIPT


def ids(items):
    return {i.id if hasattr(i, "id") else i["id"] for i in items}


def test_scripted_inputs_reference_real_entities():
    e = Engine()
    known = set(e.world.entities) | {a["id"] for a in e.world.areas}
    for s in SCRIPT:
        for ref in s.entity_refs:
            assert ref in known, (s.title, ref)


def test_unknown_track_rule_predicts_and_proposes(engine: Engine):
    ev = engine.evaluate(60)
    a = next(a for a in ev.fx.alerts if a.id == "al-R01-unk-air-01")
    assert a.severity in ("warning", "critical") and "in-001" in a.inputIds
    preds = [p for p in ev.fx.predictions if p.entityId == "unk-air-01"]
    cv = preds[0]
    assert cv.sourceKind == "predicted" and len(cv.points) == 31 and cv.uncertaintyRing and cv.hypothesis == "constant velocity"
    assert len(preds) >= 2 and abs(sum(p.probability for p in preds) - 1) < 0.05 and all(p.basedOn for p in preds)
    iv = next(i for i in ev.fx.interventions if i.id == "iv-R01-unk-air-01")
    assert iv.options and iv.recommendedOptionId in {o.id for o in iv.options}
    assert all(o.assignedEntityIds == [] or ev.entities[o.assignedEntityIds[0]].domain == "air" for o in iv.options if not o.id.startswith("opt-allied"))


def test_intel_downgrade_changes_posture(engine: Engine):
    before = next(a for a in engine.evaluate(500).fx.alerts if a.id == "al-R01-unk-air-01")
    after = next(a for a in engine.evaluate(560).fx.alerts if a.id == "al-R01-unk-air-01")
    assert before.severity in ("warning", "critical") and after.severity == "advisory"
    assert "iv-R01-unk-air-01" in ids(engine.evaluate(500).fx.interventions)
    assert "iv-R01-unk-air-01" not in ids(engine.evaluate(560).fx.interventions)


def test_fault_report_degrades_entity_and_outage_hits_dependents(engine: Engine):
    ev = engine.evaluate(120)
    assert ev.entities["coy-n1t-03"].condition == "degraded"
    assert ev.entities["power-syd"].condition == "degraded"
    assert any("Grid Node" in n for n in ev.entities["garrison-syd"].readiness.notes)


def test_directive_raises_area_priority_and_attention(engine: Engine):
    before = engine.evaluate(300).fx.priorities.get("area-gotland", 1.0)
    after = engine.evaluate(320).fx.priorities.get("area-gotland", 1.0)
    assert after > before
    att = engine.attention(320, "regional", None)
    assert att["cells"] and att["cells"][0]["score"] >= att["cells"][-1]["score"]
    assert all(c["reasons"] for c in att["cells"][:5])


def test_drone_incursion_and_cable_loiter_rules(engine: Engine):
    ev = engine.evaluate(1400)
    r16 = next(a for a in ev.fx.alerts if a.id == "al-R16-airbase-syd")
    assert r16.severity == "critical" and "unk-uas-01" in r16.entityIds
    assert any(i.id == "iv-R16-airbase-syd" and i.options for i in ev.fx.interventions)
    r17 = [a for a in ev.fx.alerts if a.ruleId == "R17"]
    assert r17 and r17[0].entityIds == ["unk-sea-03"]


def test_deception_and_fusion_are_explained(engine: Engine):
    ev = engine.evaluate(1400)
    tanker = ev.fx.deception["unk-sea-03"]
    assert tanker["probability"] >= 0.5 and {i["id"] for i in tanker["indicators"]} >= {"D5", "D6"} and tanker["wouldChange"]
    decoy = ev.fx.deception["unk-air-03"]
    assert decoy["band"] in ("likely", "very likely")
    landing = next(v for v in ev.fx.deception.values() if v["kind"] == "report" and any(i["id"] == "D14" for i in v["indicators"]))
    assert landing["probability"] > 0.6
    fz = ev.fx.fusion["unk-sea-03"]
    assert fz["corroboration"] >= 2 and all(s["grading"][0] in "ABCDEF" for s in fz["sources"]) and fz["identity"][0]["indicators"]


def test_every_alert_is_traceable():
    e = Engine()
    ev = e.evaluate(900)
    for a in ev.fx.alerts:
        assert a.ruleId.startswith("R") and (a.inputIds or a.entityIds)


def test_repeated_evaluation_does_not_drift_readiness(engine: Engine):
    first = engine.evaluate(700).entities["airbase-syd"].readiness.score
    for t in range(701, 720):
        engine.evaluate(t)
    again = engine.evaluate(720).entities["airbase-syd"].readiness.score
    assert abs(first - again) < 1e-9
    assert 0.3 < first < 1.0


def test_unknown_tracks_do_not_expose_simulator_routes(engine: Engine):
    e = engine.evaluate(100).entities["unk-air-01"]
    assert e.track is None and e.sourceKind == "observed"


def test_dark_ais_track_is_not_streamed(engine: Engine):
    rows = {r[0] for r in engine.kinematics(1800 + 1000)["rows"]}
    assert "unk-sea-03" not in rows and "unk-sea-01" in rows
