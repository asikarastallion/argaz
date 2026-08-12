"""The Flight Runs panel stays a panel, not an endless scroll.

A real installation accumulates runs — the maintainer's had dozens — and the
panel rendered every one of them, pushing the rest of the page off the screen.
It now shows the newest few and opens on demand.

Display only: `/api/runs` still returns every run and nothing under `runs/` is
touched, so these tests assert the DOM against what the API reports rather than
against a truncated response.
"""
from __future__ import annotations

import json

import pytest

from harness import (assert_no_console_errors, open_page, open_section,
                     start_server)

pytestmark = [pytest.mark.e2e, pytest.mark.tier1]

# Must match RUNS_COLLAPSED in static/app.js. Asserted below against the DOM,
# so a change on one side without the other fails here rather than in a user's
# browser.
COLLAPSED = 5
SEEDED = 8


@pytest.fixture(scope="module")
def runs_server(tmp_path_factory):
    """A server whose runs root already holds more runs than the panel shows.

    The directories are seeded rather than flown: this is a test about the
    panel, and `list_runs` describes any directory named like a run — one
    without a `result.json` is listed as `incomplete`, which is exactly what a
    session killed mid-flight leaves behind.
    """
    tmp = tmp_path_factory.mktemp("e2e-runs")
    runs_root = tmp / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    for index in range(SEEDED):
        run_id = f"2026080{index}T10{index}000Z_e2e_seeded"
        directory = runs_root / run_id
        directory.mkdir()
        (directory / "result.json").write_text(json.dumps({
            "schema": 2, "run_id": run_id, "status": "passed",
            "model": {"id": "e2e_seeded", "name": f"Seeded run {index}"},
            "started_utc": f"2026-08-0{index}T10:{index}0:00Z",
            "seconds": 42, "procedures": [], "overrides": [],
            "artefacts": {"dataflash": None},
        }), encoding="utf-8")
        # A finished run has a report, and the deep-link test opens one. Without
        # it the sheet's fetch 404s and the console-error assertion fires on a
        # fixture artefact rather than on anything the panel did.
        (directory / "report.md").write_text(f"# Seeded run {index}\n", encoding="utf-8")
        (directory / "report.json").write_text(
            json.dumps({"advisories": [], "advisory_count": 0, "plots": []}),
            encoding="utf-8")

    running = start_server(tmp)
    yield running
    running.stop()


def _rows(page) -> int:
    return page.eval_on_selector_all(
        "#runs-table tbody tr", "els => els.filter(e => !e.querySelector('.runs-empty')).length")


def test_the_panel_shows_only_the_newest_runs_until_asked(browser_page, runs_server):
    """Five rows by default, however many runs exist."""
    page = open_section(open_page(browser_page, runs_server), "runs")
    page.wait_for_function(f"() => document.querySelectorAll('#runs-table tbody tr').length "
                           f">= {COLLAPSED}", timeout=20000)

    total = len(runs_server.api("/api/runs")["runs"])
    assert total >= SEEDED, f"the fixture seeded {SEEDED} runs, the API reports {total}"
    assert _rows(page) == COLLAPSED, (
        f"the panel rendered {_rows(page)} of {total} runs; it should stop at {COLLAPSED}")

    more = page.query_selector("#btn-runs-more")
    assert more and not page.eval_on_selector("#btn-runs-more", "e => e.hidden"), (
        "runs are hidden but nothing offers to show them")
    assert str(total - COLLAPSED) in more.inner_text(), (
        f"the control does not say how many are hidden: {more.inner_text()!r}")
    assert_no_console_errors(page, "with the runs panel collapsed")


def test_show_more_reveals_the_rest_and_show_less_collapses_again(browser_page, runs_server):
    page = open_section(open_page(browser_page, runs_server), "runs")
    page.wait_for_function(f"() => document.querySelectorAll('#runs-table tbody tr').length "
                           f">= {COLLAPSED}", timeout=20000)
    total = len(runs_server.api("/api/runs")["runs"])

    page.click("#btn-runs-more")
    page.wait_for_function(f"() => document.querySelectorAll('#runs-table tbody tr').length "
                           f"=== {total}", timeout=10000)
    assert _rows(page) == total

    # The same control now collapses: "show less" replaces "show more".
    page.click("#btn-runs-more")
    page.wait_for_function(f"() => document.querySelectorAll('#runs-table tbody tr').length "
                           f"=== {COLLAPSED}", timeout=10000)
    assert _rows(page) == COLLAPSED
    assert_no_console_errors(page, "after toggling the runs list")


def test_a_deep_link_to_a_collapsed_run_still_opens_and_expands_the_list(
        browser_page, runs_server):
    """#run=<id> must not be defeated by the run being below the fold.

    Capping the display would otherwise have made older runs unreachable by
    link — a panel that hides data is fine, a link that silently does nothing
    is not.
    """
    page = open_section(open_page(browser_page, runs_server), "runs")
    page.wait_for_function(f"() => document.querySelectorAll('#runs-table tbody tr').length "
                           f">= {COLLAPSED}", timeout=20000)

    runs = runs_server.api("/api/runs")["runs"]
    buried = runs[-1]["run_id"]                 # oldest: never in the first five
    assert buried not in page.inner_text("#runs-table"), (
        "the fixture's oldest run is visible while collapsed; it cannot test this")

    page.goto(f"{runs_server.url}/#run={buried}")
    page.wait_for_function("() => !document.getElementById('sheet-run').hidden",
                           timeout=20000)
    assert page.inner_text("#run-title").strip() == buried

    # And the table behind the sheet now agrees that the run exists.
    page.wait_for_function(f"() => document.getElementById('runs-table')"
                           f".innerText.includes({buried!r})", timeout=10000)
    assert _rows(page) == len(runs)
    assert_no_console_errors(page, "after deep-linking to a collapsed run")
