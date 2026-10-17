"""Relevance of real feed items to the operational picture, and facts about feed coverage.

Kept apart from `feed_inputs` (which reads the feed caches) so the engine can filter whatever its `external_inputs`
hook returns - real feeds in production, injected reports in tests - without importing the feed registry.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

from . import geo
from .models import InputReport


def _when(s) -> datetime | None:
    if not isinstance(s, str) or not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00").replace(" ", "T", 1))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


# ---- relevance: keep only the real items that concern own sites, own road marches or reported claims --------------------
RELEVANCE_M = {"road_situation": (2_000, 5_000), "thermal_anomaly": (3_000, 15_000)}  # (from a march route, from an own site)
CLAIM_RELEVANCE_M = 25_000  # a thermal anomaly this close to a reported explosion or fire is kept as corroboration
CLAIM_TAGS = {"explosion", "fire"}


class RelevanceIndex:
    """Own sites (points) and own road-march routes (polylines) with chunked bounding boxes, so filtering hundreds of
    nationwide road situations or fire pixels costs a few box tests per item instead of a scan of every route vertex."""

    CHUNK = 24

    def __init__(self, sites: list[tuple[float, float]], lines: list[list[tuple[float, float]]]) -> None:
        self.sites = sites
        self.chunks: list[tuple[float, float, float, float, list]] = []
        for line in lines:
            for k in range(0, max(len(line) - 1, 1), self.CHUNK):
                seg = line[k:k + self.CHUNK + 1]
                xs, ys = [q[0] for q in seg], [q[1] for q in seg]
                self.chunks.append((min(xs), min(ys), max(xs), max(ys), seg))

    def near(self, p: tuple[float, float], route_m: float, site_m: float) -> bool:
        dy = route_m / 110_540
        dx = route_m / (111_320 * max(0.2, math.cos(math.radians(p[1]))))
        for x0, y0, x1, y1, seg in self.chunks:
            if x0 - dx <= p[0] <= x1 + dx and y0 - dy <= p[1] <= y1 + dy and geo.project_on_line(p, seg)[0] <= route_m:
                return True
        return any(abs(s[1] - p[1]) < 0.3 and geo.haversine_m(p, s) <= site_m for s in self.sites)


def relevant(external: list[InputReport], index: RelevanceIndex | None, claims: list[InputReport]) -> list[InputReport]:
    """Drop road situations and thermal anomalies that concern nothing in the picture: hundreds of nationwide roadworks
    would otherwise bury the operational reports. Other external inputs pass unchanged."""
    claim_pts = [(c.position.longitudeDeg, c.position.latitudeDeg) for c in claims if c.position and CLAIM_TAGS & set(c.tags)]
    out = []
    for i in external:
        lim = RELEVANCE_M.get(i.channel)
        if lim is None or i.position is None:
            if lim is None:
                out.append(i)
            continue
        p = (i.position.longitudeDeg, i.position.latitudeDeg)
        if index is not None and index.near(p, *lim):
            out.append(i)
        elif i.channel == "thermal_anomaly" and any(geo.haversine_m(p, c) <= CLAIM_RELEVANCE_M for c in claim_pts):
            out.append(i)
    return out


def thermal_coverage(external: list[InputReport]) -> str | None:
    """Latest VIIRS acquisition in the whole feed (before relevance filtering): evidence of when a satellite last passed."""
    times = [i.effectiveAt for i in external if i.channel == "thermal_anomaly"]
    return max(times, key=lambda s: _when(s) or datetime.min.replace(tzinfo=timezone.utc)) if times else None
