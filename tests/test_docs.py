"""The documentation index: extraction, headings and the language rule.

WHY THE EXTRACTION GETS TESTED
------------------------------
Several portal pages are one named section of `README.md` or `USAGE.md`.
Renaming a heading in those files is an ordinary edit that nothing else in this
project would notice, and the portal would answer with an empty page. The
browser test catches that against the real files; these catch the parser
itself, including the two cases that make a naive implementation wrong — a
heading inside a fenced code block, and a section that runs to the end of the
file.

Needs no vehicle and no browser; the `tier1` marker only says which CI job
runs it.
"""
from __future__ import annotations

import pytest

from argazui import docs

pytestmark = pytest.mark.tier1

SAMPLE = """\
# Title

intro

## Wanted

first paragraph

### Nested

still inside Wanted

```bash
# not a heading, it is a shell comment
echo hi
```

## After

outside
"""


# ------------------------------------------------------------------ headings
def test_headings_ignore_shell_comments_inside_code_fences():
    """`README.md` and `SCHEMA.md` are full of `# ...` inside bash blocks.

    Without the fence check the navigation tree fills up with fragments of
    commands, which is both wrong and unusable.
    """
    found = [h["text"] for h in docs.headings(SAMPLE)]
    assert found == ["Title", "Wanted", "Nested", "After"]


def test_heading_levels_are_reported():
    assert [h["level"] for h in docs.headings(SAMPLE)] == [1, 2, 3, 2]


# ---------------------------------------------------------------- extraction
def test_a_section_stops_at_the_next_heading_of_the_same_depth():
    section = docs.extract_section(SAMPLE, "Wanted")
    assert section.startswith("## Wanted")
    assert "still inside Wanted" in section
    assert "### Nested" in section, "a subsection was dropped"
    assert "## After" not in section
    assert "outside" not in section


def test_a_section_that_runs_to_the_end_of_the_file_is_complete():
    section = docs.extract_section(SAMPLE, "After")
    assert section.strip().endswith("outside")


def test_a_heading_only_present_inside_a_code_fence_is_not_a_section():
    assert docs.extract_section(SAMPLE, "not a heading, it is a shell comment") == ""


def test_a_renamed_section_produces_an_error_rather_than_an_empty_page():
    """Silence is the failure mode this whole module is written against."""
    assert docs.extract_section(SAMPLE, "Gone") == ""


# --------------------------------------------------------------------- pages
def test_every_declared_page_resolves_in_both_languages():
    for lang in ("en", "tr"):
        for page in docs.PAGES:
            document = docs.read(page.id, lang)
            assert document["ok"], f"{page.id} ({lang}): {document.get('error')}"
            assert document["markdown"].strip(), f"{page.id} ({lang}) is empty"


def test_a_page_names_the_file_it_came_from():
    document = docs.read("procedure-schema", "en")
    assert document["source"] == "argazui/procedures/SCHEMA.md"
    assert document["section"] == ""


def test_an_extracted_page_names_its_section_too():
    document = docs.read("architecture", "en")
    assert document["source"] == "README.md"
    assert document["section"] == "Architecture"


def test_an_unknown_page_is_refused_rather_than_guessed():
    assert docs.read("../../etc/passwd")["ok"] is False
    assert docs.read("nope")["ok"] is False


def test_html_comments_are_stripped_before_the_page_is_served():
    """They carry generator instructions and editing notes, not content."""
    assert "STATUS-SUMMARY" not in docs.read("quick-start", "en")["markdown"]


# ----------------------------------------------------------------- languages
def test_a_page_with_a_turkish_source_is_served_in_turkish():
    document = docs.read("metrics", "tr")
    assert document["translated"] is True
    assert document["source"] == "docs/metrics.tr.md"
    assert "Metrikler" in document["markdown"]


def test_a_page_without_one_falls_back_and_says_that_it_did():
    """An English page in Turkish mode must be stated, never slipped through."""
    document = docs.read("architecture", "tr")
    assert document["translated"] is False
    assert document["source_language"] == "en"
    assert document["title"] == "Mimari", "the navigation title is still Turkish"


def test_troubleshooting_uses_a_different_document_per_language():
    """Its Turkish text is the repository's own Turkish guide, not a translation."""
    assert docs.read("troubleshooting", "en")["source"] == "argazui/USAGE.md"
    turkish = docs.read("troubleshooting", "tr")
    assert turkish["source"] == "TROUBLESHOOTING.md"
    assert turkish["translated"] is True


def test_every_page_and_group_is_named_in_both_languages():
    for group in docs.GROUPS:
        assert set(group.title) >= {"en", "tr"}, group.id
    for page in docs.PAGES:
        assert set(page.title) >= {"en", "tr"}, page.id
        assert set(page.summary) >= {"en", "tr"}, page.id


# ------------------------------------------------------------------ the index
def test_the_index_groups_every_page_and_carries_its_headings():
    index = docs.index("en")
    ids = [page["id"] for group in index["groups"] for page in group["pages"]]
    assert sorted(ids) == sorted(page.id for page in docs.PAGES)
    metrics = next(p for g in index["groups"] for p in g["pages"] if p["id"] == "metrics")
    assert metrics["headings"], "the search box would have nothing to match"
    assert all(1 < h["level"] <= 3 for h in metrics["headings"])


def test_the_landing_page_states_where_every_page_comes_from():
    """It is the only page this module writes, so it may not state a fact.

    Naming each source is what keeps it a table of contents rather than a
    second copy of the documentation.
    """
    landing = docs.read("index", "en")
    assert landing["generated"] is True
    for page in docs.PAGES:
        if page.generated:
            continue
        assert f"#docs={page.id}" in landing["markdown"], page.id
    assert "README.md" in landing["markdown"]
    assert "argazui/procedures/SCHEMA.md" in landing["markdown"]
