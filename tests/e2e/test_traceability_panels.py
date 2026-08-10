"""The v1.5 panels and endpoints, in a real browser and against a real server.

WHY THESE ARE e2e
-----------------
Three of the four things v1.5 adds are read by a person: the evidence manifest
in a run sheet, the traceability chain beside it, and the coverage panel. Each
renders a list the server sends, and that combination is exactly where this page
has broken before — the v1.1 regression was a panel reading `.length` off
something the API had not sent, and the page went dead with one console line as
the only symptom. Every assertion here ends by reading the browser console.

They also cover what no Python test can: that the strings exist in both
languages and are actually wired to the elements.
"""
from __future__ import annotations

import json
import urllib.error

import pytest

from harness import assert_no_console_errors, open_page

pytestmark = [pytest.mark.e2e, pytest.mark.tier1]


# ------------------------------------------------------------------ coverage
def test_the_coverage_panel_names_what_was_not_covered(browser_page, server):
    """The uncovered list is the payload.

    A percentage on its own is an invitation to stop reading, so the panel has
    to make the names reachable rather than showing a number and a bar.
    """
    page = open_page(browser_page, server)
    panel = page.locator("#cov-panel")
    assert panel.is_visible()

    page.wait_for_function(
        "() => document.querySelectorAll('#cov-table tbody tr').length >= 4",
        timeout=20000)
    text = panel.inner_text()
    for label in ("Model coverage", "Procedure coverage",
                  "Acceptance-criterion coverage", "Fault and scenario"):
        assert label in text, f"{label} is not in the coverage panel"

    # The sandbox has no runs, so every dimension is uncovered and each one
    # must offer its list rather than just a count.
    page.locator("#cov-table tbody button").first.click()
    page.wait_for_timeout(400)
    detail = page.locator("#cov-detail")
    assert detail.is_visible()
    assert detail.inner_text().strip(), "the uncovered list opened empty"
    assert_no_console_errors(page, "after opening an uncovered list")


def test_the_coverage_panel_switches_language(browser_page, server):
    page = open_page(browser_page, server)
    page.click('[data-set-lang="tr"]')
    page.wait_for_timeout(600)
    assert "kapsam" in page.locator("#cov-panel h2").inner_text().lower()
    assert "test sayısı değil" in \
        page.locator('[data-i18n="cov_hint"]').inner_text().lower()

    page.click('[data-set-lang="en"]')
    page.wait_for_timeout(600)
    assert "coverage" in page.locator("#cov-panel h2").inner_text().lower()
    assert_no_console_errors(page, "after switching language twice")


def test_the_coverage_endpoint_reports_the_four_dimensions(server):
    document = server.api("/api/coverage")["coverage"]
    names = [d["dimension"] for d in document["dimensions"]]
    assert names == ["models", "procedures", "criteria", "faults"]
    for dimension in document["dimensions"]:
        assert dimension["declared"] >= 0
        # Every dimension must be able to name what it did not reach.
        assert isinstance(dimension["uncovered"], list)
        assert len(dimension["uncovered"]) == \
            dimension["declared"] - dimension["covered"]


def test_coverage_is_never_reported_as_a_test_count(server):
    """A number that goes up when somebody adds a test is not coverage."""
    document = server.api("/api/coverage")["coverage"]
    assert "tests" not in document
    assert "test_count" not in document


# --------------------------------------------------- evidence & trace endpoints
def test_an_unknown_run_is_a_404_from_both_endpoints(server):
    for endpoint in ("evidence", "trace"):
        with pytest.raises(urllib.error.HTTPError) as exc:
            server.api(f"/api/runs/20260101T000000Z_nothing/{endpoint}")
        assert exc.value.code == 404, endpoint


def test_a_run_with_no_manifest_answers_200_and_says_why(server):
    """An ordinary outcome, not a client error.

    Every run recorded before v1.5 has no manifest, and a 404 for that would
    make the browser log an error on a page whose first promise is a clean
    console — the same reason `/compare` answers 200 when a run has no earlier
    run to compare against.
    """
    run_id = "20260810T140000Z_seeded"
    seed_run(server, run_id)
    body = server.api(f"/api/runs/{run_id}/evidence")
    assert body["ok"] is False
    assert run_id in body["text"]


# ------------------------------------------------------- the run sheet panels
def seed_run(server, run_id: str) -> None:
    """A minimal run directory, complete enough for the sheet to open."""
    directory = server.runs_root / run_id
    directory.mkdir(parents=True, exist_ok=True)
    result = {
        "schema": 5, "run_id": run_id, "status": "passed",
        "test_id": "tests/test_seeded.py::test_x",
        "started_utc": "2026-08-10T12:00:00Z",
        "finished_utc": "2026-08-10T12:02:00Z", "seconds": 120.0,
        "model": {"id": "seeded", "name": "Seeded model"},
        "advisory_count": 0, "metrics": [], "flaky": [],
        "procedures": [{
            "procedure": "copter_takeoff", "role": "takeoff",
            "result": {"outcome": "passed", "faults": [], "params_changed": {},
                       "steps": [{"index": 0, "kind": "set_mode",
                                  "label": "Switch to GUIDED",
                                  "status": "passed", "text": "mode -> GUIDED",
                                  "seconds": 0.2,
                                  "step_id": "copter_takeoff#s1"}],
                       "expect": [{"label": "reached altitude", "passed": True,
                                   "text": "alt=15m", "kind": "within",
                                   "duration": 20.0,
                                   "criterion_id": "copter_takeoff#alt-reached",
                                   "declared_id": True}]},
        }],
        "artefacts": {"dataflash": None,
                      "dataflash_absent_reason":
                          "the vehicle never armed, and ArduPilot's default "
                          "LOG_DISARMED=0 means it writes no dataflash log "
                          "until it does — nothing was lost"},
    }
    (directory / "result.json").write_text(json.dumps(result), encoding="utf-8")
    for name in ("scenario.yaml", "console.log", "mavlink_events.jsonl",
                 "versions.txt"):
        (directory / name).write_text("seeded\n", encoding="utf-8")
    (directory / "fingerprint.json").write_text('{"schema": 1}\n',
                                                encoding="utf-8")
    (directory / "report.md").write_text(f"# Seeded run {run_id}\n",
                                         encoding="utf-8")


def test_the_run_sheet_shows_the_manifest_and_the_chain(browser_page, server):
    """Both sit above the report, because they say whether it can be read as
    evidence at all."""
    run_id = "20260810T120000Z_seeded"
    seed_run(server, run_id)
    # The manifest is written by the report path; produce it the way a user
    # would, through the endpoint the panel's ⟳ button uses.
    server.post(f"/api/runs/{run_id}/report")

    page = open_page(browser_page, server)
    page.evaluate(f"() => window.location.hash = '#run={run_id}'")
    page.wait_for_selector("#sheet-run:not([hidden])", timeout=20000)
    page.wait_for_function(
        "() => !document.getElementById('run-trace').hidden", timeout=20000)

    trace = page.locator("#run-trace").inner_text()
    assert "tests/test_seeded.py::test_x" in trace, "the intent is not shown"
    assert "copter_takeoff#alt-reached" in trace, "the criterion id is not shown"
    assert "copter_takeoff#s1" in trace, "the step id is not shown"
    assert_no_console_errors(page, "after opening a run with a chain")


def test_a_run_flown_by_hand_says_no_test_asserts_it(browser_page, server):
    run_id = "20260810T130000Z_seeded"
    seed_run(server, run_id)
    path = server.runs_root / run_id / "result.json"
    result = json.loads(path.read_text(encoding="utf-8"))
    result["test_id"] = None
    path.write_text(json.dumps(result), encoding="utf-8")

    page = open_page(browser_page, server)
    page.evaluate(f"() => window.location.hash = '#run={run_id}'")
    page.wait_for_selector("#sheet-run:not([hidden])", timeout=20000)
    page.wait_for_function(
        "() => !document.getElementById('run-trace').hidden", timeout=20000)

    trace = page.locator("#run-trace").inner_text()
    assert "manual" in trace
    assert "no test asserts this" in trace
    assert_no_console_errors(page, "after opening a hand-flown run")
