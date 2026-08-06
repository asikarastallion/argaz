"""L0 — the fleet spec and its validator. Pure: nothing here starts anything.

WHAT THESE TESTS ARE PROTECTING
-------------------------------
Every rule in the validator exists because breaking it produces a failure that
is expensive or confusing to diagnose *after* four vehicles are in the air:

    duplicate sysid      every command reaches more than one vehicle and only
                         one ACK comes back
    sysid 0              broadcast, never ACKed, unverifiable
    close spawns         overlapping collision geometry detonates the physics
                         before anything has flown
    mixed launch method  a `ros2_launch` model brings its own Gazebo and its
                         own SITL, so it cannot be one vehicle among several
    unverified model     a fleet is not the place to discover an airframe
                         does not fly

So each is asserted as an ERROR here, and each assertion checks the *message*
names the offending vehicle. A validator that says "invalid" without saying
which vehicle is a validator nobody reads twice.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from argazui.fleet import formations, spec as fleetspec

pytestmark = pytest.mark.tier1


ORIGIN = """
[fleet.origin]
lat = -35.363262
lon = 149.165237
alt = 584.0
"""


def write(tmp_path: Path, body: str, name: str = "probe") -> Path:
    path = tmp_path / f"{name}.toml"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def toml_keys(**pairs) -> str:
    """Render keys as TOML, not as Python.

    `f"{True}"` is `True`, which TOML rejects — and the resulting parse error
    surfaces as an unrelated-looking failure three tests away. Booleans are
    lowercased here so a helper cannot invent a syntax error.
    """
    lines = []
    for key, value in pairs.items():
        if isinstance(value, bool):
            lines.append(f"{key} = {str(value).lower()}")
        elif isinstance(value, str):
            lines.append(f"{key} = {value!r}")
        else:
            lines.append(f"{key} = {value}")
    return "\n".join(lines)


# Written flush-left: these bodies are edited with str.replace() in the tests
# below, and an indented heredoc makes every multi-line pattern depend on how
# far it happens to be indented here.
def sitl_fleet(**fleet_keys) -> str:
    """A valid Gazebo-free two-vehicle spec, as a string to be edited."""
    return f"""
[fleet]
name = "probe"
formation = "line"
spacing_m = 10.0
min_separation_m = 5.0
{toml_keys(**fleet_keys)}
{ORIGIN}
[[vehicle]]
id = "v1"
frame = "quad"
vehicle = "ArduCopter"
sysid = 1

[[vehicle]]
id = "v2"
frame = "quad"
vehicle = "ArduCopter"
sysid = 2
"""


def errors_of(path: Path, **kwargs) -> list[str]:
    return fleetspec.validate(fleetspec.load(path), **kwargs).errors


def joined(messages: list[str]) -> str:
    return "\n".join(messages)


# ------------------------------------------------------------------- loading
def test_a_valid_sitl_only_fleet_passes(tmp_path):
    result = fleetspec.validate(fleetspec.load(write(tmp_path, sitl_fleet())))
    assert result.ok, joined(result.errors)
    assert result.spec.gazebo is False
    assert result.spec.count == 2


def test_a_spec_with_no_vehicles_is_rejected_at_load(tmp_path):
    path = write(tmp_path, f'[fleet]\nname = "empty"\n{ORIGIN}')
    with pytest.raises(fleetspec.FleetSpecError, match="at least one"):
        fleetspec.load(path)


def test_a_missing_origin_is_rejected_at_load(tmp_path):
    """Guessing the datum puts every EKF somewhere the simulation is not."""
    path = write(tmp_path, """
        [fleet]
        name = "no_origin"
        [[vehicle]]
        id = "v1"
        frame = "quad"
        vehicle = "ArduCopter"
        sysid = 1
        """)
    with pytest.raises(fleetspec.FleetSpecError, match="origin"):
        fleetspec.load(path)


def test_an_unknown_fleet_name_lists_what_does_exist(tmp_path):
    (tmp_path / "real_one.toml").write_text("[fleet]\n", encoding="utf-8")
    with pytest.raises(fleetspec.FleetSpecError, match="real_one"):
        fleetspec.load_by_name("nope", directory=tmp_path)


# -------------------------------------------------------------------- sysids
def test_a_duplicate_sysid_is_an_error_naming_both_vehicles(tmp_path):
    body = sitl_fleet().replace("sysid = 2", "sysid = 1")
    messages = errors_of(write(tmp_path, body))
    assert any("sysid 1" in m and "v1" in m and "v2" in m for m in messages), \
        joined(messages)


def test_sysid_zero_is_rejected_as_broadcast(tmp_path):
    body = sitl_fleet().replace("sysid = 1", "sysid = 0")
    messages = errors_of(write(tmp_path, body))
    assert any("broadcast" in m.lower() for m in messages), joined(messages)


@pytest.mark.parametrize("bad", [256, -3, 999])
def test_a_sysid_outside_the_mavlink_range_is_rejected(tmp_path, bad):
    body = sitl_fleet().replace("sysid = 2", f"sysid = {bad}")
    messages = errors_of(write(tmp_path, body, name=f"s{abs(bad)}"))
    assert any(str(bad) in m and "255" in m for m in messages), joined(messages)


def test_a_duplicate_vehicle_id_is_an_error(tmp_path):
    body = sitl_fleet().replace('id = "v2"', 'id = "v1"')
    messages = errors_of(write(tmp_path, body))
    assert any("v1" in m and "unique" in m for m in messages), joined(messages)


# ------------------------------------------------------------------- geometry
def test_spawns_closer_than_min_separation_are_rejected_by_name(tmp_path):
    body = sitl_fleet().replace("spacing_m = 10.0", "spacing_m = 2.0")
    messages = errors_of(write(tmp_path, body))
    assert any("v1" in m and "v2" in m and "2.00 m" in m for m in messages), \
        joined(messages)


def test_a_formation_fills_in_every_spawn_point(tmp_path):
    result = fleetspec.validate(fleetspec.load(write(tmp_path, sitl_fleet())))
    assert result.ok, joined(result.errors)
    assert all(v.spawn is not None for v in result.spec.vehicles)
    # line, spacing 10, centred: -5 and +5
    assert [v.spawn.east_m for v in result.spec.vehicles] == [-5.0, 5.0]


def test_a_formation_and_an_explicit_spawn_cannot_both_be_given(tmp_path):
    body = sitl_fleet().replace(
        "sysid = 2", "sysid = 2\nspawn = { east_m = 30.0, north_m = 0.0 }")
    messages = errors_of(write(tmp_path, body))
    assert any("mutually exclusive" in m for m in messages), joined(messages)


def test_explicit_formation_demands_a_spawn_on_every_vehicle(tmp_path):
    body = sitl_fleet().replace('formation = "line"', 'formation = "explicit"')
    messages = errors_of(write(tmp_path, body))
    assert any("v1" in m and "v2" in m for m in messages), joined(messages)


def test_an_unknown_formation_names_the_ones_that_exist(tmp_path):
    body = sitl_fleet().replace('formation = "line"', 'formation = "spiral"')
    messages = errors_of(write(tmp_path, body))
    assert any("spiral" in m and "grid" in m for m in messages), joined(messages)


# -------------------------------------------------------------------- policies
@pytest.mark.parametrize("key,value", [
    ("start", "whenever"),
    ("on_vehicle_failure", "shrug"),
    ("group_command", "fire_and_forget"),
])
def test_an_unknown_policy_value_is_rejected(tmp_path, key, value):
    body = sitl_fleet() + f'\n[fleet.policy]\n{key} = "{value}"\n'
    messages = errors_of(write(tmp_path, body, name=key))
    assert any(value in m for m in messages), joined(messages)


# ----------------------------------------------------------------- fleet size
def test_more_vehicles_than_the_machine_allows_is_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(fleetspec, "max_vehicles", lambda: 1)
    messages = errors_of(write(tmp_path, sitl_fleet()))
    assert any("2 vehicles" in m and "1" in m for m in messages), joined(messages)


def test_the_ceiling_comes_from_config_when_it_is_set(monkeypatch):
    from argazui import paths
    monkeypatch.setattr(paths, "FLEET_MAX_VEHICLES", 6, raising=False)
    assert fleetspec.max_vehicles() == 6


def test_the_ceiling_is_a_measured_constant_not_a_core_count(monkeypatch):
    """The CPU formula was refuted by measurement; this pins the replacement.

    Real-time factor in one Gazebo world was measured at 0.78 / 0.57 / 0.43
    for two / three / four hovering vehicles — on a SIXTEEN-core machine.
    Throughput falls as roughly 1.77/N because Gazebo steps physics serially
    and lockstep waits for every FDM in turn, so cores do not buy vehicles.
    A formula keyed on core count would have allowed eight.

    See docs/fleet-rtf-scaling.md.
    """
    from argazui import paths
    monkeypatch.setattr(paths, "FLEET_MAX_VEHICLES", 0, raising=False)

    for cores in (1, 4, 8, 64):
        monkeypatch.setattr(fleetspec.os, "cpu_count", lambda c=cores: c)
        assert fleetspec.max_vehicles() == fleetspec.DEFAULT_MAX_VEHICLES, (
            f"the ceiling moved with a {cores}-core machine; it is measured "
            f"from simulator throughput, not from the host")
    assert fleetspec.DEFAULT_MAX_VEHICLES == 4


# ------------------------------------------------------- model vs SITL frame
REGISTRY = {"models": [
    {"id": "hexa_ok", "method": "gz_plus_sitl_paramfile", "vehicle": "ArduCopter"},
    {"id": "plane_ok", "method": "gz_plus_sitl_frame", "vehicle": "ArduPlane"},
    {"id": "ros_one", "method": "ros2_launch", "vehicle": "ArduCopter"},
]}


def gazebo_fleet(models: list[str], **fleet_keys) -> str:
    blocks = "\n".join(
        f'[[vehicle]]\nid = "v{i+1}"\nmodel = "{m}"\nsysid = {i+1}\n'
        for i, m in enumerate(models))
    return f"""
[fleet]
name = "gz_probe"
world = "probe_runway.sdf"
formation = "grid"
spacing_m = 10.0
min_separation_m = 5.0
{toml_keys(**fleet_keys)}
{ORIGIN}
{blocks}
"""


def passing_tier2(*model_ids: str, runs_root: Path = None):
    """A suite record in which the named models passed tier 2."""
    import json
    root = runs_root
    root.mkdir(parents=True, exist_ok=True)
    (root / "suite.json").write_text(json.dumps({
        "schema": 1, "generated_utc": "2026-08-05T00:00:00Z",
        "environment": "test", "exit_status": 0,
        "tests": [
            {"nodeid": f"tests/test_tier2_models.py::test_x[{model_id}]",
             "outcome": "passed", "reason": "", "duration": 1.0,
             "markers": ["tier2"]}
            for model_id in model_ids],
    }), encoding="utf-8")
    return [root]


def test_a_model_not_in_the_registry_is_rejected(tmp_path):
    path = write(tmp_path, gazebo_fleet(["ghost", "ghost"]))
    messages = errors_of(path, registry=REGISTRY,
                         runs_roots=passing_tier2("ghost", runs_root=tmp_path / "r"))
    assert any("ghost" in m and "models.json" in m for m in messages), joined(messages)


def test_mixing_launch_methods_names_which_vehicle_wants_which(tmp_path):
    path = write(tmp_path, gazebo_fleet(["hexa_ok", "plane_ok"]))
    messages = errors_of(
        path, registry=REGISTRY,
        runs_roots=passing_tier2("hexa_ok", "plane_ok", runs_root=tmp_path / "r"))
    joined_text = joined(messages)
    assert "gz_plus_sitl_paramfile" in joined_text and "gz_plus_sitl_frame" in joined_text
    assert "v1" in joined_text and "v2" in joined_text


def test_a_ros2_launch_model_cannot_be_composed_into_a_fleet(tmp_path):
    path = write(tmp_path, gazebo_fleet(["ros_one", "ros_one"]))
    messages = errors_of(path, registry=REGISTRY,
                         runs_roots=passing_tier2("ros_one", runs_root=tmp_path / "r"))
    assert any("ros2_launch" in m and "its own Gazebo" in m for m in messages), \
        joined(messages)


def test_a_registry_model_in_a_worldless_fleet_is_rejected(tmp_path):
    body = sitl_fleet().replace('frame = "quad"\nvehicle = "ArduCopter"',
                                'model = "hexa_ok"')
    messages = errors_of(write(tmp_path, body), registry=REGISTRY,
                         runs_roots=passing_tier2("hexa_ok", runs_root=tmp_path / "r"))
    assert any("SITL-only" in m for m in messages), joined(messages)


def test_a_bare_frame_in_a_gazebo_fleet_is_rejected(tmp_path):
    body = gazebo_fleet(["hexa_ok"]).replace('model = "hexa_ok"',
                                             'frame = "quad"\nvehicle = "ArduCopter"')
    messages = errors_of(write(tmp_path, body), registry=REGISTRY,
                         runs_roots=passing_tier2(runs_root=tmp_path / "r"))
    assert any("no Gazebo model" in m for m in messages), joined(messages)


def test_a_frame_without_a_vehicle_binary_is_rejected(tmp_path):
    body = sitl_fleet().replace('vehicle = "ArduCopter"\nsysid = 2', "sysid = 2")
    messages = errors_of(write(tmp_path, body))
    assert any("v2" in m and "ArduCopter" in m for m in messages), joined(messages)


# --------------------------------------------------- tier-2 model eligibility
def test_a_model_tier2_has_not_passed_is_rejected(tmp_path):
    """The central rule: only tier 2 may verify a model, and it must have."""
    path = write(tmp_path, gazebo_fleet(["hexa_ok", "hexa_ok"]))
    messages = errors_of(path, registry=REGISTRY,
                         runs_roots=[tmp_path / "empty"])
    assert any("hexa_ok" in m and "tier-2" in m for m in messages), joined(messages)
    assert any("allow_unverified" in m for m in messages), \
        "the error must say how to override it deliberately"


def test_one_unverified_model_produces_one_error_not_one_per_vehicle(tmp_path):
    """A fleet of eight on one bad model must not print eight identical lines.

    The verdict is about the MODEL, so it is stated once and names every
    vehicle it grounds. Repeating it per vehicle is how a real error gets
    scrolled past.
    """
    path = write(tmp_path, gazebo_fleet(["hexa_ok"] * 4))
    messages = errors_of(path, registry=REGISTRY, runs_roots=[tmp_path / "empty"])
    about_model = [m for m in messages if "hexa_ok" in m and "tier-2" in m]
    assert len(about_model) == 1, f"{len(about_model)} copies:\n{joined(about_model)}"
    for vehicle_id in ("v1", "v2", "v3", "v4"):
        assert vehicle_id in about_model[0], about_model[0]


def test_a_model_tier2_passed_is_accepted(tmp_path):
    path = write(tmp_path, gazebo_fleet(["hexa_ok", "hexa_ok"]))
    result = fleetspec.validate(
        fleetspec.load(path), registry=REGISTRY,
        runs_roots=passing_tier2("hexa_ok", runs_root=tmp_path / "r"))
    assert result.ok, joined(result.errors)


def test_allow_unverified_downgrades_the_error_to_a_warning(tmp_path):
    path = write(tmp_path, gazebo_fleet(
        ["hexa_ok", "hexa_ok"], allow_unverified=True,
        unverified_reason="fresh clone, no tier-2 record yet"))
    result = fleetspec.validate(fleetspec.load(path), registry=REGISTRY,
                                runs_roots=[tmp_path / "empty"])
    assert result.ok, joined(result.errors)
    assert any("hexa_ok" in w for w in result.warnings), joined(result.warnings)
    assert any("fresh clone" in w for w in result.warnings), \
        "the declared reason must travel with the warning"


def test_allow_unverified_without_a_reason_is_itself_an_error(tmp_path):
    """Skipping verification is allowed. Skipping it silently is not."""
    path = write(tmp_path, gazebo_fleet(["hexa_ok", "hexa_ok"],
                                        allow_unverified=True))
    messages = errors_of(path, registry=REGISTRY, runs_roots=[tmp_path / "empty"])
    assert any("unverified_reason" in m for m in messages), joined(messages)


def test_the_declared_reason_reaches_the_run_snapshot(tmp_path):
    """It is stamped into fleet.json, the way an override reaches a run."""
    path = write(tmp_path, gazebo_fleet(
        ["hexa_ok"], allow_unverified=True, unverified_reason="bring-up"))
    snapshot = fleetspec.load(path).as_dict()
    assert snapshot["allow_unverified"] is True
    assert snapshot["unverified_reason"] == "bring-up"


# ------------------------------------------------------------- shipped specs
def test_every_shipped_fleet_spec_parses_and_states_its_kind():
    """A spec that ships broken is worse than no spec."""
    names = fleetspec.available()
    assert names, "no fleet specs are shipped"
    for name in names:
        spec = fleetspec.load_by_name(name)
        assert spec.count >= 1
        assert spec.origin.lat and spec.origin.lon
        for vehicle in spec.vehicles:
            assert bool(vehicle.model) != bool(vehicle.frame), \
                f"{name}/{vehicle.id}: needs exactly one of model or frame"


def test_the_shipped_sitl_fleet_is_gazebo_free_and_valid():
    """The CI fleet must validate on any machine, with no tier-2 data at all."""
    result = fleetspec.validate(fleetspec.load_by_name("sitl_pair"),
                                runs_roots=[Path("/nonexistent")])
    assert result.ok, joined(result.errors)
    assert result.spec.gazebo is False
