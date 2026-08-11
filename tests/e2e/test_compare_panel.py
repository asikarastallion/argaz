"""Comparing two runs, from the browser.

WHY THIS EXISTS SEPARATELY FROM test_regression.py
--------------------------------------------------
`tests/test_regression.py` proves the comparison is right. This proves a person
can get one: that the button reaches an endpoint that exists, that a verdict and
a table come back, and that the refusal path — which is most of what the
comparison layer does — reaches the reader instead of an empty box.

The runs are seeded rather than flown. What is being tested here is the wiring
between a button and a verdict; `tests/test_tier1_evidence_chain.py` does the
same journey on a real flight.
"""
from __future__ import annotations

import json

import pytest

from harness import assert_no_console_errors, open_page, start_server

pytestmark = [pytest.mark.e2e, pytest.mark.tier1]

# Every identity field, present and known — the shape a real run leaves.
#
# `fingerprint.differences()` reports an ABSENT field as a difference on
# purpose: it is a statement that nothing here can show the two runs match,
# which is exactly the condition a comparison must not be made silently
# across. A fixture that omits one therefore makes the panel render
# "incomparable" and this file would be testing that rule instead of the
# comparison it means to exercise.
FINGERPRINT = {
    "schema": 1,
    "model": {"config_hash": "sha256:same"},
    "procedure_hash": "sha256:same",
    "ardupilot": {"commit": "abc123", "firmware_commit": "abc123",
                  "dirty": False, "dirty_digest": "clean"},
    "argaz": {"commit": "def456", "dirty": False, "dirty_digest": "clean"},
    "gazebo": {"version": "Gazebo Sim, version 8.9.0"},
}


def _metric(key, value, unit, better="lower", procedure=""):
    # `clock` and `window` are part of what makes two numbers the same
    # quantity; a comparison across either is refused. Both sides seed the
    # same values so these tests stay about the verdict and the table.
    return {"key": key, "value": value, "unit": unit, "better": better,
            "scope": "run", "procedure": procedure, "source": "seeded",
            "detail": "", "clock": "vehicle", "window": "log"}


def _seed(root, run_id, started, metrics, *, model="e2e_cmp", fingerprint=None):
    directory = root / run_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "result.json").write_text(json.dumps({
        "schema": 3, "run_id": run_id, "status": "passed",
        "model": {"id": model, "name": "Comparison fixture"},
        "started_utc": started, "seconds": 42,
        "procedures": [{"procedure": "copter_takeoff", "role": "takeoff",
                        "result": {"outcome": "passed", "steps": [], "expect": []}}],
        "overrides": [], "artefacts": {"dataflash": None},
        "metrics": metrics,
        "fingerprint": FINGERPRINT if fingerprint is None else fingerprint,
    }), encoding="utf-8")
    (directory / "report.md").write_text(f"# {run_id}\n", encoding="utf-8")
    (directory / "report.json").write_text(
        json.dumps({"advisories": [], "advisory_count": 0, "plots": []}),
        encoding="utf-8")
    return directory


@pytest.fixture(scope="module")
def compare_server(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("e2e-compare")
    runs = tmp / "runs"
    runs.mkdir(parents=True, exist_ok=True)

    _seed(runs, "20260801T100000Z_e2e_cmp", "2026-08-01T10:00:00Z",
          [_metric("peak_angular_rate", 40.0, "deg/s"),
           _metric("tracking_error_roll_max", 5.0, "deg")])
    # Later, same configuration, one metric three times worse.
    _seed(runs, "20260802T100000Z_e2e_cmp", "2026-08-02T10:00:00Z",
          [_metric("peak_angular_rate", 130.0, "deg/s"),
           _metric("tracking_error_roll_max", 5.1, "deg")])
    # A different aircraft entirely, flown later still.
    _seed(runs, "20260803T100000Z_e2e_other", "2026-08-03T10:00:00Z",
          [_metric("peak_angular_rate", 40.0, "deg/s")], model="e2e_other")

    running = start_server(tmp)
    yield running
    running.stop()


def _open_run(page, server, run_id):
    page.goto(f"{server.url}/#run={run_id}", wait_until="networkidle")
    page.wait_for_selector("#sheet-run:not([hidden])")
    page.wait_for_timeout(400)


def test_the_button_produces_a_verdict_and_a_table(browser_page, compare_server):
    page = open_page(browser_page, compare_server, wait_ms=1500)
    _open_run(page, compare_server, "20260802T100000Z_e2e_cmp")

    page.click("#btn-run-compare")
    page.wait_for_selector("#run-compare table")

    text = page.inner_text("#run-compare")
    assert "20260801T100000Z_e2e_cmp" in text, "the baseline it used is not named"
    assert "REGRESSION" in text.upper(), text
    # The metric that moved is called out; the one inside tolerance is not.
    rows = page.eval_on_selector_all(
        "#run-compare tbody tr", "els => els.map(e => e.innerText)")
    degraded = [r for r in rows if "peak_angular_rate" in r]
    assert degraded and "+225" in degraded[0].replace(" ", ""), degraded
    assert any("tracking_error_roll_max" in r for r in rows)

    assert_no_console_errors(page, "after comparing two runs")


def test_the_comparison_says_it_is_measurement_and_not_a_criterion(browser_page,
                                                                   compare_server):
    """The distinction the whole metrics layer rests on has to reach the reader."""
    page = open_page(browser_page, compare_server, wait_ms=1500)
    _open_run(page, compare_server, "20260802T100000Z_e2e_cmp")
    page.click("#btn-run-compare")
    page.wait_for_selector("#run-compare table")

    note = page.inner_text("#run-compare")
    assert "not acceptance criteria" in note or "measurements" in note, note


def test_a_run_with_no_baseline_says_so_instead_of_showing_an_empty_table(
        browser_page, compare_server):
    """The oldest run of a model has nothing behind it, and that is not an error."""
    page = open_page(browser_page, compare_server, wait_ms=1500)
    _open_run(page, compare_server, "20260801T100000Z_e2e_cmp")

    page.click("#btn-run-compare")
    page.wait_for_timeout(1200)

    assert page.is_hidden("#run-compare"), "an empty comparison table was shown"
    hint = page.inner_text("#run-action-hint")
    assert hint.strip(), "the button failed silently"
    assert "e2e_cmp" in hint or "baseline" in hint.lower(), hint

    assert_no_console_errors(page, "when no baseline exists")


def test_opening_another_run_clears_the_previous_comparison(browser_page,
                                                            compare_server):
    """One run's numbers must never be left under another run's name."""
    page = open_page(browser_page, compare_server, wait_ms=1500)
    _open_run(page, compare_server, "20260802T100000Z_e2e_cmp")
    page.click("#btn-run-compare")
    page.wait_for_selector("#run-compare table")

    _open_run(page, compare_server, "20260803T100000Z_e2e_other")
    assert page.is_hidden("#run-compare")
    assert_no_console_errors(page, "after switching runs")
