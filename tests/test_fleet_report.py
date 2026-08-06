"""L6 — acceptance criteria and the report, including what it refuses to claim.

Two failures are induced against REAL recorded data rather than invented:

  * a vehicle that fails its own acceptance criteria
  * a fleet-level criterion that fails — by demanding more separation than the
    recorded three-vehicle run actually achieved

The second needs no vehicles flown at each other. The run happened, its
`separation.csv` is on disk, and asking for 12 m of clearance from a run that
held 9.98 m is a genuine violation evaluated against genuine measurements.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from argazui.fleet import criteria as crit
from argazui.fleet import report as reportlib
from argazui.fleet import spec as fleetspec

pytestmark = pytest.mark.tier1


def make_spec(tmp_path, count=3, **keys) -> fleetspec.FleetSpec:
    extra = "".join(f"{k} = {v}\n" for k, v in keys.items())
    body = f"""
[fleet]
name = "report_fleet"
formation = "grid"
spacing_m = 12.0
min_separation_m = 5.0
{extra}
[fleet.origin]
lat = -35.363262
lon = 149.165237
alt = 584.0
"""
    for i in range(count):
        body += f"""
[[vehicle]]
id = "v{i+1}"
frame = "quad"
vehicle = "ArduCopter"
sysid = {i+1}
"""
    path = tmp_path / "r.toml"
    path.write_text(body, encoding="utf-8")
    spec = fleetspec.load(path)
    fleetspec.resolve_spawns(spec)
    return spec


# --------------------------------------------------- judged on time, not peaks
def test_a_brief_dip_is_forgiven_but_a_sustained_one_is_not():
    """The distinction a minimum-sample criterion cannot make.

    Both runs touch 0.265. One spent a tenth of a second there; the other sat
    there. A criterion keyed on the worst sample would give them the same
    verdict, which is the whole reason v1.1 moved attitude to seconds-outside.
    """
    brief = [(0.0, 0.9), (0.1, 0.265), (0.2, 0.9)] + [
        (0.2 + i * 0.1, 0.85) for i in range(1, 60)]
    sustained = [(i * 0.1, 0.265) for i in range(63)]

    ok = crit.rtf_criterion(brief, floor=0.35, available=True, tolerance_s=1.0)
    bad = crit.rtf_criterion(sustained, floor=0.35, available=True,
                             tolerance_s=1.0)

    assert ok.outcome == crit.PASSED, ok.detail
    assert bad.outcome == crit.FAILED, bad.detail
    assert "0.10s below 0.35" in ok.detail
    assert bad.evidence["seconds_outside"] > 1.0


def test_the_minimum_sample_alone_would_have_failed_both():
    """Stated explicitly so the improvement cannot silently regress."""
    brief = [(0.0, 0.9), (0.1, 0.265), (0.2, 0.9)] + [
        (0.2 + i * 0.1, 0.85) for i in range(1, 60)]
    assert min(v for _, v in brief) < 0.35
    assert crit.rtf_criterion(brief, floor=0.35, available=True).outcome \
        == crit.PASSED


def test_a_gap_in_the_data_cannot_manufacture_time_outside():
    """Same protection StabilityWatch has: a dropout is capped, not counted."""
    samples = [(0.0, 0.9), (0.5, 0.1), (600.0, 0.1), (600.5, 0.9)]
    outside, observed = crit.time_outside(samples, lambda v: v < 0.35)
    assert outside <= 2 * crit.MAX_GAP_S, (
        f"a 600 s gap contributed {outside:.1f}s of 'time below threshold'")
    assert observed <= 3 * crit.MAX_GAP_S


def test_separation_is_counted_on_the_simulated_clock():
    rows = [(100.0, 12.0), (100.5, 4.0), (101.0, 4.0), (101.5, 12.0)]
    result = crit.separation_criterion(rows, min_separation_m=5.0,
                                       measuring=True, tolerance_s=0.4)
    assert result.outcome == crit.FAILED
    assert "simulated time" in result.detail


# ----------------------------------------------------- three outcomes, not two
def test_a_criterion_that_could_not_be_evaluated_is_never_a_pass():
    result = crit.rtf_criterion([], floor=0.35, available=False,
                                absence_reason="SITL-only fleet: no physics "
                                               "server")
    assert result.outcome == crit.NOT_MEASURED
    assert result.passed is False
    assert "no physics server" in result.reason


def test_not_measured_requires_a_reason():
    with pytest.raises(ValueError, match="needs a reason"):
        crit.Criterion("x", "x", crit.NOT_MEASURED)


def test_an_unknown_outcome_is_refused():
    with pytest.raises(ValueError, match="unknown outcome"):
        crit.Criterion("x", "x", "probably fine")


def test_a_vehicle_with_no_data_makes_the_claim_unmeasured_not_failed():
    """"It did not climb" and "nobody watched" are different statements."""
    result = crit.altitude_criterion({"v1": 15.0, "v2": None}, target_m=10.0)
    assert result.outcome == crit.NOT_MEASURED
    assert "v2" in result.reason

    real = crit.altitude_criterion({"v1": 15.0, "v2": 3.0}, target_m=10.0)
    assert real.outcome == crit.FAILED
    assert real.evidence["short"] == ["v2"]


def test_a_vehicle_that_ran_no_procedure_does_not_count_as_passing():
    result = crit.per_vehicle_criterion({"v1": "passed", "v2": None})
    assert result.outcome == crit.NOT_MEASURED
    assert "v2" in result.reason


def test_the_fleet_verdict_separates_incomplete_from_passed():
    passed = [crit.Criterion("a", "a", crit.PASSED)]
    assert crit.fleet_verdict(passed) == crit.FLEET_PASSED

    partial = passed + [crit.Criterion("b", "b", crit.NOT_MEASURED,
                                       reason="no data")]
    assert crit.fleet_verdict(partial) == crit.FLEET_INCOMPLETE, (
        "a run with unevaluated criteria has not passed — it has not been "
        "tested")

    failing = partial + [crit.Criterion("c", "c", crit.FAILED)]
    assert crit.fleet_verdict(failing) == crit.FLEET_FAILED
    assert crit.fleet_verdict([]) == crit.FLEET_INCOMPLETE


# --------------------------------------------------------------- the report
def test_the_report_names_every_claim_it_did_not_make(tmp_path):
    spec = make_spec(tmp_path)
    criteria = [
        crit.Criterion("altitude", "every vehicle reached 10 m", crit.PASSED,
                       detail="v1 12.0 m, v2 11.8 m, v3 12.1 m"),
        crit.rtf_criterion([], floor=0.35, available=False,
                           absence_reason="SITL-only fleet: no physics server"),
        crit.separation_criterion([], 5.0, measuring=False,
                                  refusal_reason="vehicles do not share a "
                                                 "clock"),
    ]
    text = reportlib.render(spec, criteria, run_id="r1")

    assert "## What this run did not claim" in text
    assert "no physics server" in text
    assert "do not share a clock" in text
    assert "INCOMPLETE" in text
    assert "NOT MEASURED" in text
    # An unevaluated criterion must not appear as a pass anywhere.
    section = text.split("## What this run did not claim")[1]
    assert "real-time factor" in section


def test_a_fully_measured_run_says_so_explicitly(tmp_path):
    spec = make_spec(tmp_path)
    criteria = [crit.Criterion("a", "everything", crit.PASSED, detail="fine")]
    text = reportlib.render(spec, criteria)
    assert "Nothing was left unmeasured" in text
    assert "PASSED" in text


def test_the_report_surfaces_what_authorised_each_claim(tmp_path):
    spec = make_spec(tmp_path)
    criteria = [crit.separation_criterion(
        [(0.0, 12.0), (1.0, 11.0)], 5.0, measuring=True,
        authorised_by="one world-state message under a single header stamp")]
    text = reportlib.render(spec, criteria)
    assert "What authorised each claim" in text
    assert "single header stamp" in text


def test_the_report_carries_the_unverified_banner(tmp_path):
    spec = make_spec(tmp_path, allow_unverified="true",
                     unverified_reason='"bring-up on a fresh clone"')
    text = reportlib.render(spec, [crit.Criterion("a", "a", crit.PASSED)])
    assert "Unverified models were allowed" in text
    assert "bring-up on a fresh clone" in text


def test_the_report_uses_the_one_canonical_version_record(tmp_path):
    """`versions.environment()` and not a second assembled record."""
    from argazui import versions

    spec = make_spec(tmp_path)
    text = reportlib.render(spec, [crit.Criterion("a", "a", crit.PASSED)])
    record = versions.environment()
    assert "Reproducibility" in text
    for key in ("ardupilot", "argazui", "gz_sim", "python"):
        assert key in record
        assert key in text


def test_the_report_states_that_it_is_not_a_model_claim(tmp_path):
    spec = make_spec(tmp_path)
    text = reportlib.render(spec, [crit.Criterion("a", "a", crit.PASSED)])
    assert "says nothing about whether any MODEL is supported" in text


# ------------------------------------- induced failure 1: one vehicle fails
def test_a_run_where_one_vehicle_fails_its_own_criteria(tmp_path):
    spec = make_spec(tmp_path)
    criteria = [
        crit.per_vehicle_criterion({"v1": "passed", "v2": "failed",
                                    "v3": "passed"}),
        crit.altitude_criterion({"v1": 12.0, "v2": 2.1, "v3": 12.2},
                                target_m=10.0),
    ]
    assert crit.fleet_verdict(criteria) == crit.FLEET_FAILED

    text = reportlib.render(spec, criteria, run_id="induced_vehicle_failure")
    assert "FAILED" in text
    assert "v2: failed" in text
    assert "v2 2.1 m" in text
    # The passing vehicles are still named, so the failure is scoped.
    assert "v1: passed" in text


# ------------------------ induced failure 2: a fleet criterion, on real data
RECORDED = Path(__file__).resolve().parent.parent / "runs"


def _recorded_separation():
    """The real separation.csv from the phase-5 three-vehicle Gazebo run."""
    runs = sorted(RECORDED.glob("*_fleet_hexapod_trio/separation.csv"))
    if not runs:
        pytest.skip("no recorded fleet run on this machine; run the "
                    "fleet_gazebo tier first")
    # One row per pair per sample; the criterion asks about the fleet's
    # closest approach, so reduce to the minimum at each timestamp.
    closest: dict = {}
    for line in runs[-1].read_text().splitlines()[1:]:
        t, _pair, distance = line.split(",")
        t, distance = float(t), float(distance)
        if t not in closest or distance < closest[t]:
            closest[t] = distance
    return sorted(closest.items()), runs[-1]


def test_a_fleet_criterion_fails_against_real_recorded_data(tmp_path):
    """Demand more clearance than the run actually achieved.

    No vehicles are flown at each other and nothing is fabricated: the flight
    happened, the distances are the ones Gazebo reported, and the criterion is
    simply asked a stricter question than the run can answer yes to.
    """
    rows, path = _recorded_separation()
    achieved = min(d for _, d in rows)

    generous = crit.separation_criterion(rows, min_separation_m=5.0,
                                         measuring=True, tolerance_s=1.0)
    assert generous.outcome == crit.PASSED, (
        f"the recorded run should pass a 5 m rule; it held {achieved:.2f} m")

    strict = crit.separation_criterion(rows, min_separation_m=achieved + 2.0,
                                       measuring=True, tolerance_s=1.0,
                                       authorised_by="recorded world poses")
    assert strict.outcome == crit.FAILED, (
        f"asking for {achieved + 2.0:.2f} m from a run that held "
        f"{achieved:.2f} m should fail")
    assert strict.evidence["seconds_outside"] > 1.0

    spec = make_spec(tmp_path)
    text = reportlib.render(spec, [strict], run_id=path.parent.name)
    assert "FAILED" in text
    assert "below" in text
    assert "simulated time" in text


def test_the_same_data_passes_and_fails_only_because_the_question_changed(
        tmp_path):
    """The verdict moved; the measurements did not."""
    rows, _ = _recorded_separation()
    achieved = min(d for _, d in rows)
    lenient = crit.separation_criterion(rows, 5.0, measuring=True)
    strict = crit.separation_criterion(rows, achieved + 2.0, measuring=True)
    assert lenient.evidence["seconds_observed"] == \
        strict.evidence["seconds_observed"]
    assert lenient.outcome != strict.outcome


# ------------------------------------------------------------- golden report
# The report's WORDING is part of the contract, not an implementation detail.
# Its whole job is to say what was and was not proven; a silent edit that
# softened "NOT MEASURED" into something reassuring would be invisible to
# every other test here, which check structure rather than prose.
GOLDEN_REPORT = (Path(__file__).resolve().parent / "golden"
                 / "fleet_report.md")


def golden_inputs(tmp_path):
    """Fixed inputs, chosen to exercise all three outcomes at once."""
    spec = make_spec(tmp_path, count=3)
    criteria = [
        crit.separation_criterion(
            [(100.0, 12.0), (100.5, 11.4), (101.0, 4.2), (101.5, 11.9)],
            min_separation_m=5.0, measuring=True, tolerance_s=0.2,
            authorised_by="/world/runway/pose/info — one world-state message "
                          "under a single header stamp"),
        crit.rtf_criterion(
            [(0.0, 0.9), (1.0, 0.88), (2.0, 0.91)], floor=0.35, available=True,
            authorised_by="/stats, read from the running physics server"),
        crit.altitude_criterion({"v1": 12.0, "v2": 11.8, "v3": 12.1},
                                target_m=10.0,
                                authorised_by="VFR_HUD over each link"),
        crit.per_vehicle_criterion({"v1": "passed", "v2": "passed",
                                    "v3": None}),
        crit.teardown_criterion(None),
    ]
    # A fixed environment: the real one changes per machine and per commit,
    # which would make the golden file unrepeatable rather than stable.
    environment = {"ardupilot": "ArduPlane V4.8.0-dev @ 0b38722bd5a4",
                   "argazui": "1.3.0", "gz_sim": "Gazebo Sim, version 8.14.0",
                   "python": "3.12.3"}
    return spec, criteria, environment


def render_golden(tmp_path) -> str:
    spec, criteria, environment = golden_inputs(tmp_path)
    return reportlib.render(
        spec, criteria, run_id="20260806T000000Z_fleet_report_fleet",
        environment=environment,
        wiring={"ok": True, "reason": "3 vehicles each moved their own model",
                "checks": [
                    {"vehicle": "v1", "moved_m": 8.011,
                     "others": {"v2": 0.006, "v3": 0.0}, "floors": {},
                     "ok": True, "reason": ""},
                ]},
        commands=[{"command": "MODE LOITER", "policy": "parallel_ack",
                   "verdict": "PARTIAL", "seconds": 1.9,
                   "target": ["v1", "v2"],
                   "results": [
                       {"vehicle": "v1", "outcome": "ACCEPTED",
                        "ack": "ACCEPTED", "reason": "mode -> LOITER",
                        "t_ms": 40, "confirmed": True,
                        "observed": "mode == LOITER held"},
                       {"vehicle": "v2", "outcome": "REVERTED",
                        "ack": "ACCEPTED",
                        "reason": "acknowledged, then it did not hold",
                        "t_ms": 37, "confirmed": False,
                        "observed": "mode == LOITER did not hold"}]}],
        timeline_events=412)


def test_the_fleet_report_matches_its_golden_copy(tmp_path):
    produced = render_golden(tmp_path)
    if not GOLDEN_REPORT.is_file():
        pytest.fail(f"golden report missing: {GOLDEN_REPORT}\n"
                    f"Regenerate with --regenerate-golden once the wording is "
                    f"known good.\n--- produced ---\n{produced}")
    recorded = GOLDEN_REPORT.read_text(encoding="utf-8")
    # The generated-at line is the only part that legitimately moves.
    strip = lambda s: "\n".join(l for l in s.splitlines()
                                if not l.startswith("Generated 20"))
    assert strip(produced) == strip(recorded)


def test_regenerate_fleet_report(request, tmp_path):
    if not request.config.getoption("--regenerate-golden", default=False):
        pytest.skip("run with --regenerate-golden to rewrite the golden report")
    GOLDEN_REPORT.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN_REPORT.write_text(render_golden(tmp_path), encoding="utf-8")
    print(f"\nwrote {GOLDEN_REPORT}")
