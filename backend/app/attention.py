"""Attention surface: aggregates rule contributions into grid cells at the resolution the client asked for.
Score units: dimensionless attention weight (sum of rule weights × distance kernel). Legend shows this."""
from __future__ import annotations

from dataclasses import dataclass

from . import geo
from .models import AttentionCell


@dataclass
class Contribution:
    lng: float
    lat: float
    radius_m: float
    weight: float
    reason: str
    contributor: str
    rule_id: str


RESOLUTIONS = {"national": 0.5, "regional": 0.15, "local": 0.04}


def kernel(distance_m: float, radius_m: float) -> float:
    if radius_m <= 0:
        return 1.0 if distance_m < 1 else 0.0
    x = distance_m / radius_m
    return 0.0 if x >= 1 else (1 - x) ** 1.5


def aggregate(contribs: list[Contribution], cell_deg: float, max_cells: int = 600) -> list[AttentionCell]:
    cells: dict[tuple[int, int], dict] = {}
    for c in contribs:
        # Cover the footprint of the contribution with cells (bounded to keep it O(cells) not O(entities²)).
        span_deg = max(cell_deg, c.radius_m / 111_000)
        x0, y0 = geo.grid_key((c.lng - span_deg, c.lat - span_deg), cell_deg)
        x1, y1 = geo.grid_key((c.lng + span_deg, c.lat + span_deg), cell_deg)
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                key = (x, y)
                center = geo.grid_center(key, cell_deg)
                k = kernel(geo.haversine_m(center, (c.lng, c.lat)), max(c.radius_m, cell_deg * 111_000 * 0.75))
                if k <= 0.02:
                    continue
                cell = cells.setdefault(key, {"score": 0.0, "peak": 0.0, "reasons": {}, "contributors": set()})
                v = c.weight * k
                cell["score"] += v
                cell["peak"] = max(cell["peak"], v)
                cell["reasons"][c.reason] = cell["reasons"].get(c.reason, 0.0) + v
                cell["contributors"].add(c.contributor)
    out = []
    for key, cell in cells.items():
        reasons = sorted(cell["reasons"].items(), key=lambda kv: -kv[1])[:3]
        out.append(AttentionCell(key=f"{key[0]}:{key[1]}", center=list(geo.grid_center(key, cell_deg)),
                                 ring=[list(p) for p in geo.grid_ring(key, cell_deg)], score=round(cell["score"], 3), peak=round(cell["peak"], 3),
                                 reasons=[r for r, _ in reasons], contributors=sorted(cell["contributors"])[:8]))
    out.sort(key=lambda c: -c.score)
    return out[:max_cells]
