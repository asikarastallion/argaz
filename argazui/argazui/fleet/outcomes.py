"""The five things that can happen to a command, and why there are five.

WHY NOT TWO
-----------
v1.1 established that an ACK is not a pass: a command can be acknowledged and
still not do anything. v1.3 phase 3 caught the sharpest instance of that in
the wild — ArduPlane accepted a mode change, returned no NAK and no
STATUSTEXT, and was back in the previous mode 140 ms later:

    t=6.85  mode  MANUAL -> FBWA     the command was accepted
    t=6.99  mode  FBWA   -> MANUAL   and then it was not

Reported as ACCEPTED, that is a lie. Reported as DENIED, it is a different lie
— the autopilot did accept it, and an operator hunting a rejection reason will
find none. It is a third thing, and it needs a third name.

    ACCEPTED   acked, and the state still held after the hold window
    REVERTED   acked, and the state did NOT hold
    DENIED     rejected, carrying the autopilot's own reason text
    TIMEOUT    no acknowledgement inside the window
    NO_LINK    there was nothing to acknowledge it

Collapsing REVERTED into either neighbour reintroduces exactly the untruth
v1.1 removed, one level up.

WHY A GROUP VERDICT IS NOT A BOOLEAN EITHER
-------------------------------------------
    PASSED    every targeted vehicle reached ACCEPTED
    PARTIAL   some did, some did not — the normal case worth reporting
    FAILED    none did
    EMPTY     the target resolved to no vehicles at all

EMPTY is separate from FAILED on purpose. "I commanded four vehicles and none
obeyed" and "I commanded nothing" are different events, and a target selector
that quietly resolves to nobody is a bug that would otherwise report success.
"""
from __future__ import annotations

ACCEPTED = "ACCEPTED"
REVERTED = "REVERTED"
DENIED = "DENIED"
TIMEOUT = "TIMEOUT"
NO_LINK = "NO_LINK"

OUTCOMES = (ACCEPTED, REVERTED, DENIED, TIMEOUT, NO_LINK)

# The only outcome that means the vehicle is doing what was asked.
SUCCESSFUL = (ACCEPTED,)

PASSED = "PASSED"
PARTIAL = "PARTIAL"
FAILED = "FAILED"
EMPTY = "EMPTY"

VERDICTS = (PASSED, PARTIAL, FAILED, EMPTY)


def verdict_for(outcomes) -> str:
    """The group verdict from the per-vehicle outcomes."""
    outcomes = list(outcomes)
    if not outcomes:
        return EMPTY
    good = sum(1 for o in outcomes if o in SUCCESSFUL)
    if good == len(outcomes):
        return PASSED
    if good == 0:
        return FAILED
    return PARTIAL


def describe(outcome: str) -> str:
    """One line, for a report or a tooltip."""
    return {
        ACCEPTED: "acknowledged, and the state held",
        REVERTED: "acknowledged, but the vehicle did not stay in that state",
        DENIED: "rejected by the autopilot",
        TIMEOUT: "no acknowledgement arrived in time",
        NO_LINK: "no link to the vehicle",
    }.get(outcome, outcome)
