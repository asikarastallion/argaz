"""One ordered event stream for a whole fleet.

WHY THE ROUTER'S OWN MONOTONIC CLOCK IS THE SORT KEY
----------------------------------------------------
The obvious key is the vehicle's own timestamp — it is what the aircraft
believes, and it is already in every message. It is also wrong for this
purpose, and measurably so.

Two free-running SITLs carry a constant clock offset of boot-stagger x
speedup: 0.9 s at speedup 1, 4.5 s at speedup 5 (docs/fleet-clock-drift.md).
Keyed on vehicle time, an event on v2 that happened *after* an event on v1
sorts *before* it — and a timeline that reorders cause and effect does not
merely lose precision, it asserts something false about what led to what.
Reading such a timeline, a takeoff would appear to precede the arm command
that caused it.

So:

    sort key   the router's `time.monotonic()`, one clock, one process
    field      the vehicle's own time, kept on every event, never sorted on

`time.monotonic()` and not `time.time()`: a wall clock can step backwards
(NTP, a suspend/resume) and a timeline that goes backwards is worse than one
that is merely offset. The absolute UTC start is recorded once, so a monotonic
offset can still be turned into a real timestamp for a human.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

SCHEMA_VERSION = 1


@dataclass
class Event:
    """One thing that happened, ordered by `t`."""

    t: float                       # seconds since the bus started, monotonic
    kind: str
    vehicle: Optional[str] = None
    payload: dict = field(default_factory=dict)
    # The vehicle's own clock when this happened, if it came from a vehicle.
    # A FIELD, never the sort key. See the module docstring.
    vehicle_time_s: Optional[float] = None

    def as_dict(self) -> dict:
        out = {"t": round(self.t, 4), "kind": self.kind}
        if self.vehicle is not None:
            out["vehicle"] = self.vehicle
        if self.vehicle_time_s is not None:
            out["vehicle_time_s"] = round(self.vehicle_time_s, 4)
        out.update(self.payload)
        return out


class EventBus:
    """Thread-safe, append-only, monotonically ordered.

    Every vehicle link runs on its own thread, so ordering has to be imposed
    at the point of entry rather than assumed from arrival. The lock covers
    stamping and appending together: two threads that stamped, were
    descheduled, and then appended would produce a list whose `t` values are
    out of order, which is precisely the defect this class exists to avoid.
    """

    def __init__(self, sink: Optional[Callable[[Event], None]] = None) -> None:
        self._events: list = []
        self._lock = threading.Lock()
        self._started_monotonic = time.monotonic()
        self.started_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.sink = sink

    def emit(self, kind: str, vehicle: Optional[str] = None,
             vehicle_time_s: Optional[float] = None, **payload) -> Event:
        with self._lock:
            event = Event(t=time.monotonic() - self._started_monotonic,
                          kind=kind, vehicle=vehicle,
                          vehicle_time_s=vehicle_time_s, payload=payload)
            self._events.append(event)
        if self.sink is not None:
            try:
                self.sink(event)
            except Exception:
                pass                      # a sink must never break the fleet
        return event

    # ------------------------------------------------------------------ query
    @property
    def events(self) -> list:
        with self._lock:
            return list(self._events)

    def for_vehicle(self, vehicle_id: str) -> list:
        return [e for e in self.events if e.vehicle == vehicle_id]

    def of_kind(self, kind: str) -> list:
        return [e for e in self.events if e.kind == kind]

    def ordered(self) -> bool:
        """Is the stream monotonically ordered? Asserted by the tests."""
        times = [e.t for e in self.events]
        return times == sorted(times)

    # ---------------------------------------------------------------- writing
    def write_jsonl(self, path: Path) -> Path:
        """`timeline.jsonl` — one event per line, in order."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "schema": SCHEMA_VERSION, "kind": "timeline_start",
                "t": 0.0, "started_utc": self.started_utc,
                "clock": "router monotonic; vehicle_time_s is a field, not the "
                         "sort key — see docs/fleet-clock-drift.md"}) + "\n")
            for event in self.events:
                handle.write(json.dumps(event.as_dict(), ensure_ascii=False) + "\n")
        return path
