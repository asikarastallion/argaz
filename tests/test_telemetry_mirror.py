"""The live telemetry mirror: does a listener on that port really get a flight?

TWO KINDS OF TEST IN ONE FILE
-----------------------------
The encoder tests need no vehicle at all — they pin the shape of a datagram and
the two ways a plot dies silently (a NaN that makes the JSON invalid, a string
field that is not a series). The relay test needs a real one, because "the port
is open" is a claim and "a HEARTBEAT came out of it" is a measurement, and the
second is the only one worth making.

WHAT IS NOT ASSERTED HERE
-------------------------
That PlotJuggler draws a graph. Nothing automated in this project can see a
rendered window, and pretending otherwise is exactly the unearned tick this
suite exists to remove. That step is in docs/manual-checklist.md, marked as
covered by nothing but a person.

`tier1` on the encoder tests only says which CI job runs them.
"""
from __future__ import annotations

import json
import socket
import time

import pytest

from argazui import telemetry_mirror as mirror_mod
from argazui.telemetry_mirror import TelemetryMirror, encode

from support import boot

pytestmark = pytest.mark.tier1


# --------------------------------------------------------------------- encoder
class FakeMessage:
    """The surface `encode` uses, which is all pymavlink guarantees it needs.

    Deliberately not a real MAVLink message: these tests are about what leaves
    the mirror for values a vehicle can produce, and constructing a NaN-bearing
    ATTITUDE through pymavlink would test pymavlink.
    """

    def __init__(self, kind: str, **fields) -> None:
        self._kind = kind
        self._fields = fields
        for name, value in fields.items():
            setattr(self, name, value)

    def get_type(self) -> str:
        return self._kind

    def get_fieldnames(self) -> list:
        return list(self._fields)


def test_a_message_becomes_one_json_object_named_after_its_type():
    payload = encode(FakeMessage("ATTITUDE", roll=0.5, pitch=-0.25, time_boot_ms=1234),
                     when=1785938401.7325)
    document = json.loads(payload)

    # PlotJuggler's JSON parser flattens this into ATTITUDE/roll, ATTITUDE/pitch
    # …, which is the whole reason the fields are nested under the message name
    # rather than emitted flat.
    assert document["ATTITUDE"] == {"roll": 0.5, "pitch": -0.25, "time_boot_ms": 1234}
    assert document["t"] == pytest.approx(1785938401.7325)


def test_a_non_finite_field_is_dropped_rather_than_written_as_nan():
    """One NaN would end the live plot, not just spoil one point.

    `json.dumps` writes NaN and Infinity as bare literals, which are not JSON.
    PlotJuggler answers a datagram it cannot parse by STOPPING the stream
    ("Problem parsing the message. UDP Server will be stopped."), so a field
    ArduPilot leaves unpopulated would take the whole flight's plot with it.
    """
    payload = encode(FakeMessage("VFR_HUD", alt=12.5, airspeed=float("nan"),
                                 climb=float("inf")), when=1.0)
    document = json.loads(payload)          # would raise on a bare NaN

    assert document["VFR_HUD"] == {"alt": 12.5}
    assert "nan" not in payload.decode().lower()
    assert "inf" not in payload.decode().lower()


def test_text_fields_are_dropped_and_flags_become_numbers():
    payload = encode(FakeMessage("STATUSTEXT", severity=6, text="PreArm: waiting",
                                 blob=b"\x01\x02", ok=True), when=1.0)
    document = json.loads(payload)

    assert document["STATUSTEXT"] == {"severity": 6, "ok": 1}


def test_a_message_with_nothing_plottable_is_not_sent_at_all():
    assert encode(FakeMessage("STATUSTEXT", text="only words"), when=1.0) is None
    for kind in mirror_mod.SKIP_TYPES:
        assert encode(FakeMessage(kind, data=[1, 2, 3]), when=1.0) is None


# -------------------------------------------------------------------- socket
def test_a_disabled_mirror_never_opens_a_socket():
    mirror = TelemetryMirror(port=0)
    assert not mirror.enabled
    assert not mirror.open()
    assert not mirror.running
    mirror.send(FakeMessage("ATTITUDE", roll=0.1))       # must not raise
    assert mirror.info()["messages"] == 0


def test_sending_with_nothing_listening_is_not_an_error():
    """The normal case: PlotJuggler is not running, and the flight is fine.

    This is why the socket is never connect()ed. A connected UDP socket is told
    about the ICMP port-unreachable that comes back, and every later send would
    raise ECONNREFUSED — turning "no plotter today" into a stream of errors.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.bind(("127.0.0.1", 0))
        free_port = probe.getsockname()[1]           # bound, then released below

    mirror = TelemetryMirror(port=free_port)
    assert mirror.open()
    try:
        for _ in range(20):
            mirror.send(FakeMessage("ATTITUDE", roll=0.1))
        assert mirror.info()["messages"] == 20
        assert mirror.info()["error"] == ""
    finally:
        mirror.close()
    assert not mirror.running


# ------------------------------------------------------- against a real vehicle
def test_the_mirror_relays_a_live_flight_and_closes_with_the_session(request, runs_root):
    """A listener on the mirror port receives real vehicle telemetry.

    SITL's own generic quad frame, because this is an application-level feature:
    the claim is "a session mirrors its telemetry", not anything about a model.
    """
    listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    listener.bind(("127.0.0.1", 0))
    listener.settimeout(1.0)
    port = listener.getsockname()[1]

    frame = {"id": "sitl_quad", "name": "SITL quad frame", "vehicle_class": "Copter",
             "method": "sitl_frame", "vehicle": "ArduCopter", "frame": "quad"}
    try:
        vehicle = boot(request, runs_root, frame, frame["frame"], mirror_port=port)
        assert vehicle.link.mirror.running, "START did not open the mirror port"

        # Bounded: a heartbeat is 1 Hz, and the link is already connected by
        # the time boot() returns, so 30 s is generous rather than hopeful.
        seen = {}
        deadline = time.time() + 30
        while time.time() < deadline and "HEARTBEAT" not in seen:
            try:
                datagram, _ = listener.recvfrom(65535)
            except socket.timeout:
                continue
            # Every datagram must parse, not just the one we are waiting for:
            # a single invalid one stops PlotJuggler's stream (see the encoder
            # tests), so "some of them are JSON" is not good enough.
            document = json.loads(datagram)
            assert "t" in document, f"no timestamp in {document}"
            for name, fields in document.items():
                if name != "t":
                    seen[name] = fields

        assert "HEARTBEAT" in seen, (
            f"no HEARTBEAT reached the mirror port in 30 s; saw {sorted(seen)}\n"
            f"{vehicle.sitl.tail()}")
        assert "custom_mode" in seen["HEARTBEAT"], seen["HEARTBEAT"]
        assert vehicle.link.mirror.info()["messages"] > 0

        # ------------------------------------------------------------- STOP
        # The port must close with the session, not merely stop being useful.
        vehicle.link.stop()
        assert not vehicle.link.mirror.running

        # Drain whatever was already in the socket buffer, then prove silence.
        listener.settimeout(0.2)
        while True:
            try:
                listener.recvfrom(65535)
            except socket.timeout:
                break
        listener.settimeout(2.0)
        with pytest.raises(socket.timeout):
            listener.recvfrom(65535)
    finally:
        listener.close()
