from datetime import datetime, timezone

from app import inputs
from app.models import InputIn


def test_scripted_timeline_is_monotonic_and_bounded():
    epoch = datetime(2026, 1, 1, tzinfo=timezone.utc)
    early = inputs.scripted_reports(epoch, 50)
    later = inputs.scripted_reports(epoch, 700)
    assert len(early) == 2 and len(later) >= 16
    assert [r.id for r in early] == [r.id for r in later[:2]]
    channels = {r.channel for r in inputs.scripted_reports(epoch, 10_000)}
    assert len(channels) >= 12


def test_parse_input_extracts_severity_entities_tags_and_place():
    body = InputIn(channel="field_report", authorLevel="soldier", author="Pvt X", title="Fuel truck fault near Umeå",
                   text="gv-07 reports hydraulic failure on E4 near umea, convoy halted")
    r = inputs.parse_input(body, {"gv-07", "gv-08"}, datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert r.severity == "warning"
    assert r.entityRefs == ["gv-07"]
    assert {"fuel", "fault"} <= set(r.tags) and "place:umea" in r.tags
    assert r.position and abs(r.position.latitudeDeg - 63.83) < 0.01
    assert r.sourceKind == "observed"
