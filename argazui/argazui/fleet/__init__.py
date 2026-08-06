"""Fleet engine — multi-vehicle simulation, beside the single-vehicle path.

WHAT THIS PACKAGE IS AND IS NOT
-------------------------------
It is an *additional* path. The single-vehicle path (session.py, app.py's
Manager, the START button) is untouched by everything in here, and
tests/test_characterisation.py exists to prove that stays true.

LAYERS, AND WHY THEY ARE SPLIT THIS WAY
---------------------------------------
    spec.py        L0  the declarative fleet contract and its validator
    formations.py  L0  spawn geometry — pure maths, no I/O at all
    allocator.py   L1  instance numbers, ports, working directories, leases

L0 and L1 own no processes and open no sockets except to *probe* one, which
is what lets the whole of Phase 1 run in CI in under a second. Everything that
forks, listens or flies arrives in later layers and stays out of these files.
"""
from __future__ import annotations

from .spec import (FleetSpec, VehicleSpec, Origin, Policy, Spawn,
                   Validation, FleetSpecError, load, load_by_name,
                   available, validate)

__all__ = ["FleetSpec", "VehicleSpec", "Origin", "Policy", "Spawn",
           "Validation", "FleetSpecError", "load", "load_by_name",
           "available", "validate"]
