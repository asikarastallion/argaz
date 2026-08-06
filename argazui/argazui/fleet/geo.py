"""ENU ⇄ LLA for a fleet's local working area. Pure maths, no I/O.

WHY A FLAT-EARTH APPROXIMATION IS THE RIGHT ONE HERE
----------------------------------------------------
A fleet occupies tens of metres. Over that range the equirectangular
approximation is exact to well below the noise floor of anything that
consumes it, and it has the property that matters more: it is the same
formula ArduPilot's own SITL uses to place a vehicle, so the conversion
agrees with the thing being measured rather than being more "correct" than it.

    lat = lat0 + north_m / M
    lon = lon0 + east_m  / (M * cos(lat0))
    alt = alt0 + up_m

WHICH M, AND WHY NOT THE ROUND NUMBER
-------------------------------------
`M = 111318.845`, taken from ArduPilot's own `LATLON_TO_M`
(`libraries/AP_Math/definitions.h`: 0.011131884502145034 m per 1e-7 degree).

The first version of this used the familiar 111320. That is a defensible
constant but it is not the one the autopilot uses, and the docstring claimed
otherwise. The difference is about 0.1 mm over 10 m — far too small to matter
to a separation rule, and exactly the sort of unearned claim this project
exists to remove. Using ArduPilot's number makes the sentence true.

VALIDATED AGAINST A REAL VEHICLE, NOT ONLY AGAINST ITSELF
---------------------------------------------------------
A round trip closing on itself proves only that the inverse was typed
correctly. This was checked against a measured flight: one iris spawned at
Gazebo pose `10 0 0.2`, fleet origin (-35.363262, 149.165237).

    commanded Gazebo pose   10.000 m east
    SITL LOCAL_POSITION_NED  9.995 m east      <- physics + plugin path
    SITL GLOBAL_POSITION_INT lon 149.1653475
    this formula             lon 149.1653472   <- ~3 cm apart

The 3 cm is not an error in the conversion. `LOCAL_POSITION_NED` is relative
to the EKF origin, while `GLOBAL_POSITION_INT` is the EKF's *absolute*
estimate fused from a simulated GPS that has noise in it; there is no reason
for the two to agree to the centimetre, and a test that demanded they do
would be asserting that SITL's GPS is noiseless. What the comparison
establishes is the scale and the direction, to well inside the tolerance any
separation rule cares about. See docs/fleet-world-composition.md.

THE VERTICAL AXIS IS THE ONE THAT CATCHES PEOPLE
------------------------------------------------
ENU `up_m` is positive upward; the NED frames the autopilot reports are
positive downward. Nothing in this module speaks NED — every function here is
ENU, and the conversion to NED belongs to whatever reads MAVLink.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

# Metres per degree of latitude, as ArduPilot defines it:
#   LATLON_TO_M = 0.011131884502145034 m per 1e-7 degree
#     -> 0.011131884502145034 * 1e7 = 111318.84502145034 m per degree
# Kept identical to the autopilot's own constant so that a position this
# module computes and a position the vehicle reports are on the same map.
METRES_PER_DEGREE = 111318.84502145034

# Earth radius used by `haversine_m` only, for the independent cross-check.
# It is a DIFFERENT earth model from the constant above (spherical mean radius
# vs ArduPilot's), so the two disagree by about 0.11% — 1.1 cm over 10 m,
# 11 cm over 100 m. That is a difference between models, not an error in
# either, and the tests state the range over which it stays negligible.
HAVERSINE_RADIUS_M = 6_371_000.0

# Beyond this the flat-earth error stops being negligible. A fleet is tens of
# metres across; anything approaching this is a mistake in the spec, not a
# geodesy problem, so it is reported rather than silently approximated.
SANE_RANGE_M = 100_000.0


class GeoError(ValueError):
    """An offset is too large for the approximation to be honest about."""


@dataclass(frozen=True)
class LLA:
    lat: float
    lon: float
    alt: float

    def as_dict(self) -> dict:
        # 7 decimals is GLOBAL_POSITION_INT's resolution (1e7-scaled int) and
        # about 1.1 cm of latitude. More digits would imply precision the
        # source data does not have.
        return {"lat": round(self.lat, 7), "lon": round(self.lon, 7),
                "alt": round(self.alt, 3)}


def enu_to_lla(lat0: float, lon0: float, alt0: float,
               east_m: float, north_m: float, up_m: float = 0.0) -> LLA:
    """Fleet-origin-relative ENU offset -> absolute latitude/longitude/altitude."""
    if abs(east_m) > SANE_RANGE_M or abs(north_m) > SANE_RANGE_M:
        raise GeoError(
            f"offset ({east_m:.1f}, {north_m:.1f}) m is beyond {SANE_RANGE_M:.0f} m; "
            f"the flat-earth conversion is not honest at that range")
    scale = math.cos(math.radians(lat0))
    if abs(scale) < 1e-9:
        raise GeoError(f"origin latitude {lat0} is at a pole; longitude is undefined")
    return LLA(lat=lat0 + north_m / METRES_PER_DEGREE,
               lon=lon0 + east_m / (METRES_PER_DEGREE * scale),
               alt=alt0 + up_m)


def lla_to_enu(lat0: float, lon0: float, alt0: float,
               lat: float, lon: float, alt: float) -> tuple[float, float, float]:
    """The exact inverse of `enu_to_lla`, as (east_m, north_m, up_m)."""
    scale = math.cos(math.radians(lat0))
    if abs(scale) < 1e-9:
        raise GeoError(f"origin latitude {lat0} is at a pole; longitude is undefined")
    return ((lon - lon0) * METRES_PER_DEGREE * scale,
            (lat - lat0) * METRES_PER_DEGREE,
            alt - alt0)


def haversine_m(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    """Great-circle distance, for checking the approximation against a curve.

    Not used to place anything — it is the independent second opinion the
    round-trip test compares against, so that test proves more than "the
    inverse was typed correctly".
    """
    radius = HAVERSINE_RADIUS_M
    phi_a, phi_b = math.radians(lat_a), math.radians(lat_b)
    d_phi = math.radians(lat_b - lat_a)
    d_lambda = math.radians(lon_b - lon_a)
    a = (math.sin(d_phi / 2) ** 2
         + math.cos(phi_a) * math.cos(phi_b) * math.sin(d_lambda / 2) ** 2)
    return 2 * radius * math.asin(min(1.0, math.sqrt(a)))


def custom_location(lat: float, lon: float, alt: float, heading: float) -> str:
    """The `--custom-location=` argument SITL expects.

    READ THIS BEFORE CALLING IT PER VEHICLE
    ---------------------------------------
    Every vehicle in a fleet gets the SAME home: the fleet origin. It is
    measured, not assumed — ArduPilotPlugin reports the IMU link's WORLD pose,
    so a model spawned 10 m east already reports 10 m east, and SITL adds that
    to its own home. Offsetting home per vehicle as well puts vehicle 2 at
    twenty metres when the world says ten, and the error is invisible on
    screen because Gazebo draws the vehicle where the pose says.

    So the ENU offsets go into the Gazebo `<pose>` and nowhere else.
    """
    return f"{lat:.7f},{lon:.7f},{alt:.2f},{heading:.1f}"
