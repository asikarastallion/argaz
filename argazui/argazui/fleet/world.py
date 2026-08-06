"""L2 — the world composer: N models in one world, each on its own FDM port.

THE PROBLEM, STATED EXACTLY
---------------------------
`ardupilot_gazebo` model SDFs carry `<fdm_port_in>9002</fdm_port_in>` inside
the model. Including the same model four times gives four plugins all binding
9002 — and because `SocketUDP` is constructed with `reuseaddress=true`
(ArduPilotPlugin.cc:227), all four binds SUCCEED. There is no error, no log
line, and no failed bind to notice. The vehicles then silently share one
stream of servo commands.

THREE APPROACHES WERE TRIED. TWO WORK. ONE IS A TRAP.
-----------------------------------------------------
Measured on Gazebo Sim 8.14.0 (Harmonic), judged by which UDP ports the `gz`
process actually binds. Full write-up in docs/fleet-world-composition.md.

  A  `<plugin>` override inside `<include>`      REJECTED
     It ADDS a second ArduPilotPlugin rather than replacing the model's own.
     Two vehicles overridden to 9012 and 9022 bound {9002, 9012, 9022} — the
     built-in 9002 is still there, on BOTH vehicles, sharing one port. The
     first test of this looked like it worked only because one override value
     happened to equal the built-in default. This is the most dangerous of the
     three precisely because it looks correct.

  B  per-vehicle materialisation into the run dir   KEPT
     Copy the model directory, patch `fdm_port_in`, rename the model, fix the
     namespaced `<imuName>`, prepend the run directory to
     GZ_SIM_RESOURCE_PATH. Bound exactly {9002, 9012}.

  C  runtime spawn via `gz service .../create`      WORKS, NOT USED IN v1.3
     Verified: spawning a materialised model bound 9012 with no errors. But it
     still needs a materialised SDF, so it is not an alternative to B — it is
     a different way to PLACE what B produces. B is kept because the generated
     `fleet.sdf` is itself the reproducibility artefact the run directory has
     to contain, and because every vehicle then exists before physics starts,
     which keeps lockstep consistent from the first step. C is the path for
     adding a vehicle mid-run, which v1.3 does not do.

ONLY `fdm_port_in` IS PATCHED
-----------------------------
`fdm_addr` is the plugin's BIND address (`sock.bind(fdm_address, fdm_port_in)`)
and stays 127.0.0.1. The reply path is not configured at all: the plugin learns
SITL's address from the first packet it receives (`get_client_address`), and
SITL's FDM socket is unbound with an ephemeral source port. See
docs/fleet-ports.md.
"""
from __future__ import annotations

import re
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .allocator import FleetAllocation, VehicleAllocation
from .geo import enu_to_lla
from .spec import FleetSpec

SCHEMA_VERSION = 1


class WorldCompositionError(RuntimeError):
    """The world could not be composed. Never leaves a half-built run dir."""


@dataclass
class ComposedWorld:
    """What the composer produced, and where it put it."""

    world_path: Path
    models_dir: Path
    vehicle_models: dict = field(default_factory=dict)   # vehicle_id -> Path
    resource_path_prefix: list = field(default_factory=list)
    base_world: Optional[Path] = None
    removed_includes: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"schema": SCHEMA_VERSION,
                "world": str(self.world_path),
                "models_dir": str(self.models_dir),
                "base_world": str(self.base_world) if self.base_world else "",
                "removed_includes": list(self.removed_includes),
                "vehicle_models": {k: str(v) for k, v in self.vehicle_models.items()},
                "resource_path_prefix": [str(p) for p in self.resource_path_prefix]}


# --------------------------------------------------------------- model patching
def _patch_model_sdf(text: str, vehicle_id: str, fdm_port: int) -> tuple[str, str]:
    """Returns (patched xml, original model name).

    Three edits, and the third is the one that is easy to miss:

      1. `<fdm_port_in>`  -> this vehicle's port. The whole point.
      2. `<model name=>`  -> the vehicle id, so two copies can coexist in one
         world without a name collision.
      3. `<imuName>`      -> re-namespaced. It reads
         `iris_with_standoffs::imu_link::imu_sensor`, i.e. it is prefixed with
         the ORIGINAL model name. Renaming the model without fixing this
         leaves the plugin looking for a sensor under a name that no longer
         exists — and the plugin still binds its port and still logs nothing,
         so the failure looks like "the vehicle does not respond" rather than
         like a broken reference.
    """
    match = re.search(r'<model\s+name="([^"]+)"', text)
    if not match:
        raise WorldCompositionError("model.sdf has no <model name=...> element")
    original = match.group(1)

    if "<fdm_port_in>" not in text:
        raise WorldCompositionError(
            "model.sdf has no <fdm_port_in> — this is not an ardupilot_gazebo "
            "model, so there is no FDM port to give it")

    text = re.sub(r"<fdm_port_in>\s*\d+\s*</fdm_port_in>",
                  f"<fdm_port_in>{fdm_port}</fdm_port_in>", text)
    text = re.sub(r'<model\s+name="[^"]+"', f'<model name="{vehicle_id}"',
                  text, count=1)

    def _renamespace(m: re.Match) -> str:
        parts = m.group(1).split("::")
        if len(parts) > 1 and parts[0] == original:
            parts[0] = vehicle_id
        return f"<imuName>{'::'.join(parts)}</imuName>"

    text = re.sub(r"<imuName>([^<]+)</imuName>", _renamespace, text)
    return text, original


def materialise_model(base_model_dir: Path, target_dir: Path, vehicle_id: str,
                      fdm_port: int) -> Path:
    """Copy one model directory and make it this vehicle's own."""
    base_model_dir = Path(base_model_dir)
    if not base_model_dir.is_dir():
        raise WorldCompositionError(f"model directory not found: {base_model_dir}")
    sdf = base_model_dir / "model.sdf"
    if not sdf.is_file():
        raise WorldCompositionError(f"no model.sdf in {base_model_dir}")

    target_dir = Path(target_dir)
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(base_model_dir, target_dir)

    patched, original = _patch_model_sdf(sdf.read_text(encoding="utf-8"),
                                         vehicle_id, fdm_port)
    (target_dir / "model.sdf").write_text(patched, encoding="utf-8")

    # model.config carries the name Gazebo shows in its resource listing. A
    # stale one is not fatal but makes four identical entries in the GUI.
    config = target_dir / "model.config"
    if config.is_file():
        config.write_text(
            re.sub(r"<name>[^<]*</name>", f"<name>{vehicle_id}</name>",
                   config.read_text(encoding="utf-8"), count=1),
            encoding="utf-8")
    return target_dir


# ---------------------------------------------------------------- world building
def _indent(element: ET.Element, level: int = 0) -> None:
    """Two-space indentation, so a generated world is readable evidence."""
    pad = "\n" + "  " * level
    if len(element):
        if not (element.text or "").strip():
            element.text = pad + "  "
        for child in element:
            _indent(child, level + 1)
        if not (child.tail or "").strip():
            child.tail = pad
    if level and not (element.tail or "").strip():
        element.tail = pad


def _spherical_coordinates(spec: FleetSpec) -> ET.Element:
    """The datum, emitted from [fleet.origin] so the world is self-describing.

    MEASURED CAVEAT, RECORDED HERE SO NOBODY RE-DERIVES IT
    ------------------------------------------------------
    This does NOT change where SITL thinks the vehicle is. The plugin reports
    a local ENU offset from the world origin, and SITL converts it against its
    own `--custom-location` home; Gazebo's datum is not in that path. Measured
    both ways — with and without this block, one iris at pose `10 0 0.2`
    reported the identical latitude, longitude and NED east (9.995 m).

    It is emitted anyway because the generated world is an artefact somebody
    reads later, and a world that states its own datum cannot disagree with
    the spec that produced it. It also gives every other Gazebo consumer
    (the GUI, ros_gz bridges, any future sensor plugin) the same reference the
    fleet spec declares.
    """
    node = ET.Element("spherical_coordinates")
    for tag, value in (("surface_model", "EARTH_WGS84"),
                       ("world_frame_orientation", "ENU"),
                       ("latitude_deg", f"{spec.origin.lat:.7f}"),
                       ("longitude_deg", f"{spec.origin.lon:.7f}"),
                       ("elevation", f"{spec.origin.alt:.2f}"),
                       ("heading_deg", f"{spec.origin.heading:.1f}")):
        ET.SubElement(node, tag).text = value
    return node


def _looks_like_vehicle(include: ET.Element, model_names: set) -> bool:
    uri = (include.findtext("uri") or "").strip()
    tail = uri.rsplit("/", 1)[-1]
    return tail in model_names


def compose(spec: FleetSpec, allocation: FleetAllocation, base_world: Path,
            base_model_dir: Path, run_dir: Path,
            gazebo_model_name: Optional[str] = None) -> ComposedWorld:
    """Materialise N models and generate `fleet.sdf` from the base world.

    `gazebo_model_name` is the name the base world includes for the single
    vehicle it already contains — that include is removed, because a fleet
    world must contain the fleet and nothing else. It defaults to the base
    model directory's own name.
    """
    run_dir = Path(run_dir)
    models_dir = run_dir / "models"
    world_dir = run_dir / "world"
    base_world = Path(base_world)
    if not base_world.is_file():
        raise WorldCompositionError(f"base world not found: {base_world}")

    try:
        tree = ET.parse(base_world)
    except ET.ParseError as exc:
        raise WorldCompositionError(f"cannot parse {base_world}: {exc}") from exc

    world = tree.getroot().find("world")
    if world is None:
        raise WorldCompositionError(f"{base_world} has no <world> element")

    composed = ComposedWorld(world_path=world_dir / "fleet.sdf",
                             models_dir=models_dir, base_world=base_world)

    # -- one materialised model per vehicle -------------------------------
    for vehicle in spec.vehicles:
        entry = allocation.for_vehicle(vehicle.id)
        if entry is None:
            raise WorldCompositionError(
                f"no allocation for vehicle {vehicle.id!r}; the allocator and "
                f"the spec disagree about which vehicles exist")
        composed.vehicle_models[vehicle.id] = materialise_model(
            base_model_dir, models_dir / vehicle.id, vehicle.id, entry.fdm_port)

    # -- strip the base world's own vehicle --------------------------------
    names = {gazebo_model_name or Path(base_model_dir).name}
    for include in list(world.findall("include")):
        if _looks_like_vehicle(include, names):
            composed.removed_includes.append(
                (include.findtext("uri") or "").strip())
            world.remove(include)

    # -- state the datum ----------------------------------------------------
    for existing in list(world.findall("spherical_coordinates")):
        world.remove(existing)
    world.insert(0, _spherical_coordinates(spec))

    # -- place the fleet ----------------------------------------------------
    for vehicle in spec.vehicles:
        entry = allocation.for_vehicle(vehicle.id)
        spawn = vehicle.spawn
        if spawn is None:
            raise WorldCompositionError(
                f"vehicle {vehicle.id!r} has no spawn point; validate the spec "
                f"before composing a world from it")
        include = ET.SubElement(world, "include")
        ET.SubElement(include, "name").text = vehicle.id
        pose = ET.SubElement(include, "pose")
        pose.set("degrees", "true")
        # SDF <pose> is "x y z roll pitch yaw"; the Gazebo world frame is ENU,
        # so x is east and y is north.
        pose.text = (f"{spawn.east_m:g} {spawn.north_m:g} {spawn.up_m:g} "
                     f"0 0 {spawn.yaw_deg:g}")
        ET.SubElement(include, "uri").text = f"model://{vehicle.id}"

    _indent(tree.getroot())
    world_dir.mkdir(parents=True, exist_ok=True)
    tree.write(composed.world_path, encoding="unicode", xml_declaration=True)
    # ElementTree omits the trailing newline; a generated file that is read by
    # humans and diffed by git gets one.
    with composed.world_path.open("a", encoding="utf-8") as handle:
        handle.write("\n")

    composed.resource_path_prefix = [models_dir]
    return composed


def resource_path(composed: ComposedWorld, existing: str = "") -> str:
    """GZ_SIM_RESOURCE_PATH with the run's models FIRST.

    First, not appended: the materialised copies are named after vehicles
    (`v1`, `v2`) so they cannot collide with the base model's name, but
    prepending keeps the run directory authoritative for anything it does
    define — which is what makes a run reproducible from its own artefacts.
    """
    parts = [str(p) for p in composed.resource_path_prefix]
    if existing:
        parts.append(existing)
    return ":".join(parts)


def home_for(spec: FleetSpec) -> str:
    """The `--home` every vehicle in a GAZEBO fleet shares.

    One home for the whole fleet. The per-vehicle ENU offsets live in the
    Gazebo `<pose>` and are already reflected in what the plugin reports, so
    offsetting home per vehicle would count them twice. Measured; see
    docs/fleet-world-composition.md.

    Not for SITL-only fleets — use `home_for_vehicle`, which handles both.
    """
    return (f"{spec.origin.lat:.7f},{spec.origin.lon:.7f},"
            f"{spec.origin.alt:.2f},{spec.origin.heading:.1f}")


def home_for_vehicle(spec: FleetSpec, vehicle_id: str) -> str:
    """One vehicle's `--home`, and the rule differs by fleet kind.

    THE ASYMMETRY, AND WHY IT IS NOT AN INCONSISTENCY
    -------------------------------------------------
    The spawn offset has to be expressed exactly once. Which channel carries
    it depends on whether there is a Gazebo in the loop:

      GAZEBO fleet     the `<pose>` in the generated world carries it, and the
                       plugin reports the model's WORLD pose, so SITL already
                       sees the offset. Home is the fleet origin for every
                       vehicle. Adding it again would double it.

      SITL-ONLY fleet  there is no world and no pose. Each SITL runs its own
                       physics from its own home and nothing else knows where
                       it is. If every vehicle shared one home, all of them
                       would sit at the same coordinates — the exact "every
                       EKF believes it is at the same point" failure, arrived
                       at from the other direction.

    So: shared home with Gazebo, offset home without. Same principle in both —
    the offset is applied once — and the two branches exist because the number
    of channels available differs, not because the rule does.
    """
    vehicle = spec.vehicle(vehicle_id)
    if vehicle is None:
        raise WorldCompositionError(f"no vehicle {vehicle_id!r} in fleet "
                                    f"{spec.name!r}")
    if spec.gazebo:
        return home_for(spec)

    if vehicle.spawn is None:
        raise WorldCompositionError(
            f"vehicle {vehicle_id!r} has no resolved spawn point; validate the "
            f"spec before deriving a home from it")
    point = enu_to_lla(spec.origin.lat, spec.origin.lon, spec.origin.alt,
                       vehicle.spawn.east_m, vehicle.spawn.north_m,
                       vehicle.spawn.up_m)
    heading = spec.origin.heading + vehicle.spawn.yaw_deg
    return f"{point.lat:.7f},{point.lon:.7f},{point.alt:.2f},{heading % 360:.1f}"


def spawn_lla(spec: FleetSpec, vehicle_id: str) -> dict:
    """Where a vehicle actually is, in absolute terms, for the run record."""
    vehicle = spec.vehicle(vehicle_id)
    if vehicle is None or vehicle.spawn is None:
        raise WorldCompositionError(f"no resolved spawn for {vehicle_id!r}")
    return enu_to_lla(spec.origin.lat, spec.origin.lon, spec.origin.alt,
                      vehicle.spawn.east_m, vehicle.spawn.north_m,
                      vehicle.spawn.up_m).as_dict()
