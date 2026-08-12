"""The v1.6 experiments panel in a real browser, and the endpoints behind it.

WHY THIS IS AN e2e TEST
-----------------------
The panel renders a list the server sends and is reachable before a vehicle
exists — the exact combination that has broken this page before, when a panel
read `.length` off something the API had not sent and the page went dead with
one console line as the only symptom. Every assertion here ends by reading the
browser console.

It also covers the half of the release no Python test can: that the strings the
panel shows exist in **both** languages and change when the language does.
`test_localisation.py` proves the keys are present; only a browser can prove
they are wired to elements.
"""
from __future__ import annotations

import urllib.error

import pytest

from harness import assert_no_console_errors, open_page, open_section

pytestmark = [pytest.mark.e2e, pytest.mark.tier1]


# ------------------------------------------------------------------- panel
def test_the_panel_lists_what_is_declared_before_anything_has_been_flown(
        browser_page, server):
    """A declared experiment nobody has run is the entry that matters most.

    It is a question this project asked and never answered, and it is invisible
    in a listing that only shows results — so the panel shows both, and says
    "declared, never flown" out loud rather than leaving an empty cell.
    """
    page = open_section(open_page(browser_page, server), "experiments")
    panel = page.locator("#exp-panel")
    assert panel.is_visible()

    table = page.locator("#exp-table").inner_text()
    assert "copter_gps_loss_vs_nominal" in table
    assert "declared, never flown" in table

    assert "No experiment is running" in page.locator("#exp-active").inner_text()
    # Nothing is running, so there is nothing to cancel.
    assert page.locator("#btn-exp-cancel").is_hidden()
    # An experiment names its own model, so unlike a campaign it does not need
    # one started first.
    assert page.locator("#btn-exp-start").is_enabled()
    assert_no_console_errors(page, "with the experiment panel idle")


def test_the_panel_switches_language(browser_page, server):
    """Turkish is a release artefact, and a key nothing renders is not wired."""
    page = open_section(open_page(browser_page, server), "experiments")
    page.click('[data-set-lang="tr"]')
    page.wait_for_timeout(600)

    def text(selector: str) -> str:
        return page.locator(selector).inner_text().lower()

    assert "deneyler" in text("#exp-panel h2")
    assert "çalışan deney yok" in text("#exp-active")
    assert "beyan edildi, hiç uçurulmadı" in text("#exp-table")
    # The hint is what tells a reader what an experiment even is.
    assert "kontrollü karşılaştırma" in text('[data-i18n="exp_hint"]')

    page.click('[data-set-lang="en"]')
    page.wait_for_timeout(600)
    assert "experiments" in text("#exp-panel h2")
    assert "no experiment is running" in text("#exp-active")
    assert_no_console_errors(page, "after switching language twice")


# ---------------------------------------------------------------- endpoints
def test_the_experiments_endpoint_serves_declarations_and_runs(server):
    listing = server.api("/api/experiments")
    assert listing["experiments_error"] == "", listing["experiments_error"]
    declared = {item["id"] for item in listing["experiments"]}
    assert "copter_gps_loss_vs_nominal" in declared
    assert listing["runs"] == [], "nothing has been flown in this sandbox"
    assert listing["active"]["running"] is False

    for item in listing["experiments"]:
        assert item["question"], f"{item['id']} states no question"
        assert item["model_id"] and item["arms"] and item["metrics"]
        assert item["compare"]["policy"] in listing["policies"]
        assert item["total_runs"] == sum(arm["runs"] for arm in item["arms"])


def test_an_experiment_that_has_never_been_flown_is_a_404(server):
    """Unlike "this run has no baseline", which is an ordinary outcome and 200.

    An id nothing carries is genuinely not found, and answering 200 with an
    empty document would be a document pretending to be an experiment.
    """
    with pytest.raises(urllib.error.HTTPError) as exc:
        server.api("/api/experiments/20260101T000000Z_nothing.here")
    assert exc.value.code == 404

    with pytest.raises(urllib.error.HTTPError) as exc:
        server.api("/api/experiments/copter_gps_loss_vs_nominal")
    assert exc.value.code == 404


def test_an_unknown_experiment_cannot_be_started(server):
    res = server.post("/api/experiment", {"experiment_id": "not_an_experiment"})
    assert res["ok"] is False
    assert "not_an_experiment" in res["text"]


def test_an_experiment_naming_a_model_that_is_not_registered_is_refused(server,
                                                                        tmp_path):
    """The check that cannot be done at load time, done where it can.

    A definition stays readable on a checkout whose registry has not been
    scanned; what may not happen is flying it against an aircraft that is not
    there.
    """
    (server.tree / "experiments" / "no_such_model.yaml").write_text(
        """
schema: 1
id: no_such_model
question: {en: "Does a missing model fail loudly?", tr: "Eksik model gurultuyle mi hata verir?"}
model: definitely_not_in_the_registry
values: {alt: 10}
arms:
  - {id: only, procedure: copter_takeoff, runs: 1}
metrics: [time_to_target_alt]
compare: {policy: repeats}
""", encoding="utf-8")
    res = server.post("/api/experiment", {"experiment_id": "no_such_model"})
    assert res["ok"] is False
    assert "definitely_not_in_the_registry" in res["text"]


def test_cancelling_when_nothing_runs_says_so_rather_than_failing(server):
    res = server.post("/api/experiment/cancel")
    assert res["ok"] is False
    assert "no experiment" in res["text"].lower()


def test_the_limitation_catalogue_is_served_and_follows_the_language(server):
    """The interface must never show a limitation the module does not have.

    Served from `limitations.py` for the same reason the fault and metric
    catalogues are served from their modules: a copy in the front end drifts,
    and what it would be wrong about is where a result's claims stop.
    """
    server.post("/api/lang", {"lang": "en"})
    catalogue = server.api("/api/limitations")
    categories = {entry["category"] for entry in catalogue["categories"]}
    assert categories == {"assumptions", "model_limitations",
                          "unverified_effects", "out_of_scope"}
    for entry in catalogue["categories"]:
        assert entry["label"] and entry["what"]
        assert entry["standing"], (
            f"{entry['category']} has no standing statement, so a definition "
            f"that declares nothing would say nothing about it")

    server.post("/api/lang", {"lang": "tr"})
    try:
        turkish = server.api("/api/limitations")
        english = {e["category"]: e for e in catalogue["categories"]}
        for entry in turkish["categories"]:
            other = english[entry["category"]]
            assert entry["what"] != other["what"], (
                f"{entry['category']} shows its English text in Turkish mode")
            assert entry["standing"] != other["standing"], (
                f"{entry['category']}'s standing statements are untranslated")
    finally:
        server.post("/api/lang", {"lang": "en"})


def test_the_status_endpoint_reports_the_experiment_state(server):
    status = server.api("/api/status")
    assert status["experiment"]["running"] is False
    assert status["experiment"]["last"] is None
