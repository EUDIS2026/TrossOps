"""Synthetic national world: the order of battle (`orbat`) evaluated at any scenario time.

Everything is generated deterministically from a seed so replay, tests and the browser agree. No real military
installation, unit identity, route or capability is represented (see `orbat` for what *is* public: platform
classes, road and sea geometry). Platforms move with `motion.MotionSpec`; the browser evaluates the same motion
model itself (`/api/world` publishes it), so only observed tracks are streamed.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from . import geo, motion
from .models import GeoPosition, Kinematics, Readiness, SceneEntity
from .orbat import AREAS_STATIC, CABLES, COUNTY_OF, P, SITES, Node, Orbat

SCENARIO_ID = "sweden-synthetic"
MODEL_VERSION = "2.0.0"

KIND_DOMAIN: dict[str, str] = {
    "fixed_wing": "air", "helicopter": "air", "multirotor": "air", "ground_vehicle": "land", "personnel": "land",
    "vessel": "sea", "facility": "site", "infrastructure": "infra", "unknown": "unknown",
}
CREW = {"fixed_wing": 2, "helicopter": 4, "multirotor": 1, "ground_vehicle": 4, "vessel": 24, "personnel": 30, "unknown": 0}
FAULTS = ["Hydraulic pressure low", "Radio set B intermittent", "Track tension warning", "Nav sensor drift", "Cooling loop pressure", "Generator output low"]

__all__ = ["SyntheticWorld", "WorldEntity", "P", "SITES", "COUNTY_OF", "SCENARIO_ID", "MODEL_VERSION"]


@dataclass
class WorldEntity:
    node: Node
    base: SceneEntity
    readiness: Readiness | None = None
    condition: str = "normal"
    motion: motion.MotionSpec | None = None
    children: list[str] = field(default_factory=list)

    @property
    def spec(self) -> Node:
        return self.node


class SyntheticWorld:
    """Deterministic national world. `seconds` is scenario time since the scenario epoch."""

    def __init__(self, seed: int = 20261016) -> None:
        self.seed = seed
        self.orbat = Orbat(seed)
        self.sites: dict[str, tuple[float, float]] = self.orbat.sites
        self.layouts = self.orbat.layouts
        self.routes = self.orbat.routes
        self.cables = CABLES
        self.entities: dict[str, WorldEntity] = {}
        self.formations: dict[str, WorldEntity] = {}
        for n in self.orbat.nodes.values():
            base = SceneEntity(
                id=n.id, resourceId=f"asset-{n.id}", kind=n.kind, domain=n.domain if n.kind != "formation" else n.domain,  # type: ignore[arg-type]
                affiliation=n.affiliation, label=n.label, unit=self._unit_label(n), modelKey=n.model, region=n.region,  # type: ignore[arg-type]
                capabilities=n.capabilities, sourceKind="observed" if n.affiliation == "unknown" else "simulated", visualPriority=n.priority if n.affiliation != "unknown" else 4,
                sidc=n.sidc, echelon=n.echelon, parentId=n.parent, layer=n.layer, platform=n.platform, siteId=n.site, short=n.short, rangeKm=n.range_km, tags=n.tags,
            )
            we = WorldEntity(node=n, base=base, motion=n.motion, readiness=self._readiness(n) if n.kind != "formation" else None)
            (self.formations if n.kind == "formation" else self.entities)[n.id] = we
        for n in self.orbat.nodes.values():
            if n.parent and n.parent in self.formations:
                self.formations[n.parent].children.append(n.id)
        self.areas = self._areas()

    def add_node(self, n: Node) -> None:
        """Add a platform at runtime (scenario injection); it behaves exactly like a built-in one."""
        base = SceneEntity(id=n.id, resourceId=f"asset-{n.id}", kind=n.kind, domain=n.domain, affiliation=n.affiliation, label=n.label, modelKey=n.model,  # type: ignore[arg-type]
                           capabilities=n.capabilities, sourceKind="observed" if n.affiliation == "unknown" else "simulated", visualPriority=4, sidc=n.sidc,
                           layer=n.layer, short=n.short, tags=n.tags)
        self.orbat.nodes[n.id] = n
        self.entities[n.id] = WorldEntity(node=n, base=base, motion=n.motion, readiness=self._readiness(n))

    # ---- construction helpers -------------------------------------------------------------------------------------
    def _unit_label(self, n: Node) -> str | None:
        chain = []
        p = n.parent
        while p and p in self.orbat.nodes and len(chain) < 2:
            chain.append(self.orbat.nodes[p].label)
            p = self.orbat.nodes[p].parent
        return " · ".join(chain) if chain else (n.tags[1] if len(n.tags) > 1 else None)

    def _readiness(self, n: Node) -> Readiness:
        r = random.Random(f"{self.seed}:{n.id}")
        if n.affiliation == "unknown":
            return Readiness(score=0, commsStatus="n/a")
        if n.kind in ("facility", "infrastructure"):
            return Readiness(score=round(r.uniform(0.74, 0.98), 2), fuelPct=round(r.uniform(55, 100)) if "fuel" in n.capabilities else None,
                             ammunitionPct=round(r.uniform(60, 100)) if "ammunition" in n.capabilities else None,
                             crewPresent=r.randint(int(n.crew * 0.7), n.crew), crewRequired=n.crew, commsStatus="nominal")
        crew = n.crew or CREW.get(n.kind, 2)
        ammo = round(r.uniform(45, 100)) if n.kind in ("fixed_wing", "ground_vehicle", "vessel", "personnel", "helicopter") and n.affiliation == "own" else None
        faults = [r.choice(FAULTS)] if r.random() < 0.035 and n.affiliation == "own" else []
        fuel = n.motion.fuel_start if n.motion and n.motion.fuel_start is not None else round(r.uniform(50, 100))
        rd = Readiness(score=0.0, fuelPct=fuel, ammunitionPct=ammo, crewPresent=crew if r.random() > 0.08 else max(1, crew - 1), crewRequired=crew,
                       commsStatus="nominal", maintenanceDueH=round(r.uniform(4, 220), 1), faults=faults)
        rd.score = score(rd, "normal")
        return rd

    def _areas(self) -> list[dict]:
        areas = [dict(a) for a in AREAS_STATIC]
        for sid in ("radar-gotland", "radar-syd", "radar-ost", "radar-norr", "radar-vast", "radar-bothnia"):
            areas.append({"id": f"zone-sensor-{sid[6:]}", "label": f"Sensor coverage {self.orbat.nodes[sid].label} (model: 180 km nominal)", "kind": "coverage_model",
                          "ring": [[round(p[0], 5), round(p[1], 5)] for p in geo.circle_ring(self.sites[sid], 180_000, 64)], "requires": [sid], "priority": 5})
        return areas

    # ---- kinematics -------------------------------------------------------------------------------------------------
    def motion_of(self, ent: WorldEntity) -> motion.MotionSpec:
        return ent.motion or motion.MotionSpec("static", pos=(ent.base.position.longitudeDeg, ent.base.position.latitudeDeg, None) if ent.base.position else (0, 0, None))

    def state_at(self, ent: WorldEntity, t: float) -> motion.State:
        return motion.state_at(self.motion_of(ent), t)

    def samples(self, ent: WorldEntity, t_from: float, t_to: float, step_s: float) -> list[list[float | None]]:
        return motion.sample(self.motion_of(ent), t_from, t_to, step_s)

    def entity_at(self, ent: WorldEntity, t: float, observed_iso: str, revision: int) -> SceneEntity:
        st = self.state_at(ent, t)
        n = ent.node
        e = ent.base.model_copy(deep=True)
        airborne = n.kind in ("fixed_wing", "helicopter", "multirotor") or (n.kind == "unknown" and n.domain == "air")
        if airborne and st.alt is not None:
            datum, alt = "MSL", round(st.alt, 1)
        elif n.kind == "vessel" and st.alt is not None and st.alt < 0:
            datum, alt = "MSL", round(st.alt, 1)  # submerged
        else:
            datum, alt = ("AGL", 0.0) if n.kind in ("facility", "infrastructure") else ("UNKNOWN", None)
        e.position = GeoPosition(longitudeDeg=round(st.lng, 6), latitudeDeg=round(st.lat, 6), altitudeM=alt, altitudeDatum=datum,  # type: ignore[arg-type]
                                 horizontalAccuracyM=None if e.affiliation != "unknown" else 1500.0)
        e.kinematics = Kinematics(headingDeg=round(st.heading, 1), speedMps=round(st.speed, 2), pitchDeg=round(st.pitch, 1), bankDeg=round(st.bank, 1), phase=st.phase)
        e.condition = ent.condition  # type: ignore[assignment]
        if ent.readiness:
            e.readiness = ent.readiness.model_copy(deep=True)
            if st.fuel is not None and e.readiness.fuelPct is not None:
                e.readiness.fuelPct = round(st.fuel, 1)
                e.readiness.score = score(e.readiness, e.condition)
        e.observedAt = observed_iso
        e.worldRevision = revision
        return e

    # ---- catalogue for the browser ----------------------------------------------------------------------------------
    def catalog(self, overrides: dict[str, motion.MotionSpec] | None = None) -> dict:
        overrides = overrides or {}
        out = []
        for we in list(self.formations.values()) + list(self.entities.values()):
            b = we.base
            item = {"id": b.id, "label": b.label, "short": b.short, "kind": b.kind, "domain": b.domain, "affiliation": b.affiliation, "sidc": b.sidc,
                    "echelon": b.echelon, "parentId": b.parentId, "layer": b.layer, "platform": b.platform, "model": b.modelKey, "siteId": b.siteId,
                    "region": b.region, "capabilities": b.capabilities, "rangeKm": b.rangeKm, "tags": b.tags, "unit": b.unit, "sourceKind": b.sourceKind}
            if b.kind != "formation" and b.affiliation != "unknown":
                m = overrides.get(b.id) or we.motion
                item["motion"] = m.to_api() if m else None
            out.append(item)
        return {"entities": out, "routes": {rid: motion.encode_path(p) for rid, p in self.routes.items()}}

    def site_summaries(self) -> list[dict]:
        return [{"id": sid, "kind": lay.kind, "center": [round(lay.center[0], 6), round(lay.center[1], 6)], "axis": lay.axis,
                 "footprint": [[round(p[0], 6), round(p[1], 6)] for p in lay.footprint], "runway": lay.runway} for sid, lay in self.layouts.items()]


def score(r: Readiness, condition: str) -> float:
    if condition == "unavailable":
        return 0.0
    fuel = (r.fuelPct if r.fuelPct is not None else 70) / 100
    ammo = (r.ammunitionPct / 100) if r.ammunitionPct is not None else 1.0
    comms = {"nominal": 1.0, "degraded": 0.7, "lost": 0.3, "n/a": 1.0}[r.commsStatus]
    crew = (r.crewPresent / r.crewRequired) if r.crewPresent and r.crewRequired else 1.0
    return round(max(0.0, min(1.0, 0.05 + 0.35 * fuel + 0.2 * ammo + 0.2 * comms + 0.2 * crew - 0.2 * len(r.faults) - (0.25 if condition == "degraded" else 0))), 2)
