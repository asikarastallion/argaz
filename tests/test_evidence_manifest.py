"""The manifest catches an incomplete run — which is the only reason to have one.

WHAT THESE PIN DOWN
-------------------
A manifest that always says "complete" is a decoration. Each test below removes
one thing from a run directory and asserts the manifest notices, in the right
category: a missing **required** artefact is an evidence failure, a missing
**optional** one is fine *with a stated reason* and a gap without one.

That middle case is the whole design. "There are no plots because matplotlib is
not installed" and "there are no plots" are different facts, and only the first
is an answer.

Needs no vehicle; the `tier1` marker only says which CI job runs them.
"""
from __future__ import annotations

import json

import pytest

from argazui import evidence, failures

pytestmark = pytest.mark.tier1

REQUIRED_FILES = {
    "result.json": '{"run_id": "x"}\n',
    "scenario.yaml": "# procedures\n",
    "console.log": "boot\n",
    "mavlink_events.jsonl": '{"kind": "state"}\n',
    "versions.txt": "argazui = 1.5.0\n",
    "fingerprint.json": '{"schema": 1}\n',
}


def build(directory, *, armed=True, dataflash=True, report=False,
          plots=False, regression=False) -> dict:
    """A run directory with exactly the artefacts a test wants in it."""
    for name, body in REQUIRED_FILES.items():
        (directory / name).write_text(body, encoding="utf-8")
    if dataflash:
        (directory / "00000001.BIN").write_bytes(b"\xa3\x95" + b"\x00" * 64)
    if report:
        (directory / "report.json").write_text('{"schema": 3}\n', encoding="utf-8")
        (directory / "report.md").write_text("# report\n", encoding="utf-8")
        (directory / "params_full.txt").write_text("A,1\n", encoding="utf-8")
        (directory / "params_diff.txt").write_text("A,1\n", encoding="utf-8")
    if plots:
        (directory / "plots").mkdir(exist_ok=True)
        (directory / "plots" / "altitude.png").write_bytes(b"\x89PNG\r\n")
    if regression:
        (directory / "regression.json").write_text('{"schema": 1}\n',
                                                   encoding="utf-8")
        (directory / "regression.md").write_text("# comparison\n",
                                                 encoding="utf-8")

    return {
        "run_id": directory.name,
        "status": "passed",
        "procedures": [{"procedure": "copter_takeoff", "role": "takeoff",
                        "result": {"outcome": "passed", "steps": [],
                                   "expect": [], "faults": [],
                                   "params_changed": {}}}],
        "artefacts": {
            "dataflash": "00000001.BIN" if dataflash else None,
            "dataflash_check": ({"complete": True, "error": ""}
                                if dataflash else None),
            "dataflash_absent_reason": (
                None if dataflash else
                ("the vehicle never armed, and ArduPilot's default "
                 "LOG_DISARMED=0 means it writes no dataflash log until it "
                 "does — nothing was lost") if not armed else
                "the vehicle armed but no .BIN newer than the run start "
                "was found"),
        },
    }


def row(manifest: dict, name: str) -> dict:
    return next(r for r in manifest["artefacts"] if r["name"] == name)


# --------------------------------------------------------------- completeness
def test_a_complete_run_is_reported_complete(tmp_path):
    result = build(tmp_path, report=True, plots=True)
    manifest = evidence.capture(tmp_path, result)
    assert manifest["complete"] is True
    assert manifest["missing_required"] == []
    # Everything but the two regression artefacts, which only exist once a run
    # has been compared against a baseline — and are absent with a reason.
    assert manifest["counts"]["present"] == manifest["counts"]["expected"] - 2
    assert manifest["counts"]["absent_unexplained"] == 0
    assert evidence.problems(manifest) == []


@pytest.mark.parametrize("missing", sorted(REQUIRED_FILES))
def test_removing_any_required_artefact_is_detected(tmp_path, missing):
    """The one thing a manifest exists to do."""
    result = build(tmp_path, report=True)
    (tmp_path / missing).unlink()
    manifest = evidence.capture(tmp_path, result)

    assert manifest["complete"] is False
    assert manifest["missing_required"], f"{missing} was removed and not noticed"
    problems = evidence.problems(manifest)
    assert any(p["problem"] == "missing-required" for p in problems)


def test_a_missing_required_artefact_is_an_evidence_failure(tmp_path):
    """It has to reach the run's verdict, not only the manifest.

    A run whose procedures all passed and whose proof is missing has still
    failed — a flight nobody can prove happened is worth what one that did not
    is.
    """
    result = build(tmp_path, report=True)
    (tmp_path / "fingerprint.json").unlink()
    manifest = evidence.capture(tmp_path, result)

    failure = failures.classify_run(result, manifest)
    assert failure is not None
    assert failure.category == failures.EVIDENCE
    assert failure.code == failures.CODE_MISSING_ARTEFACT
    assert "fingerprint" in failure.detail


def test_a_passing_run_with_complete_evidence_has_no_failure(tmp_path):
    result = build(tmp_path, report=True, plots=True)
    manifest = evidence.capture(tmp_path, result)
    assert failures.classify_run(result, manifest) is None


# --------------------------------------------------------------- conditional
def test_the_dataflash_log_is_required_only_when_the_vehicle_armed(tmp_path):
    """ArduPilot ships LOG_DISARMED=0. A session that never armed writes no
    log, and nothing was lost — so demanding one would report a healthy run as
    missing its evidence."""
    result = build(tmp_path, armed=False, dataflash=False, report=False)
    manifest = evidence.capture(tmp_path, result)

    entry = row(manifest, "dataflash")
    assert entry["level_declared"] == evidence.CONDITIONAL
    assert entry["level"] == evidence.OPTIONAL, (
        "a run that never armed was asked for a log it correctly did not write")
    assert entry["absent_reason"], "the absence was not explained"
    assert manifest["complete"] is True


def test_a_missing_log_after_arming_is_required_and_missing(tmp_path):
    result = build(tmp_path, armed=True, dataflash=False)
    manifest = evidence.capture(tmp_path, result)

    entry = row(manifest, "dataflash")
    assert entry["level"] == evidence.REQUIRED
    assert manifest["complete"] is False


# ------------------------------------------------------------------ optional
def test_an_absent_optional_artefact_is_fine_with_a_stated_reason(tmp_path):
    result = build(tmp_path, report=False)
    manifest = evidence.capture(tmp_path, result)

    assert manifest["complete"] is True, "an optional absence invalidated a run"
    assert manifest["absent_unexplained"] == []
    for name in ("report_json", "report_md", "plots", "regression_json"):
        assert row(manifest, name)["absent_reason"], (
            f"{name} is absent with no reason recorded")


def test_an_empty_plot_directory_counts_as_absent(tmp_path):
    """A directory that exists and is empty is absence wearing a folder."""
    result = build(tmp_path, report=True)
    (tmp_path / "plots").mkdir()
    manifest = evidence.capture(tmp_path, result)

    entry = row(manifest, "plots")
    assert entry["exists"] is False
    assert entry["absent_reason"], "an empty plots/ was absent with no reason"


def test_an_optional_absence_with_no_reason_is_reported_as_a_gap(tmp_path):
    """The rule the whole design turns on, checked against the mechanism.

    An artefact whose catalogue entry cannot explain its own absence must be
    listed as unexplained rather than quietly accepted.
    """
    silent = evidence.Artefact("silent", "nothing.txt", "text/plain",
                               evidence.OPTIONAL, "test",
                               "an artefact with no explanation")
    original = list(evidence.CATALOGUE)
    evidence.CATALOGUE.append(silent)
    try:
        manifest = evidence.capture(tmp_path, build(tmp_path))
    finally:
        evidence.CATALOGUE[:] = original

    assert "silent" in manifest["absent_unexplained"]
    assert any(p["problem"] == "absent-unexplained"
               for p in evidence.problems(manifest))


# ------------------------------------------------------------ what is recorded
def test_each_artefact_records_its_type_size_hash_and_producer(tmp_path):
    result = build(tmp_path, report=True)
    manifest = evidence.capture(tmp_path, result)

    entry = row(manifest, "fingerprint")
    assert entry["type"] == "application/json"
    assert entry["size_bytes"] > 0
    assert entry["hash"].startswith("sha256:")
    assert entry["producer"] == "argazui.fingerprint"
    assert entry["producer_schema"] is not None


def test_the_run_record_is_listed_and_deliberately_unhashed(tmp_path):
    """A hash of it would be right at one moment and wrong at the next.

    `result.json` is rewritten when the flight report completes, so a digest
    taken at any single point would fail an integrity check for a run that is
    perfectly intact.
    """
    manifest = evidence.capture(tmp_path, build(tmp_path))
    entry = row(manifest, "result")
    assert entry["exists"] is True
    assert entry["hash"] is None
    assert entry["hash_absent_reason"] == evidence.SELF_DESCRIBING


def test_a_changed_file_changes_its_hash(tmp_path):
    """Otherwise the digest is decoration."""
    result = build(tmp_path)
    before = row(evidence.capture(tmp_path, result), "console")["hash"]
    (tmp_path / "console.log").write_text("boot\nand then something else\n",
                                          encoding="utf-8")
    after = row(evidence.capture(tmp_path, result), "console")["hash"]
    assert before != after


def test_the_report_copy_carries_no_hashes(tmp_path):
    """The report is one of the artefacts the manifest covers.

    A copy embedded in it is taken before its own last write, so carrying the
    digests there would mean two documents disagreeing about the digest of a
    third for no reason but the order they were written in.
    """
    manifest = evidence.capture(tmp_path, build(tmp_path, report=True))
    embedded = evidence.for_report(manifest)

    assert embedded["complete"] == manifest["complete"]
    assert embedded["counts"] == manifest["counts"]
    assert embedded["hashes_in"] == evidence.FILENAME
    for entry in embedded["artefacts"]:
        assert "hash" not in entry
        assert "path" in entry and "level" in entry and "exists" in entry


def test_the_manifest_survives_a_directory_it_cannot_read(tmp_path):
    """A run must never be lost over its own bookkeeping."""
    manifest = evidence.capture(tmp_path / "does-not-exist",
                                {"run_id": "ghost", "artefacts": {}})
    assert manifest["complete"] is False
    assert manifest["counts"]["present"] == 0


def test_a_written_manifest_reads_back(tmp_path):
    manifest = evidence.capture(tmp_path, build(tmp_path))
    path = evidence.write(tmp_path, manifest)
    assert path.name == evidence.FILENAME
    assert json.loads(path.read_text(encoding="utf-8"))["run_id"] == \
        manifest["run_id"]
    assert evidence.read(tmp_path)["counts"] == manifest["counts"]


def test_reading_a_run_without_a_manifest_gives_an_empty_one(tmp_path):
    """A run recorded before v1.5 has none, and that must not raise."""
    assert evidence.read(tmp_path) == {}


def test_the_rendered_manifest_names_what_is_missing(tmp_path):
    result = build(tmp_path)
    (tmp_path / "console.log").unlink()
    text = "\n".join(evidence.render(evidence.capture(tmp_path, result)))
    assert "required artefact(s) are missing" in text
    assert "console.log" in text
