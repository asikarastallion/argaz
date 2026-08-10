"""Controlled fault injection — simulation only, declared, recorded, reversible.

WHAT THIS IS
------------
Two faults, and only two: the GPS degrading or going away, and the MAVLink link
to the ground station being interrupted or made lossy. They exist so a
procedure can ask the question a nominal flight cannot — *what does this
aircraft do when something is wrong* — and answer it with the same evidence
chain a nominal flight produces.

WHY SO FEW
----------
A general fault DSL would take a week to write and produce scenarios nobody has
watched a vehicle respond to. These two were chosen because each has a
mechanism ArduPilot's own SITL already provides, an observable that is measured
rather than assumed, and a failure mode that occurs in real flying. Wind, motor
loss and arbitrary sensor corruption are deliberately not here.

FIVE RULES, AND EACH ONE EXISTS BECAUSE ITS OPPOSITE IS DANGEROUS
----------------------------------------------------------------
1. **Simulation only.** Every mechanism below writes a `SIM_*` parameter or
   changes ArgazUI's own socket behaviour. Nothing here has a path to hardware,
   and nothing here is conditional on being in a simulator — the mechanisms
   simply do not exist outside one, which is a stronger guarantee than a flag.

2. **Declared in the procedure.** A fault is a `failures:` entry in the YAML
   that ran, so it is in `scenario.yaml`, it is hashed into the run's
   fingerprint through the procedure text, and a run cannot have been degraded
   by something the archived document does not mention.

3. **Fail closed.** If the mechanism cannot be applied — an ArduPilot without
   the parameter, a value the vehicle refuses — the procedure ABORTS. It does
   not carry on nominally. An off-nominal test whose off-nominal condition
   never happened is a nominal test wearing the wrong name, and it would report
   a pass for a behaviour nobody exercised.

4. **Cleaned up.** Every injector restores what it changed, from a `finally`,
   including when the procedure fails or is cancelled. Whether the restore
   actually succeeded is recorded rather than assumed; a fault that could not
   be cleared is itself a classified failure.

5. **Deterministic.** No randomness anywhere. Packet loss drops one in N by
   count, not by probability, so two runs of the same scenario degrade the link
   in the same places.

WHY THE TIMING IS NOT IN HERE
-----------------------------
An injector knows how to make a fault happen and how to undo it. When it
happens, how long it is held and whether the aircraft behaved are the runner's
business, because they are measured on the vehicle's clock through the same
`_Window` the temporal acceptance criteria use. Splitting it that way keeps one
implementation of "a duration in a procedure means vehicle seconds".
"""
from __future__ import annotations

from typing import Any, Optional

SCHEMA = 1

# ------------------------------------------------------------------- kinds
GPS_LOSS = "gps_loss"
GPS_DEGRADATION = "gps_degradation"
MAVLINK_INTERRUPT = "mavlink_interrupt"
MAVLINK_DEGRADATION = "mavlink_degradation"

KINDS = (GPS_LOSS, GPS_DEGRADATION, MAVLINK_INTERRUPT, MAVLINK_DEGRADATION)

# Targets, per kind. Stated as a closed set rather than a free string: a typo
# in a target would otherwise inject a fault into nothing and report a pass.
#
# Only the primary GPS is offered. ArduPilot's SITL simulates a second GPS only
# when SIM_GPS2_ENABLE is set, so "disable GPS 2" on a normal model degrades
# nothing at all — which is exactly the silent no-op rule 3 above exists to
# prevent.
TARGETS: dict[str, tuple[str, ...]] = {
    GPS_LOSS: ("gps1",),
    GPS_DEGRADATION: ("gps1",),
    MAVLINK_INTERRUPT: ("gcs_link",),
    MAVLINK_DEGRADATION: ("gcs_link",),
}

# Signals a fault's verdict may be required to rest on. The value is the flag
# on `VehicleState` that says the signal has actually been observed — the same
# mechanism the temporal criteria use, for the same reason: a criterion judged
# against telemetry that never arrived reports silence as success.
EVIDENCE_SIGNALS: dict[str, str] = {
    "attitude": "attitude_known",
    "prearm": "prearm_known",
    "heartbeat": "connected",
}

# Options each kind accepts in the procedure, with their defaults. Anything
# else is a load-time error.
OPTIONS: dict[str, dict[str, Any]] = {
    GPS_LOSS: {},
    GPS_DEGRADATION: {"satellites": 4, "fix_type": None},
    MAVLINK_INTERRUPT: {},
    MAVLINK_DEGRADATION: {"drop_one_in": 2},
}

CATALOGUE: dict[str, dict] = {
    GPS_LOSS: {
        "label": {"en": "GPS loss", "tr": "GPS kaybi"},
        "what": {
            "en": "The simulated GPS receiver is switched off entirely. The "
                  "autopilot loses its absolute position source and falls back "
                  "on whatever its EKF can do without one.",
            "tr": "Simule GPS alicisi tamamen kapatilir. Otopilot mutlak konum "
                  "kaynagini kaybeder ve EKF'nin onsuz yapabildigine duser."},
        "mechanism": "SIM_GPS1_ENABLE = 0 (SIM_GPS_DISABLE = 1 on older "
                     "ArduPilot), restored to the value read before injection",
        "observe": {
            "en": "an EKF failsafe, a mode change chosen by the autopilot, and "
                  "position estimate drift",
            "tr": "EKF failsafe'i, otopilotun kendi sectigi bir mod degisimi "
                  "ve konum kestiriminde kayma"},
        "source": "https://ardupilot.org/dev/docs/using-sitl-for-ardupilot-testing.html",
    },
    GPS_DEGRADATION: {
        "label": {"en": "GPS degradation", "tr": "GPS bozulmasi"},
        "what": {
            "en": "The GPS keeps reporting, with fewer satellites and — where "
                  "the firmware supports it — a worse fix type. The autopilot "
                  "still has a position; it has a worse one.",
            "tr": "GPS bildirmeye devam eder ama uydu sayisi azalir ve — "
                  "yazilim destekliyorsa — fix tipi kotulesir. Otopilotun hala "
                  "bir konumu vardir; daha kotusu."},
        "mechanism": "SIM_GPS1_NUMSATS and SIM_GPS1_FIXTYPE, both restored",
        "observe": {
            "en": "pre-arm complaints, a larger EKF position innovation, and "
                  "in some modes a refusal to continue",
            "tr": "arm oncesi uyarilar, EKF konum yeniliginde buyume ve bazi "
                  "modlarda devam etmeyi reddetme"},
        "source": "https://ardupilot.org/dev/docs/using-sitl-for-ardupilot-testing.html",
    },
    MAVLINK_INTERRUPT: {
        "label": {"en": "MAVLink interruption", "tr": "MAVLink kesintisi"},
        "what": {
            "en": "ArgazUI stops transmitting and stops accepting telemetry for "
                  "the duration. To the autopilot the ground station has gone "
                  "away; to ArgazUI the aircraft has.",
            "tr": "ArgazUI belirtilen sure boyunca gondermeyi ve telemetri "
                  "kabul etmeyi birakir. Otopilota gore yer istasyonu, "
                  "ArgazUI'ye gore arac ortadan kaybolmustur."},
        "mechanism": "the link's own socket handling — no packet is sent and "
                     "every received packet is discarded unread",
        "observe": {
            "en": "the GCS failsafe if the model enables one, and — always — "
                  "whether the aircraft is still where it was when the link "
                  "comes back",
            "tr": "model etkinlestirmisse GCS failsafe'i ve her durumda "
                  "baglanti geri geldiginde aracin hala ayni durumda olup "
                  "olmadigi"},
        "source": "https://ardupilot.org/copter/docs/gcs-failsafe.html",
    },
    MAVLINK_DEGRADATION: {
        "label": {"en": "MAVLink degradation", "tr": "MAVLink bozulmasi"},
        "what": {
            "en": "One received packet in N is discarded, by count rather than "
                  "by chance. The link works and is lossy, which is the state a "
                  "real telemetry radio spends most of its life in.",
            "tr": "Alinan her N pakettten biri, sansa degil sayiya gore "
                  "atilir. Baglanti calisir ama kayiplidir; gercek bir "
                  "telemetri radyosunun cogu zaman icinde bulundugu durum."},
        "mechanism": "the link discards every Nth received message; nothing is "
                     "written to the vehicle",
        "observe": {
            "en": "whether acceptance criteria that rest on telemetry still "
                  "have enough samples to be judged at all",
            "tr": "telemetriye dayanan kabul kriterlerinin hala "
                  "degerlendirilebilecek kadar ornek bulup bulmadigi"},
        "source": "https://ardupilot.org/dev/docs/mavlink-basics.html",
    },
}

# ------------------------------------------------------- GPS parameter families
# ArduPilot renamed the SITL GPS parameters when it gained multiple simulated
# receivers: `SIM_GPS_DISABLE` became `SIM_GPS1_ENABLE`, with the sense
# inverted. Both are probed and whichever the connected vehicle answers is
# used, because ArgazUI is a front end for a checkout it does not control.
GPS_SCHEMES: tuple[dict, ...] = (
    {
        "id": "gps1",
        "enable": "SIM_GPS1_ENABLE", "on": 1.0, "off": 0.0,
        "satellites": "SIM_GPS1_NUMSATS", "fix_type": "SIM_GPS1_FIXTYPE",
    },
    {
        "id": "legacy",
        "enable": "SIM_GPS_DISABLE", "on": 0.0, "off": 1.0,
        "satellites": "SIM_GPS_NUMSATS", "fix_type": None,
    },
)


class FaultUnavailable(RuntimeError):
    """The mechanism this fault needs does not exist on this vehicle.

    Raised by `probe()`, before anything has been changed. The runner turns it
    into an aborted procedure with an `environment` failure classification —
    never into a nominal flight.
    """


class FaultRefused(RuntimeError):
    """The mechanism exists and the vehicle would not accept the change."""


# ------------------------------------------------------------------ injectors
class Injector:
    """Applies one fault to one live vehicle, and undoes it.

    Every subclass follows the same three-call contract:

        probe()   is the mechanism here? Raises FaultUnavailable if not.
                  Changes nothing.
        apply()   make the fault happen. Raises FaultRefused if it did not.
        clear()   put it back. Returns whether it succeeded; never raises,
                  because it is called from a `finally` and the procedure's own
                  verdict must survive it.
    """

    kind = ""

    def __init__(self, target: str, options: Optional[dict] = None) -> None:
        self.target = target
        self.options = dict(options or {})
        self.applied = False
        self.cleared: Optional[bool] = None
        # What was changed and what it was before, for the run record. A fault
        # that says only "GPS loss" cannot be reproduced; this can.
        self.changed: dict[str, dict] = {}
        self.mechanism_text = ""

    # -- contract ----------------------------------------------------------
    def probe(self, link) -> None:                   # pragma: no cover - base
        raise NotImplementedError

    def apply(self, link) -> None:                   # pragma: no cover - base
        raise NotImplementedError

    def clear(self, link) -> bool:                   # pragma: no cover - base
        raise NotImplementedError

    # -- reporting ---------------------------------------------------------
    def as_dict(self) -> dict:
        return {"kind": self.kind, "target": self.target,
                "options": dict(self.options), "mechanism": self.mechanism_text,
                "changed": self.changed,
                "applied": self.applied, "cleared": self.cleared}


class GpsInjector(Injector):
    """GPS loss and GPS degradation, through ArduPilot's own SIM_GPS parameters."""

    def __init__(self, kind: str, target: str, options: Optional[dict] = None) -> None:
        super().__init__(target, options)
        self.kind = kind
        self.scheme: Optional[dict] = None

    def _params(self) -> list[tuple[str, float]]:
        """(parameter, value) pairs this fault writes, given the probed scheme."""
        scheme = self.scheme or {}
        if self.kind == GPS_LOSS:
            return [(scheme["enable"], scheme["off"])]
        out: list[tuple[str, float]] = []
        satellites = self.options.get("satellites")
        if satellites is not None and scheme.get("satellites"):
            out.append((scheme["satellites"], float(satellites)))
        fix_type = self.options.get("fix_type")
        if fix_type is not None and scheme.get("fix_type"):
            out.append((scheme["fix_type"], float(fix_type)))
        return out

    def probe(self, link) -> None:
        tried: list[str] = []
        for scheme in GPS_SCHEMES:
            value = link.submit(
                lambda l, n=scheme["enable"]: {"ok": True, "value": l._param_get(n)},
                timeout=8.0, label=f"probe {scheme['enable']}").get("value")
            tried.append(scheme["enable"])
            if value is not None:
                self.scheme = scheme
                break
        if self.scheme is None:
            raise FaultUnavailable(
                f"this ArduPilot exposes none of {', '.join(tried)}, so a "
                f"simulated GPS fault cannot be injected. The scenario is not "
                f"run rather than run without its fault.")

        if self.kind == GPS_DEGRADATION and not self._params():
            # Degradation with nothing to degrade. Explicitly refused rather
            # than allowed to inject nothing and pass.
            missing = "SIM_GPS1_FIXTYPE" if self.options.get("fix_type") is not None \
                else "the satellite count"
            raise FaultUnavailable(
                f"none of the degradation knobs this scenario asks for exist on "
                f"this firmware ({missing}); nothing would be degraded")
        self.mechanism_text = ", ".join(
            f"{name} = {value:g}" for name, value in self._params())

    def apply(self, link) -> None:
        for name, value in self._params():
            def _set(l, n=name, v=value) -> dict:
                previous = l._param_get(n)
                res = l._do_param(["set", n, str(v)])
                if res.get("ok"):
                    res["previous"] = previous
                return res

            res = link.submit(_set, timeout=12.0, label=f"fault {name}")
            if not res.get("ok"):
                raise FaultRefused(
                    f"the vehicle refused {name} = {value:g}: "
                    f"{res.get('text', 'no reason reported')}")
            self.changed[name] = {"set_to": value, "restore_to": res.get("previous")}
        self.applied = True

    def clear(self, link) -> bool:
        ok = True
        for name, record in self.changed.items():
            previous = record.get("restore_to")
            if previous is None:
                # Unreadable before the write, so there is nothing to put back
                # and nothing to claim. Recorded, not silently skipped.
                record["restored"] = None
                ok = False
                continue
            res = link.submit(
                lambda l, n=name, v=previous: l._do_param(["set", n, str(v)]),
                timeout=12.0, label=f"restore {name}")
            record["restored"] = bool(res.get("ok"))
            ok = ok and bool(res.get("ok"))
        self.cleared = ok
        return ok


class LinkInjector(Injector):
    """MAVLink interruption and degradation, in ArgazUI's own link.

    WHY NOT A SIM_ PARAMETER
    ------------------------
    ArduPilot has no parameter for "the ground station went away", and it
    should not: the ground station is this program. The fault therefore lives
    where the fault would live in reality — in the link — and it is honest in
    both directions, because ArgazUI genuinely stops hearing the aircraft for
    the duration rather than pretending to.
    """

    def __init__(self, kind: str, target: str, options: Optional[dict] = None) -> None:
        super().__init__(target, options)
        self.kind = kind

    def _fault(self) -> dict:
        if self.kind == MAVLINK_INTERRUPT:
            return {"drop_one_in": 1, "block_tx": True}
        return {"drop_one_in": int(self.options.get("drop_one_in", 2)),
                "block_tx": False}

    def probe(self, link) -> None:
        if not hasattr(link, "set_link_fault"):
            raise FaultUnavailable(
                "this MAVLink link does not implement fault injection")
        spec = self._fault()
        self.mechanism_text = (
            "every received packet discarded, nothing transmitted"
            if spec["block_tx"] else
            f"one received packet in {spec['drop_one_in']} discarded")

    def apply(self, link) -> None:
        spec = self._fault()
        link.set_link_fault(**spec)
        self.changed["link"] = {"set_to": spec, "restore_to": None}
        self.applied = True

    def clear(self, link) -> bool:
        link.clear_link_fault()
        # Unlike a parameter write this cannot be refused: it is a flag in this
        # process, and the call above has already returned.
        for record in self.changed.values():
            record["restored"] = True
        self.cleared = True
        return True


def injector_for(kind: str, target: str, options: Optional[dict] = None) -> Injector:
    """The mechanism for one declared fault."""
    if kind in (GPS_LOSS, GPS_DEGRADATION):
        return GpsInjector(kind, target, options)
    if kind in (MAVLINK_INTERRUPT, MAVLINK_DEGRADATION):
        return LinkInjector(kind, target, options)
    raise ValueError(f"unknown fault kind {kind!r}")


# ------------------------------------------------------------------ validation
def check_declaration(kind: Any, target: Any, options: Any, where: str) -> dict:
    """Validates one `failures:` entry's mechanism half. Returns the options.

    Raises ValueError with a message naming the alternatives; procedures.py
    turns that into a ProcedureError so a typo fails at load time rather than
    in flight.
    """
    if kind not in KINDS:
        raise ValueError(
            f"{where}: unknown fault '{kind}'. Implemented: {', '.join(KINDS)}. "
            f"Wind, motor failure and arbitrary sensor corruption are "
            f"deliberately not implemented.")
    allowed_targets = TARGETS[kind]
    if target not in allowed_targets:
        raise ValueError(
            f"{where}: '{kind}' can only target {', '.join(allowed_targets)}, "
            f"not {target!r}")

    spec = OPTIONS[kind]
    given = dict(options or {})
    for key in given:
        if key not in spec:
            raise ValueError(
                f"{where}: '{kind}' takes no option '{key}'"
                + (f". Known: {', '.join(spec)}" if spec else " at all"))
    resolved = {**spec, **given}

    if kind == GPS_DEGRADATION:
        satellites = resolved.get("satellites")
        if satellites is not None and not 0 <= float(satellites) <= 20:
            raise ValueError(f"{where}: satellites must be between 0 and 20")
        fix_type = resolved.get("fix_type")
        if fix_type is not None and int(fix_type) not in range(0, 7):
            raise ValueError(
                f"{where}: fix_type is ArduPilot's AP_GPS_FixType, 0-6 "
                f"(0 no GPS, 1 no fix, 2 2D, 3 3D, 4 DGPS, 5 RTK float, "
                f"6 RTK fixed)")
        if resolved.get("satellites") is None and fix_type is None:
            raise ValueError(
                f"{where}: state at least one of satellites or fix_type — a "
                f"degradation that degrades nothing is a nominal flight")
    if kind == MAVLINK_DEGRADATION:
        drop = int(resolved.get("drop_one_in", 2))
        if drop < 2:
            raise ValueError(
                f"{where}: drop_one_in must be 2 or more. 1 would discard every "
                f"packet, which is '{MAVLINK_INTERRUPT}' — declare that instead, "
                f"so the run record says what actually happened.")
        resolved["drop_one_in"] = drop
    return resolved


def label_for(kind: str, lang: str = "en") -> str:
    entry = CATALOGUE.get(kind, {}).get("label", {})
    return entry.get(lang) or entry.get("en") or kind


def catalogue(lang: str = "en") -> list[dict]:
    """The published fault catalogue, for the interface and the docs portal."""
    return [{"kind": kind,
             "label": spec["label"].get(lang) or spec["label"]["en"],
             "what": spec["what"].get(lang) or spec["what"]["en"],
             "observe": spec["observe"].get(lang) or spec["observe"]["en"],
             "mechanism": spec["mechanism"],
             "targets": list(TARGETS[kind]),
             "options": dict(OPTIONS[kind]),
             "source": spec["source"]}
            for kind, spec in CATALOGUE.items()]
