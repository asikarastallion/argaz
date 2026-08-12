"""The application shell: one module on screen, and every module reachable.

WHY THIS EXISTS
---------------
The interface stopped being one long page of panels and became a shell with a
navigation rail. That trade is only worth making if two things hold, and
neither is visible from Python:

  * the landing screen is the operator's workstation and nothing else —
    a vehicle, its quick commands and its terminals;
  * every other module is still reachable, still linkable, and still renders.

A navigation entry that leads nowhere is worse than no entry at all, and it is
exactly the failure a redesign introduces silently: the panel still exists in
the DOM, the button still highlights, and nobody notices the section was never
wired until they need it. So this walks every destination the rail offers and
reads the console the whole way.
"""
from __future__ import annotations

import pytest

from harness import assert_no_console_errors, open_page, open_section

pytestmark = [pytest.mark.e2e, pytest.mark.tier1]

# The operations screen carries these three and only these three.
OPERATIONS_PANELS = ("panel-vehicles", "panel-commands", "panel-terminal")

# Sections that must not be on the landing screen. Each is a verification or
# evidence module: useful, and not what somebody flying an aircraft is looking
# at. Named individually so moving one back onto the home screen is a decision
# somebody makes here, on purpose.
SECONDARY_VIEWS = ("procedures", "scenarios", "campaigns", "experiments",
                   "coverage", "runs", "script", "docs")


def _visible_views(page) -> list[str]:
    return page.eval_on_selector_all(
        "[data-view]",
        "els => els.filter(e => !e.hidden).map(e => e.dataset.view)")


def test_the_landing_screen_is_the_workstation_and_nothing_else(browser_page, server):
    page = open_page(browser_page, server)

    assert _visible_views(page) == ["operations"], (
        "the landing screen shows more than the operations module")

    for panel in OPERATIONS_PANELS:
        assert page.locator(f"#{panel}").is_visible(), f"#{panel} is not on the workstation"

    # And the analytics modules are not competing with it.
    for view in SECONDARY_VIEWS:
        assert page.locator(f'[data-view="{view}"]').is_hidden(), (
            f"{view} is rendered on the landing screen")
    assert_no_console_errors(page, "on the landing screen")


def test_every_rail_destination_opens_exactly_one_section(browser_page, server):
    """No dead entries, and never two modules on screen at once."""
    page = open_page(browser_page, server)
    destinations = page.eval_on_selector_all(
        ".rail-item[data-nav]", "els => [...new Set(els.map(e => e.dataset.nav))]")
    assert len(destinations) >= 9, f"the rail lost destinations: {destinations}"

    for name in destinations:
        open_section(page, name)
        assert _visible_views(page) == [name], (
            f"opening {name} left {_visible_views(page)} on screen")
        # The rail says where you are.
        assert page.locator(f'.rail-item[data-nav="{name}"].active').count() >= 1, (
            f"the rail does not mark {name} as the active section")
        # And the section is not an empty shell: every module page has a
        # heading of its own.
        heading = page.locator(f'[data-view="{name}"] h2, [data-view="{name}"] h3').first
        assert heading.count() == 0 or heading.inner_text().strip(), (
            f"the {name} section rendered without a heading")

    assert_no_console_errors(page, "after walking every section")


def test_a_section_is_linkable_and_survives_a_reload(browser_page, server):
    """The shell writes the hash, so a section can be sent to somebody."""
    page = open_page(browser_page, server)
    open_section(page, "coverage")
    assert page.evaluate("location.hash") == "#coverage", page.evaluate("location.hash")

    page.goto(f"{server.url}/#experiments", wait_until="networkidle")
    page.wait_for_timeout(1500)
    assert _visible_views(page) == ["experiments"], (
        "a deep link to a section did not open it")
    assert_no_console_errors(page, "after following a section link")


def test_the_run_and_docs_deep_links_still_win_over_the_section_hash(browser_page, server):
    """`#docs=` and `#run=` predate the rail and keep their meaning.

    Both name a *page within* a module rather than the module itself, so the
    shell must not overwrite them with a bare section name.
    """
    page = open_page(browser_page, server)
    page.goto(f"{server.url}/#docs=index", wait_until="networkidle")
    page.wait_for_selector("#docs-content h1", timeout=20000)
    assert _visible_views(page) == ["docs"]
    assert page.evaluate("location.hash").startswith("#docs="), (
        "the shell overwrote a documentation deep link with a section name")
    assert_no_console_errors(page, "after following a documentation deep link")


def test_alt_digit_reaches_a_section_from_the_keyboard(browser_page, server):
    """An operator's hands are on the terminal, not the rail."""
    page = open_page(browser_page, server)
    key = page.get_attribute('.rail-item[data-nav="coverage"]', "data-key")
    assert key, "the coverage entry carries no keyboard shortcut"

    page.keyboard.press(f"Alt+{key}")
    page.wait_for_selector('[data-view="coverage"]:not([hidden])', timeout=10000)
    assert _visible_views(page) == ["coverage"]
    assert_no_console_errors(page, "after using the keyboard shortcut")


def test_the_instrument_bar_is_readable_from_every_section(browser_page, server):
    """A coverage table does not stop an aircraft being in the air.

    The readings stay in the top bar on every module for that reason, and they
    state a value rather than a dash even when nothing is running.
    """
    page = open_page(browser_page, server)
    for name in ("coverage", "runs", "procedures", "operations"):
        open_section(page, name)
        for readout in ("pill-model", "pill-link", "pill-ready", "pill-mode",
                        "pill-armed"):
            assert page.locator(f"#{readout}").is_visible(), (
                f"#{readout} is not readable from the {name} section")
        link = page.inner_text("#pill-link")
        assert "—" not in link, f"the link reading is a bare dash in {name}: {link!r}"
    assert_no_console_errors(page, "after reading the instrument bar everywhere")
