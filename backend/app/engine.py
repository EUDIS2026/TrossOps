"""Engine: scenario clock, persisted mutations, world evaluation and the revision-aware API payloads.
Scenario time `t` is seconds since the scenario epoch, advancing at `speed` × wall clock. Every read takes an
explicit `t`, so replay (`at=` in the past), simulation (`at=` in the future) and live share one code path.

Payload split (v2):
- `catalog()` — the order of battle with declared motion and the shared route geometry. Changes only when a plan
  is committed (`catalogRevision`), so the browser fetches it once and evaluates motion itself at display rate.
- `snapshot(t)` — the evaluated picture: per-entity status, alerts, interventions, predictions, inputs, areas.
- `observed(t)` — positions of tracks the operator only knows from sensors (never their simulator route).
"""
from __future__ import annotations

import json
import math
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import attention, inputs as inputs_mod, motion, optimize, rules, views
from .inputs import SEVERITY_RANK
from .models import Alert, EventIn, InputIn, InputReport, Intervention, PredictedPath, Readiness, SceneEntity
from .world import MODEL_VERSION, SCENARIO_ID, SyntheticWorld, score

DATA_NOTICE = "Synthetic national exercise: all units, sites, reports and positions are fictional. Real public feeds (air and sea traffic, SMHI, police events) are labelled as such."
EVAL_STEP_S = 2.0  # rules are evaluated on a 2 s scenario grid; motion itself is continuous


@dataclass
class Evaluation:
    t: float
    revision: int
    entities: dict[str, SceneEntity]
    inputs: list[InputReport]
    fx: rules.Effects


class Engine:
    def __init__(self, db_path: Path | None = None, seed: int = 20261016, speed: float = 1.0, epoch: datetime | None = None, start_s: float = 0.0) -> None:
        self.world = SyntheticWorld(seed)
        self.epoch = epoch or (datetime.now(timezone.utc) - timedelta(seconds=start_s / speed))
        self.speed = speed
        self.revision = 1
        self.catalog_revision = 1
        self.lock = threading.RLock()
        self.events: list[dict] = []
        self.posted: list[InputReport] = []
        self.commits: dict[str, dict] = {}
        self.acks: set[str] = set()
        self.plans: dict[str, dict] = {}  # entityId -> {"motion": MotionSpec, "plan": api dict}
        self.listeners: list = []
        self.external_inputs = lambda t: []  # real public feeds turned into inputs (wired by main)
        self._cache: tuple[tuple[int, int], Evaluation] | None = None
        self._catalog: tuple[int, dict] | None = None
        self.db: sqlite3.Connection | None = None
        if db_path is not None:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(db_path, check_same_thread=False)
            self.db.execute("CREATE TABLE IF NOT EXISTS mutations (revision INTEGER PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL, recorded_at TEXT NOT NULL, at_s REAL NOT NULL)")
            self.db.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            row = self.db.execute("SELECT value FROM meta WHERE key='epoch'").fetchone()
            ver = self.db.execute("SELECT value FROM meta WHERE key='model'").fetchone()
            stale_model = ver is not None and ver[0] != MODEL_VERSION
            if (row and epoch is not None and datetime.fromisoformat(row[0]) != epoch) or stale_model or (row and ver is None):
                # A pinned epoch or a new world model wins over the store: recorded mutations no longer apply.
                self.db.execute("DELETE FROM mutations"); self.db.execute("DELETE FROM meta"); self.db.commit()
                row = None
            if row:
                self.epoch = datetime.fromisoformat(row[0])
            else:
                self.db.execute("INSERT OR REPLACE INTO meta VALUES ('epoch', ?)", (self.epoch.isoformat(),))
            self.db.execute("INSERT OR REPLACE INTO meta VALUES ('model', ?)", (MODEL_VERSION,))
            self.db.commit()
            for revision, kind, payload, recorded_at, at_s in self.db.execute("SELECT revision, kind, payload, recorded_at, at_s FROM mutations ORDER BY revision"):
                self._replay(kind, json.loads(payload), recorded_at, at_s, revision)

    # ---- clock ---------------------------------------------------------------------------------
    def now_s(self) -> float:
        return (datetime.now(timezone.utc) - self.epoch).total_seconds() * self.speed

    def iso_at(self, t: float) -> str:
        return (self.epoch + timedelta(seconds=t / self.speed)).isoformat()

    def clock(self) -> dict:
        return {"epoch": self.epoch.isoformat(), "nowS": round(self.now_s(), 1), "serverNow": datetime.now(timezone.utc).isoformat(), "speed": self.speed,
                "worldRevision": self.revision, "catalogRevision": self.catalog_revision}

    # ---- mutations -----------------------------------------------------------------------------
    def _persist(self, kind: str, payload: dict) -> None:
        self.revision += 1
        recorded_at = datetime.now(timezone.utc).isoformat()
        at_s = self.now_s()
        if self.db is not None:
            self.db.execute("INSERT INTO mutations VALUES (?, ?, ?, ?, ?)", (self.revision, kind, json.dumps(payload), recorded_at, at_s))
            self.db.commit()
        self._replay(kind, payload, recorded_at, at_s, self.revision)
        self._cache = None
        for cb in list(self.listeners):
            cb({"type": "revision", "worldRevision": self.revision, "catalogRevision": self.catalog_revision, "kind": kind})

    def _replay(self, kind: str, payload: dict, recorded_at: str, at_s: float, revision: int) -> None:
        self.revision = max(self.revision, revision)
        if kind == "event":
            self.events.append({**payload, "worldRevision": revision, "recordedAt": recorded_at, "atS": at_s, "id": f"event-{revision}", "sourceKind": "simulated"})
        elif kind == "input":
            self.posted.append(InputReport(**payload))
        elif kind == "commit":
            self.commits[payload["interventionId"]] = {"optionId": payload["optionId"], "committedAt": recorded_at, "committedAtS": at_s, "revision": revision}
        elif kind == "abort":
            self.commits.pop(payload["interventionId"], None)
        elif kind == "ack":
            self.acks.add(payload["alertId"])
        elif kind == "plan":
            path = motion.Path([tuple(p) for p in payload["path"]], payload["speeds"])  # type: ignore[misc]
            spec = motion.MotionSpec("path", path=path, start_s=payload["startS"], mode="once", airborne=payload.get("airborne", False),
                                     fuel_start=payload.get("fuelStart"), fuel_burn_per_km=payload.get("fuelBurnPerKm", 0.0))
            self.plans[payload["entityId"]] = {"motion": spec, "plan": {**payload, "worldRevision": revision, "recordedAt": recorded_at}}
            self.catalog_revision += 1
        elif kind == "plan_cancel":
            if self.plans.pop(payload["entityId"], None):
                self.catalog_revision += 1

    def apply_event(self, event: EventIn) -> dict:
        with self.lock:
            if event.expectedRevision != self.revision:
                raise ValueError("revision")
            if event.assetId not in self.world.entities:
                raise KeyError(event.assetId)
            self._persist("event", {"assetId": event.assetId, "kind": event.kind})
            return {"worldRevision": self.revision}

    def post_input(self, body: InputIn) -> InputReport:
        with self.lock:
            report = inputs_mod.parse_input(body, set(self.world.entities), datetime.now(timezone.utc))
            report.id = f"in-u{self.revision + 1:04d}"
            self._persist("input", report.model_dump())
            return report

    def commit(self, intervention_id: str, option_id: str, expected_revision: int) -> dict:
        with self.lock:
            if expected_revision != self.revision:
                raise ValueError("revision")
            ev = self.evaluate(self.now_s())
            iv = next((i for i in ev.fx.interventions if i.id == intervention_id), None)
            if not iv or not any(o.id == option_id for o in iv.options):
                raise KeyError(intervention_id)
            self._persist("commit", {"interventionId": intervention_id, "optionId": option_id})
            return {"worldRevision": self.revision}

    def abort(self, intervention_id: str) -> dict:
        with self.lock:
            self._persist("abort", {"interventionId": intervention_id})
            return {"worldRevision": self.revision}

    def ack(self, alert_id: str) -> dict:
        with self.lock:
            if alert_id not in self.acks:
                self._persist("ack", {"alertId": alert_id})
            return {"worldRevision": self.revision}

    def commit_plan(self, entity_id: str, plan: dict, expected_revision: int) -> dict:
        """Replace an entity's declared motion with a planned route starting now (simulated execution)."""
        with self.lock:
            if expected_revision != self.revision:
                raise ValueError("revision")
            if entity_id not in self.world.entities:
                raise KeyError(entity_id)
            self._persist("plan", {"entityId": entity_id, **plan})
            return {"worldRevision": self.revision, "catalogRevision": self.catalog_revision}

    def cancel_plan(self, entity_id: str) -> dict:
        with self.lock:
            self._persist("plan_cancel", {"entityId": entity_id})
            return {"worldRevision": self.revision, "catalogRevision": self.catalog_revision}

    # ---- evaluation ----------------------------------------------------------------------------
    def motion_overrides(self) -> dict[str, motion.MotionSpec]:
        return {eid: p["motion"] for eid, p in self.plans.items()}

    def entities_at(self, t: float) -> dict[str, SceneEntity]:
        iso = self.iso_at(t)
        out: dict[str, SceneEntity] = {}
        overrides = self.motion_overrides()
        for ent in self.world.entities.values():
            if ent.node.id in overrides:
                saved = ent.motion
                ent.motion = overrides[ent.node.id]
                e = self.world.entity_at(ent, t, iso, self.revision)
                ent.motion = saved
            else:
                e = self.world.entity_at(ent, t, iso, self.revision)
            out[e.id] = e
        for ev in self.events:
            if ev["atS"] > t:
                continue
            e = out.get(ev["assetId"])
            if not e:
                continue
            r = e.readiness or Readiness(score=0.5)
            if ev["kind"] == "fault":
                e.condition = "unavailable"
                r.faults = list(r.faults) + [f"Fault recorded (rev {ev['worldRevision']})"]
            elif ev["kind"] == "repair":
                e.condition = "normal"
                r.faults = []
            elif ev["kind"] == "resupply":
                r.fuelPct = 100.0
                r.ammunitionPct = 100.0 if r.ammunitionPct is not None else None
            elif ev["kind"] == "comms_loss":
                r.commsStatus = "lost"
            elif ev["kind"] == "comms_restored":
                r.commsStatus = "nominal"
            r.score = score(r, e.condition)
            e.readiness = r
        return out

    def inputs_at(self, t: float) -> list[InputReport]:
        scripted = inputs_mod.scripted_reports(self.epoch, t)
        cutoff = self.iso_at(t)
        posted = [p for p in self.posted if p.receivedAt <= cutoff or self.speed != 1.0]
        external = self.external_inputs(t) if t >= self.now_s() - 30 else []  # real feeds only describe the present
        allr = scripted + posted + external
        for r in allr:
            r.acknowledged = r.id in self.acks
        return sorted(allr, key=lambda r: r.effectiveAt)

    def evaluate(self, t: float) -> Evaluation:
        t = math.ceil(t / EVAL_STEP_S - 1e-9) * EVAL_STEP_S  # up, so a report posted a moment ago is always inside "now"
        key = (int(t), self.revision)
        with self.lock:
            if self._cache and self._cache[0] == key:
                return self._cache[1]
            entities = self.entities_at(t)
            inputs = self.inputs_at(t)
            ctx = rules.Context(t=t, now_iso=self.iso_at(t), revision=self.revision, entities=entities, inputs=inputs, areas=self.world.areas,
                                committed=self.commits, acknowledged=self.acks, cables=self.world.cables, sites=self.world.sites)
            fx = rules.evaluate(ctx)
            for eid, st in fx.entity_status.items():
                e = entities.get(eid)
                if not e:
                    continue
                if st.get("condition") and e.condition == "normal":
                    e.condition = st["condition"]
                if e.readiness:
                    if st.get("readinessDelta"):
                        e.readiness.score = round(max(0.0, min(1.0, e.readiness.score + st["readinessDelta"])), 2)
                    if st.get("notes"):
                        e.readiness.notes = list(dict.fromkeys(e.readiness.notes + st["notes"]))
            for eid in fx.stale_ids:
                if eid in entities:
                    entities[eid].stale = True
            for i in inputs:
                for eid in i.entityRefs:
                    if eid in entities and entities[eid].readiness:
                        lr = entities[eid].readiness.lastReportAt
                        if lr is None or i.effectiveAt > lr:
                            entities[eid].readiness.lastReportAt = i.effectiveAt
            ev = Evaluation(t=t, revision=self.revision, entities=entities, inputs=inputs, fx=fx)
            self._cache = (key, ev)
            return ev

    # ---- views ---------------------------------------------------------------------------------
    def in_scope(self, role_id: str | None, e: SceneEntity) -> bool:
        regions = views.REGION_SCOPE.get(role_id or "")
        if not regions:
            return True
        lat_lo, lat_hi = (-90.0, 58.9) if role_id == "regional_south" else (62.0, 90.0)
        return (e.region in regions) or bool(e.position and lat_lo <= e.position.latitudeDeg <= lat_hi)

    def kpis(self, ev: Evaluation, scoped: list[SceneEntity]) -> dict:
        own = [e for e in scoped if e.affiliation == "own" and e.readiness]
        mobile = [e for e in own if e.kind not in ("facility", "infrastructure")]
        fuel = [e.readiness.fuelPct for e in mobile if e.readiness and e.readiness.fuelPct is not None]
        ids = {e.id for e in scoped}
        alerts = [a for a in ev.fx.alerts if not a.entityIds or any(i in ids for i in a.entityIds)]
        infra = [e for e in scoped if e.kind == "infrastructure"]
        areas = ev.fx.area_status

        def mean(xs):
            return round(sum(xs) / len(xs), 2) if xs else None
        airborne = [e for e in mobile if e.domain == "air" and e.kinematics and e.kinematics.phase in ("moving", "returning") and e.position and e.position.altitudeM]
        return {
            "readiness": mean([e.readiness.score for e in own]),
            "airReady": mean([e.readiness.score for e in own if e.domain == "air"]), "seaReady": mean([e.readiness.score for e in own if e.domain == "sea"]),
            "landReady": mean([e.readiness.score for e in own if e.domain == "land"]),
            "unavailable": len([e for e in own if e.condition == "unavailable"]), "degraded": len([e for e in own if e.condition == "degraded"]),
            "units": len(mobile), "airborne": len(airborne), "moving": len([e for e in mobile if e.kinematics and (e.kinematics.speedMps or 0) > 0.5]),
            "unknown": len([e for e in scoped if e.affiliation == "unknown"]),
            "alerts": len([a for a in alerts if not a.acknowledged]), "critical": len([a for a in alerts if a.severity == "critical" and not a.acknowledged]),
            "fuel": round(sum(fuel) / len(fuel)) if fuel else None, "faults": len([e for e in own if e.readiness and e.readiness.faults]),
            "interventions": len([i for i in ev.fx.interventions if i.status == "proposed"]), "committed": len([i for i in ev.fx.interventions if i.status in ("in_progress", "completed")]),
            "infra": f"{len([e for e in infra if e.condition == 'normal'])}/{len(infra)}", "incidents": len([i for i in ev.inputs if i.channel == "civil_emergency"]),
            "weather": len([i for i in ev.inputs if i.channel == "weather_advisory"]), "inputs": len(ev.inputs),
            "coverage": f"{len([a for a in areas.values() if a['status'] == 'covered'])}/{len(areas)}",
            "deception": len([d for d in ev.fx.deception.values() if d["probability"] >= 0.5]),
            "plan": "optimised" if any(i.status == "proposed" for i in ev.fx.interventions) else "idle",
        }

    def layer_attention(self, ev: Evaluation) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for a in ev.fx.alerts:
            if a.acknowledged:
                continue
            for layer in a.layerIds:
                cur = out.setdefault(layer, {"count": 0, "severity": "info", "alertIds": []})
                cur["count"] += 1
                cur["alertIds"].append(a.id)
                if SEVERITY_RANK[a.severity] > SEVERITY_RANK[cur["severity"]]:
                    cur["severity"] = a.severity
        return out

    def catalog(self) -> dict:
        with self.lock:
            if self._catalog and self._catalog[0] == self.catalog_revision:
                return self._catalog[1]
            cat = self.world.catalog(self.motion_overrides())
            payload = {"scenarioId": SCENARIO_ID, "modelVersion": MODEL_VERSION, "catalogRevision": self.catalog_revision, "worldRevision": self.revision,
                       "epoch": self.epoch.isoformat(), "speed": self.speed, "dataNotice": DATA_NOTICE, **cat,
                       "sites": self.world.site_summaries(), "areas": self.world.areas, "cables": self.world.cables,
                       "plans": [p["plan"] for p in self.plans.values()]}
            self._catalog = (self.catalog_revision, payload)
            return payload

    @staticmethod
    def status_row(e: SceneEntity) -> list:
        r = e.readiness
        return [e.condition, r.score if r else None, r.fuelPct if r else None, r.ammunitionPct if r else None, r.commsStatus if r else None, e.stale,
                len(r.faults) if r else 0]

    def snapshot(self, t: float | None = None, role_id: str | None = None) -> dict:
        t = self.now_s() if t is None else t
        ev = self.evaluate(t)
        scoped = [e for e in ev.entities.values() if self.in_scope(role_id, e)]
        areas = [{**a, **ev.fx.area_status.get(a["id"], {"status": "n/a", "blockers": [], "priority": a["priority"], "requires": a["requires"]})} for a in self.world.areas]
        return {
            "scenarioId": SCENARIO_ID, "worldRevision": self.revision, "catalogRevision": self.catalog_revision, "modelVersion": MODEL_VERSION,
            "atS": round(ev.t, 1), "atTime": self.iso_at(ev.t), "serverNow": datetime.now(timezone.utc).isoformat(), "nowS": round(self.now_s(), 1),
            "speed": self.speed, "live": t >= self.now_s() - 2, "future": t > self.now_s() + 5, "sourceKind": "simulated", "dataNotice": DATA_NOTICE, "role": role_id,
            "statusColumns": ["condition", "score", "fuelPct", "ammunitionPct", "comms", "stale", "faults"],
            "status": {e.id: self.status_row(e) for e in scoped}, "scope": [e.id for e in scoped] if role_id in views.REGION_SCOPE else None,
            "observed": self.observed_rows(ev), "areas": areas,
            "alerts": [a.model_dump() for a in ev.fx.alerts], "interventions": [i.model_dump() for i in ev.fx.interventions],
            "predictions": [p.model_dump() for p in ev.fx.predictions], "inputs": [i.model_dump() for i in ev.inputs[-120:]],
            "events": self.events, "kpis": self.kpis(ev, scoped), "layerAttention": self.layer_attention(ev), "ruleTrace": ev.fx.traces[-200:],
            "priorities": ev.fx.priorities, "deception": ev.fx.deception, "fusion": ev.fx.fusion,
        }

    @staticmethod
    def observed_rows(ev: Evaluation) -> list[list]:
        rows = []
        for e in ev.entities.values():
            if e.affiliation != "unknown" or not e.position:
                continue
            k = e.kinematics
            if "dark" in (ev.fx.entity_status.get(e.id, {}).get("flags") or []):
                continue  # not transmitting / not held by sensors right now
            rows.append([e.id, e.position.longitudeDeg, e.position.latitudeDeg, e.position.altitudeM, k.headingDeg if k else None, k.speedMps if k else None, e.condition])
        return rows

    def kinematics(self, t: float | None = None) -> dict:
        """Compact live positions of observed tracks: [id, lng, lat, altM, headingDeg, speedMps, condition]."""
        t = self.now_s() if t is None else t
        ev = self.evaluate(t)
        return {"atS": round(t, 1), "atTime": self.iso_at(t), "worldRevision": self.revision, "catalogRevision": self.catalog_revision, "rows": self.observed_rows(ev)}

    def attention(self, t: float | None, resolution: str, role_id: str | None) -> dict:
        t = self.now_s() if t is None else t
        ev = self.evaluate(t)
        cell = attention.RESOLUTIONS.get(resolution, attention.RESOLUTIONS["regional"])
        cells = attention.aggregate(ev.fx.attention, cell)
        return {"atS": round(t, 1), "worldRevision": self.revision, "resolution": resolution, "cellDeg": cell, "unit": "attention weight (sum of rule weights × kernel)",
                "maxScore": cells[0].score if cells else 0, "cells": [c.model_dump() for c in cells],
                "contributions": [{"lng": c.lng, "lat": c.lat, "radiusM": c.radius_m, "weight": c.weight, "reason": c.reason, "contributor": c.contributor, "ruleId": c.rule_id} for c in ev.fx.attention]}

    def tracks(self, entity_id: str, t_from: float, t_to: float, step_s: float) -> dict:
        ent = self.world.entities[entity_id]
        spec = self.motion_overrides().get(entity_id) or self.world.motion_of(ent)
        samples = motion.sample(spec, t_from, t_to, step_s)
        return {"entityId": entity_id, "sourceKind": ent.base.sourceKind, "fromS": t_from, "toS": t_to, "stepS": step_s, "samples": samples,
                "note": "Samples are reconstructed from the synthetic motion model at the requested cadence."}

    def entity_detail(self, entity_id: str, t: float | None = None) -> dict:
        t = self.now_s() if t is None else t
        ev = self.evaluate(t)
        if entity_id in self.world.formations:
            return self.formation_detail(entity_id, ev)
        e = ev.entities.get(entity_id)
        if not e:
            raise KeyError(entity_id)
        related_inputs = [i for i in ev.inputs if entity_id in i.entityRefs]
        alerts = [a for a in ev.fx.alerts if entity_id in a.entityIds]
        ivs = [i for i in ev.fx.interventions if any(entity_id in o.assignedEntityIds for o in i.options) or i.alertId in {a.id for a in alerts}]
        preds = [p for p in ev.fx.predictions if p.entityId == entity_id or entity_id in p.threatenedEntityIds]
        areas = [a["id"] for a in self.world.areas if entity_id in a["requires"]]
        return {"entity": e.model_dump(), "inputs": [i.model_dump() for i in related_inputs[-30:]], "alerts": [a.model_dump() for a in alerts],
                "interventions": [i.model_dump() for i in ivs], "predictions": [p.model_dump() for p in preds], "areas": areas,
                "events": [ev_ for ev_ in self.events if ev_["assetId"] == entity_id], "worldRevision": self.revision, "atS": round(ev.t, 1),
                "ruleTrace": [tr for tr in ev.fx.traces if tr.get("subject") == entity_id], "fusion": ev.fx.fusion.get(entity_id),
                "deception": ev.fx.deception.get(entity_id), "plan": self.plans[entity_id]["plan"] if entity_id in self.plans else None,
                "layout": self.world.layouts[entity_id].to_api() if entity_id in self.world.layouts else None,
                "based": [x.node.id for x in self.world.entities.values() if x.node.site == entity_id and x.node.kind not in ("facility", "infrastructure")][:400]}

    def formation_detail(self, fid: str, ev: Evaluation) -> dict:
        f = self.world.formations[fid]
        leaves: list[str] = []
        stack = [fid]
        while stack:
            cur = stack.pop()
            for c in self.world.formations[cur].children if cur in self.world.formations else []:
                (stack if c in self.world.formations else leaves).append(c)
        ents = [ev.entities[i] for i in leaves if i in ev.entities]
        rs = [e.readiness.score for e in ents if e.readiness]
        fuel = [e.readiness.fuelPct for e in ents if e.readiness and e.readiness.fuelPct is not None]
        alerts = [a for a in ev.fx.alerts if any(i in leaves for i in a.entityIds)]
        by_platform: dict[str, int] = {}
        for e in ents:
            by_platform[e.platform or e.kind] = by_platform.get(e.platform or e.kind, 0) + 1
        return {"formation": f.base.model_dump(), "children": f.children, "platforms": len(ents), "byPlatform": by_platform,
                "readiness": round(sum(rs) / len(rs), 2) if rs else None, "fuel": round(sum(fuel) / len(fuel)) if fuel else None,
                "unavailable": len([e for e in ents if e.condition == "unavailable"]), "degraded": len([e for e in ents if e.condition == "degraded"]),
                "moving": len([e for e in ents if e.kinematics and (e.kinematics.speedMps or 0) > 0.5]),
                "alerts": [a.model_dump() for a in alerts[:30]], "worldRevision": self.revision, "atS": round(ev.t, 1)}

    def optimise(self, t: float | None = None) -> dict:
        t = self.now_s() if t is None else t
        ev = self.evaluate(t)
        result = optimize.optimise(ev.fx.interventions, {a.id: a for a in ev.fx.alerts})
        return {**result, "worldRevision": self.revision, "atS": round(ev.t, 1)}
