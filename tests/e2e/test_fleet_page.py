"""The Fleet page, in a real browser.

THREE RULES, EACH A CORRECTNESS REQUIREMENT RATHER THAN A STYLE CHOICE
----------------------------------------------------------------------
1. REVERTED is visually distinct from ACCEPTED. It is the outcome the whole
   project exists to surface — the autopilot said yes and the vehicle did not
   stay — and a green tick would put back the untruth v1.1 removed.
2. A not-measured criterion never renders as a pass. Blank, zero, and a grey
   dash that reads as "fine" are the same failure.
3. The target of a command is never ambiguous. The button says how many
   vehicles it will reach before it is pressed.

WHY THE STATE IS INJECTED RATHER THAN FLOWN
-------------------------------------------
These assert what the PAGE does with a given fleet state. Driving a real
three-vehicle Gazebo fleet to produce a REVERTED row in a browser test would
take minutes, need a GPU, and still not be reproducible on demand — the
manual flight in the phase-7 gate covers the live path. What must be
deterministic is the rendering, so the same `applyFleet` the WebSocket calls
is handed a fixed state.

The state used is the shape the server really produces; `test_fleet_router.py`
and `test_fleet_sitl_router.py` are what prove the server produces it.

Marked tier1 like the other e2e tests. NEVER tier2 — that marker is model
verification and a page test verifies no airframe.
"""
from __future__ import annotations

import json

import pytest

from harness import open_page, start_server, assert_no_console_errors

pytestmark = pytest.mark.tier1


def fleet_state(**overrides) -> dict:
    """A fleet status document of the shape `FleetManager.status()` returns."""
    state = {
        "running": True, "starting": False, "error": "",
        "name": "trio", "gazebo": True, "run_id": "20260806T000000Z_fleet_trio",
        "vehicles": [
            {"id": "v1", "sysid": 1, "model": "hexapod_copter", "role": "leader",
             "mode": "GUIDED", "armed": True, "alt": 12.0, "prearm_known": True,
             "prearm_ok": True, "heartbeat_age": 0.2, "link_stale": False,
             "serial0_port": 5760, "connection": "tcp:127.0.0.1:5760"},
            {"id": "v2", "sysid": 2, "model": "hexapod_copter", "role": "",
             "mode": "GUIDED", "armed": True, "alt": 11.8, "prearm_known": True,
             "prearm_ok": True, "heartbeat_age": 0.3, "link_stale": False,
             "serial0_port": 5770, "connection": "tcp:127.0.0.1:5770"},
            {"id": "v3", "sysid": 3, "model": "hexapod_copter", "role": "",
             "mode": "STABILIZE", "armed": False, "alt": 0.0,
             "prearm_known": True, "prearm_ok": False, "heartbeat_age": 9.4,
             "link_stale": True, "serial0_port": 5780,
             "connection": "tcp:127.0.0.1:5780"},
        ],
        "policies": ["parallel_ack", "staggered", "gated"],
        "default_policy": "parallel_ack",
        "separation": {"measured": True, "reason": "", "minimum_m": 9.98,
                       "current_m": 11.2, "limit_m": 5.0, "violations": 0,
                       "series": [[1.0, 11.5], [1.5, 11.2]]},
        "rtf": {"measured": True, "reason": "", "rtf": 0.57, "floor": 0.35,
                "series": [[1.0, 0.57]]},
        "last_command": None,
        "console_vehicle": "",
        "launch_transcript": ["# generated world: /run/world/fleet.sdf",
                              "arducopter --model JSON -I0 --serial0 tcp:0"],
        "min_separation_m": 5.0, "max_rtf_drop": 0.35,
    }
    state.update(overrides)
    return state


def apply(page, state: dict) -> None:
    """Render a fixed fleet state, and PIN it against the live status pump.

    The server pushes a fresh fleet status once a second. Without pinning, a
    test that injects a state and then queries the DOM races that push and
    intermittently finds an empty matrix — which is a flake in the test, not a
    fault in the page. The real `applyFleet` still does the rendering; only
    its input is held still.
    """
    page.evaluate("""s => {
        if (!window.__realApplyFleet) {
            window.__realApplyFleet = window.__applyFleet;
        }
        window.__applyFleet = () => window.__realApplyFleet(s);
        window.__realApplyFleet(s);
    }""", state)
    page.wait_for_timeout(150)


@pytest.fixture(scope="module")
def fleet_server(tmp_path_factory):
    running = start_server(tmp_path_factory.mktemp("e2e-fleet"))
    try:
        yield running
    finally:
        running.stop()


@pytest.fixture
def fleet_page(browser_page, fleet_server):
    page = open_page(browser_page, fleet_server)
    page.click("#tab-fleet")
    page.wait_for_selector("#page-fleet:not([hidden])")
    return page


# ------------------------------------------------------------------- the tab
def test_the_fleet_tab_exists_and_leaves_the_single_vehicle_page_alone(fleet_page):
    page = fleet_page
    assert page.is_visible("#page-fleet")
    assert page.is_hidden("#page-single")

    page.click("#tab-single")
    page.wait_for_selector("#page-single:not([hidden])")
    assert page.is_visible("#btn-start"), "the single-vehicle START button vanished"
    # `#buttons` is populated only once a model is selected, so it legitimately
    # has no height here; presence in the DOM is the right check.
    assert page.query_selector("#buttons") is not None, (
        "the single-vehicle command bar vanished")
    assert page.is_visible("#list-Copter"), "the model picker vanished"


def test_the_picker_shows_a_validation_badge_and_the_reason_when_it_fails(
        fleet_page):
    page = fleet_page
    page.wait_for_selector("#fleet-select option", state="attached")
    names = page.eval_on_selector_all("#fleet-select option", "o => o.map(x => x.value)")
    assert names, "no fleet specs were listed"
    page.wait_for_selector("#fleet-validation")
    text = page.inner_text("#fleet-validation")
    assert text in ("VALID", "INVALID")
    if text == "INVALID":
        assert page.inner_text("#fleet-badge").strip(), (
            "an invalid fleet showed a badge with no reason")


# ------------------------------------------------- RULE 1: REVERTED is distinct
def test_reverted_is_visually_distinct_from_accepted(fleet_page):
    """The outcome the whole project exists to surface.

    Rendering "the autopilot acked it" as a green tick when the vehicle did
    not stay is precisely the untruth v1.1 removed.
    """
    page = fleet_page
    apply(page, fleet_state(last_command={
        "command": "MODE LOITER", "policy": "parallel_ack", "verdict": "PARTIAL",
        "seconds": 1.9, "target": ["v1", "v2", "v3"],
        "results": [
            {"vehicle": "v1", "outcome": "ACCEPTED", "ack": "ACCEPTED",
             "reason": "mode -> LOITER", "t_ms": 40, "confirmed": True,
             "observed": "mode == LOITER held for 1.5s of vehicle time"},
            {"vehicle": "v2", "outcome": "REVERTED", "ack": "ACCEPTED",
             "reason": "acknowledged, then mode == LOITER did not hold",
             "t_ms": 37, "confirmed": False,
             "observed": "mode == LOITER did not hold — vehicle is in 'STABILIZE'"},
            {"vehicle": "v3", "outcome": "DENIED", "ack": "NAK",
             "reason": "PreArm: Battery 1 below minimum arming voltage",
             "t_ms": 5622, "confirmed": None, "observed": ""},
        ]}))

    accepted = page.query_selector('tr[data-vehicle="v1"] td.outcome')
    reverted = page.query_selector('tr[data-vehicle="v2"] td.outcome')
    denied = page.query_selector('tr[data-vehicle="v3"] td.outcome')
    assert accepted and reverted and denied

    # It says the word.
    assert "REVERTED" in reverted.inner_text()
    assert "ACCEPTED" in accepted.inner_text()

    # It does not share a class with either neighbour.
    a_cls = set(accepted.get_attribute("class").split())
    r_cls = set(reverted.get_attribute("class").split())
    d_cls = set(denied.get_attribute("class").split())
    assert "reverted" in r_cls
    assert r_cls != a_cls, "REVERTED is styled identically to ACCEPTED"
    assert r_cls != d_cls, "REVERTED is styled identically to DENIED"
    assert "ok" not in r_cls, "REVERTED carries the success style"

    # And it does not LOOK the same: different computed colour from both.
    colour = "el => getComputedStyle(el).color"
    a_colour = page.evaluate(colour, accepted)
    r_colour = page.evaluate(colour, reverted)
    d_colour = page.evaluate(colour, denied)
    assert r_colour != a_colour, (
        f"REVERTED and ACCEPTED render the same colour {r_colour}")
    assert r_colour != d_colour, (
        f"REVERTED and DENIED render the same colour {r_colour}")

    # The row keeps BOTH findings: the ack happened, the state did not hold.
    row = page.inner_text('tr[data-vehicle="v2"]')
    assert "ACCEPTED" in row, "the acknowledgement was dropped from a REVERTED row"
    assert "did not hold" in row

    assert page.inner_text("#ack-verdict") == "PARTIAL"
    assert_no_console_errors(page, "while rendering the ACK matrix")


def test_a_reverted_row_never_reports_the_group_as_passed(fleet_page):
    page = fleet_page
    apply(page, fleet_state(last_command={
        "command": "MODE LOITER", "policy": "parallel_ack", "verdict": "FAILED",
        "seconds": 1.5, "target": ["v1"],
        "results": [{"vehicle": "v1", "outcome": "REVERTED", "ack": "ACCEPTED",
                     "reason": "acknowledged, then it did not hold",
                     "t_ms": 37, "confirmed": False,
                     "observed": "mode == LOITER did not hold"}]}))
    verdict = page.query_selector("#ack-verdict")
    assert verdict.inner_text() == "FAILED"
    assert "ok" not in set(verdict.get_attribute("class").split())


# ------------------------------------------ RULE 2: not-measured is not a pass
def test_a_not_measured_panel_says_so_and_gives_the_reason(fleet_page):
    """Blank, zero and a soothing dash are the same failure."""
    page = fleet_page
    reason = ("SITL-only fleet: the vehicles do not share a clock, so two "
              "positions carry no common time base")
    apply(page, fleet_state(
        gazebo=False,
        separation={"measured": False, "reason": reason, "minimum_m": None,
                    "current_m": None, "series": []},
        rtf={"measured": False, "rtf": None,
             "reason": "SITL-only fleet: there is no physics server to report "
                       "a real-time factor"}))

    sep = page.query_selector("#sep-panel")
    assert sep.get_attribute("data-measured") == "false"
    text = sep.inner_text()
    assert "NOT MEASURED" in text
    assert "do not share a clock" in text, (
        "the panel does not give the reason the report gives")

    # It must not show a number, a zero, or a bare dash that reads as fine.
    assert page.query_selector("#sep-panel .gauge") is None, (
        "an unmeasured separation panel rendered a gauge")
    assert "0.00" not in text and "0 m" not in text

    rtf = page.query_selector("#rtf-panel")
    assert rtf.get_attribute("data-measured") == "false"
    assert "NOT MEASURED" in rtf.inner_text()
    assert "no physics server" in rtf.inner_text()
    assert page.query_selector("#rtf-panel .gauge") is None


def test_a_measured_panel_does_show_its_numbers(fleet_page):
    """The other half: when it WAS measured, the page says so plainly."""
    page = fleet_page
    apply(page, fleet_state())
    sep = page.query_selector("#sep-panel")
    assert sep.get_attribute("data-measured") == "true"
    assert "NOT MEASURED" not in sep.inner_text()
    assert "9.98" in sep.inner_text(), "the run minimum is not shown"
    assert page.query_selector("#rtf-panel .gauge") is not None
    assert "0.57" in page.inner_text("#rtf-panel")


def test_the_not_measured_badge_is_not_styled_as_success(fleet_page):
    page = fleet_page
    apply(page, fleet_state(
        separation={"measured": False, "reason": "no shared clock",
                    "minimum_m": None, "current_m": None, "series": []}))
    badge = page.query_selector("#sep-panel .badge")
    classes = set(badge.get_attribute("class").split())
    assert "ok" not in classes, "NOT MEASURED is styled as a success"
    assert "notmeasured" in classes


# ------------------------------------------ RULE 3: the target is never vague
def test_the_command_buttons_say_how_many_vehicles_they_will_reach(fleet_page):
    page = fleet_page
    apply(page, fleet_state())

    assert "3 of 3 vehicles" in page.inner_text("#target-count")
    assert page.inner_text("#btn-fleet-arm").strip() == "ARM → 3"
    assert "v1, v2, v3" in page.get_attribute("#btn-fleet-arm", "title")


def test_selecting_two_of_four_says_two_before_the_button_is_pressed(fleet_page):
    """The exact scenario the rule was written for."""
    page = fleet_page
    state = fleet_state()
    state["vehicles"].append(
        {"id": "v4", "sysid": 4, "model": "hexapod_copter", "role": "",
         "mode": "STABILIZE", "armed": False, "alt": 0.0, "prearm_known": True,
         "prearm_ok": True, "heartbeat_age": 0.4, "link_stale": False,
         "serial0_port": 5790, "connection": "tcp:127.0.0.1:5790"})
    apply(page, state)

    page.click('input.vsel[data-vehicle="v1"]')
    page.click('input.vsel[data-vehicle="v3"]')
    page.click("#btn-target-selected")
    page.wait_for_timeout(120)

    count = page.inner_text("#target-count")
    assert "2 of 4 vehicles" in count, count
    assert "v1, v3" in count
    assert page.inner_text("#btn-fleet-arm").strip() == "ARM → 2"
    assert "v1, v3" in page.get_attribute("#btn-fleet-arm", "title")


def test_targeting_nobody_disables_the_buttons_and_says_so(fleet_page):
    """A command that would reach nobody must not look sendable."""
    page = fleet_page
    apply(page, fleet_state())
    page.click("#btn-target-selected")     # nothing ticked
    page.wait_for_timeout(120)

    assert "0 of 3" in page.inner_text("#target-count")
    assert "nothing will be commanded" in page.inner_text("#target-count")
    assert page.inner_text("#btn-fleet-arm").strip() == "ARM → none"
    assert page.is_disabled("#btn-fleet-arm")


# --------------------------------------------------------------- the grid etc
def test_the_grid_shows_one_card_per_vehicle_with_its_identity(fleet_page):
    page = fleet_page
    apply(page, fleet_state())
    cards = page.query_selector_all(".vcard")
    assert len(cards) == 3
    first = page.inner_text('.vcard[data-vehicle="v1"]')
    for expected in ("v1", "sysid 1", "hexapod_copter", "GUIDED", "ARMED",
                     "12.0 m", "ready"):
        assert expected in first, f"{expected!r} missing from the v1 card"


def test_a_stale_link_is_marked_on_the_card(fleet_page):
    page = fleet_page
    apply(page, fleet_state())
    stale = page.query_selector('.vcard[data-vehicle="v3"]')
    assert "stale" in stale.get_attribute("class")
    assert "9.4 s ago" in stale.inner_text()
    fresh = page.query_selector('.vcard[data-vehicle="v1"]')
    assert "stale" not in fresh.get_attribute("class")


def test_the_launch_transcript_shows_the_exact_commands(fleet_page):
    page = fleet_page
    apply(page, fleet_state())
    page.click('.tab[data-stream="launch"]')
    page.wait_for_timeout(120)
    text = page.inner_text("#term-launch")
    assert "arducopter --model JSON -I0 --serial0 tcp:0" in text
    assert "fleet.sdf" in text


def test_there_are_three_terminals_not_one_per_vehicle(fleet_page):
    """The design decision: one transcript, one attach console, one shell."""
    page = fleet_page
    apply(page, fleet_state())
    tabs = page.eval_on_selector_all(
        ".tab[data-stream]", "els => els.map(e => e.dataset.stream)")
    assert sorted(tabs) == ["launch", "shell", "sim"], tabs
    assert len(page.query_selector_all(".vattach")) == 3, (
        "each vehicle should offer the single console, not own one")


def test_the_page_has_no_console_errors(fleet_page):
    page = fleet_page
    apply(page, fleet_state())
    assert_no_console_errors(page, "on the fleet page")


# ------------------------------------------------------------ language switch
# The Fleet page builds most of its text at render time rather than putting it
# in the HTML, so `data-i18n` alone cannot reach it. It was shipped English-only
# by mistake: switching to TR left the grid, the ACK matrix and the measurement
# panels in English. These pin both halves — the static swap and the re-render.

def test_the_fleet_tab_switches_to_turkish(fleet_page):
    page = fleet_page
    apply(page, fleet_state())

    page.click('[data-set-lang="tr"]')
    page.wait_for_timeout(300)

    # static, via data-i18n
    assert page.inner_text("#tab-fleet") == "FİLO"
    assert page.inner_text("#btn-fleet-start").strip() == "▶ FİLOYU BAŞLAT"
    # `inner_text` returns RENDERED text, and the panel headings carry
    # `text-transform: uppercase`, so compare case-insensitively.
    assert "araçlar" in page.inner_text("#page-fleet").lower()

    # dynamic, via the re-render hook — this is the half that was broken
    grid = page.inner_text('.vcard[data-vehicle="v1"]')
    assert "mod" in grid and "irtifa" in grid, grid
    assert "hazır" in grid
    assert "pre-arm" not in grid and "alt" not in grid.split("\n")

    target = page.inner_text("#target-count")
    assert "3 araçtan 3 tanesi" in target, target
    assert "vehicles" not in target


def test_turkish_reaches_the_ack_matrix_and_the_panels(fleet_page):
    page = fleet_page
    apply(page, fleet_state(
        last_command={
            "command": "MODE LOITER", "policy": "parallel_ack",
            "verdict": "PARTIAL", "seconds": 1.9, "target": ["v1", "v2"],
            "results": [
                {"vehicle": "v1", "outcome": "ACCEPTED", "ack": "ACCEPTED",
                 "reason": "mode -> LOITER", "t_ms": 40, "confirmed": True,
                 "observed": "held"},
                {"vehicle": "v2", "outcome": "REVERTED", "ack": "ACCEPTED",
                 "reason": "did not hold", "t_ms": 37, "confirmed": False,
                 "observed": "did not hold"}]},
        separation={"measured": False, "reason": "saatler ortak değil",
                    "minimum_m": None, "current_m": None, "series": []}))

    page.click('[data-set-lang="tr"]')
    page.wait_for_timeout(300)

    header = page.inner_text("#ack-matrix")
    assert "araç" in header and "sonuç" in header, header

    # The OUTCOME vocabulary stays English on purpose: it is what fleet.json,
    # timeline.jsonl and fleet_report.md all record, and a row that disagrees
    # with the artefact it came from is harder to trace, not easier to read.
    assert "REVERTED" in header
    assert "ACCEPTED" in header

    assert "ÖLÇÜLMEDİ" in page.inner_text("#sep-panel")
    assert "NOT MEASURED" not in page.inner_text("#sep-panel")


def test_switching_back_to_english_restores_it(fleet_page):
    page = fleet_page
    apply(page, fleet_state())
    page.click('[data-set-lang="tr"]')
    page.wait_for_timeout(250)
    page.click('[data-set-lang="en"]')
    page.wait_for_timeout(250)

    assert page.inner_text("#tab-fleet") == "FLEET"
    assert "3 of 3 vehicles" in page.inner_text("#target-count")
    assert page.inner_text("#btn-fleet-arm").strip() == "ARM → 3"


def test_no_fleet_string_is_missing_from_either_language(fleet_page):
    """A key present in one dictionary and absent from the other renders as
    the key itself — visible, but only if somebody happens to look."""
    page = fleet_page
    missing = page.evaluate("""() => {
        const t = window.__t;
        if (!t) return ["__t was never exposed"];
        const bad = [];
        // Every key the fleet page uses, taken from the English dictionary.
        for (const k of window.__fleetKeys || []) {
            for (const lang of ["en", "tr"]) {
                localStorage.setItem("argazui.lang", lang);
            }
        }
        return bad;
    }""")
    assert missing == []
    # The real check is done in Python against the source, which cannot be
    # fooled by whichever language happens to be active.
    from pathlib import Path
    source = (Path(__file__).resolve().parents[2]
              / "argazui" / "static" / "app.js").read_text(encoding="utf-8")
    import re
    en_block = source.split("    tr: {")[0]
    tr_block = source.split("    tr: {")[1].split("\n  };")[0]
    keys = lambda s: set(re.findall(r"\b(fleet_[a-z_]+|nav_single|nav_fleet):", s))
    en, tr = keys(en_block), keys(tr_block)
    assert en - tr == set(), f"missing from tr: {sorted(en - tr)}"
    assert tr - en == set(), f"missing from en: {sorted(tr - en)}"

    used = set(re.findall(r'T\("(fleet_[a-z_]+)"', source))
    assert used - en == set(), f"used but never defined: {sorted(used - en)}"


def test_the_help_sheet_covers_the_fleet_in_both_languages(fleet_page):
    """The panel is the first thing a new user reads; it must describe v1.3.

    Both language blocks are checked, because the help sheet keeps its two
    languages as separate blocks of markup rather than as translated keys —
    so one can be updated and the other silently left behind.

    `text_content()` and not `inner_text()`: the latter returns RENDERED text,
    which applies `text-transform: uppercase` to headings. Lower-casing that
    back is not safe for Turkish — `"FİLO".lower()` is `"fi\u0307lo"`, an `i`
    plus a combining dot, which matches nothing. Reading the markup avoids
    both problems and is what this test is actually about.
    """
    page = fleet_page
    page.click('[data-sheet="sheet-help"]')
    page.wait_for_selector("#sheet-help:not([hidden])")

    en = page.text_content('#sheet-help [data-lang-block="en"]')
    for expected in ("FLEET", "REVERTED", "NOT MEASURED is not a pass",
                     "FLEET LAUNCH", "argazui fleet validate",
                     "attach console"):
        assert expected in en, f"the English help never mentions {expected!r}"
    assert "two terminal tabs" not in en, "the help still claims there are two"

    tr = page.text_content('#sheet-help [data-lang-block="tr"]')
    for expected in ("FİLO", "REVERTED", "ÖLÇÜLMEDİ", "FİLO BAŞLATMA",
                     "argazui fleet validate", "konsola bağlan"):
        assert expected in tr, f"the Turkish help never mentions {expected!r}"
    assert "iki sekmesi" not in tr, "the Turkish help still claims there are two"

    # One block updated and the other forgotten is the failure this guards.
    assert abs(len(en) - len(tr)) < len(en) * 0.35, (
        f"the language blocks have drifted apart: en={len(en)} chars, "
        f"tr={len(tr)}")
