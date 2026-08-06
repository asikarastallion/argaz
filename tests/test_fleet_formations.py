"""Spawn geometry. Pure maths — the fastest thing in the suite.

WHY THE VALIDATOR AND THE WORLD COMPOSER SHARE THIS MODULE
----------------------------------------------------------
If the separation validator computed spawn points one way and the SDF
generator another, a fleet could pass validation at 6 m spacing and be built
at 4 m — and the symptom would be a physics explosion at t=0 with a green
validation badge beside it. One generator, called by both.
"""
from __future__ import annotations

import math

import pytest

from argazui.fleet import formations

pytestmark = pytest.mark.tier1


# --------------------------------------------------------------------- grid
@pytest.mark.parametrize("count,side", [(1, 1), (2, 2), (3, 2), (4, 2),
                                        (5, 3), (9, 3), (10, 4)])
def test_a_grid_side_is_ceil_sqrt_n(count, side):
    points = formations.grid(count, spacing_m=10.0)
    assert len(points) == count
    columns = {round(p.east_m, 6) for p in points}
    assert len(columns) <= side


def test_a_grid_is_centred_on_the_origin(count=4):
    points = formations.grid(count, spacing_m=10.0)
    assert math.isclose(sum(p.east_m for p in points), 0.0, abs_tol=1e-9)
    assert math.isclose(sum(p.north_m for p in points), 0.0, abs_tol=1e-9)


def test_a_grid_of_four_is_the_corners_of_a_square():
    points = formations.grid(4, spacing_m=10.0)
    corners = sorted((round(p.east_m, 3), round(p.north_m, 3)) for p in points)
    assert corners == [(-5.0, -5.0), (-5.0, 5.0), (5.0, -5.0), (5.0, 5.0)]


def test_grid_spacing_is_the_distance_between_neighbours():
    points = formations.grid(4, spacing_m=7.0)
    closest, _, _ = formations.closest_pair(points)
    assert math.isclose(closest, 7.0, rel_tol=1e-9)


# --------------------------------------------------------------------- line
def test_a_line_runs_east_and_is_centred():
    points = formations.line(3, spacing_m=10.0)
    assert [round(p.east_m, 3) for p in points] == [-10.0, 0.0, 10.0]
    assert all(p.north_m == 0.0 for p in points)


def test_line_spacing_is_the_neighbour_distance():
    points = formations.line(5, spacing_m=4.0)
    closest, _, _ = formations.closest_pair(points)
    assert math.isclose(closest, 4.0, rel_tol=1e-9)


# ------------------------------------------------------------------- circle
def test_a_circle_puts_every_vehicle_on_the_radius():
    points = formations.circle(6, radius_m=20.0)
    for point in points:
        assert math.isclose(math.hypot(point.east_m, point.north_m), 20.0,
                            rel_tol=1e-9)


def test_a_circle_faces_every_vehicle_at_the_centre():
    """Vehicle at bearing B from the origin must head B+180 to look inward."""
    for point in formations.circle(4, radius_m=15.0):
        bearing_from_origin = math.degrees(math.atan2(point.east_m, point.north_m)) % 360
        assert math.isclose(point.yaw_deg, (bearing_from_origin + 180) % 360,
                            abs_tol=1e-6)


def test_a_circle_of_one_is_allowed_and_sits_due_north():
    points = formations.circle(1, radius_m=10.0)
    assert math.isclose(points[0].north_m, 10.0, rel_tol=1e-9)
    assert math.isclose(points[0].east_m, 0.0, abs_tol=1e-9)


# ------------------------------------------------------------------ contract
def test_every_generated_vehicle_starts_above_the_ground():
    """A model spawned on the ground plane is launched by the first step."""
    for name, kwargs in (("grid", {}), ("line", {}), ("circle", {})):
        for point in formations.generate(name, 4, **kwargs):
            assert point.up_m > 0, f"{name} spawns on the ground plane"


def test_separation_is_horizontal_only():
    """Two vehicles stacked vertically are in the same place at spawn."""
    a = formations.Point(east_m=0.0, north_m=0.0, up_m=0.2)
    b = formations.Point(east_m=0.0, north_m=0.0, up_m=50.0)
    assert formations.distance_m(a, b) == 0.0


def test_the_closest_pair_of_a_single_vehicle_is_infinite():
    """One vehicle cannot violate a separation rule; 0.0 would say it had."""
    distance, left, right = formations.closest_pair(
        [formations.Point(east_m=0.0, north_m=0.0)])
    assert distance == math.inf and left == -1 and right == -1


def test_explicit_is_not_generated():
    with pytest.raises(formations.FormationError, match="explicit"):
        formations.generate("explicit", 3)


def test_an_unknown_formation_names_the_valid_ones():
    with pytest.raises(formations.FormationError, match="grid"):
        formations.generate("helix", 3)


@pytest.mark.parametrize("name", ["grid", "line"])
def test_a_nonpositive_spacing_is_refused(name):
    with pytest.raises(formations.FormationError, match="spacing_m"):
        formations.generate(name, 3, spacing_m=0.0)


def test_a_nonpositive_radius_is_refused():
    with pytest.raises(formations.FormationError, match="radius_m"):
        formations.generate("circle", 3, radius_m=-1.0)
