"""L0 — the fleet spec: a declarative contract, and a validator with no mercy.

WHY A FILE AND NOT CODE
-----------------------
"Reproducible" is a claim, and a claim needs something to point at. A fleet is
defined in `argazui/config/fleets/<name>.toml`, that file is snapshotted into
every run directory, and running the same file twice is the only thing that
makes two runs comparable. Nothing about a fleet is decided in Python.

EVERY RULE IS AN ERROR, NOT A WARNING
-------------------------------------
A warning in a launcher is a line of text nobody reads at the moment it
appears, because at that moment four vehicles are starting. All of these stop
the fleet:

    * duplicate, zero or out-of-range sysid
    * a model that Tier 2 has not passed  (unless declared — see below)
    * mixed launch methods in one world
    * two spawn points closer than min_separation_m
    * more vehicles than argaz.toml allows
    * a formation AND explicit spawn blocks

MODEL ELIGIBILITY IS TIER 2, NEVER TIER 1
-----------------------------------------
Tier 1 flies SITL's own generic frames and — by this project's central rule —
verifies nothing about any registered model. So the validator reads the most
recent **Tier 2** suite record, through the same `status.collect()` the status
table is generated from, and rejects any model not marked `passed`.

    THE ESCAPE HATCH, AND WHY IT IS SHAPED LIKE THIS
    A machine with no Tier 2 data must still be able to fly a fleet, but never
    silently. A spec may set

        allow_unverified = true
        unverified_reason = "first bring-up on a fresh clone; no tier 2 yet"

    The reason is MANDATORY — `allow_unverified` without one is itself an
    error. It is stamped into fleet.json and printed at the top of
    fleet_report.md, exactly the way a procedure's parameter overrides are.
    A fleet that skips verification says so on the front page of its own
    report or it does not run.

SITL-ONLY FLEETS
----------------
A fleet with no `world` is Gazebo-free: its vehicles name a SITL frame
(`frame = "quad"`) instead of a registry model. No registered model is
involved, so model eligibility does not apply. This is what Tier 2 of the
fleet suite flies, and it is the reason roughly 80% of the fleet engine can be
tested without Gazebo at all.
"""
from __future__ import annotations

import math
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .. import paths
from . import formations
from .formations import Point

SCHEMA_VERSION = 1

FLEETS_DIR = paths.CONFIG_DIR / "fleets"

START_POLICIES = ("parallel", "staggered", "gated")
FAILURE_POLICIES = ("abort_fleet", "continue_degraded", "hold")
GROUP_COMMAND_POLICIES = ("parallel_ack", "staggered", "gated")

# Launch methods that can share one Gazebo world. `ros2_launch` starts its own
# Gazebo *and* its own SITL through a launch file, so it cannot be one vehicle
# among several in a world this project composed.
COMPOSABLE_METHODS = ("gz_plus_sitl_paramfile", "gz_plus_sitl_frame")

SYSID_MIN, SYSID_MAX = 1, 255


class FleetSpecError(ValueError):
    """The spec file could not be read or parsed at all."""


# --------------------------------------------------------------------- pieces
@dataclass(frozen=True)
class Origin:
    """The world's datum. Must match the world's <spherical_coordinates>."""

    lat: float
    lon: float
    alt: float = 0.0
    heading: float = 0.0

    def as_dict(self) -> dict:
        return {"lat": self.lat, "lon": self.lon, "alt": self.alt,
                "heading": self.heading}


@dataclass(frozen=True)
class Policy:
    start: str = "staggered"
    start_delay_s: float = 3.0
    on_vehicle_failure: str = "abort_fleet"
    group_command: str = "parallel_ack"

    def as_dict(self) -> dict:
        return {"start": self.start, "start_delay_s": self.start_delay_s,
                "on_vehicle_failure": self.on_vehicle_failure,
                "group_command": self.group_command}


# Re-exported so callers do not have to know spawn points live in formations.py.
Spawn = Point


@dataclass
class VehicleSpec:
    """One vehicle. Either a registry `model` or a bare SITL `frame`."""

    id: str
    sysid: int
    model: Optional[str] = None       # id in models.json (Gazebo fleets)
    frame: Optional[str] = None       # SITL frame name (Gazebo-free fleets)
    vehicle: Optional[str] = None     # ArduCopter / ArduPlane, required with frame
    spawn: Optional[Point] = None     # None until a formation resolves it
    role: str = ""
    params: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"id": self.id, "sysid": self.sysid, "model": self.model,
                "frame": self.frame, "vehicle": self.vehicle,
                "spawn": self.spawn.as_dict() if self.spawn else None,
                "role": self.role, "params": dict(self.params)}


@dataclass
class FleetSpec:
    name: str
    vehicles: list[VehicleSpec]
    origin: Origin
    world: Optional[str] = None
    description: str = ""
    formation: str = "explicit"
    spacing_m: float = 10.0
    radius_m: float = 20.0
    max_rtf_drop: float = 0.35
    min_separation_m: float = 5.0
    policy: Policy = field(default_factory=Policy)
    allow_unverified: bool = False
    unverified_reason: str = ""
    path: Optional[Path] = None

    @property
    def gazebo(self) -> bool:
        """A fleet with a world needs Gazebo; one without is SITL-only."""
        return bool(self.world)

    @property
    def count(self) -> int:
        return len(self.vehicles)

    def vehicle(self, vehicle_id: str) -> Optional[VehicleSpec]:
        return next((v for v in self.vehicles if v.id == vehicle_id), None)

    def as_dict(self) -> dict:
        """The snapshot written into `runs/<run_id>/fleet.json`."""
        return {
            "schema": SCHEMA_VERSION,
            "name": self.name,
            "description": self.description,
            "world": self.world,
            "gazebo": self.gazebo,
            "formation": self.formation,
            "spacing_m": self.spacing_m,
            "radius_m": self.radius_m,
            "max_rtf_drop": self.max_rtf_drop,
            "min_separation_m": self.min_separation_m,
            "origin": self.origin.as_dict(),
            "policy": self.policy.as_dict(),
            "allow_unverified": self.allow_unverified,
            "unverified_reason": self.unverified_reason,
            "vehicles": [v.as_dict() for v in self.vehicles],
            "source": str(self.path) if self.path else "",
        }


@dataclass
class Validation:
    """What the validator found. `ok` is `not errors` — warnings never block."""

    spec: Optional[FleetSpec]
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict:
        return {"ok": self.ok, "errors": list(self.errors),
                "warnings": list(self.warnings), "notes": list(self.notes),
                "fleet": self.spec.as_dict() if self.spec else None}


# --------------------------------------------------------------------- loading
def available(directory: Optional[Path] = None) -> list[str]:
    """Fleet names with a spec file, sorted. Never raises on a bad file."""
    directory = Path(directory or FLEETS_DIR)
    if not directory.is_dir():
        return []
    return sorted(p.stem for p in directory.glob("*.toml") if p.is_file())


def load_by_name(name: str, directory: Optional[Path] = None) -> FleetSpec:
    directory = Path(directory or FLEETS_DIR)
    path = directory / f"{name}.toml"
    if not path.is_file():
        known = available(directory)
        raise FleetSpecError(
            f"no fleet spec called {name!r} in {directory}"
            + (f" — available: {', '.join(known)}" if known else " (none defined)"))
    return load(path)


def load(path: Path) -> FleetSpec:
    """Parse a spec file into a FleetSpec. Shape errors raise; rule violations
    are for `validate()`, which needs a parsed spec to report against."""
    path = Path(path)
    try:
        with path.open("rb") as handle:
            document = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise FleetSpecError(f"cannot read fleet spec {path}: {exc}") from exc

    fleet = document.get("fleet")
    if not isinstance(fleet, dict):
        raise FleetSpecError(f"{path}: missing a [fleet] table")

    raw_vehicles = document.get("vehicle")
    if not isinstance(raw_vehicles, list) or not raw_vehicles:
        raise FleetSpecError(f"{path}: needs at least one [[vehicle]] entry")

    origin_raw = fleet.get("origin")
    if not isinstance(origin_raw, dict):
        raise FleetSpecError(
            f"{path}: [fleet.origin] is required — it must match the world's "
            f"<spherical_coordinates>, and guessing it puts every vehicle's "
            f"EKF position somewhere the simulation is not")
    for key in ("lat", "lon"):
        if origin_raw.get(key) is None:
            raise FleetSpecError(f"{path}: [fleet.origin] needs {key}")
    origin = Origin(lat=float(origin_raw["lat"]), lon=float(origin_raw["lon"]),
                    alt=float(origin_raw.get("alt", 0.0)),
                    heading=float(origin_raw.get("heading", 0.0)))

    policy_raw = fleet.get("policy") or {}
    if not isinstance(policy_raw, dict):
        raise FleetSpecError(f"{path}: [fleet.policy] must be a table")
    default = Policy()
    policy = Policy(
        start=str(policy_raw.get("start", default.start)),
        start_delay_s=float(policy_raw.get("start_delay_s", default.start_delay_s)),
        on_vehicle_failure=str(policy_raw.get("on_vehicle_failure",
                                              default.on_vehicle_failure)),
        group_command=str(policy_raw.get("group_command", default.group_command)))

    vehicles = [_parse_vehicle(raw, index, path)
                for index, raw in enumerate(raw_vehicles)]

    return FleetSpec(
        name=str(fleet.get("name") or path.stem),
        description=str(fleet.get("description", "")),
        world=(str(fleet["world"]) if fleet.get("world") else None),
        formation=str(fleet.get("formation", "explicit")),
        spacing_m=float(fleet.get("spacing_m", 10.0)),
        radius_m=float(fleet.get("radius_m", 20.0)),
        max_rtf_drop=float(fleet.get("max_rtf_drop", 0.35)),
        min_separation_m=float(fleet.get("min_separation_m", 5.0)),
        origin=origin,
        policy=policy,
        allow_unverified=bool(fleet.get("allow_unverified", False)),
        unverified_reason=str(fleet.get("unverified_reason", "")).strip(),
        vehicles=vehicles,
        path=path)


def _parse_vehicle(raw: Any, index: int, path: Path) -> VehicleSpec:
    where = f"{path}: [[vehicle]] #{index + 1}"
    if not isinstance(raw, dict):
        raise FleetSpecError(f"{where} must be a table")
    if not raw.get("id"):
        raise FleetSpecError(f"{where} needs an id")
    if raw.get("sysid") is None:
        raise FleetSpecError(f"{where} ({raw['id']}) needs a sysid")
    try:
        sysid = int(raw["sysid"])
    except (TypeError, ValueError) as exc:
        raise FleetSpecError(
            f"{where} ({raw['id']}): sysid must be a whole number, "
            f"got {raw['sysid']!r}") from exc

    spawn = None
    spawn_raw = raw.get("spawn")
    if spawn_raw is not None:
        if not isinstance(spawn_raw, dict):
            raise FleetSpecError(f"{where} ({raw['id']}): spawn must be a table")
        spawn = Point(east_m=float(spawn_raw.get("east_m", 0.0)),
                      north_m=float(spawn_raw.get("north_m", 0.0)),
                      up_m=float(spawn_raw.get("up_m", formations.DEFAULT_UP_M)),
                      yaw_deg=float(spawn_raw.get("yaw_deg", 0.0)))

    params = raw.get("params") or {}
    if not isinstance(params, dict):
        raise FleetSpecError(f"{where} ({raw['id']}): params must be a table")

    return VehicleSpec(
        id=str(raw["id"]), sysid=sysid,
        model=(str(raw["model"]) if raw.get("model") else None),
        frame=(str(raw["frame"]) if raw.get("frame") else None),
        vehicle=(str(raw["vehicle"]) if raw.get("vehicle") else None),
        spawn=spawn, role=str(raw.get("role", "")),
        params={str(k).upper(): v for k, v in params.items()})


# ------------------------------------------------------------------ validation
# Measured, not derived from core count. See docs/fleet-rtf-scaling.md.
#
# THE CPU FORMULA WAS WRONG AND THE MEASUREMENT SAYS SO
# -----------------------------------------------------
# v1.3 phase 1 used `max(2, cores // 2)`, which on a 16-core machine allows 8
# vehicles. Phase 5 measured what actually happens, three hovering vehicles at
# a time, in one Gazebo world:
#
#     vehicles   RTF mean   RTF min   sim seconds per wall second
#         2        0.781     0.544              0.886
#         3        0.572     0.361              0.607
#         4        0.434     0.265              0.489
#
# Simulated throughput falls as roughly 1.77/N. It is NOT limited by cores —
# the machine has sixteen and four vehicles already halve it — because Gazebo
# steps physics serially and lockstep makes the server wait for every FDM in
# turn. Adding cores does not buy vehicles.
#
# At four vehicles the *minimum* RTF (0.265) is already below the 0.35 that
# the shipped specs set as `max_rtf_drop`, so eight would be far past the
# point where every measurement describes the host rather than the fleet.
#
# Four is therefore the default ceiling: the largest count measured to stay
# usable, with the runtime RTF monitor — not this number — as the real guard.
DEFAULT_MAX_VEHICLES = 4


def max_vehicles() -> int:
    """The ceiling from argaz.toml, or the measured default.

    A guard rail against an obviously impossible fleet, not a performance
    guarantee. What actually decides whether a run was viable is the RTF
    monitor, which measures the world that ran rather than predicting it.
    """
    configured = getattr(paths, "FLEET_MAX_VEHICLES", None)
    if configured:
        return int(configured)
    return DEFAULT_MAX_VEHICLES


def resolve_spawns(spec: FleetSpec) -> list[str]:
    """Fill in spawn points from the formation. Returns errors, if any.

    Mutates `spec.vehicles`, so a validated spec always carries concrete spawn
    points whichever way they were specified — which is what lets the
    separation check, the SDF generator and the report all read one field.
    """
    explicit = [v for v in spec.vehicles if v.spawn is not None]

    if spec.formation == "explicit":
        missing = [v.id for v in spec.vehicles if v.spawn is None]
        if missing:
            return [f"formation is 'explicit', so every vehicle needs a spawn "
                    f"block — missing on: {', '.join(missing)}"]
        return []

    if explicit:
        return [f"formation is {spec.formation!r} AND {len(explicit)} vehicle(s) "
                f"carry an explicit spawn block ({', '.join(v.id for v in explicit)}). "
                f"They are mutually exclusive: either the formation places every "
                f"vehicle or every vehicle places itself."]

    try:
        points = formations.generate(spec.formation, len(spec.vehicles),
                                     spacing_m=spec.spacing_m,
                                     radius_m=spec.radius_m)
    except formations.FormationError as exc:
        return [str(exc)]

    for vehicle, point in zip(spec.vehicles, points):
        vehicle.spawn = point
    return []


def validate(spec: FleetSpec, registry: Optional[dict] = None,
             runs_roots: Optional[list[Path]] = None) -> Validation:
    """Every rule, with no simulation started and nothing launched."""
    result = Validation(spec=spec)
    errors, warnings, notes = result.errors, result.warnings, result.notes

    # -- identity ---------------------------------------------------------
    seen_ids: dict[str, int] = {}
    for vehicle in spec.vehicles:
        seen_ids[vehicle.id] = seen_ids.get(vehicle.id, 0) + 1
    for vehicle_id, times in sorted(seen_ids.items()):
        if times > 1:
            errors.append(f"vehicle id {vehicle_id!r} is used {times} times; "
                          f"ids address vehicles in commands and must be unique")

    by_sysid: dict[int, list[str]] = {}
    for vehicle in spec.vehicles:
        by_sysid.setdefault(vehicle.sysid, []).append(vehicle.id)
    for sysid, owners in sorted(by_sysid.items()):
        if len(owners) > 1:
            errors.append(
                f"sysid {sysid} is claimed by {', '.join(owners)}. Every command "
                f"is addressed by sysid, so duplicates mean a command reaches "
                f"more than one vehicle and only one ACK comes back.")
        if sysid == 0:
            errors.append(
                f"{owners[0]}: sysid 0 is the broadcast address. It is never "
                f"ACKed, so nothing it is sent to can be verified.")
        elif not (SYSID_MIN <= sysid <= SYSID_MAX):
            errors.append(f"{owners[0]}: sysid {sysid} is outside {SYSID_MIN}"
                          f"–{SYSID_MAX} (SITL rejects it too)")

    # -- size -------------------------------------------------------------
    ceiling = max_vehicles()
    if spec.count > ceiling:
        errors.append(
            f"{spec.count} vehicles, but the ceiling is {ceiling} "
            f"(fleet.max_vehicles in argaz.toml; default "
            f"{DEFAULT_MAX_VEHICLES}, measured rather than derived from the "
            f"{os.cpu_count()} cores this machine has). Simulated throughput "
            f"falls as roughly 1.77/N because Gazebo steps physics serially "
            f"and lockstep waits for every FDM in turn — see "
            f"docs/fleet-rtf-scaling.md.")

    # -- policies ---------------------------------------------------------
    for value, allowed, label in (
            (spec.policy.start, START_POLICIES, "fleet.policy.start"),
            (spec.policy.on_vehicle_failure, FAILURE_POLICIES,
             "fleet.policy.on_vehicle_failure"),
            (spec.policy.group_command, GROUP_COMMAND_POLICIES,
             "fleet.policy.group_command")):
        if value not in allowed:
            errors.append(f"{label} is {value!r}; expected one of "
                          f"{', '.join(allowed)}")
    if spec.formation not in formations.FORMATIONS:
        errors.append(f"formation is {spec.formation!r}; expected one of "
                      f"{', '.join(formations.FORMATIONS)}")
    if spec.min_separation_m <= 0:
        errors.append(f"min_separation_m must be positive, got "
                      f"{spec.min_separation_m!r}")

    # -- spawn geometry ---------------------------------------------------
    errors.extend(resolve_spawns(spec))
    points = [v.spawn for v in spec.vehicles if v.spawn is not None]
    if len(points) == len(spec.vehicles) and len(points) > 1:
        closest, left, right = formations.closest_pair(points)
        if closest < spec.min_separation_m:
            errors.append(
                f"{spec.vehicles[left].id} and {spec.vehicles[right].id} spawn "
                f"{closest:.2f} m apart, closer than min_separation_m="
                f"{spec.min_separation_m:g}. Overlapping spawns detonate the "
                f"physics before anything has flown.")
        else:
            notes.append(f"closest spawn pair: {spec.vehicles[left].id} ↔ "
                         f"{spec.vehicles[right].id} at {closest:.2f} m "
                         f"(minimum {spec.min_separation_m:g} m)")

    # -- what each vehicle actually is ------------------------------------
    errors.extend(_validate_airframes(spec, registry, runs_roots, warnings, notes))

    return result


def _validate_airframes(spec: FleetSpec, registry: Optional[dict],
                        runs_roots: Optional[list[Path]],
                        warnings: list[str], notes: list[str]) -> list[str]:
    """Model/frame selection, launch-method compatibility, Tier-2 eligibility."""
    from .. import status as statuslib

    errors: list[str] = []

    for vehicle in spec.vehicles:
        if vehicle.model and vehicle.frame:
            errors.append(f"{vehicle.id}: names both a model ({vehicle.model!r}) "
                          f"and a SITL frame ({vehicle.frame!r}); pick one")
        elif not vehicle.model and not vehicle.frame:
            errors.append(f"{vehicle.id}: needs either model (a registry id, for "
                          f"a Gazebo fleet) or frame (a SITL frame, for a "
                          f"Gazebo-free one)")
        elif vehicle.frame and not vehicle.vehicle:
            errors.append(f"{vehicle.id}: frame {vehicle.frame!r} also needs "
                          f"vehicle = \"ArduCopter\" or \"ArduPlane\" — the "
                          f"frame name alone does not say which binary to run")

    modelled = [v for v in spec.vehicles if v.model]
    framed = [v for v in spec.vehicles if v.frame and not v.model]

    if spec.gazebo and framed:
        errors.append(
            f"fleet declares world {spec.world!r} but "
            f"{', '.join(v.id for v in framed)} name a bare SITL frame. A frame "
            f"has no Gazebo model to place in that world.")
    if not spec.gazebo and modelled:
        errors.append(
            f"fleet has no world, so it is SITL-only, but "
            f"{', '.join(v.id for v in modelled)} name registry models "
            f"({', '.join(sorted({v.model for v in modelled}))}). A registry "
            f"model needs the Gazebo world its SDF belongs to.")

    if not modelled:
        # A SITL-only fleet: no registered model is involved, so there is
        # nothing for Tier 2 to have verified.
        if spec.allow_unverified:
            warnings.append(
                "allow_unverified is set on a fleet with no registry models. "
                "It has no effect here — model eligibility only applies to "
                "Gazebo fleets.")
        return errors

    registry = registry or _read_registry()
    known = {m.get("id"): m for m in registry.get("models", [])}

    unknown = [v for v in modelled if v.model not in known]
    for vehicle in unknown:
        errors.append(
            f"{vehicle.id}: model {vehicle.model!r} is not in models.json"
            + (f" — known: {', '.join(sorted(k for k in known if k))}"
               if known else ""))

    # -- launch-method compatibility --------------------------------------
    methods: dict[str, list[str]] = {}
    for vehicle in modelled:
        entry = known.get(vehicle.model)
        if entry is None:
            continue
        methods.setdefault(entry.get("method", "?"), []).append(
            f"{vehicle.id} ({vehicle.model})")
    if len(methods) > 1:
        detail = "; ".join(f"{method}: {', '.join(owners)}"
                           for method, owners in sorted(methods.items()))
        errors.append(f"a fleet shares one Gazebo world, so every vehicle must "
                      f"use the same launch method. This one mixes {len(methods)} "
                      f"— {detail}")
    for method, owners in sorted(methods.items()):
        if method not in COMPOSABLE_METHODS:
            errors.append(
                f"launch method {method!r} cannot be composed into a fleet "
                f"({', '.join(owners)}). It starts its own Gazebo and its own "
                f"SITL through a launch file, so it cannot be one vehicle among "
                f"several in a world ArgazUI generated. Composable methods: "
                f"{', '.join(COMPOSABLE_METHODS)}.")

    # -- Tier-2 eligibility ------------------------------------------------
    errors.extend(_check_tier2(spec, modelled, known, registry, runs_roots,
                               warnings, notes))
    return errors


def _check_tier2(spec: FleetSpec, modelled: list[VehicleSpec],
                 known: dict, registry: dict, runs_roots: Optional[list[Path]],
                 warnings: list[str], notes: list[str]) -> list[str]:
    """Reject any model the most recent Tier-2 record does not mark passed."""
    from .. import status as statuslib

    errors: list[str] = []

    if spec.allow_unverified and not spec.unverified_reason:
        errors.append(
            "allow_unverified is set but unverified_reason is empty. Skipping "
            "verification is allowed; skipping it silently is not — the reason "
            "is stamped into fleet.json and printed at the top of "
            "fleet_report.md.")

    roots = [Path(r) for r in (runs_roots or [paths.RUNS_DIR])]
    data = statuslib.collect(roots, registry=registry)
    results = {row.model_id: row for row in data["rows"]}

    # Grouped by model, because the verdict is about the model. A fleet of
    # eight on one unverified airframe is one problem, and printing it eight
    # times is how the line that matters gets scrolled past.
    users: dict[str, list[str]] = {}
    for vehicle in modelled:
        if vehicle.model in results:
            users.setdefault(vehicle.model, []).append(vehicle.id)

    for model_id, vehicle_ids in sorted(users.items()):
        row = results[model_id]
        who = ", ".join(vehicle_ids)
        if row.result == statuslib.PASSED:
            notes.append(f"{model_id} passed tier 2"
                         + (f" ({row.last_run})" if row.last_run else "")
                         + f" — flown by {who}")
            continue

        because = (row.reason or "").strip()
        detail = (f"model {model_id!r} is '{row.result}' in the most recent "
                  f"tier-2 record"
                  + (f" — {because}" if because else "")
                  + f". It is used by {who}. "
                  f"Tier 2 is the only tier that verifies a model.")
        if spec.allow_unverified:
            warnings.append(detail + " Allowed by allow_unverified: "
                            + spec.unverified_reason)
        else:
            errors.append(
                detail + " Set allow_unverified = true with an "
                "unverified_reason to fly it anyway.")
    return errors


def _read_registry() -> dict:
    import json
    try:
        return json.loads(paths.MODELS_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise FleetSpecError(f"cannot read {paths.MODELS_JSON}: {exc}") from exc


def validate_by_name(name: str, directory: Optional[Path] = None,
                     registry: Optional[dict] = None,
                     runs_roots: Optional[list[Path]] = None) -> Validation:
    """Load and validate in one call — what the CLI and the UI badge use."""
    return validate(load_by_name(name, directory), registry=registry,
                    runs_roots=runs_roots)
