"""Registry of live public-data feeds. See `base.Feed` for the contract and status semantics.

Set `TROSSOPS_FEEDS=off` to disable every network call (tests, CI, offline demos).
"""
from __future__ import annotations

from .adsb import AdsbFeed
from .ais import AisFeed
from .aisstream import AisStreamFeed
from .base import Feed, feeds_disabled
from .firms import FirmsFeed
from .krisinfo import KrisinfoFeed
from .openmeteo import OpenMeteoFeed
from .polisen import PolisenFeed
from .rainviewer import RainViewerFeed
from .smhi import SmhiObservationsFeed, SmhiWarningsFeed
from .swpc import SwpcFeed
from .trafikverket import TrafikverketFeed

ADSB = AdsbFeed()
AIS = AisFeed()
AISSTREAM = AisStreamFeed(history_sink=AIS.record)
SMHI_OBS = SmhiObservationsFeed()
SMHI_WARNINGS = SmhiWarningsFeed()
OPEN_METEO = OpenMeteoFeed()
RAINVIEWER = RainViewerFeed()
POLISEN = PolisenFeed()
KRISINFO = KrisinfoFeed()
SWPC = SwpcFeed()
TRAFIKVERKET = TrafikverketFeed()
FIRMS = FirmsFeed()

FEEDS: dict[str, Feed] = {f.id: f for f in (ADSB, AIS, AISSTREAM, SMHI_OBS, SMHI_WARNINGS, OPEN_METEO, RAINVIEWER,
                                             POLISEN, KRISINFO, SWPC, TRAFIKVERKET, FIRMS)}


def get(feed_id: str) -> dict:
    return FEEDS[feed_id].get()


def statuses() -> list[dict]:
    return [f.status() for f in FEEDS.values()]


__all__ = ["FEEDS", "Feed", "feeds_disabled", "get", "statuses", "ADSB", "AIS", "AISSTREAM", "SMHI_OBS", "SMHI_WARNINGS",
           "OPEN_METEO", "RAINVIEWER", "POLISEN", "KRISINFO", "SWPC", "TRAFIKVERKET", "FIRMS"]
