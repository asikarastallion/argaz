"""Live telemetry mirror — the running flight, as a graph, in PlotJuggler.

WHY THIS IS JSON AND NOT MAVLINK
--------------------------------
The obvious design is to fan MAVLink out to a third UDP port and let
PlotJuggler's MAVLink plugin read it. **PlotJuggler has no MAVLink plugin.**
Checked against the installed build (3.17.2): its data sources are UDP Server,
WebSocket, ZMQ, MQTT, serial, ROS 2 and the Foxglove bridge, and its parsers
are JSON/CBOR/BSON/MessagePack, Protobuf, ROS 1/2, DataTamer and InfluxDB line
protocol. ArduPilot's own PlotJuggler plugin
(github.com/ArduPilot/plotjuggler-apbin-plugins) is a *dataflash `.BIN`
loader* — offline, post-flight, and a different problem.

So a raw MAVLink mirror would have had no consumer. The format PlotJuggler can
read live, with nothing installed, is one JSON object per UDP datagram:

    {"t": 1785938401.732, "ATTITUDE": {"roll": 0.01, "pitch": -0.03, ...}}

which its JSON parser flattens into `ATTITUDE/roll`, `ATTITUDE/pitch`, … —
one plottable series per MAVLink field, named after the message it came from.

If you want *raw* MAVLink somewhere else, that already exists and does not
belong here: `sim_vehicle.py --out 127.0.0.1:<port>` is how 14551 is made, and
another `--out` gives QGroundControl or a second script the same stream.

WHY IT DOES NOT PARSE ANYTHING ITSELF
-------------------------------------
It does not decode a single byte. `MavlinkLink` already holds the one
pymavlink connection and every message passes through its `_absorb`; this
module is handed those already-decoded objects and only serialises them. There
is no second MAVLink implementation in the project and this did not add one.

WHY IT SENDS AND DOES NOT LISTEN
--------------------------------
Same discipline as 14550 and 14551: the producer sends, the consumer binds.
PlotJuggler's UDP Server *binds* the port, so ArgazUI must be the sender. Two
consequences worth writing down:

  * `argazui doctor` deliberately does **not** check this port. It checks that
    14550/14551 are free to bind; this one is *supposed* to be held — by
    PlotJuggler. A bind check would report FAIL exactly when the feature is
    working.
  * the socket is never `connect()`ed. A connected UDP socket receives the
    ICMP port-unreachable that comes back when nothing is listening, and every
    subsequent `send` raises `ECONNREFUSED`. Since not running PlotJuggler is
    the normal case, `sendto()` on an unconnected socket is the correct call:
    the datagrams go nowhere and cost nothing.
"""
from __future__ import annotations

import json
import math
import socket
import time
from typing import Callable, Optional

# Loopback only. This mirror carries live vehicle state with no authentication
# in front of it, and the project as a whole is localhost-only; there is no
# configuration that binds it to anything else.
HOST = "127.0.0.1"

# Never mirrored. BAD_DATA is not a message, it is the bytes the parser could
# not make one out of, and forwarding it would put garbage through a JSON
# encoder for no reader's benefit.
SKIP_TYPES = ("BAD_DATA",)


def _numeric(value):
    """The value as something JSON and a plotter can both use, or None.

    Three kinds are dropped rather than encoded:

      * strings and byte fields (`STATUSTEXT.text`, `PARAM_VALUE.param_id`) —
        nothing plots a string, and they are already in the run's event stream;
      * NaN and infinity, which ArduPilot really does send in unpopulated
        fields. `json.dumps` writes them as bare `NaN`/`Infinity`, which is not
        JSON — and PlotJuggler answers a message it cannot parse by *stopping
        the stream*, so one NaN would silently end the live plot;
      * anything else (nested structures do not occur in MAVLink payloads).
    """
    if isinstance(value, bool):
        return int(value)                       # plot a flag as 0/1, not true/false
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (list, tuple)):
        items = [_numeric(item) for item in value]
        return items if items and all(item is not None for item in items) else None
    return None


def encode(msg, when: float, namespace: str = "") -> Optional[bytes]:
    """One MAVLink message as one JSON datagram, or None if nothing plottable.

    `when` is wall-clock seconds. It is deliberately not the vehicle's own
    clock: different messages carry different time bases (`time_boot_ms`,
    `time_usec`, none at all), so there is no single field to key them on, and
    under SITL speedup the vehicle clock does not advance at one second per
    second. The reception time is the one axis every message shares — and it is
    the axis PlotJuggler uses by default, so a stream plots correctly with no
    options set. Vehicle timestamps are still present as ordinary fields for
    anyone who wants them.

    `namespace` (v1.3) prefixes the message key, so a fleet's N vehicles share
    one port without their series colliding:

        ""    -> {"t": ..., "ATTITUDE": {...}}       ATTITUDE/roll
        "v2"  -> {"t": ..., "v2/ATTITUDE": {...}}    v2/ATTITUDE/roll

    Empty by default, so the single-vehicle stream is byte-for-byte what v1.2
    produced. PlotJuggler's JSON parser splits on `/`, which is why the
    separator is a slash and not a dot — a dot would leave one flat series
    name per vehicle instead of a tree that can be expanded and collapsed.
    """
    kind = msg.get_type()
    if kind in SKIP_TYPES:
        return None
    fields = {}
    for name in msg.get_fieldnames():
        value = _numeric(getattr(msg, name, None))
        if value is not None:
            fields[name] = value
    if not fields:
        return None
    key = f"{namespace}/{kind}" if namespace else kind
    return json.dumps({"t": round(when, 6), key: fields},
                      separators=(",", ":")).encode("utf-8")


class TelemetryMirror:
    """A one-way UDP mirror of the live link, for a plotting tool to listen on.

    Opened when a session starts and closed when it stops, so the port is live
    for exactly as long as there is a vehicle to plot. `port=0` disables it
    entirely and every method becomes a no-op.
    """

    def __init__(self, port: int = 0, host: str = HOST,
                 on_log: Optional[Callable[[str], None]] = None,
                 namespace: str = "") -> None:
        self.port = int(port or 0)
        self.host = host
        # Per-vehicle series prefix for a fleet. Empty for the single-vehicle
        # path, which therefore emits exactly what v1.2 emitted.
        self.namespace = namespace or ""
        self.on_log = on_log or (lambda text: None)
        self._sock: Optional[socket.socket] = None
        self._sent = 0
        self._skipped = 0
        self._opened_at: Optional[float] = None
        # Reported once and then never again: a mirror that cannot send is a
        # nuisance, not a flight problem, and it must not fill the terminal
        # with one line per telemetry message.
        self._error: str = ""

    # ------------------------------------------------------------- lifecycle
    @property
    def enabled(self) -> bool:
        return self.port > 0

    @property
    def running(self) -> bool:
        return self._sock is not None

    def open(self) -> bool:
        if not self.enabled or self._sock is not None:
            return self.running
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        except OSError as exc:
            self._sock = None
            self._error = str(exc)
            return False
        self._sent = 0
        self._skipped = 0
        self._error = ""
        self._opened_at = time.time()
        return True

    def close(self) -> None:
        sock, self._sock = self._sock, None
        self._opened_at = None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    # ----------------------------------------------------------------- sending
    def send(self, msg) -> None:
        """Mirror one decoded MAVLink message. Never raises.

        Called from the link's worker thread for every message that arrives, so
        a fault here must not be able to take the vehicle connection with it.
        """
        sock = self._sock
        if sock is None:
            return
        try:
            payload = encode(msg, time.time(), self.namespace)
        except Exception:                       # a malformed message is not fatal
            payload = None
        if payload is None:
            self._skipped += 1
            return
        try:
            sock.sendto(payload, (self.host, self.port))
            self._sent += 1
        except OSError as exc:
            self._skipped += 1
            if not self._error:
                self._error = str(exc)
                self.on_log(f"telemetry mirror ({self.host}:{self.port}): {exc}")

    # ------------------------------------------------------------------ status
    def info(self) -> dict:
        """What the interface shows: where to listen, and whether it is flowing."""
        return {
            "enabled": self.enabled,
            "running": self.running,
            "host": self.host,
            "port": self.port,
            "messages": self._sent,
            "skipped": self._skipped,
            "seconds": (None if self._opened_at is None
                        else round(time.time() - self._opened_at, 1)),
            "error": self._error,
        }
