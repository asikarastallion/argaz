"""The documentation portal, through a real browser.

WHAT THIS LAYER IS FOR HERE
---------------------------
The portal renders markdown that lives in the repository, in a renderer written
for this page. Two things can go wrong that no backend test can see: the
renderer throwing on a document somebody edits later, and the navigation
claiming a page that does not open. Both look like a working page until you
click.

So these tests do what a reader does — open the portal, walk the tree, search,
follow a deep link — and they watch the console the whole time.

WHAT THEY DELIBERATELY DO NOT CHECK
-----------------------------------
Whether the documentation is *correct*. No test can read prose. What they check
is that every page the tree offers actually resolves to a file, which is the
failure that would otherwise appear months later as a blank page after somebody
renamed a heading in README.md.
"""
from __future__ import annotations

import pytest

from harness import assert_no_console_errors, open_page

pytestmark = [pytest.mark.e2e, pytest.mark.tier1]


def test_every_page_the_tree_offers_actually_resolves(server):
    """A navigation entry that cannot be opened is worse than a missing one.

    Pages are extracted from named sections of `README.md` and `USAGE.md`.
    Renaming one of those headings is an ordinary edit that nothing else in
    this project would notice, and the portal would answer with an empty page.
    """
    index = server.api("/api/docs")
    pages = [page for group in index["groups"] for page in group["pages"]]
    assert len(pages) >= 20, "the portal lost most of its pages"

    broken = [(p["id"], p["error"]) for p in pages if not p["available"]]
    assert not broken, f"pages whose source no longer resolves: {broken}"

    for page in pages:
        document = server.api(f"/api/docs/{page['id']}")
        assert document["markdown"].strip(), f"{page['id']} rendered empty"
        assert document["ok"] is True


def test_the_portal_opens_navigates_and_keeps_the_console_clean(server, browser_page):
    page = open_page(browser_page, server)
    page.click("#btn-docs")
    page.wait_for_selector("#docs-tree .docs-link")

    links = page.query_selector_all("#docs-tree .docs-link")
    assert len(links) >= 20, f"only {len(links)} pages in the tree"

    # The landing page names its own generator rather than pretending to be a
    # document somebody wrote.
    assert "docs.py" in page.inner_text("#docs-source")

    # Walk to a page with tables, code blocks and links in it. The selector is
    # scoped to the tree on purpose: the landing page links to the same titles,
    # and a bare text match would test that link rather than the navigation.
    page.click(".docs-link:has-text('Acceptance Criteria')")
    page.wait_for_selector("#docs-content h1")
    content = page.inner_text("#docs-content")
    assert "within" in content and "never" in content
    assert page.query_selector("#docs-content table"), "no table was rendered"
    assert page.query_selector("#docs-content pre code"), "no code block was rendered"
    assert "docs/acceptance-criteria.md" in page.inner_text("#docs-source")

    assert_no_console_errors(page, "after opening the documentation portal")


def test_markdown_is_escaped_rather_than_executed(server, browser_page):
    """Documents are files anyone with a checkout can edit.

    The renderer escapes before it transforms, so raw HTML in a document is
    text. This asserts the property on the one page that certainly contains
    angle brackets — the schema reference is full of them.
    """
    page = open_page(browser_page, server)
    page.goto(f"{server.url}/#docs=procedure-schema", wait_until="networkidle")
    page.wait_for_selector("#docs-content h1")

    # Nothing from a document may become a script or an iframe.
    assert not page.query_selector("#docs-content script")
    assert not page.query_selector("#docs-content iframe")
    assert_no_console_errors(page, "on the procedure schema page")


def test_search_matches_headings_not_only_page_titles(server, browser_page):
    page = open_page(browser_page, server)
    page.click("#btn-docs")
    page.wait_for_selector("#docs-tree .docs-link")

    page.fill("#docs-search", "threshold")
    page.wait_for_timeout(200)
    assert page.query_selector_all("#docs-tree .docs-heading"), (
        "searching matched pages but no headings inside them")

    page.fill("#docs-search", "zzzznotathing")
    page.wait_for_timeout(200)
    assert not page.query_selector_all("#docs-tree .docs-link")
    assert "zzzznotathing" in page.inner_text("#docs-searchhint")

    assert_no_console_errors(page, "while searching the documentation")


def test_a_deep_link_opens_the_page_and_scrolls_to_the_heading(server, browser_page):
    """The whole point of the portal over twenty browser tabs."""
    page = open_page(browser_page, server)
    page.goto(f"{server.url}/#docs=regression/exit-codes", wait_until="networkidle")
    page.wait_for_selector("#docs-content h1")

    assert not page.is_hidden("#sheet-docs")
    assert page.query_selector("#docs-content #exit-codes"), (
        "the heading the link names is not in the rendered page")
    assert page.evaluate("document.getElementById('docs-page').scrollTop") > 0, (
        "the page did not scroll to the linked heading")
    assert_no_console_errors(page, "after following a documentation deep link")


def test_turkish_says_when_a_page_has_no_turkish_source(server, browser_page):
    """An English page in Turkish mode is stated, not slipped through.

    Forking every repository document into a second language would recreate
    the duplicate-source problem the portal exists to avoid, so the pages that
    have no Turkish source show the canonical English text — and say so, in
    Turkish, above it.
    """
    page = open_page(browser_page, server)
    page.click("[data-set-lang='tr']")
    page.wait_for_timeout(400)
    page.click("#btn-docs")
    page.wait_for_selector("#docs-tree .docs-link")

    # A page that does have a Turkish source: no notice, Turkish body.
    page.click(".docs-link:has-text('Metrikler')")
    page.wait_for_selector("#docs-content h1")
    assert page.is_hidden("#docs-notice")
    assert "Metrikler" in page.inner_text("#docs-content h1")

    # A page that does not: the notice appears, in Turkish. Waited for by the
    # notice rather than by a heading level — an extracted section keeps the
    # heading depth it has in its source file, and README's is an `##`.
    page.click(".docs-link:has-text('Mimari')")
    page.wait_for_selector("#docs-notice:not([hidden])")
    assert not page.is_hidden("#docs-notice")
    notice = page.inner_text("#docs-notice")
    assert "Türkçe" in notice, notice

    assert_no_console_errors(page, "in Turkish mode")
