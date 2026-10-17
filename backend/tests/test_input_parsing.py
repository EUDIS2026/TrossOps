"""Text parsing and feed time handling: keywords match whole word starts, negations do not raise severity, and real feed
times are compared as instants."""
from datetime import datetime, timedelta, timezone

from app import inputs
from app.models import InputIn

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def parse(title: str, text: str = ""):
    return inputs.parse_input(InputIn(channel="field_report", authorLevel="soldier", author="Pvt X", title=title, text=text), set(), T0)


def test_keywords_match_word_starts_only():
    r = parse("Police notice at the office window", "Engineers arrived to inspect the manpower plan.")
    assert not {"weather", "fault"} & set(r.tags)  # "police"/"notice" are not ice, "window" not wind, "engineers" not an engine fault
    assert {"weather", "fault"} <= set(parse("Ice on the road", "engine stalled").tags)


def test_negated_keywords_do_not_raise_severity():
    assert parse("Exercise update", "No casualties and no fire reported. Convoy on schedule.").severity == "info"
    assert parse("Collision on E4", "Two vehicles, no casualties").severity == "critical"  # collision itself is still critical
    assert parse("Patrol report", "Observed one vehicle without lights").severity == "advisory"


def test_police_events_are_filtered_by_instant_not_by_string(monkeypatch):
    from app import feed_inputs, feeds as F
    now = datetime.now(timezone.utc)
    local = timezone(timedelta(hours=2))
    fresh = (now - timedelta(hours=5, minutes=30)).astimezone(local).isoformat()  # 5.5 h ago, written in local time
    stale = (now - timedelta(hours=7)).astimezone(local).isoformat()
    items = [{"id": k, "datetime": d, "name": "Explosion", "summary": "", "keywords": ["explosion"], "lng": 18.0, "lat": 59.3, "precision": "municipality"}
             for k, d in ((1, fresh), (2, stale))]
    monkeypatch.setattr(F.POLISEN, "_data", {"items": items}, raising=False)
    monkeypatch.setattr(F.ADSB, "gnss", lambda: [])
    ids = {i.id for i in feed_inputs.inputs_for_engine(0)}
    assert "in-x-pol-1" in ids and "in-x-pol-2" not in ids


def test_expired_smhi_warnings_are_dropped(monkeypatch):
    from app import feed_inputs, feeds as F
    now = datetime.now(timezone.utc)
    geom = {"type": "Polygon", "coordinates": [[[18.0, 59.0], [18.5, 59.0], [18.5, 59.5], [18.0, 59.5], [18.0, 59.0]]]}
    items = [{"id": "old", "level": "yellow", "event": "Wind", "areaName": "A", "geometry": geom, "validFrom": (now - timedelta(hours=10)).isoformat(),
              "validTo": (now - timedelta(hours=1)).isoformat()},
             {"id": "open", "level": "orange", "event": "Wind", "areaName": "B", "geometry": geom, "validFrom": (now - timedelta(hours=1)).isoformat(), "validTo": None}]
    monkeypatch.setattr(F.SMHI_WARNINGS, "_data", {"items": items}, raising=False)
    monkeypatch.setattr(F.ADSB, "gnss", lambda: [])
    ids = {i.id for i in feed_inputs.inputs_for_engine(0)}
    assert "in-x-smhi-open" in ids and "in-x-smhi-old" not in ids
