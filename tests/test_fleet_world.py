"""L2 — ENU⇄LLA and the generated world. Pure: no Gazebo, no processes.

WHAT THE GOLDEN FILE IS FOR
---------------------------
`fleet.sdf` is the reproducibility artefact: it is what a run directory
contains so that somebody can rebuild the world a flight happened in. That
makes its exact content part of the contract, not an implementation detail —
a silent change to how vehicles are placed would invalidate every archived
run without invalidating any test. So the generated XML is compared byte for
byte against a recorded copy.

THE THREE FACTS THIS PINS ARE MEASURED ONES
-------------------------------------------
    fdm_port_in patched per vehicle   two vehicles on one port bind SILENTLY
                                      (SocketUDP reuseaddress=true), so
                                      nothing downstream would report it
    imuName re-namespaced             renaming the model without this leaves
                                      the plugin looking for a sensor that no
                                      longer exists, and it still binds and
                                      still logs nothing
    ONE home for the whole fleet      the plugin reports the IMU link's WORLD
                                      pose, so the Gazebo <pose> already
                                      carries the offset; adding it to home
                                      too doubles it

See docs/fleet-world-composition.md for the experiments behind each.
"""
from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from argazui.fleet import allocator, geo, spec as fleetspec, world as worldlib

pytestmark = pytest.mark.tier1

GOLDEN = Path(__file__).resolve().parent / "golden" / "fleet_world.sdf"

# The datum every measurement in Phase 2 was taken at.
LAT0, LON0, ALT0 = -35.363262, 149.165237, 584.0


# ------------------------------------------------------------------- geodesy
# What a real vehicle reported when spawned at Gazebo pose `10 0 0.2` with the
# fleet origin below. Recorded from GLOBAL_POSITION_INT; see
# docs/fleet-world-composition.md.
MEASURED_LON_AT_10M_EAST = 149.1653475

# SITL's GPS is simulated WITH NOISE, and GLOBAL_POSITION_INT is the EKF's
# fused absolute estimate rather than a readback of the spawn pose. The same
# vehicle's LOCAL_POSITION_NED read 9.995 m for a commanded 10.000 m. So this
# comparison is held to a tolerance that reflects what was measured — a test
# demanding centimetre agreement would be asserting the GPS is noiseless.
EKF_NOISE_TOLERANCE_M = 0.5


def test_ten_metres_east_matches_what_a_real_vehicle_reported():
    """The one check that is not self-referential.

    If this conversion disagrees with what the vehicle actually reported, the
    separation monitor and the simulator are using different maps. The
    quantity being pinned is scale and direction, not centimetres.
    """
    result = geo.enu_to_lla(LAT0, LON0, ALT0, east_m=10.0, north_m=0.0, up_m=0.2)
    east_error, north_error, _ = geo.lla_to_enu(
        LAT0, LON0, ALT0, LAT0, MEASURED_LON_AT_10M_EAST, ALT0)
    predicted_east, _, _ = geo.lla_to_enu(LAT0, LON0, ALT0,
                                          result.lat, result.lon, result.alt)
    assert abs(predicted_east - east_error) < EKF_NOISE_TOLERANCE_M, (
        f"predicted {predicted_east:.4f} m east, vehicle reported "
        f"{east_error:.4f} m")
    assert round(result.lat, 7) == round(LAT0, 7), "pure east must not move latitude"
    assert math.isclose(result.alt, ALT0 + 0.2, abs_tol=1e-9)


def test_the_scale_constant_is_ardupilots_own():
    """The conversion must be on the same map as the autopilot, not near it.

    ArduPilot: LATLON_TO_M = 0.011131884502145034 m per 1e-7 degree
    (libraries/AP_Math/definitions.h).
    """
    assert geo.METRES_PER_DEGREE == pytest.approx(0.011131884502145034 * 1e7,
                                                  abs=1e-6)


@pytest.mark.parametrize("east,north,up", [
    (0.0, 0.0, 0.0), (10.0, 0.0, 0.2), (-25.5, 40.25, 3.0),
    (100.0, -100.0, 0.0), (0.0, 500.0, -12.0),
])
def test_the_round_trip_closes_well_inside_a_tenth_of_a_metre(east, north, up):
    point = geo.enu_to_lla(LAT0, LON0, ALT0, east, north, up)
    back_e, back_n, back_u = geo.lla_to_enu(LAT0, LON0, ALT0,
                                            point.lat, point.lon, point.alt)
    assert math.hypot(back_e - east, back_n - north) < 0.1
    assert abs(back_u - up) < 0.1


@pytest.mark.parametrize("east,north", [(10.0, 0.0), (0.0, 10.0),
                                        (50.0, 50.0), (0.0, 60.0)])
def test_the_flat_approximation_agrees_with_a_great_circle(east, north):
    """An independent second opinion, so this is not just testing its inverse.

    Held to 100 m of separation, which is well beyond any fleet this ships
    with (the widest shipped formation is a 10 m grid). See the divergence
    test below for what happens further out and why it is not an error.
    """
    point = geo.enu_to_lla(LAT0, LON0, ALT0, east, north)
    curved = geo.haversine_m(LAT0, LON0, point.lat, point.lon)
    flat = math.hypot(east, north)
    assert abs(curved - flat) < 0.1, f"{curved:.4f} vs {flat:.4f}"


def test_the_divergence_from_a_sphere_is_a_stated_scale_difference():
    """Measured, and recorded rather than hidden behind a loose tolerance.

    `haversine_m` uses a spherical mean radius (6371 km); the conversion uses
    ArduPilot's constant. Those are different earth models, so they disagree
    by a fixed ~0.11% of distance — NOT by a curvature term that would grow
    quadratically. Pinning the linearity is what proves it is a scale choice
    and not a bug that happens to be small nearby.
    """
    ratios = []
    for north in (100.0, 200.0, 500.0, 1000.0):
        point = geo.enu_to_lla(LAT0, LON0, ALT0, 0.0, north)
        curved = geo.haversine_m(LAT0, LON0, point.lat, point.lon)
        ratios.append((north - curved) / north)
    assert all(abs(r - ratios[0]) < 1e-6 for r in ratios), (
        f"the divergence is not a constant scale factor: {ratios}")
    assert 0.0010 < ratios[0] < 0.0013, f"unexpected scale difference {ratios[0]}"


def test_an_absurd_offset_is_refused_rather_than_approximated():
    with pytest.raises(geo.GeoError, match="flat-earth"):
        geo.enu_to_lla(LAT0, LON0, ALT0, east_m=500_000.0, north_m=0.0)


def test_a_pole_is_refused_because_longitude_is_undefined():
    with pytest.raises(geo.GeoError, match="pole"):
        geo.enu_to_lla(90.0, 0.0, 0.0, east_m=1.0, north_m=0.0)


# ------------------------------------------------------------ model patching
BASE_MODEL_SDF = """<?xml version="1.0" ?>
<sdf version="1.9">
  <model name="iris_with_standoffs">
    <link name="imu_link"><sensor name="imu_sensor" type="imu"/></link>
    <plugin name="ArduPilotPlugin" filename="ArduPilotPlugin">
      <fdm_addr>127.0.0.1</fdm_addr>
      <fdm_port_in>9002</fdm_port_in>
      <lock_step>1</lock_step>
      <imuName>iris_with_standoffs::imu_link::imu_sensor</imuName>
    </plugin>
  </model>
</sdf>
"""


@pytest.fixture
def base_model(tmp_path) -> Path:
    directory = tmp_path / "base" / "iris_with_ardupilot"
    directory.mkdir(parents=True)
    (directory / "model.sdf").write_text(BASE_MODEL_SDF, encoding="utf-8")
    (directory / "model.config").write_text(
        "<model><name>iris_with_ardupilot</name></model>", encoding="utf-8")
    (directory / "meshes").mkdir()
    (directory / "meshes" / "body.dae").write_text("mesh", encoding="utf-8")
    return directory


def test_materialising_patches_only_the_fdm_port_in(base_model, tmp_path):
    out = worldlib.materialise_model(base_model, tmp_path / "v2", "v2", 9012)
    text = (out / "model.sdf").read_text(encoding="utf-8")
    assert "<fdm_port_in>9012</fdm_port_in>" in text
    # fdm_addr is the BIND address and the reply path is learned, so it must
    # be left exactly as it was.
    assert "<fdm_addr>127.0.0.1</fdm_addr>" in text


def test_materialising_renames_the_model_and_its_imu_reference(base_model, tmp_path):
    out = worldlib.materialise_model(base_model, tmp_path / "v2", "v2", 9012)
    text = (out / "model.sdf").read_text(encoding="utf-8")
    assert '<model name="v2">' in text
    assert "<imuName>v2::imu_link::imu_sensor</imuName>" in text, (
        "the IMU reference is namespaced by the ORIGINAL model name; leaving "
        "it stale makes the plugin bind its port, log nothing, and never "
        "produce state")
    assert "iris_with_standoffs" not in text


def test_materialising_copies_the_whole_model_not_just_the_sdf(base_model, tmp_path):
    out = worldlib.materialise_model(base_model, tmp_path / "v1", "v1", 9002)
    assert (out / "meshes" / "body.dae").is_file()
    assert (out / "model.config").read_text(encoding="utf-8").count("v1") == 1


def test_materialising_twice_does_not_accumulate(base_model, tmp_path):
    worldlib.materialise_model(base_model, tmp_path / "v1", "v1", 9002)
    out = worldlib.materialise_model(base_model, tmp_path / "v1", "v1", 9032)
    text = (out / "model.sdf").read_text(encoding="utf-8")
    assert text.count("<fdm_port_in>") == 1
    assert "<fdm_port_in>9032</fdm_port_in>" in text


def test_a_model_without_an_fdm_port_is_refused(tmp_path):
    directory = tmp_path / "plain"
    directory.mkdir()
    (directory / "model.sdf").write_text(
        '<sdf version="1.9"><model name="rock"/></sdf>', encoding="utf-8")
    with pytest.raises(worldlib.WorldCompositionError, match="fdm_port_in"):
        worldlib.materialise_model(directory, tmp_path / "v1", "v1", 9002)


# ------------------------------------------------------------- world building
BASE_WORLD = """<?xml version="1.0" ?>
<sdf version="1.9">
  <world name="runway">
    <physics name="1ms" type="ignored">
      <max_step_size>0.001</max_step_size>
      <real_time_factor>1</real_time_factor>
    </physics>
    <plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics" />
    <include>
      <pose degrees="true">-29 545 0 0 0 363</pose>
      <uri>model://runway</uri>
    </include>
    <include>
      <pose degrees="true">0 0 0.12 0 0 90</pose>
      <uri>model://iris_with_ardupilot</uri>
    </include>
  </world>
</sdf>
"""


@pytest.fixture
def three_vehicle_setup(tmp_path, base_model):
    path = tmp_path / "trio.toml"
    path.write_text(f"""
[fleet]
name = "trio"
world = "runway.sdf"
formation = "grid"
spacing_m = 10.0
min_separation_m = 5.0

[fleet.origin]
lat = {LAT0}
lon = {LON0}
alt = {ALT0}

[[vehicle]]
id = "v1"
model = "probe"
sysid = 1

[[vehicle]]
id = "v2"
model = "probe"
sysid = 2

[[vehicle]]
id = "v3"
model = "probe"
sysid = 3
""", encoding="utf-8")
    spec = fleetspec.load(path)
    fleetspec.resolve_spawns(spec)

    base_world = tmp_path / "runway.sdf"
    base_world.write_text(BASE_WORLD, encoding="utf-8")

    allocation = allocator.allocate(spec, "run_world", runs_root=tmp_path / "runs",
                                    work_root=tmp_path / "work")
    return spec, allocation, base_world, base_model, tmp_path / "rundir"


def test_every_vehicle_gets_a_distinct_fdm_port_in_the_generated_models(
        three_vehicle_setup):
    spec, allocation, base_world, base_model, run_dir = three_vehicle_setup
    composed = worldlib.compose(spec, allocation, base_world, base_model, run_dir,
                                gazebo_model_name="iris_with_ardupilot")
    ports = []
    for vehicle_id, directory in sorted(composed.vehicle_models.items()):
        text = (directory / "model.sdf").read_text(encoding="utf-8")
        found = re.findall(r"<fdm_port_in>(\d+)</fdm_port_in>", text)
        assert len(found) == 1, f"{vehicle_id} has {len(found)} FDM ports"
        ports.append(int(found[0]))
    assert len(set(ports)) == 3, f"FDM ports collide: {ports}"
    assert ports == [9002, 9012, 9022]


def test_the_generated_world_replaces_the_base_vehicle_with_the_fleet(
        three_vehicle_setup):
    spec, allocation, base_world, base_model, run_dir = three_vehicle_setup
    composed = worldlib.compose(spec, allocation, base_world, base_model, run_dir,
                                gazebo_model_name="iris_with_ardupilot")
    root = ET.parse(composed.world_path).getroot()
    world = root.find("world")
    uris = [(inc.findtext("uri") or "") for inc in world.findall("include")]

    assert "model://iris_with_ardupilot" not in uris, (
        "the base world's own vehicle is still there; a fleet world must "
        "contain the fleet and nothing else")
    assert "model://runway" in uris, "the scenery was removed with the vehicle"
    for vehicle_id in ("v1", "v2", "v3"):
        assert f"model://{vehicle_id}" in uris
    assert composed.removed_includes == ["model://iris_with_ardupilot"]


def test_the_generated_world_states_its_own_datum(three_vehicle_setup):
    spec, allocation, base_world, base_model, run_dir = three_vehicle_setup
    composed = worldlib.compose(spec, allocation, base_world, base_model, run_dir,
                                gazebo_model_name="iris_with_ardupilot")
    world = ET.parse(composed.world_path).getroot().find("world")
    spherical = world.find("spherical_coordinates")
    assert spherical is not None, "the generated world declares no datum"
    assert spherical.findtext("latitude_deg") == f"{LAT0:.7f}"
    assert spherical.findtext("longitude_deg") == f"{LON0:.7f}"
    assert spherical.findtext("world_frame_orientation") == "ENU"


def test_the_poses_are_enu_east_first(three_vehicle_setup):
    """SDF <pose> is x y z r p y, and the Gazebo world frame is ENU."""
    spec, allocation, base_world, base_model, run_dir = three_vehicle_setup
    composed = worldlib.compose(spec, allocation, base_world, base_model, run_dir,
                                gazebo_model_name="iris_with_ardupilot")
    world = ET.parse(composed.world_path).getroot().find("world")
    poses = {inc.findtext("name"): inc.find("pose").text
             for inc in world.findall("include") if inc.findtext("name")}
    # grid of 3, spacing 10, centred: v1 (-5, +5), v2 (+5, +5), v3 (-5, -5)
    assert poses["v1"].split()[:2] == ["-5", "5"]
    assert poses["v2"].split()[:2] == ["5", "5"]
    assert poses["v3"].split()[:2] == ["-5", "-5"]


def test_the_run_directory_models_come_first_on_the_resource_path(
        three_vehicle_setup):
    spec, allocation, base_world, base_model, run_dir = three_vehicle_setup
    composed = worldlib.compose(spec, allocation, base_world, base_model, run_dir,
                                gazebo_model_name="iris_with_ardupilot")
    combined = worldlib.resource_path(composed, existing="/usr/share/gz/models")
    assert combined.startswith(str(composed.models_dir))
    assert combined.endswith("/usr/share/gz/models")


def test_composing_without_resolved_spawns_is_refused(tmp_path, base_model):
    """A world must never be built from a spec that was not validated."""
    path = tmp_path / "raw.toml"
    path.write_text(f"""
[fleet]
name = "raw"
world = "runway.sdf"
formation = "explicit"

[fleet.origin]
lat = {LAT0}
lon = {LON0}
alt = {ALT0}

[[vehicle]]
id = "v1"
model = "probe"
sysid = 1
""", encoding="utf-8")
    spec = fleetspec.load(path)          # deliberately NOT resolved
    base_world = tmp_path / "runway.sdf"
    base_world.write_text(BASE_WORLD, encoding="utf-8")
    allocation = allocator.allocate(spec, "r", runs_root=tmp_path / "runs",
                                    work_root=tmp_path / "w")
    with pytest.raises(worldlib.WorldCompositionError, match="spawn"):
        worldlib.compose(spec, allocation, base_world, base_model,
                         tmp_path / "out")


# ------------------------------------------------------------ one shared home
def test_the_whole_fleet_shares_one_home(three_vehicle_setup):
    """The single most consequential line in this layer.

    The plugin reports the IMU link's WORLD pose, so a model at 10 m east
    already reports 10 m east. Offsetting --custom-location per vehicle as
    well puts it at twenty — and Gazebo still draws it at ten, so the error is
    invisible on screen and only shows up as a separation monitor that
    disagrees with the picture.
    """
    spec, _, _, _, _ = three_vehicle_setup
    home = worldlib.home_for(spec)
    assert home == f"{LAT0:.7f},{LON0:.7f},{ALT0:.2f},0.0"
    for vehicle in spec.vehicles:
        assert worldlib.home_for(spec) == home, \
            "home_for must not vary by vehicle"


def test_a_sitl_only_fleet_offsets_home_per_vehicle_instead(tmp_path):
    """The other half of the rule, and the failure it prevents.

    With Gazebo the `<pose>` carries the offset. Without Gazebo there is no
    pose — so if every vehicle also shared one home, all of them would sit at
    identical coordinates. That is the same "every EKF at one point" failure
    the shared home prevents under Gazebo, reached from the opposite side.
    """
    path = tmp_path / "pair.toml"
    path.write_text(f"""
[fleet]
name = "pair"
formation = "line"
spacing_m = 10.0
min_separation_m = 5.0

[fleet.origin]
lat = {LAT0}
lon = {LON0}
alt = {ALT0}

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
""", encoding="utf-8")
    spec = fleetspec.load(path)
    fleetspec.resolve_spawns(spec)
    assert spec.gazebo is False

    home1 = worldlib.home_for_vehicle(spec, "v1")
    home2 = worldlib.home_for_vehicle(spec, "v2")
    assert home1 != home2, (
        "a SITL-only fleet gave both vehicles the same home; with no Gazebo "
        "pose to carry the offset, they are now at the same coordinates")

    lat1, lon1 = (float(x) for x in home1.split(",")[:2])
    lat2, lon2 = (float(x) for x in home2.split(",")[:2])
    east1, _, _ = geo.lla_to_enu(LAT0, LON0, ALT0, lat1, lon1, ALT0)
    east2, _, _ = geo.lla_to_enu(LAT0, LON0, ALT0, lat2, lon2, ALT0)
    assert math.isclose(east2 - east1, 10.0, abs_tol=0.05), (
        f"line formation at 10 m spacing produced {east2 - east1:.3f} m")


def test_a_gazebo_fleet_gives_every_vehicle_the_same_home(three_vehicle_setup):
    spec, _, _, _, _ = three_vehicle_setup
    assert spec.gazebo is True
    homes = {worldlib.home_for_vehicle(spec, v.id) for v in spec.vehicles}
    assert len(homes) == 1, (
        f"a Gazebo fleet offset home per vehicle, double-counting the pose: "
        f"{homes}")
    assert homes.pop() == worldlib.home_for(spec)


def test_absolute_spawn_positions_are_available_for_the_record(three_vehicle_setup):
    spec, _, _, _, _ = three_vehicle_setup
    v1 = worldlib.spawn_lla(spec, "v1")
    v2 = worldlib.spawn_lla(spec, "v2")
    # v1 and v2 are 10 m apart in east; latitude identical.
    assert v1["lat"] == v2["lat"]
    east_delta = geo.lla_to_enu(LAT0, LON0, ALT0, v2["lat"], v2["lon"], v2["alt"])[0]
    east_v1 = geo.lla_to_enu(LAT0, LON0, ALT0, v1["lat"], v1["lon"], v1["alt"])[0]
    assert math.isclose(east_delta - east_v1, 10.0, abs_tol=0.01)


# -------------------------------------------------------------- golden world
def test_the_generated_world_is_byte_for_byte_what_was_recorded(three_vehicle_setup):
    spec, allocation, base_world, base_model, run_dir = three_vehicle_setup
    composed = worldlib.compose(spec, allocation, base_world, base_model, run_dir,
                                gazebo_model_name="iris_with_ardupilot")
    produced = composed.world_path.read_text(encoding="utf-8")
    if not GOLDEN.is_file():
        pytest.fail(f"golden world missing: {GOLDEN}\n"
                    f"Regenerate with --regenerate-golden once the output is "
                    f"known good.\n--- produced ---\n{produced}")
    assert produced == GOLDEN.read_text(encoding="utf-8")


def test_regenerate_world(request, three_vehicle_setup):
    if not request.config.getoption("--regenerate-golden", default=False):
        pytest.skip("run with --regenerate-golden to rewrite the golden world")
    spec, allocation, base_world, base_model, run_dir = three_vehicle_setup
    composed = worldlib.compose(spec, allocation, base_world, base_model, run_dir,
                                gazebo_model_name="iris_with_ardupilot")
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text(composed.world_path.read_text(encoding="utf-8"),
                      encoding="utf-8")
    print(f"\nwrote {GOLDEN}")
