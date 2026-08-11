"""Both languages are release artefacts, so both are a test.

WHY THIS IS CHECKED BY A MACHINE
--------------------------------
The interface falls back to English for a key Turkish does not have. That is
the right runtime behaviour — a missing string must not blank a button — and it
is exactly why a missing string is invisible until somebody switches language
and reads carefully. Every release since v1.1 has shipped Turkish as a
first-class artefact; this is what keeps that true without anyone remembering
to look.

It checks parity and wiring, not quality. No test can tell a good translation
from a literal one — that part is a human reading the text as an engineer.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from argazui import docs
from argazui.i18n import CATALOG, DEFAULT_LANG, LANGUAGES

pytestmark = pytest.mark.tier1

ROOT = Path(__file__).resolve().parent.parent
APP_JS = ROOT / "argazui" / "static" / "app.js"
INDEX_HTML = ROOT / "argazui" / "static" / "index.html"

# Keys sit at the start of a line or after a comma, always followed by a
# string. The trailing quote is what keeps `{field}: {reason}` inside a message
# from being read as a key.
_KEY = re.compile(r'(?:^|,)\s*([a-z][a-z0-9_]*)\s*:\s*"', re.MULTILINE)


def _block(source: str, lang: str) -> str:
    """The `en: { ... }` or `tr: { ... }` object literal, by brace matching."""
    start = source.index(f"\n    {lang}: {{")
    depth, index = 0, source.index("{", start)
    for position in range(index, len(source)):
        if source[position] == "{":
            depth += 1
        elif source[position] == "}":
            depth -= 1
            if depth == 0:
                return source[index:position + 1]
    raise AssertionError(f"the {lang} catalogue in app.js is not brace-balanced")


def interface_catalogue() -> dict[str, set]:
    source = APP_JS.read_text(encoding="utf-8")
    return {lang: set(_KEY.findall(_block(source, lang))) for lang in LANGUAGES}


# ------------------------------------------------------------------- backend
def test_every_backend_message_exists_in_every_language():
    missing = {lang: sorted(key for key, entry in CATALOG.items()
                            if not entry.get(lang))
               for lang in LANGUAGES}
    assert not any(missing.values()), missing


def test_no_backend_message_is_the_english_text_pasted_into_turkish():
    """A Turkish entry identical to the English one is a forgotten translation.

    Exceptions are listed by name rather than by a rule, so adding one is a
    decision somebody makes on purpose.
    """
    identical = [key for key, entry in CATALOG.items()
                 if entry.get("tr") and entry["tr"] == entry.get("en")]
    allowed = {
        # Command syntax and MAVLink identifiers are not language.
        "proc_step", "param_ok", "rc_ok", "mode_ok", "signal_sent",
    }
    assert set(identical) <= allowed, sorted(set(identical) - allowed)


# ----------------------------------------------------------------- interface
def test_the_interface_catalogue_has_the_same_keys_in_both_languages():
    catalogue = interface_catalogue()
    english, turkish = catalogue["en"], catalogue["tr"]
    assert english, "the English catalogue could not be read out of app.js"
    assert not english - turkish, f"missing from Turkish: {sorted(english - turkish)}"
    assert not turkish - english, f"only in Turkish: {sorted(turkish - english)}"


def test_every_data_i18n_attribute_has_a_string_behind_it():
    """A `data-i18n` with no entry renders as its own key name."""
    used = set(re.findall(r'data-i18n="([^"]+)"', INDEX_HTML.read_text(encoding="utf-8")))
    catalogue = interface_catalogue()
    assert used, "no data-i18n attributes were found; the parser is wrong"
    for lang in LANGUAGES:
        assert not used - catalogue[lang], (
            f"index.html asks for strings {lang} does not have: "
            f"{sorted(used - catalogue[lang])}")


def test_the_v13_surfaces_are_translated():
    """Named explicitly, so a later edit that drops one is a failure here.

    These are the strings v1.3 added to the interface: the documentation portal
    and the regression comparison.
    """
    catalogue = interface_catalogue()
    expected = {
        "nav_docs", "nav_docs_title", "docs_search", "docs_search_hint",
        "docs_untranslated", "docs_source", "docs_source_section",
        "docs_source_generated", "runs_compare", "cmp_passed", "cmp_regressed",
        "cmp_incomparable", "cmp_verdict", "cmp_v_degraded", "cmp_note",
    }
    for lang in LANGUAGES:
        assert expected <= catalogue[lang], (
            f"{lang} is missing {sorted(expected - catalogue[lang])}")


def test_the_v16_surfaces_are_translated():
    """The strings v1.6 added: the experiments panel and its document.

    Named explicitly for the same reason the v1.3 set is. The ones that matter
    most are the last four — a document that stated its limitations in English
    to a Turkish reader would be stating them to nobody.
    """
    catalogue = interface_catalogue()
    expected = {
        "exp_title", "exp_hint", "exp_start", "exp_cancel", "exp_idle",
        "exp_running", "exp_none", "exp_no_runs", "exp_never_flown",
        "exp_question", "exp_criteria", "exp_delta", "exp_overlap",
        "exp_basis", "exp_v_passed", "exp_v_failed", "exp_v_incomplete",
        "exp_v_not_judged", "exp_v_not_run",
        "exp_no_stats", "exp_limits", "exp_limits_none", "exp_verification",
    }
    for lang in LANGUAGES:
        assert expected <= catalogue[lang], (
            f"{lang} is missing {sorted(expected - catalogue[lang])}")


def test_the_v16_corrective_surfaces_are_translated():
    """The strings the corrective release added to the interface.

    `proc_unevaluable` names the third criterion outcome — not a pass and not a
    failure, but nothing measured. A Turkish reader shown that mark with an
    English explanation would be told the one thing this release exists to make
    unmissable, in a language they did not pick.
    """
    catalogue = interface_catalogue()
    for lang in LANGUAGES:
        assert "proc_unevaluable" in catalogue[lang], (
            f"{lang} has no string for the unevaluated criterion state")


def test_the_evidence_and_abort_messages_exist_in_both_languages():
    """Backend strings the corrective release added, named explicitly.

    Both are read by an operator at the moment something has gone wrong, which
    is exactly when falling back to English is least acceptable.
    """
    for key in ("cond_no_evidence", "proc_no_vehicle_ready"):
        for lang in LANGUAGES:
            assert CATALOG.get(key, {}).get(lang), f"{key} has no {lang} text"


def test_every_failure_category_explains_itself_in_both_languages():
    """The taxonomy is a user-visible string, and it changed in this release."""
    from argazui import failures

    for category in failures.CATEGORIES:
        entry = failures.CATALOGUE[category]
        for lang in LANGUAGES:
            for part in ("label", "what", "look_at"):
                assert entry[part].get(lang), f"{category}.{part} has no {lang}"


def test_the_experiment_verdicts_all_have_a_string_behind_them():
    """The panel builds a key from the verdict word, so a new one goes silent.

    `exp_v_` + the verdict with hyphens replaced. A verdict added to
    `analysis.py` and not here would render as its own key name.
    """
    from argazui import analysis

    catalogue = interface_catalogue()
    for verdict in analysis.VERDICTS:
        key = "exp_v_" + verdict.replace("-", "_")
        for lang in LANGUAGES:
            assert key in catalogue[lang], (
                f"the verdict '{verdict}' has no {lang} string ({key})")


def test_every_limitation_category_is_named_in_both_languages():
    """A limitation shown in English to a Turkish reader is shown to nobody."""
    from argazui import limitations

    for category in limitations.CATEGORIES:
        for lang in LANGUAGES:
            assert limitations.LABELS[category].get(lang), \
                f"{category} has no {lang} label"
            assert limitations.WHAT[category].get(lang), \
                f"{category} does not say what belongs in it, in {lang}"
        for text in limitations.STANDING[category]:
            for lang in LANGUAGES:
                assert text.get(lang), \
                    f"a standing limitation in {category} has no {lang} text"


# ---------------------------------------------------------------------- docs
def test_every_documentation_page_is_named_in_both_languages():
    for group in docs.GROUPS:
        for lang in LANGUAGES:
            assert group.title.get(lang), f"group {group.id} has no {lang} title"
    for page in docs.PAGES:
        for lang in LANGUAGES:
            assert page.title.get(lang), f"page {page.id} has no {lang} title"
            assert page.summary.get(lang), f"page {page.id} has no {lang} summary"


def test_the_documents_v13_added_exist_in_turkish():
    """Every subject this release introduced has a Turkish source.

    The pages that are sections of README.md or USAGE.md deliberately do not —
    the portal states that instead of hiding it — but a document written for
    v1.3 having no Turkish twin would just be an omission.
    """
    for page in docs.PAGES:
        english = page.source.get("en", "")
        if not english.startswith("docs/"):
            continue
        assert page.source.get("tr"), f"{page.id} has no Turkish source"
        turkish = docs.paths.ARGAZ / page.source["tr"]
        assert turkish.is_file(), f"{turkish} is declared but missing"
        assert len(turkish.read_text(encoding="utf-8")) > 500, (
            f"{turkish} is too short to be a translation of {english}")


def test_a_page_without_a_turkish_source_is_flagged_rather_than_silently_english():
    document = docs.read("changelog", "tr")
    assert document["ok"] and document["translated"] is False
    assert document["source_language"] == DEFAULT_LANG
