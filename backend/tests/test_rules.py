from app.engine import Engine


def ids(items):
    return {i.id if hasattr(i, "id") else i["id"] for i in items}


def test_unknown_track_rule_predicts_and_proposes(engine: Engine):
    ev = engine.evaluate(60)
    a = next(a for a in ev.fx.alerts if a.id == "al-R01-unk-air-01")
    assert a.severity in ("warning", "critical") and "in-001" in a.inputIds
    pred = next(p for p in ev.fx.predictions if p.entityId == "unk-air-01")
    assert pred.sourceKind == "predicted" and len(pred.points) == 31 and pred.uncertaintyRing
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
    assert ev.entities["gv-01"].condition == "degraded"
    assert ev.entities["power-syd"].condition == "degraded"
    assert any("Grid Node" in n for n in ev.entities["garrison-syd"].readiness.notes)


def test_directive_raises_area_priority_and_attention(engine: Engine):
    before = engine.evaluate(300).fx.priorities.get("area-gotland", 1.0)
    after = engine.evaluate(320).fx.priorities.get("area-gotland", 1.0)
    assert after > before
    att = engine.attention(320, "regional", None)
    assert att["cells"] and att["cells"][0]["score"] >= att["cells"][-1]["score"]
    assert all(c["reasons"] for c in att["cells"][:5])


def test_every_alert_is_traceable():
    e = Engine()
    ev = e.evaluate(900)
    for a in ev.fx.alerts:
        assert a.ruleId.startswith("R") and (a.inputIds or a.entityIds)
