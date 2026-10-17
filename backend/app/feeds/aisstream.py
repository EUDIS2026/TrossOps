"""AISStream.io websocket adapter (terrestrial AIS, global, free key).

Without `AISSTREAM_API_KEY` the feed reports `adapter-only`. With a key, and only in a long-lived process (`VERCEL`
unset), a daemon thread subscribes to the Sweden + Baltic bounding box and keeps the latest position per MMSI in the
same normalised vessel shape as Digitraffic (`source: "aisstream"`). The websocket library (`websockets`, shipped with
`uvicorn[standard]`) is imported lazily inside the thread.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Callable

from .ais import BBOX, course, heading, in_bbox, nav_status_label, ship_type_label, speed_mps
from .base import USER_AGENT, Feed, feeds_disabled, num, on_vercel

STREAM_URL = "wss://stream.aisstream.io/v0/stream"
POSITION_TYPES = ("PositionReport", "StandardClassBPositionReport", "ExtendedClassBPositionReport")
FORGET_S = 1800.0
_TIME_RE = re.compile(r"(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})(?:\.(\d+))?")


def parse_time_utc(text: str | None) -> int | None:
    """AISStream MetaData.time_utc, e.g. '2022-12-29 18:22:32.318353 +0000 UTC' -> epoch ms."""
    m = _TIME_RE.match(text or "")
    if not m:
        return None
    frac = (m.group(3) or "0")[:6].ljust(6, "0")
    dt = datetime.fromisoformat(f"{m.group(1)}T{m.group(2)}.{frac}+00:00")
    return int(dt.astimezone(timezone.utc).timestamp() * 1000)


class AisStreamFeed(Feed):
    id = "aisstream"
    label = "AIS vessels (AISStream.io websocket)"
    category = "sea"
    url = STREAM_URL
    licence = "AISStream.io terms of service (free API key)"
    attribution = "AIS data: aisstream.io"
    ttl_s = 60.0
    note = "Streaming terrestrial AIS for the Sweden + Baltic box; merged into /api/live/vessels."
    credential_env = ("AISSTREAM_API_KEY",)
    credential_help = "Create a free API key at https://aisstream.io (sign in with GitHub, then 'API Keys') and set AISSTREAM_API_KEY."

    def __init__(self, history_sink: Callable[[dict], None] | None = None) -> None:
        super().__init__()
        self.history_sink = history_sink
        self._vessels: dict[int, dict] = {}
        self._static: dict[int, dict] = {}
        self._vlock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._connected = False
        self._messages = 0
        self._unavailable: str | None = None

    # -- message handling (pure, unit-testable) ------------------------------------------------------------------------
    def handle_message(self, msg: dict) -> dict | None:
        kind = msg.get("MessageType")
        meta = msg.get("MetaData") or {}
        body = (msg.get("Message") or {}).get(kind) or {}
        mmsi = meta.get("MMSI") or body.get("UserID")
        if not mmsi:
            return None
        mmsi = int(mmsi)
        self._messages += 1
        if kind == "ShipStaticData":
            draught = num(body.get("MaximumStaticDraught"))
            static = {"name": (body.get("Name") or meta.get("ShipName") or "").strip() or None,
                      "callsign": (body.get("CallSign") or "").strip() or None, "imo": body.get("ImoNumber") or None,
                      "shipType": body.get("Type"), "shipTypeLabel": ship_type_label(body.get("Type")),
                      "destination": (body.get("Destination") or "").strip() or None, "draughtM": draught or None}
            with self._vlock:
                self._static[mmsi] = static
                if mmsi in self._vessels:
                    self._vessels[mmsi].update({k: v for k, v in static.items() if v is not None})
            return None
        if kind not in POSITION_TYPES:
            return None
        lat, lng = num(body.get("Latitude", meta.get("latitude"))), num(body.get("Longitude", meta.get("longitude")))
        if lat is None or lng is None or not in_bbox(lng, lat):
            return None
        static = self._static.get(mmsi, {})
        nav = body.get("NavigationalStatus")
        item = {"id": mmsi, "name": static.get("name") or ((meta.get("ShipName") or "").strip() or None),
                "callsign": static.get("callsign"), "imo": static.get("imo"), "shipType": static.get("shipType"),
                "shipTypeLabel": static.get("shipTypeLabel"), "lng": lng, "lat": lat, "speedMps": speed_mps(body.get("Sog")),
                "courseDeg": course(body.get("Cog")), "headingDeg": heading(body.get("TrueHeading")), "navStatus": nav,
                "navStatusLabel": nav_status_label(nav), "destination": static.get("destination"),
                "draughtM": static.get("draughtM"), "timestampMs": parse_time_utc(meta.get("time_utc")) or int(time.time() * 1000),
                "source": "aisstream"}
        with self._vlock:
            self._vessels[mmsi] = item
        if self.history_sink:
            try:
                self.history_sink(item)
            except Exception:  # noqa: BLE001
                pass
        return item

    def snapshot(self) -> list[dict]:
        cutoff = (time.time() - FORGET_S) * 1000
        with self._vlock:
            for mmsi in [m for m, v in self._vessels.items() if v["timestampMs"] < cutoff]:
                del self._vessels[mmsi]
            return [dict(v) for v in self._vessels.values()]

    # -- background stream ----------------------------------------------------------------------------------------------
    def _run(self, key: str) -> None:
        try:
            from websockets.sync.client import connect  # lazy: only needed for the long-lived stream
        except ImportError:
            self._unavailable = "websockets not installed (pip install websockets==17.2)"
            return
        backoff = 5.0
        subscribe = json.dumps({"APIKey": key, "BoundingBoxes": [[[BBOX[1], BBOX[0]], [BBOX[3], BBOX[2]]]],
                                "FilterMessageTypes": list(POSITION_TYPES) + ["ShipStaticData"]})
        while not self._stop.is_set():
            got_any = False
            try:
                with connect(STREAM_URL, open_timeout=10, close_timeout=2, user_agent_header=USER_AGENT) as ws:
                    ws.send(subscribe)
                    self._connected = True
                    while not self._stop.is_set():
                        raw = ws.recv(timeout=120)
                        msg = json.loads(raw)
                        got_any = True
                        if "error" in msg:
                            raise RuntimeError(str(msg["error"])[:200])
                        if self.handle_message(msg):
                            self._fetched_at = self._last_ok = time.time()
                            backoff = 5.0
            except Exception as exc:  # noqa: BLE001 - reconnect with backoff
                hint = "" if got_any else " (closed before any message: AISStream drops invalid API keys this way)"
                self._last_error = f"{type(exc).__name__}: {exc}{hint}"[:300]
                self._last_error_at = time.time()
            self._connected = False
            self._stop.wait(backoff)
            backoff = min(backoff * 2, 300.0)

    def refresh(self, force: bool = False) -> None:
        if feeds_disabled() or self.missing_credentials() or on_vercel():
            return
        if self._thread is None or not self._thread.is_alive():
            if self._unavailable:
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, args=(os.environ["AISSTREAM_API_KEY"],),
                                            name="aisstream", daemon=True)
            self._thread.start()
        self._data = {"items": self.snapshot()}

    def stop(self) -> None:
        self._stop.set()

    def _status_value(self) -> tuple[str, bool, str]:
        if feeds_disabled() or self.missing_credentials():
            return super()._status_value()
        if on_vercel():
            return "adapter-only", False, "websocket stream needs a long-lived process; not started on Vercel"
        if self._unavailable:
            return "blocked", False, self._unavailable
        if self._thread is None:
            return "adapter-only", False, "stream not started yet in this process"
        if self._connected and self._last_ok:
            stale = time.time() - self._last_ok > self.ttl_s * 3
            return ("partial" if stale else "working"), stale, f"streaming; {self._messages} messages since start"
        if self._last_error:
            return ("partial" if self._last_ok else "blocked"), bool(self._last_ok), f"reconnecting after error: {self._last_error}"
        return "partial", False, "connecting / waiting for first position in the box"
