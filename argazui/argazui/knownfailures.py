"""Exact matching for documented tier-2 model limitations.

A known limitation is not a pass and is not hidden from run artefacts or the
status table. This module answers one narrower question: is the failure we just
observed the same failure the model registry explicitly documents? CI may treat
that exact case as an expected failure; any drift in category, code, procedure
or distinguishing detail remains a new failure.
"""
from __future__ import annotations


def matches(model: dict, failure: dict | None) -> bool:
    expected = model.get("expected_failure")
    if not expected or not failure:
        return False

    for key in ("category", "code", "procedure"):
        wanted = expected.get(key)
        if wanted is not None and failure.get(key, "") != wanted:
            return False

    contains = expected.get("detail_contains")
    if contains and contains not in (failure.get("detail") or ""):
        return False

    return True
