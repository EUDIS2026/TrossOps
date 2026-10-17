"""Correctness of the rule engine's bookkeeping: ordering, de-duplication, non-stacking penalties, stable option ids,
time handling and the explanations each output carries."""
from datetime import timedelta

from app.engine import Engine
from app.models import EventIn, GeoPosition, InputReport


def report(engine: Engine, rid: str, channel: str, title: str, *, at_s: float = 0.0, severity: str = "warning", pos=None, radius=None, refs=(), tags=(),
           text: str = "Synthetic test report.") -> InputReport:
    ts = engine.iso_at(at_s)
    r = InputReport(id=rid, channel=channel, authorLevel="operator", author="test", receivedAt=ts, effectiveAt=ts, severity=severity, title=title, text=text,  # type: ignore[arg-type]
                    position=GeoPosition(longitudeDeg=pos[0], latitudeDeg=pos[1]) if pos else None, radiusM=radius, entityRefs=list(refs), tags=list(tags), sourceKind="simulated")
    engine.posted.append(r)
    engine._cache = None
    return r


def test_monitoring_sees_interventions_from_every_rule(engine: Engine):
    """R13 used to run before R16-R19 registered their interventions, so committing a counter-UAS or cable option was never monitored."""
    ev = engine.evaluate(1400)
    iv = next(i for i in ev.fx.interventions if i.id == "iv-R16-airbase-syd")
    engine.commit(iv.id, iv.recommendedOptionId, engine.revision)
    iv2 = next(i for i in engine.evaluate(engine.now_s() + 4).fx.interventions if i.id == iv.id)
    assert iv2.status == "in_progress" and iv2.monitorAlerts, iv2


def test_option_ids_name_the_unit_so_a_commit_survives_reranking(engine: Engine):
    ev = engine.evaluate(1400)
    for iv in ev.fx.interventions:
        ids = [o.id for o in iv.options]
        assert len(ids) == len(set(ids)), iv.id
        for o in iv.options:
            if o.assignedEntityIds:
                assert o.id.startswith(f"opt-{o.assignedEntityIds[0]}")


def test_repeated_reports_merge_into_one_alert_and_one_intervention(engine: Engine):
    report(engine, "in-t-f1", "maintenance_log", "Hydraulic leak again on N1T-03", refs=("coy-n1t-03",), tags=("fault",))
    ev = engine.evaluate(1010)
    alerts = [a for a in ev.fx.alerts if a.id == "al-R03-coy-n1t-03"]
    assert len(alerts) == 1 and {"in-003", "in-t-f1"} <= set(alerts[0].inputIds) and "Also reported" in alerts[0].detail
    assert len([i for i in ev.fx.interventions if i.id == "iv-R03-coy-n1t-03"]) == 1
    assert len({i.id for i in ev.fx.interventions}) == len(ev.fx.interventions)


def test_overlapping_weather_and_outage_reports_do_not_stack(engine: Engine):
    base = engine.evaluate(1010)
    unit = next(e for e in base.entities.values() if e.affiliation == "own" and e.domain == "sea" and e.position and e.readiness
                and not base.fx.entity_status.get(e.id, {}).get("readinessDelta"))
    p = (unit.position.longitudeDeg, unit.position.latitudeDeg)
    report(engine, "in-t-w1", "weather_advisory", "Gale warning A", pos=p, radius=50_000, tags=("weather",))
    report(engine, "in-t-w2", "weather_advisory", "Gale warning B", pos=p, radius=80_000, tags=("weather",))
    report(engine, "in-t-p2", "infrastructure_status", "Grid Node Skåne second report", refs=("power-syd", "garrison-syd"), tags=("power", "outage"))
    ev = engine.evaluate(1012)
    st = ev.fx.entity_status[unit.id]
    assert st["penalties"]["weather"] == -0.1 and st["readinessDelta"] <= -0.1 and st["readinessDelta"] > -0.2 + 1e-9
    garrison = ev.fx.entity_status["garrison-syd"]
    assert garrison["penalties"]["outage:power-syd"] == -0.15


def test_forecast_weather_is_shown_but_not_yet_penalised(engine: Engine):
    base = engine.evaluate(1010)
    unit = next(e for e in base.entities.values() if e.affiliation == "own" and e.domain == "air" and e.position and e.readiness
                and not base.fx.entity_status.get(e.id, {}).get("readinessDelta"))
    p = (unit.position.longitudeDeg, unit.position.latitudeDeg)
    r = report(engine, "in-t-fc", "weather_advisory", "Storm from tonight", pos=p, radius=40_000, tags=("weather",))
    r.effectiveAt = (engine.epoch + timedelta(hours=6)).isoformat()
    ev = engine.evaluate(1012)
    a = next(a for a in ev.fx.alerts if a.id == "al-R07-in-t-fc")
    assert a.severity == "info" and "Valid from" in a.detail
    assert "weather" not in ev.fx.entity_status.get(unit.id, {}).get("penalties", {})


def test_directives_do_not_compound_and_priority_is_explained(engine: Engine):
    report(engine, "in-t-d2", "command_directive", "Priority: Gotland sector (re-issued)", refs=("area-gotland",), tags=("priority",))
    ev = engine.evaluate(1010)
    assert abs(ev.fx.priorities["area-gotland"] - 1.5 * 1.3) < 1e-6  # directive ×1.5 once, intelligence ×1.3 once
    basis = ev.fx.area_status["area-gotland"]["priorityBasis"]
    assert any("command directive" in b for b in basis) and any("intel report" in b for b in basis)


def test_units_without_comms_are_not_offered(engine: Engine):
    ev = engine.evaluate(1004)
    iv = next(i for i in ev.fx.interventions if i.id == "iv-R01-unk-sea-01")
    unit = next(o.assignedEntityIds[0] for o in iv.options if o.assignedEntityIds)
    engine.apply_event(EventIn(assetId=unit, kind="comms_loss", expectedRevision=engine.revision))
    iv2 = next(i for i in engine.evaluate(engine.now_s() + 4).fx.interventions if i.id == "iv-R01-unk-sea-01")
    assert unit not in {e for o in iv2.options for e in o.assignedEntityIds}


def test_intercept_eta_drives_success_and_outcomes(engine: Engine):
    ev = engine.evaluate(1004)
    iv = next(i for i in ev.fx.interventions if i.id == "iv-R01-unk-sea-01")
    for o in iv.options:
        if not o.assignedEntityIds:
            continue
        expected = next(b for b in o.outcomes if b.label == "expected")
        assert abs(expected.timeToEffectMin - round(o.etaMin * 1.15, 1)) <= 0.11, o
        assert "success =" in o.rationale and "→" in o.rationale


def test_mpa_offer_only_serves_surface_tracks(engine: Engine):
    ev = engine.evaluate(1004)
    for iv in ev.fx.interventions:
        if iv.id.startswith("iv-R01-unk-air"):
            assert not any(o.id.startswith("opt-allied") for o in iv.options)
    sea = [iv for iv in ev.fx.interventions if iv.id == "iv-R01-unk-sea-03"]
    assert sea and any(o.id.startswith("opt-allied") for o in sea[0].options)


def test_police_drone_report_attaches_by_position_and_corroboration_raises_severity(engine: Engine):
    site = engine.world.sites["depot-mitt"]
    report(engine, "in-t-pol", "police_event", "Drone observed near depot", severity="advisory", pos=(site[0] + 0.02, site[1]), radius=5_000, tags=("police", "drone"))
    ev = engine.evaluate(1010)
    a = next(a for a in ev.fx.alerts if a.id == "al-R16-depot-mitt")
    assert a.severity == "advisory" and "in-t-pol" in a.inputIds and "Independent channels: police event (1)" in a.detail
    assert not any(i.id == "iv-R16-depot-mitt" for i in ev.fx.interventions)
    report(engine, "in-t-fr", "field_report", "Drone over depot fence", severity="advisory", refs=("depot-mitt",), tags=("drone",))
    ev = engine.evaluate(1012)
    a = next(a for a in ev.fx.alerts if a.id == "al-R16-depot-mitt")
    assert a.severity == "warning" and "(2)" in a.detail


def test_acknowledged_alert_halves_its_attention(engine: Engine):
    before = [c.weight for c in engine.evaluate(1010).fx.attention if c.rule_id == "R06"]
    engine.ack("al-R06-in-005")
    after = [c for c in engine.evaluate(1012).fx.attention if c.rule_id == "R06"]
    assert before and abs(after[0].weight - before[0] * 0.5) < 1e-6 and after[0].reason.endswith("(acknowledged)")


def test_emergency_squawk_raises_an_alert(engine: Engine):
    report(engine, "in-t-sq", "sensor_detection", "SAS123 squawks 7700 (general emergency)", pos=(17.3, 62.3), radius=20_000, tags=("air", "squawk", "real"))
    ev = engine.evaluate(1010)
    a = next(a for a in ev.fx.alerts if a.id == "al-R20-in-t-sq")
    assert a.ruleId == "R20" and "in-005" in a.inputIds and "Corroborated" in a.detail  # the E4 bus collision 112 report is ~6 km away


def test_real_police_event_is_a_valid_input_and_a_feed_error_never_breaks_evaluation(engine: Engine, monkeypatch):
    """police_event was missing from the Channel literal: any real police drone/explosion event made every evaluation raise."""
    from datetime import datetime, timezone

    from app import feed_inputs, feeds as F
    now = datetime.now(timezone.utc).isoformat()
    monkeypatch.setattr(F.POLISEN, "_data", {"items": [{"id": 1, "datetime": now, "name": "17 oktober, Explosion, Uppsala", "summary": "Explosion reported.",
                                                          "keywords": ["explosion"], "lng": 17.64, "lat": 59.86, "precision": "municipality"}]}, raising=False)
    monkeypatch.setattr(F.ADSB, "gnss", lambda: [])
    ins = feed_inputs.inputs_for_engine(0)
    assert any(i.channel == "police_event" for i in ins)

    def broken(_t):
        raise ValueError("malformed feed item")
    engine.external_inputs = broken
    assert engine.evaluate(engine.now_s()).fx.alerts


def test_r01_explains_its_threshold(engine: Engine):
    a = next(a for a in engine.evaluate(1004).fx.alerts if a.id == "al-R01-unk-sea-01")
    assert ("critical" in a.detail or "warning" in a.detail or "No own site within" in a.detail) and "km" in a.detail
