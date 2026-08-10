"""The v1.4 panels in a real browser, and the endpoints behind them.

WHY THIS IS AN e2e TEST AND NOT A UNIT ONE
------------------------------------------
Both panels render lists the server sends and both are reachable before a
vehicle exists. That combination is where this page has broken before: the v1.1
regression was a panel reading `.length` off something the API had not sent,
and the page went dead with one console line as the only symptom. Every
assertion below therefore ends by reading the browser console.

They also cover the half of a release that no Python test can: that the strings
these panels show exist in **both** languages and change when the language
does. `test_localisation.py` proves the keys are present; only a browser can
prove they are wired to the elements.
"""
from __future__ import annotations

import pytest

from harness import assert_no_console_errors, open_page

pytestmark = [pytest.mark.e2e, pytest.mark.tier1]


# ------------------------------------------------------------------- panels
def test_the_scenario_panel_explains_itself_before_a_vehicle_exists(
        browser_page, server):
    """A panel that can inject a fault has to say so with nothing running.

    "Start a vehicle to see which scenarios apply" is a state; a blank box is
    an absence of information, and this panel is the one place in the interface
    where a user can deliberately break the simulated aircraft.
    """
    page = open_page(browser_page, server)
    panel = page.locator("#scen-panel")
    assert panel.is_visible()

    # The warning is unconditional: it must not depend on a scenario having
    # been loaded, because it is what tells a reader the panel is harmless.
    warning = panel.locator('[data-i18n="scen_warn"]').inner_text()
    assert "SIMULATED" in warning
    assert "restored" in warning

    assert "Start a vehicle" in page.locator("#scen-hint").inner_text()
    assert_no_console_errors(page, "with the scenario panel idle")


def test_the_campaign_panel_lists_nothing_and_says_so(browser_page, server):
    page = open_page(browser_page, server)
    panel = page.locator("#camp-panel")
    assert panel.is_visible()

    assert "No campaign is running" in page.locator("#camp-active").inner_text()
    assert "No campaign has been recorded" in \
        page.locator("#camp-table").inner_text()
    # Nothing is running, so there is nothing to cancel.
    assert page.locator("#btn-camp-cancel").is_hidden()
    # And no model is started, so a campaign cannot be launched either.
    assert page.locator("#btn-camp-start").is_disabled()
    assert_no_console_errors(page, "with the campaign panel idle")


def test_both_new_panels_switch_language(browser_page, server):
    """Turkish is a release artefact, and a key nothing renders is not wired."""
    page = open_page(browser_page, server)
    page.click('[data-set-lang="tr"]')
    page.wait_for_timeout(600)

    # `inner_text` returns RENDERED text, and the panel headings are
    # uppercased by CSS — so these compare case-insensitively rather than
    # asserting a capitalisation the stylesheet owns.
    def text(selector: str) -> str:
        return page.locator(selector).inner_text().lower()

    assert "senaryolar" in text("#scen-panel h2")
    # Not "kampanyası": the heading is uppercased by CSS, and Turkish dotless
    # ı survives that round trip as i. The stem is what is being checked.
    assert "kampanya" in text("#camp-panel h2")
    assert "si̇müle" in text('[data-i18n="scen_warn"]')
    assert "çalışan kampanya yok" in text("#camp-active")
    # The hint this panel writes itself, rather than through data-i18n.
    assert "araç başlat" in text("#scen-hint")

    page.click('[data-set-lang="en"]')
    page.wait_for_timeout(600)
    assert "scenarios" in text("#scen-panel h2")
    assert "start a vehicle" in text("#scen-hint")
    assert_no_console_errors(page, "after switching language twice")


# ---------------------------------------------------------------- endpoints
def test_the_fault_catalogue_is_served_and_follows_the_language(server):
    """The interface must never name a fault the module does not have.

    Served from `faults.py` for the same reason the metric catalogue is served
    from `metrics.py`: a copy in the front end drifts, and the thing it would
    be wrong about is what a button does to the aircraft.
    """
    # The language is a single global server setting and this module shares one
    # server, so it is set explicitly rather than assumed — a test that
    # depended on the order it ran in would be measuring the order.
    server.post("/api/lang", {"lang": "en"})
    catalogue = server.api("/api/faults")
    kinds = {entry["kind"] for entry in catalogue["faults"]}
    assert kinds == {"gps_loss", "gps_degradation",
                     "mavlink_interrupt", "mavlink_degradation"}
    for entry in catalogue["faults"]:
        assert entry["label"] and entry["what"] and entry["observe"]
        assert entry["mechanism"] and entry["source"]
        assert entry["targets"], f"{entry['kind']} names no target"

    server.post("/api/lang", {"lang": "tr"})
    try:
        turkish = server.api("/api/faults")
        english = {e["kind"]: e for e in catalogue["faults"]}
        for entry in turkish["faults"]:
            other = english[entry["kind"]]
            assert entry["what"] != other["what"], (
                f"{entry['kind']} shows its English description in Turkish mode")
            assert entry["observe"] != other["observe"], (
                f"{entry['kind']} shows its English observable in Turkish mode")
    finally:
        server.post("/api/lang", {"lang": "en"})


def test_the_failure_taxonomy_is_served_with_somewhere_to_look(server):
    document = server.api("/api/failure-categories")
    categories = {entry["category"] for entry in document["categories"]}
    assert categories == {"environment", "vehicle_readiness", "procedure",
                          "acceptance", "evidence", "regression",
                          "infrastructure"}
    for entry in document["categories"]:
        assert entry["what"], f"{entry['category']} has no explanation"
        assert entry["look_at"], (
            f"{entry['category']} says what went wrong but not where to look, "
            f"which is the half that makes it a diagnosis")


def test_the_campaign_endpoints_answer_before_any_campaign_exists(server):
    listing = server.api("/api/campaigns")
    assert listing["campaigns"] == []
    assert listing["active"]["running"] is False
    assert listing["default_runs"] == 5

    # An id that no run carries is a 404, not a 500 and not an empty document
    # pretending to be a campaign. Unlike "this run has no baseline to compare
    # against", which is an ordinary outcome and answers 200, an unknown
    # campaign id is genuinely not found.
    import urllib.error

    with pytest.raises(urllib.error.HTTPError) as exc:
        server.api("/api/campaigns/20260101T000000Z_nothing.here")
    assert exc.value.code == 404


def test_a_campaign_of_one_run_is_refused(server):
    """One run is not a repeatability measurement, and the message says so."""
    res = server.post("/api/campaign", {"model_id": "iris",
                                        "procedure_id": "copter_takeoff",
                                        "runs": 1})
    assert res["ok"] is False
    assert "2" in res["text"]


def test_a_campaign_on_an_unregistered_model_is_refused(server):
    res = server.post("/api/campaign", {"model_id": "not_a_model",
                                        "procedure_id": "copter_takeoff",
                                        "runs": 3})
    assert res["ok"] is False
    assert "not_a_model" in res["text"]


def test_the_scenarios_a_vehicle_has_are_only_offered_once_it_is_connected(server):
    """No vehicle means no probed capabilities, so no scenario can apply.

    A scenario offered against an unknown aircraft would be a fault chosen by
    guesswork, which is the one thing the `scenario` role exists to prevent.
    """
    overview = server.api("/api/procedures")
    assert overview["capabilities"] is None
    assert overview["scenarios"] == []
    # And the auto-selected roles are still only the two that may be.
    assert set(overview["roles"]) <= {"takeoff", "land"}
