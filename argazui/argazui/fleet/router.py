"""L4 — one link per vehicle, group commands, and the ACK matrix.

THREADS, NOT ASYNCIO, AND WHY
-----------------------------
The architecture note asks for one asyncio task per vehicle *and* for the v1.1
procedure engine to be reused per vehicle. Those are incompatible:
`ProcedureRunner` is synchronous and blocks on `MavlinkLink.submit()`, which
hands work to that link's single worker thread — the only thread allowed to
touch pymavlink. Rewriting the procedure engine to be async would rewrite the
one component whose stability the whole test suite rests on.

So: one `MavlinkLink` per vehicle, each with its own thread, exactly as the
single-vehicle path uses. One shared ordered event bus. asyncio stays at the
WebSocket edge, where it already lives.

A COMMAND RESULT IS NOT AN ACK
------------------------------
Every per-vehicle result carries two separate findings:

    the acknowledgement   did the autopilot accept the command?
    the confirmation      taken from heartbeats AFTER the ack, did the state
                          it was supposed to produce still hold `hold_s` later?

Both are needed because phase 3 caught a real case where the first said yes
and the second said no — ArduPlane accepted a mode change and was back in the
old mode 140 ms later, with no NAK and no STATUSTEXT. That is `REVERTED`, and
it is a distinct outcome from both ACCEPTED and DENIED. See outcomes.py.

NO sysid=0
----------
Every command is addressed to one vehicle over that vehicle's own link.
`MavlinkLink` targets `self._conn.target_system`, learned from the heartbeat
on that connection, so a fleet of N links is N distinct addresses with no
broadcast anywhere. A broadcast cannot be ACKed and therefore cannot be
verified, which makes it unusable here by construction rather than by policy.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from ..mavlink_link import MavlinkLink
from . import outcomes
from .eventbus import EventBus

# How long a state must hold after the ack before the command counts as
# ACCEPTED — in SIMULATED seconds, not wall-clock ones.
#
# WHY VEHICLE TIME, MEASURED RATHER THAN CHOSEN
# ---------------------------------------------
# This was a wall-clock constant, and that was wrong in both directions:
#
#   SITL-only at speedup 5   1.5 s wall = 7.5 VEHICLE seconds, three quarters
#                            of ArduCopter's 10 s DISARM_DELAY. Measured: a
#                            vehicle armed, held armed for the whole window,
#                            and had auto-disarmed by the next statement.
#   Gazebo lockstep          measured RTF 0.45-1.12 (mean ~0.6), so 1.5 s wall
#                            is only ~0.9 vehicle seconds — a *shorter* look
#                            at the aircraft than intended, in the tier that
#                            matters most.
#
# Every timer the question is really about — DISARM_DELAY, mode-switch
# re-reads, failsafes — runs on the vehicle's clock. So the window does too,
# and the conversion uses `MavlinkLink.speedup`, which is measured from the
# vehicle's own timestamps rather than assumed.
#
# 1.5 vehicle seconds is ~10x the 140 ms revert measured in phase 3 and 15%
# of DISARM_DELAY: wide enough to catch the failure, narrow enough not to
# trip over the aircraft's own housekeeping.
DEFAULT_HOLD_S = 1.5

# Whatever the simulation rate, one command may not block the fleet for
# longer than this in wall-clock terms. A world running at 0.05x would
# otherwise turn a 1.5 s window into half a minute.
MAX_HOLD_WALL_S = 8.0

# How often the hold window re-checks the vehicle's state.
HOLD_POLL_S = 0.1

DEFAULT_ACK_TIMEOUT_S = 15.0


@dataclass
class Confirmation:
    """What the state has to look like for a command to have worked."""

    describe: str
    check: Callable[[object], bool]

    def holds(self, state) -> bool:
        try:
            return bool(self.check(state))
        except Exception:
            return False


def mode_is(mode: str) -> Confirmation:
    return Confirmation(f"mode == {mode}",
                        lambda st, m=mode.upper(): (st.mode or "").upper() == m)


def armed_is(armed: bool) -> Confirmation:
    return Confirmation(f"armed == {armed}", lambda st, a=armed: st.armed == a)


def altitude_above(metres: float) -> Confirmation:
    return Confirmation(f"alt > {metres:g} m", lambda st, m=metres: st.alt > m)


@dataclass
class VehicleResult:
    """One vehicle's answer to one command. Both findings, never merged."""

    vehicle: str
    outcome: str
    t_ms: int = 0
    ack: str = ""                  # what the autopilot said
    reason: str = ""               # its own words when it refused
    confirmed: Optional[bool] = None
    observed: str = ""             # what the state actually looked like

    def as_dict(self) -> dict:
        return {"vehicle": self.vehicle, "outcome": self.outcome,
                "ack": self.ack, "reason": self.reason, "t_ms": self.t_ms,
                "confirmed": self.confirmed, "observed": self.observed}


@dataclass
class GroupResult:
    """The ACK matrix for one group command."""

    command: str
    target: list
    policy: str
    results: list = field(default_factory=list)
    seconds: float = 0.0

    @property
    def verdict(self) -> str:
        return outcomes.verdict_for(r.outcome for r in self.results)

    def by_outcome(self, outcome: str) -> list:
        return [r.vehicle for r in self.results if r.outcome == outcome]

    def as_dict(self) -> dict:
        return {"command": self.command, "target": list(self.target),
                "policy": self.policy, "verdict": self.verdict,
                "seconds": round(self.seconds, 2),
                "results": [r.as_dict() for r in self.results]}


# ------------------------------------------------------------------- targets
def resolve_target(target, spec, connected=None) -> list:
    """`all` | `selected` | ["v1","v3"] | `role:leader` -> vehicle ids.

    An unknown id raises rather than being dropped. A group command that
    silently commands three of the four vehicles it was given is the failure
    the explicit-target rule exists to prevent.
    """
    known = [v.id for v in spec.vehicles]

    if target in (None, "all"):
        return list(known)
    if target == "selected":
        return list(connected or [])
    if isinstance(target, str) and target.startswith("role:"):
        role = target.split(":", 1)[1].strip()
        return [v.id for v in spec.vehicles if v.role == role]
    if isinstance(target, str):
        target = [target]

    chosen = [str(t) for t in target]
    unknown = [t for t in chosen if t not in known]
    if unknown:
        raise ValueError(
            f"unknown vehicle(s) in target: {', '.join(unknown)}; "
            f"this fleet has {', '.join(known)}")
    return chosen


# -------------------------------------------------------------------- router
class FleetRouter:
    """Owns one link per vehicle and executes group commands against them."""

    def __init__(self, spec, links: dict, bus: Optional[EventBus] = None,
                 hold_s: float = DEFAULT_HOLD_S) -> None:
        self.spec = spec
        self.links = dict(links)               # vehicle_id -> MavlinkLink
        self.bus = bus or EventBus()
        self.hold_s = hold_s
        self.last_result: Optional[GroupResult] = None

    # ------------------------------------------------------------- vehicles
    def state(self, vehicle_id: str):
        link = self.links.get(vehicle_id)
        return link.state if link is not None else None

    def states(self) -> dict:
        return {vid: link.state.as_dict() for vid, link in self.links.items()}

    def connected(self) -> list:
        return [vid for vid, link in self.links.items()
                if link.is_running() and link.state.connected]

    # -------------------------------------------------------- one vehicle
    def _execute(self, vehicle_id: str, label: str,
                 action: Callable[[MavlinkLink], dict],
                 confirm: Optional[Confirmation],
                 ack_timeout: float) -> VehicleResult:
        """Send, collect the ack, then watch the state for `hold_s`."""
        link = self.links.get(vehicle_id)
        if link is None or not link.is_running():
            return VehicleResult(vehicle=vehicle_id, outcome=outcomes.NO_LINK,
                                 reason="no link to this vehicle")

        started = time.monotonic()
        try:
            response = link.submit(action, timeout=ack_timeout, label=label)
        except Exception as exc:
            return VehicleResult(
                vehicle=vehicle_id, outcome=outcomes.TIMEOUT,
                t_ms=int((time.monotonic() - started) * 1000),
                reason=f"{type(exc).__name__}: {exc}")
        elapsed_ms = int((time.monotonic() - started) * 1000)

        text = str(response.get("text", "") or "")
        if not response.get("ok"):
            # `MavlinkLink` reports a command that never came back with a
            # timeout message; anything else is the autopilot refusing.
            timed_out = "timeout" in text.lower() or "no link" in text.lower()
            return VehicleResult(
                vehicle=vehicle_id,
                outcome=outcomes.TIMEOUT if timed_out else outcomes.DENIED,
                t_ms=elapsed_ms, ack="NAK" if not timed_out else "",
                reason=text)

        result = VehicleResult(vehicle=vehicle_id, outcome=outcomes.ACCEPTED,
                               t_ms=elapsed_ms, ack="ACCEPTED", reason=text)
        if confirm is None:
            result.confirmed = None
            result.observed = "no state confirmation was requested"
            return result

        held, observed = self._hold(link, confirm)
        result.confirmed = held
        result.observed = observed
        if not held:
            result.outcome = outcomes.REVERTED
            result.reason = (f"acknowledged, then {observed}. The autopilot "
                             f"accepted the command and did not stay in the "
                             f"state it produces.")
        return result

    def hold_wall_seconds(self, link: MavlinkLink) -> float:
        """`hold_s` vehicle-seconds converted to wall time for this vehicle.

        `link.speedup` is measured from the vehicle's own timestamps and is
        1.0 until enough telemetry has arrived to know better, so a fresh link
        behaves exactly as a wall-clock window would.
        """
        rate = getattr(link, "speedup", 1.0) or 1.0
        rate = max(float(rate), 0.05)
        return min(self.hold_s / rate, MAX_HOLD_WALL_S)

    def _hold(self, link: MavlinkLink, confirm: Confirmation) -> tuple:
        """Watch the state for `hold_s` VEHICLE seconds after the ack.

        Returns (held-for-the-whole-window, what-was-seen). The check runs
        repeatedly rather than once at the end: a state that flickers away and
        back inside the window did not hold, and sampling only the final
        instant would call that ACCEPTED.
        """
        wall = self.hold_wall_seconds(link)
        rate = max(float(getattr(link, "speedup", 1.0) or 1.0), 0.05)
        deadline = time.monotonic() + wall
        broke_at = None
        while time.monotonic() < deadline:
            if not confirm.holds(link.state):
                broke_at = link.state.mode
                break
            time.sleep(HOLD_POLL_S)

        window = (f"{self.hold_s:g}s of vehicle time "
                  f"({wall:.2f}s wall at {rate:.2f}x)")
        if broke_at is None:
            return True, f"{confirm.describe} held for {window}"
        return False, (f"{confirm.describe} did not hold — vehicle is in "
                       f"{broke_at!r} after {window}")

    # ------------------------------------------------------ group commands
    def send(self, command: str, action_for: Callable[[str], Callable],
             confirm: Optional[Confirmation] = None, target=None,
             policy: Optional[str] = None, delay_s: Optional[float] = None,
             gate: Optional[Confirmation] = None,
             gate_timeout_s: float = 60.0,
             ack_timeout: float = DEFAULT_ACK_TIMEOUT_S) -> GroupResult:
        """Run one command against a target set and return the ACK matrix."""
        policy = policy or self.spec.policy.group_command
        delay_s = self.spec.policy.start_delay_s if delay_s is None else delay_s
        vehicles = resolve_target(target, self.spec, connected=self.connected())

        started = time.monotonic()
        self.bus.emit("group_command", command=command, target=list(vehicles),
                      policy=policy)

        if not vehicles:
            result = GroupResult(command=command, target=[], policy=policy,
                                 seconds=time.monotonic() - started)
            self.bus.emit("group_result", **result.as_dict())
            self.last_result = result
            return result

        if policy == "parallel_ack":
            results = self._parallel(vehicles, command, action_for, confirm,
                                     ack_timeout)
        elif policy == "staggered":
            results = self._staggered(vehicles, command, action_for, confirm,
                                      ack_timeout, delay_s)
        elif policy == "gated":
            results = self._gated(vehicles, command, action_for, confirm,
                                  ack_timeout, gate or confirm, gate_timeout_s)
        else:
            raise ValueError(
                f"unknown group command policy {policy!r}; expected "
                f"parallel_ack, staggered or gated")

        result = GroupResult(command=command, target=list(vehicles),
                             policy=policy, results=results,
                             seconds=time.monotonic() - started)
        for entry in results:
            # `vehicle` is a first-class field on an event, so it is passed
            # positionally and removed from the payload rather than being sent
            # twice — which is a TypeError, not a silent duplicate.
            payload = entry.as_dict()
            payload.pop("vehicle", None)
            self.bus.emit("command_result", vehicle=entry.vehicle,
                          command=command, **payload)
        self.bus.emit("group_result", **result.as_dict())
        self.last_result = result
        return result

    def _parallel(self, vehicles, command, action_for, confirm, ack_timeout):
        """All at once, ACKs collected together. One thread per vehicle.

        Ordered by the target list on return, not by which finished first — a
        matrix whose rows moved between runs would be unreadable.
        """
        collected: dict = {}
        lock = threading.Lock()

        def run(vehicle_id: str) -> None:
            entry = self._execute(vehicle_id, command, action_for(vehicle_id),
                                  confirm, ack_timeout)
            with lock:
                collected[vehicle_id] = entry

        threads = [threading.Thread(target=run, args=(v,), daemon=True,
                                    name=f"cmd-{command}-{v}")
                   for v in vehicles]
        for thread in threads:
            thread.start()
        budget = ack_timeout + self.hold_s + 10.0
        for thread in threads:
            thread.join(timeout=budget)

        return [collected.get(v) or VehicleResult(
                    vehicle=v, outcome=outcomes.TIMEOUT,
                    reason=f"the command thread did not finish within "
                           f"{budget:.0f}s")
                for v in vehicles]

    def _staggered(self, vehicles, command, action_for, confirm, ack_timeout,
                   delay_s):
        """One at a time with a fixed delay between them.

        Prevents the RTF spike of N simultaneous takeoffs, and the prop-wash
        interaction between vehicles ten metres apart.
        """
        results = []
        for index, vehicle_id in enumerate(vehicles):
            if index:
                time.sleep(delay_s)
            results.append(self._execute(vehicle_id, command,
                                         action_for(vehicle_id), confirm,
                                         ack_timeout))
        return results

    def _gated(self, vehicles, command, action_for, confirm, ack_timeout,
               gate, gate_timeout_s):
        """Vehicle i+1 starts only once vehicle i meets the gate condition.

        The safest and the slowest. A vehicle that never meets its gate stops
        the sequence: the remainder are reported as NO_LINK-free TIMEOUTs
        against the gate rather than being commanded into a situation the
        previous vehicle has not cleared.
        """
        results = []
        blocked = False
        for vehicle_id in vehicles:
            if blocked:
                results.append(VehicleResult(
                    vehicle=vehicle_id, outcome=outcomes.TIMEOUT,
                    reason=f"not commanded: an earlier vehicle never met the "
                           f"gate ({gate.describe if gate else 'n/a'})"))
                continue

            entry = self._execute(vehicle_id, command, action_for(vehicle_id),
                                  confirm, ack_timeout)
            results.append(entry)
            if entry.outcome != outcomes.ACCEPTED:
                blocked = True
                continue
            if gate is not None and not self._wait_gate(vehicle_id, gate,
                                                        gate_timeout_s):
                blocked = True
                entry.reason = (entry.reason + " " if entry.reason else "") + \
                    (f"but the gate {gate.describe!r} was not met within "
                     f"{gate_timeout_s:g}s, so the sequence stopped here")
        return results

    def _wait_gate(self, vehicle_id: str, gate: Confirmation,
                   timeout_s: float) -> bool:
        link = self.links.get(vehicle_id)
        if link is None:
            return False
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if gate.holds(link.state):
                self.bus.emit("gate_met", vehicle=vehicle_id,
                              gate=gate.describe)
                return True
            time.sleep(0.2)
        self.bus.emit("gate_missed", vehicle=vehicle_id, gate=gate.describe,
                      timeout_s=timeout_s)
        return False

    # ------------------------------------------------- convenience commands
    def set_mode(self, mode: str, target=None, **kwargs) -> GroupResult:
        mode = mode.upper()
        return self.send(f"MODE {mode}",
                         action_for=lambda v, m=mode: (lambda link: link._do_mode([m])),
                         confirm=mode_is(mode), target=target, **kwargs)

    def arm(self, target=None, **kwargs) -> GroupResult:
        return self.send("ARM",
                         action_for=lambda v: (lambda link: link._do_arm([], arm=True)),
                         confirm=armed_is(True), target=target, **kwargs)

    def disarm(self, target=None, **kwargs) -> GroupResult:
        return self.send("DISARM",
                         action_for=lambda v: (lambda link: link._do_arm([], arm=False)),
                         confirm=armed_is(False), target=target, **kwargs)

    # ------------------------------------------------------------- teardown
    def abort(self, vehicles=None, mode: str = "LAND") -> GroupResult:
        """Command the fleet down, and report whether it actually worked.

        `abort_fleet` is a safety policy, and a safety policy that cannot be
        verified is a wish. An abort that reaches nobody has aborted nothing,
        so this returns the same five-outcome matrix as any other command and
        the caller decides what the run status becomes from the verdict.

        "commanded down" and "confirmed down" are different claims.
        """
        target = list(vehicles) if vehicles is not None else None
        result = self.send(f"ABORT->{mode.upper()}",
                           action_for=lambda v, m=mode.upper():
                               (lambda link: link._do_mode([m])),
                           confirm=mode_is(mode), target=target,
                           policy="parallel_ack")
        self.bus.emit("fleet_abort_result", **result.as_dict())
        return result

    def stop(self) -> None:
        for link in self.links.values():
            try:
                link.stop()
            except Exception:
                pass
