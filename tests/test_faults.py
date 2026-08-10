"""Fault injection: the declaration, the mechanism, and the five rules.

WHAT THESE COVER AND WHAT THEY CANNOT
-------------------------------------
Everything here runs against a stand-in link, so it proves the mechanism does
what it says — probes before it writes, restores what it changed, drops the
packets it claims to, refuses a declaration that would inject nothing. It
proves nothing about how an aircraft responds to a fault; that is
`tests/test_tier1_faults.py`, which flies one.

The stand-in is deliberately a recording double rather than a mock of
pymavlink: it answers `_param_get` and `_do_param` the way a vehicle does and
remembers every write, so a restore that did not happen is visible as a missing
line rather than as an unasserted call.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from argazui import faults, procedures as procs

pytestmark = pytest.mark.tier1


class FakeState:
    attitude_known = True
    prearm_known = True
    connected = True
    vehicle_clock_s = 10.0


class FakeLink:
    """A link that answers parameter reads and records every write."""

    def __init__(self, params: dict, refuse: tuple = ()) -> None:
        self.params = dict(params)
        self.refuse = set(refuse)
        self.writes: list[tuple] = []
        self.state = FakeState()
        self.link_fault = None

    # -- what the injectors use ------------------------------------------
    def submit(self, fn, timeout=0.0, label="") -> dict:
        return fn(self)

    def _param_get(self, name, timeout=5.0):
        return self.params.get(name)

    def _do_param(self, args) -> dict:
        _, name, value = args
        self.writes.append((name, float(value)))
        if name in self.refuse:
            return {"ok": False, "text": f"the vehicle refused {name}"}
        self.params[name] = float(value)
        return {"ok": True, "text": f"param {name} = {value}"}

    def set_link_fault(self, drop_one_in=1, block_tx=False) -> None:
        self.link_fault = {"drop_one_in": drop_one_in, "block_tx": block_tx}

    def clear_link_fault(self) -> dict:
        record = self.link_fault or {}
        self.link_fault = None
        return record


MODERN = {"SIM_GPS1_ENABLE": 1.0, "SIM_GPS1_NUMSATS": 10.0,
          "SIM_GPS1_FIXTYPE": 6.0}
LEGACY = {"SIM_GPS_DISABLE": 0.0, "SIM_GPS_NUMSATS": 10.0}


# ------------------------------------------------------------- declarations
def test_the_catalogue_is_complete_in_both_languages():
    """A fault a user cannot read about is a fault they cannot use safely."""
    assert set(faults.CATALOGUE) == set(faults.KINDS)
    for kind, spec in faults.CATALOGUE.items():
        for field in ("label", "what", "observe"):
            for lang in ("en", "tr"):
                assert spec[field].get(lang), f"{kind}.{field} has no {lang}"
        assert spec["mechanism"] and spec["source"]
        assert faults.TARGETS[kind], f"{kind} names no target"


def test_an_unknown_fault_names_the_alternatives():
    with pytest.raises(ValueError) as exc:
        faults.check_declaration("engine_fire", "engine1", None, "x.yaml")
    assert "gps_loss" in str(exc.value)
    # The message has to say what is deliberately absent, or the next person
    # assumes it is a bug rather than a decision.
    assert "deliberately not implemented" in str(exc.value)


def test_a_fault_cannot_target_something_it_does_not_act_on():
    with pytest.raises(ValueError) as exc:
        faults.check_declaration("gps_loss", "gcs_link", None, "x.yaml")
    assert "gps1" in str(exc.value)


def test_only_the_primary_gps_is_offered():
    """SITL simulates GPS 2 only when asked to, so degrading it is a no-op."""
    assert faults.TARGETS[faults.GPS_LOSS] == ("gps1",)
    with pytest.raises(ValueError):
        faults.check_declaration("gps_loss", "gps2", None, "x.yaml")


def test_a_degradation_that_degrades_nothing_is_refused():
    with pytest.raises(ValueError) as exc:
        faults.check_declaration("gps_degradation", "gps1",
                                 {"satellites": None}, "x.yaml")
    assert "degrades nothing" in str(exc.value)


def test_dropping_every_packet_must_be_declared_as_an_interruption():
    """The run record has to say which of the two actually happened."""
    with pytest.raises(ValueError) as exc:
        faults.check_declaration("mavlink_degradation", "gcs_link",
                                 {"drop_one_in": 1}, "x.yaml")
    assert "mavlink_interrupt" in str(exc.value)


def test_an_unknown_option_is_refused_rather_than_ignored():
    with pytest.raises(ValueError):
        faults.check_declaration("gps_loss", "gps1", {"satellites": 4}, "x.yaml")


def test_defaults_are_filled_in_from_the_catalogue():
    resolved = faults.check_declaration("gps_degradation", "gps1", None, "x.yaml")
    assert resolved["satellites"] == 4


# ------------------------------------------------------------------ GPS loss
def test_gps_loss_probes_before_it_writes_anything():
    """Rule 3, fail closed: a probe that changes the vehicle is not a probe."""
    link = FakeLink(MODERN)
    injector = faults.injector_for(faults.GPS_LOSS, "gps1")
    injector.probe(link)
    assert link.writes == []
    assert "SIM_GPS1_ENABLE" in injector.mechanism_text


def test_gps_loss_disables_and_then_restores_the_receiver():
    link = FakeLink(MODERN)
    injector = faults.injector_for(faults.GPS_LOSS, "gps1")
    injector.probe(link)
    injector.apply(link)
    assert link.params["SIM_GPS1_ENABLE"] == 0.0
    assert injector.applied

    assert injector.clear(link) is True
    assert link.params["SIM_GPS1_ENABLE"] == 1.0, "the receiver was left off"
    assert injector.changed["SIM_GPS1_ENABLE"]["restore_to"] == 1.0


def test_gps_loss_falls_back_to_the_older_parameter_name():
    """`SIM_GPS_DISABLE` became `SIM_GPS1_ENABLE`, with the sense inverted.

    ArgazUI is a front end for a checkout it does not control, so both are
    probed — and the inverted sense has to survive the fallback or the fault
    would enable a receiver it was asked to disable.
    """
    link = FakeLink(LEGACY)
    injector = faults.injector_for(faults.GPS_LOSS, "gps1")
    injector.probe(link)
    injector.apply(link)
    assert link.params["SIM_GPS_DISABLE"] == 1.0, "disable=1 means the GPS is off"
    injector.clear(link)
    assert link.params["SIM_GPS_DISABLE"] == 0.0


def test_a_firmware_with_neither_parameter_fails_closed():
    link = FakeLink({"SIM_SPEEDUP": 1.0})
    injector = faults.injector_for(faults.GPS_LOSS, "gps1")
    with pytest.raises(faults.FaultUnavailable) as exc:
        injector.probe(link)
    assert "SIM_GPS1_ENABLE" in str(exc.value)
    assert link.writes == []


def test_a_refused_write_raises_rather_than_reporting_success():
    link = FakeLink(MODERN, refuse=("SIM_GPS1_ENABLE",))
    injector = faults.injector_for(faults.GPS_LOSS, "gps1")
    injector.probe(link)
    with pytest.raises(faults.FaultRefused):
        injector.apply(link)
    assert not injector.applied


# --------------------------------------------------------- GPS degradation
def test_gps_degradation_writes_only_the_knobs_it_was_given():
    link = FakeLink(MODERN)
    injector = faults.injector_for(faults.GPS_DEGRADATION, "gps1",
                                   {"satellites": 4, "fix_type": None})
    injector.probe(link)
    injector.apply(link)
    assert link.params["SIM_GPS1_NUMSATS"] == 4.0
    assert link.params["SIM_GPS1_FIXTYPE"] == 6.0, "fix type was not asked for"
    injector.clear(link)
    assert link.params["SIM_GPS1_NUMSATS"] == 10.0


def test_degrading_a_fix_type_the_firmware_has_no_parameter_for_fails_closed():
    """Rule 3 again, in the case that would otherwise inject nothing at all."""
    link = FakeLink(LEGACY)          # legacy scheme has no FIXTYPE
    injector = faults.injector_for(faults.GPS_DEGRADATION, "gps1",
                                   {"satellites": None, "fix_type": 1})
    with pytest.raises(faults.FaultUnavailable):
        injector.probe(link)


def test_a_restore_that_had_nothing_to_put_back_reports_failure():
    """Unreadable before the write means nothing to claim, not a clean restore."""
    link = FakeLink({"SIM_GPS1_ENABLE": 1.0, "SIM_GPS1_FIXTYPE": 6.0})
    injector = faults.injector_for(faults.GPS_DEGRADATION, "gps1",
                                   {"satellites": 4, "fix_type": None})
    injector.probe(link)
    injector.apply(link)
    assert injector.clear(link) is False
    assert injector.changed["SIM_GPS1_NUMSATS"]["restored"] is None


# -------------------------------------------------------------- link faults
def test_an_interruption_blocks_transmission_and_discards_everything():
    link = FakeLink(MODERN)
    injector = faults.injector_for(faults.MAVLINK_INTERRUPT, "gcs_link")
    injector.probe(link)
    injector.apply(link)
    assert link.link_fault == {"drop_one_in": 1, "block_tx": True}
    assert injector.clear(link) is True
    assert link.link_fault is None


def test_degradation_drops_one_in_n_and_leaves_transmission_alone():
    link = FakeLink(MODERN)
    injector = faults.injector_for(faults.MAVLINK_DEGRADATION, "gcs_link",
                                   {"drop_one_in": 3})
    injector.probe(link)
    injector.apply(link)
    assert link.link_fault == {"drop_one_in": 3, "block_tx": False}


def test_the_link_fault_is_deterministic_by_count():
    """Rule 5. Two runs of one scenario must lose the same packets."""
    from argazui.mavlink_link import MavlinkLink

    link = MavlinkLink(port=0)
    link.set_link_fault(drop_one_in=3, block_tx=False)
    dropped = [link._drop_received() for _ in range(9)]
    assert dropped == [False, False, True, False, False, True,
                       False, False, True]
    record = link.clear_link_fault()
    assert record["received"] == 9 and record["discarded"] == 3
    assert link._drop_received() is False, "the fault outlived its own clear"


def test_an_interruption_discards_every_received_message():
    from argazui.mavlink_link import MavlinkLink

    link = MavlinkLink(port=0)
    link.set_link_fault(drop_one_in=1, block_tx=True)
    assert all(link._drop_received() for _ in range(5))
    assert link._tx_blocked() is True
    link.clear_link_fault()
    assert link._tx_blocked() is False


def test_stopping_the_link_clears_any_injected_fault():
    """A fault must not outlive the link that carried it."""
    from argazui.mavlink_link import MavlinkLink

    link = MavlinkLink(port=0)
    link.set_link_fault(drop_one_in=1, block_tx=True)
    link.stop()                       # never started; stop is still the teardown
    assert link.link_fault is None


# ------------------------------------------------------------------ recovery
class ClockLink(FakeLink):
    """A link whose vehicle clock only moves when telemetry is flowing."""

    def __init__(self, resumes_after: float) -> None:
        super().__init__(MODERN)
        self.state = FakeState()
        self.state.vehicle_clock_s = 100.0
        self.stability = None
        self.speedup = 1.0
        self.pumps = 0
        self.resumes_after = resumes_after

    def submit(self, fn, timeout=0.0, label="") -> dict:
        if label in ("resync", "observe"):
            self.pumps += 1
            if self.pumps >= self.resumes_after:
                self.state.vehicle_clock_s += 1.0
            return {"ok": True, "text": ""}
        return fn(self)


def test_recovery_waits_for_fresh_telemetry_before_it_judges_anything():
    """A cleared fault is not a recovered one.

    Every field of the vehicle state still holds what arrived before the fault,
    so a `within:` criterion evaluated immediately would pass on a reading the
    fault itself froze — silence reported as success.
    """
    from argazui.procrunner import ProcedureRunner

    link = ClockLink(resumes_after=3)
    runner = ProcedureRunner(link)
    assert runner._resync(timeout=5.0) is True
    assert link.pumps >= 3, "it returned before the clock had actually moved"


def test_a_link_that_never_comes_back_is_reported_as_not_judged():
    """The honest outcome, not a pass and not a verdict about the aircraft."""
    from argazui.procrunner import ProcedureRunner

    link = ClockLink(resumes_after=float("inf"))     # telemetry never resumes
    runner = ProcedureRunner(link)
    assert runner._resync(timeout=0.5) is False
    assert link.state.vehicle_clock_s == 100.0, "the clock moved after all"


# -------------------------------------------------------- the schema itself
def parse(body: str, name: str = "scenario_x"):
    return procs.parse(body, Path(f"{name}.yaml"))


SKELETON = """\
schema: {schema}
id: scenario_x
name: {{en: X, tr: X}}
sources: [https://example.invalid/doc]
applies_to: {{role: scenario, autopilot: ArduCopter}}
steps:
  - set_mode: GUIDED
expect:
  - condition: {{armed: true}}
{failures}
"""


def document(failures_block: str = "", schema: int = 3) -> str:
    return SKELETON.format(schema=schema, failures=failures_block)


VALID_FAULT = """\
failures:
  - id: gps_off
    fault: gps_loss
    target: gps1
    inject_after_step: 1
    duration: 10s
    expected: {en: it stays airborne, tr: havada kalir}
    expect:
      - condition: {armed: true}
        for: 5s
    evidence: [attitude]
"""


def test_a_valid_scenario_parses():
    parsed = parse(document(VALID_FAULT))
    assert parsed.role == "scenario"
    fault = parsed.failures[0]
    assert fault.kind == faults.GPS_LOSS
    assert fault.duration == 10.0
    assert fault.evidence == ["attitude"]
    assert fault.expected_text("tr") == "havada kalir"


def test_failures_is_rejected_before_schema_3():
    """The version moves rather than being extended in place — same rule as v1.3."""
    with pytest.raises(procs.ProcedureError) as exc:
        parse(document(VALID_FAULT, schema=2))
    assert "schema 3" in str(exc.value)


def test_a_fault_with_no_criteria_is_refused():
    """Otherwise it proves only that the fault was injected."""
    body = VALID_FAULT.replace("""    expect:
      - condition: {armed: true}
        for: 5s
""", "")
    with pytest.raises(procs.ProcedureError) as exc:
        parse(document(body))
    assert "expect" in str(exc.value) and "recovery" in str(exc.value)


def test_a_fault_with_no_evidence_is_refused():
    body = VALID_FAULT.replace("    evidence: [attitude]\n", "")
    with pytest.raises(procs.ProcedureError):
        parse(document(body))


def test_an_unknown_evidence_signal_names_the_known_ones():
    body = VALID_FAULT.replace("[attitude]", "[vibes]")
    with pytest.raises(procs.ProcedureError) as exc:
        parse(document(body))
    assert "attitude" in str(exc.value)


def test_an_injection_point_past_the_last_step_is_refused():
    body = VALID_FAULT.replace("inject_after_step: 1", "inject_after_step: 9")
    with pytest.raises(procs.ProcedureError) as exc:
        parse(document(body))
    assert "between 0 and 1" in str(exc.value)


def test_a_duration_without_a_unit_is_refused():
    """Same rule as every other duration in this format — v1.3's, unchanged."""
    body = VALID_FAULT.replace("duration: 10s", "duration: 10")
    with pytest.raises(procs.ProcedureError) as exc:
        parse(document(body))
    assert "unit" in str(exc.value)


def test_two_faults_cannot_share_an_injection_point():
    """One fault is held at a time; list position is not an execution order."""
    second = VALID_FAULT.replace("failures:\n", "").replace("id: gps_off",
                                                            "id: link_out")
    second = second.replace("fault: gps_loss", "fault: mavlink_interrupt")
    second = second.replace("target: gps1", "target: gcs_link")
    with pytest.raises(procs.ProcedureError) as exc:
        parse(document(VALID_FAULT + second))
    assert "same step" in str(exc.value)


def test_the_scenario_role_is_never_auto_selected():
    """A fault must not start because a capability heuristic thought it applied."""
    assert "scenario" not in procs.AUTO_ROLES
    caps = {"autopilot": "ArduCopter", "quadplane": False, "tailsitter": False,
            "fw_takeoff_allowed": False, "arm_vtol_only": False}
    for role in procs.AUTO_ROLES:
        chosen = procs.select(role, caps)
        assert chosen is None or chosen.role != "scenario"


def test_the_shipped_scenarios_load_and_declare_a_fault_each():
    """The two procedures v1.4 ships are part of the release, not examples."""
    everything = procs.load_all(force=True)
    for name in ("copter_gps_loss", "copter_link_loss"):
        scenario = everything[name]
        assert scenario.schema == 3
        assert scenario.role == "scenario"
        assert scenario.failures, f"{name} declares no fault"
        for fault in scenario.failures:
            assert fault.expected_text("en") and fault.expected_text("tr")
            assert fault.expect or fault.recovery
            assert fault.evidence
