from app.engine import Engine


def test_injections_spawn_tracks_and_fire_rules(tmp_path):
    e = Engine(tmp_path / "s.sqlite", start_s=1000)
    r = e.inject("drone_swarm")
    assert r["catalogRevision"] == 2 and "UAS" in r["message"]
    ev = e.evaluate(e.now_s() + 120)
    assert any(a.id == "al-R16-airbase-norr" for a in ev.fx.alerts)
    e.inject("air_raid")
    ev = e.evaluate(e.now_s() + 60)
    raid = [a for a in ev.fx.alerts if a.ruleId == "R01" and "inj" in a.id]
    assert len(raid) == 4 and any(p.threatenedEntityIds for p in ev.fx.predictions if "inj" in p.entityId)
    e.inject("gnss_jamming")
    assert any(a.ruleId == "R18" for a in e.evaluate(e.now_s() + 5).fx.alerts)
    again = Engine(tmp_path / "s.sqlite")
    assert len([x for x in again.world.entities if x.startswith("inj")]) == 10


def test_disinformation_is_scored(tmp_path):
    e = Engine(tmp_path / "d.sqlite", start_s=1000)
    e.inject("disinformation")
    ev = e.evaluate(e.now_s() + 5)
    d = next(v for k, v in ev.fx.deception.items() if k.startswith("in-j"))
    assert d["probability"] > 0.7 and {i["id"] for i in d["indicators"]} >= {"D10", "D13", "D14"}
