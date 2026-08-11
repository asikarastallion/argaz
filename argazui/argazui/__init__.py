"""ArgazUI — a single-page control panel for ArduPilot SITL + Gazebo."""

# Recorded in every run's versions.txt and result.json, so an archived flight
# says which ArgazUI produced it.
# 1.6.1 is a corrective release. It adds no feature: it closes the two defects
# an independent audit found in the verification result itself — a criterion
# that could pass on telemetry that never arrived, and a simulator failure
# reported as an aircraft failure — plus the HIGH findings beside them. See
# docs/V1.6_CORRECTIVE_RELEASE_VERIFICATION.md.
__version__ = "1.6.1"
