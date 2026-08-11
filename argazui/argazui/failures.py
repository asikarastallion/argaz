"""Why a run failed — one machine-readable category, never a guess.

WHAT THIS LAYER IS FOR
----------------------
Until v1.4 a run had a verdict and a sentence. `failed` plus "the expected
state did not arrive within 60s" is true and almost useless: it does not say
whether the aircraft misbehaved, whether SITL never started, whether the
dataflash log was lost, or whether ArgazUI itself broke. Those four call for
four different people to look at four different things, and reading a sentence
to work out which is exactly the kind of judgement a machine should not leave
to a reader in a hurry.

So every failure is classified into one of seven categories, the category is
written into `result.json`, and the report, the status table and the run
listing all show it.

THE CATEGORIES ARE FIXED, AND SEVEN IS THE POINT
------------------------------------------------
The set below is closed. A taxonomy that grows a category whenever something
new goes wrong stops being a diagnosis and becomes a second copy of the error
message. Each of these names a *different investigation*:

    environment        the simulation never got into the state the run needed
    vehicle_readiness  the aircraft refused to be made ready — pre-arm, arming
    procedure          a step of the flow did not do what it asked for
    acceptance         the flow ran and a declared criterion did not hold
    evidence           it flew, and the proof of what happened is missing
    regression         nothing failed; a measured quantity got worse
    infrastructure     ArgazUI, the link or CI broke. Not a verdict about the
                       aircraft at all.

`acceptance` is the only one that means "the aircraft did something wrong that
the procedure had declared it must not do". Everything else is a statement
about the test, the tooling or the evidence, and conflating them is how a
broken harness comes to be reported as a broken aircraft.

NOTHING IS CLASSIFIED THAT DID NOT FAIL
---------------------------------------
`classify_*` returns None for a passing run. A "category: none" field would
read like a verdict of its own, and a reader scanning for the word `failure`
would find one on every run in the directory.
"""
from __future__ import annotations

import re
from typing import Optional

SCHEMA = 1

# ---------------------------------------------------------------- categories
ENVIRONMENT = "environment"
VEHICLE_READINESS = "vehicle_readiness"
PROCEDURE = "procedure"
ACCEPTANCE = "acceptance"
EVIDENCE = "evidence"
REGRESSION = "regression"
INFRASTRUCTURE = "infrastructure"

CATEGORIES = (ENVIRONMENT, VEHICLE_READINESS, PROCEDURE, ACCEPTANCE, EVIDENCE,
              REGRESSION, INFRASTRUCTURE)

# What each category means, who it is for, and — the part that makes it worth
# recording — what to look at first. Both languages, because a category shown
# in the interface is a user-visible string.
CATALOGUE: dict[str, dict] = {
    ENVIRONMENT: {
        "label": {"en": "Environment / startup",
                  "tr": "Ortam / baslangic"},
        "what": {
            "en": "The simulation could not be brought into the state the run "
                  "required: SITL or Gazebo did not start, an asset was "
                  "missing, or a requested fault could not be applied.",
            "tr": "Simulasyon, kosunun ihtiyac duydugu duruma getirilemedi: "
                  "SITL ya da Gazebo baslamadi, bir varlik eksikti veya "
                  "istenen ariza enjekte edilemedi."},
        "look_at": {
            "en": "console.log, the launch commands at the top of it, and "
                  "`argazui doctor`.",
            "tr": "console.log, dosyanin basindaki baslatma komutlari ve "
                  "`argazui doctor`."},
    },
    VEHICLE_READINESS: {
        "label": {"en": "Vehicle readiness", "tr": "Arac hazir olmama"},
        "what": {
            "en": "The aircraft would not be made ready: pre-arm checks never "
                  "passed, or an arm/disarm was refused. The autopilot's own "
                  "wording is in the detail.",
            "tr": "Arac hazir hale getirilemedi: arm oncesi kontroller hic "
                  "gecmedi ya da arm/disarm reddedildi. Otopilotun kendi "
                  "ifadesi ayrinti alanindadir."},
        "look_at": {
            "en": "the autopilot messages in console.log and the STATUSTEXT "
                  "lines in mavlink_events.jsonl.",
            "tr": "console.log icindeki otopilot mesajlari ve "
                  "mavlink_events.jsonl icindeki STATUSTEXT satirlari."},
    },
    PROCEDURE: {
        "label": {"en": "Procedure execution", "tr": "Prosedur yurutme"},
        "what": {
            "en": "A step of the flow did not do what it asked for — a mode "
                  "was refused, a command was rejected, a wait timed out. The "
                  "acceptance criteria were never reached.",
            "tr": "Akisin bir adimi istedigini yapamadi — bir mod reddedildi, "
                  "bir komut geri cevrildi, bir bekleme zaman asimina ugradi. "
                  "Kabul kriterlerine hic gelinmedi."},
        "look_at": {
            "en": "the failing step in result.json, and the procedure verbatim "
                  "in scenario.yaml.",
            "tr": "result.json icindeki basarisiz adim ve scenario.yaml "
                  "icindeki prosedurun kendisi."},
    },
    ACCEPTANCE: {
        "label": {"en": "Acceptance criterion", "tr": "Kabul kriteri"},
        "what": {
            "en": "The flow ran to the end and a declared criterion did not "
                  "hold. This is the only category that is a verdict about the "
                  "aircraft.",
            "tr": "Akis sonuna kadar kostu ve beyan edilen bir kriter "
                  "saglanmadi. Arac hakkinda hukum veren tek kategori budur."},
        "look_at": {
            "en": "the `expect` block in result.json — each entry states what "
                  "was measured — and the plots in report.md.",
            "tr": "result.json icindeki `expect` blogu — her madde neyin "
                  "olculdugunu yazar — ve report.md icindeki grafikler."},
    },
    EVIDENCE: {
        "label": {"en": "Evidence / data", "tr": "Kanit / veri"},
        "what": {
            "en": "The flight happened and the proof of it is incomplete: no "
                  "dataflash log, a truncated one, a report that could not be "
                  "produced, or a criterion whose telemetry never arrived so "
                  "nothing was measured. The run cannot support a claim either "
                  "way.",
            "tr": "Ucus gerceklesti ama kaniti eksik: dataflash logu yok, "
                  "yarim kalmis, rapor uretilemedi ya da bir kriterin dayandigi "
                  "telemetri hic gelmedigi icin hicbir sey olculmedi. Kosu "
                  "hicbir yonde iddiayi destekleyemez."},
        "look_at": {
            "en": "artefacts.dataflash_check in result.json, and the working "
                  "directory the log should have been copied from.",
            "tr": "result.json icindeki artefacts.dataflash_check ve logun "
                  "kopyalanmasi gereken calisma dizini."},
    },
    REGRESSION: {
        "label": {"en": "Regression", "tr": "Regresyon"},
        "what": {
            "en": "Nothing failed. A measured quantity moved past its declared "
                  "threshold against a named baseline — the aircraft is doing "
                  "the same thing measurably less well.",
            "tr": "Hicbir sey basarisiz olmadi. Olculen bir buyukluk, adi "
                  "verilmis bir referansa gore beyan edilen esigi asti — arac "
                  "ayni isi olculebilir bicimde daha kotu yapiyor."},
        "look_at": {
            "en": "regression.md beside the run, and the baseline it names.",
            "tr": "kosunun yanindaki regression.md ve adini verdigi referans."},
    },
    INFRASTRUCTURE: {
        "label": {"en": "Infrastructure / CI", "tr": "Altyapi / CI"},
        "what": {
            "en": "ArgazUI, the MAVLink link or the CI job broke — or the run "
                  "was stopped by hand before it finished. This says nothing "
                  "about the aircraft and must never be reported as if it did.",
            "tr": "ArgazUI, MAVLink baglantisi ya da CI isi bozuldu; ya da "
                  "kosu bitmeden elle durduruldu. Bu, arac hakkinda hicbir sey "
                  "soylemez ve oyleymis gibi raporlanmamalidir."},
        "look_at": {
            "en": "the traceback in the run's `text`, and the workflow log.",
            "tr": "kosunun `text` alanindaki hata izi ve is akisi kaydi."},
    },
}

# ------------------------------------------------------------------- codes
# A code is finer than a category and coarser than a message: it is what two
# runs that failed the same way have in common. The category answers "who
# investigates"; the code answers "is this the same thing as last time".
CODE_PREARM = "prearm-never-passed"
CODE_ARM_REFUSED = "arm-refused"
CODE_STEP_FAILED = "step-failed"
CODE_STEP_TIMEOUT = "step-timeout"
CODE_CRITERION_FAILED = "criterion-failed"
CODE_CRITERION_NOT_JUDGED = "criterion-not-judged"
CODE_OVERRIDE_FAILED = "override-not-applied"
CODE_FAULT_NOT_APPLIED = "fault-not-applied"
CODE_FAULT_NOT_CLEARED = "fault-not-cleared"
CODE_NO_DATAFLASH = "dataflash-missing"
CODE_TRUNCATED_DATAFLASH = "dataflash-truncated"
CODE_MISSING_ARTEFACT = "evidence-artefact-missing"
CODE_RUNNER_ERROR = "runner-error"
CODE_METRIC_DEGRADED = "metric-degraded"
CODE_NOT_COMPARABLE = "runs-not-comparable"
# Added by the v1.6 corrective release, one per abort reason the runner can
# now state outright instead of leaving to be reconstructed.
CODE_FAULT_UNAVAILABLE = "fault-mechanism-unavailable"
CODE_FAULT_START_MISSED = "fault-start-missed"
CODE_PROCEDURE_TIMEOUT = "procedure-timeout"
CODE_CANCELLED = "procedure-cancelled"
CODE_NO_VEHICLE = "vehicle-never-connected"
CODE_CONFIG_ERROR = "procedure-config-error"
# Added by v1.7, one per lifecycle rung a start-up can stop on. v1.6.1 could
# already say "no vehicle ever connected"; these say WHICH part of the
# environment did not come up, which is the difference between a category and a
# diagnosis. See simlifecycle.PHASE_FAILURES.
#
# There is deliberately no separate code for a model environment that is not
# the declared one. That refusal happens BEFORE the simulator is launched, so
# the environment genuinely never became ready, and `environment-not-ready` is
# the accurate answer — the specific reason is in the failure's `detail`, which
# names the revision and the reconciling command. A third code would let two
# strings describe one state, and they would eventually disagree.
CODE_ENVIRONMENT_NOT_READY = "environment-not-ready"
CODE_VEHICLE_START_FAILED = "vehicle-start-failed"

# WHY AN ABORT REASON IS A TABLE AND NOT A CHAIN OF `if`s
# -------------------------------------------------------
# `procrunner.ABORT_KINDS` and this map are the contract between the two
# modules, and a kind with no entry here is a bug that shows up as the wrong
# category rather than as an exception. `_abort_failure` therefore treats an
# unknown kind as an ordinary step failure and nothing silently becomes
# `acceptance`.
#
# Only ABORT_STEP is absent from this table: a step that returned not-ok has a
# failed step in the document, which the step loop below classifies with far
# more detail than a kind could.
ABORT_CATEGORIES: dict[str, tuple[str, str]] = {
    # The simulator could not be brought into the state the run needed.
    "fault-unavailable": (ENVIRONMENT, CODE_FAULT_UNAVAILABLE),
    "fault-refused": (ENVIRONMENT, CODE_FAULT_NOT_APPLIED),
    "override-failed": (ENVIRONMENT, CODE_OVERRIDE_FAILED),
    "vehicle-never-connected": (ENVIRONMENT, CODE_NO_VEHICLE),
    # The document itself is wrong. Not the aircraft, not the simulator.
    "procedure-config-error": (ENVIRONMENT, CODE_CONFIG_ERROR),
    # The flow ran and did not get where it was going.
    "overall-timeout": (PROCEDURE, CODE_PROCEDURE_TIMEOUT),
    "fault-start-missed": (PROCEDURE, CODE_FAULT_START_MISSED),
    # A person or a campaign stopped it. Says nothing about anything.
    "cancelled": (INFRASTRUCTURE, CODE_CANCELLED),
}

# Step kinds whose failure is the vehicle refusing to be made ready, rather
# than the flow going wrong. Kept explicit: an `arm` that is refused and a
# `set_mode` that is refused look identical in a result document and are two
# different investigations.
READINESS_STEPS = ("arm", "disarm")

# Substrings in a step's own text that mean the autopilot would not become
# ready. Matched case-insensitively against the message the autopilot itself
# sent, so this list follows ArduPilot's wording rather than inventing any.
READINESS_HINTS = (
    "prearm", "pre-arm", "waiting for home", "ekf", "ahrs", "3d fix",
    "compass", "accels inconsistent", "gyros inconsistent", "calibrat",
    "not healthy", "logging not started",
)

# `_not_judged` has to recognise the runner's own "nothing was measured"
# wording in both languages, because the run record stores the message in
# whichever language the run was flown in.
_NOT_JUDGED = re.compile(
    r"not judged|not evaluated|degerlendirilmedi", re.IGNORECASE)

# The same problem for a step that ran out of time. These are the exact
# messages `i18n.py` produces — `proc_wait_timeout`, `proc_overall_timeout`
# and `cmd_timeout` — in both languages, matched on the part that does not
# carry a formatted number.
_TIMED_OUT = re.compile(
    r"timed out|timeout|did not arrive within"
    r"|zaman asimina|ulasilmadi|sinirini asti", re.IGNORECASE)


class Failure:
    """One classified failure: a category, a code, and what was seen."""

    __slots__ = ("category", "code", "detail", "source", "procedure")

    def __init__(self, category: str, code: str, detail: str = "",
                 source: str = "", procedure: str = "") -> None:
        if category not in CATEGORIES:
            raise ValueError(f"unknown failure category {category!r}")
        self.category = category
        self.code = code
        self.detail = detail
        self.source = source
        self.procedure = procedure

    def as_dict(self) -> dict:
        return {"schema": SCHEMA, "category": self.category, "code": self.code,
                "detail": self.detail[:500], "source": self.source,
                "procedure": self.procedure}

    def label(self, lang: str = "en") -> str:
        entry = CATALOGUE[self.category]["label"]
        return entry.get(lang) or entry["en"]

    def __repr__(self) -> str:                       # pragma: no cover - debug
        return f"<Failure {self.category}/{self.code}: {self.detail[:60]}>"


def label_for(category: str, lang: str = "en") -> str:
    entry = CATALOGUE.get(category, {}).get("label", {})
    return entry.get(lang) or entry.get("en") or category


def catalogue(lang: str = "en") -> list[dict]:
    """The published taxonomy, for the interface and the documentation portal."""
    return [{"category": key,
             "label": spec["label"].get(lang) or spec["label"]["en"],
             "what": spec["what"].get(lang) or spec["what"]["en"],
             "look_at": spec["look_at"].get(lang) or spec["look_at"]["en"]}
            for key, spec in CATALOGUE.items()]


# ------------------------------------------------------------------ helpers
def _reads_as_readiness(text: str) -> bool:
    lowered = (text or "").lower()
    return any(hint in lowered for hint in READINESS_HINTS)


def _not_judged(criterion: dict) -> bool:
    """Was this criterion left unjudged rather than judged and failed?

    Reads the `evaluated` flag the runner now records. The prose fallback is
    for runs written before that field existed: those documents say it in
    English or Turkish and nothing else, and refusing to read them would
    reclassify every archived run.
    """
    if "evaluated" in criterion:
        return not criterion.get("evaluated")
    return bool(_NOT_JUDGED.search(criterion.get("text") or ""))


def _abort_failure(result: dict) -> Optional[Failure]:
    """The classified reason a procedure stopped early, if it stopped early.

    This runs BEFORE the step and criterion loops, and that order is the whole
    point. An abort leaves skipped steps and unevaluated criteria behind, so a
    classifier that looked at the residue first found a criterion that had not
    passed and called it `acceptance` — the one category that means the
    aircraft did something wrong. A fault mechanism this firmware does not have
    was reported as an aircraft that failed its acceptance criteria.
    """
    abort = result.get("abort") or {}
    kind = abort.get("kind")
    if not kind:
        return None
    entry = ABORT_CATEGORIES.get(kind)
    if entry is None:
        # ABORT_STEP, or a kind added to the runner and not to the table. The
        # step loop below has more detail; fall through to it rather than
        # guessing a category here.
        return None
    category, code = entry
    return Failure(category, code,
                   detail=abort.get("text") or kind,
                   source="procedure.abort",
                   procedure=result.get("procedure") or "")


# --------------------------------------------------------------- procedures
def classify_procedure(result: dict) -> Optional[Failure]:
    """Why one procedure execution failed, or None if it passed.

    The order below is the order of investigation, not of severity. A run that
    could not arm never reached its acceptance criteria, so reporting the
    unevaluated criteria would name a symptom and hide the cause; the first
    thing that went wrong is the thing worth classifying.
    """
    outcome = result.get("outcome")
    if outcome == "passed":
        return None

    procedure = result.get("procedure") or ""

    # A runner error is not a verdict about the aircraft, and it outranks
    # everything: whatever else the document says was recorded by a run that
    # was already broken.
    if outcome == "error":
        return Failure(INFRASTRUCTURE, CODE_RUNNER_ERROR,
                       detail=result.get("text") or "the procedure could not "
                                                    "be evaluated",
                       source="procrunner", procedure=procedure)

    # Why it stopped, when the runner stated it. Before everything below,
    # because everything below reads the residue an abort leaves rather than
    # the abort itself. See `_abort_failure`.
    aborted = _abort_failure(result)
    if aborted is not None:
        return aborted

    # A declared override that would not apply. The vehicle is not in the
    # configuration the procedure requires, so nothing after it means anything.
    for name, record in (result.get("params_changed") or {}).items():
        if record.get("applied") is False:
            return Failure(ENVIRONMENT, CODE_OVERRIDE_FAILED,
                           detail=f"the declared override {name} = "
                                  f"{record.get('set_to')} could not be applied",
                           source=f"overrides.{name}", procedure=procedure)

    # A fault the scenario declared and the simulator would not accept. Fail
    # closed: an off-nominal test whose off-nominal condition never happened is
    # a nominal test wearing the wrong name.
    for fault in result.get("faults") or []:
        if fault.get("applied") is False:
            return Failure(ENVIRONMENT, CODE_FAULT_NOT_APPLIED,
                           detail=f"{fault.get('id')}: {fault.get('text') or ''}",
                           source=f"failures.{fault.get('id')}",
                           procedure=procedure)
        if fault.get("cleared") is False:
            return Failure(ENVIRONMENT, CODE_FAULT_NOT_CLEARED,
                           detail=f"{fault.get('id')}: the injected fault could "
                                  f"not be cleared; the simulated vehicle may "
                                  f"still be degraded",
                           source=f"failures.{fault.get('id')}",
                           procedure=procedure)

    for step in result.get("steps") or []:
        if step.get("status") != "failed":
            continue
        text = step.get("text") or ""
        label = step.get("label") or step.get("kind") or "step"
        source = f"steps[{step.get('index')}]"
        if step.get("kind") in READINESS_STEPS or _reads_as_readiness(text):
            return Failure(VEHICLE_READINESS,
                           CODE_ARM_REFUSED if step.get("kind") in READINESS_STEPS
                           else CODE_PREARM,
                           detail=f"{label}: {text}", source=source,
                           procedure=procedure)
        code = CODE_STEP_TIMEOUT if _TIMED_OUT.search(text) else CODE_STEP_FAILED
        return Failure(PROCEDURE, code, detail=f"{label}: {text}",
                       source=source, procedure=procedure)

    # A criterion that was judged and did not hold, before one that could not
    # be judged at all: the first is a result about the aircraft and the second
    # is a gap in the evidence, and when a run has both the aircraft result is
    # the one worth naming.
    for index, criterion in enumerate(result.get("expect") or []):
        if criterion.get("passed") or _not_judged(criterion):
            continue
        return Failure(ACCEPTANCE, CODE_CRITERION_FAILED,
                       detail=f"{criterion.get('label') or 'criterion'}: "
                              f"{criterion.get('text') or ''}",
                       source=f"expect[{index}]", procedure=procedure)

    for index, criterion in enumerate(result.get("expect") or []):
        if criterion.get("passed") or not _not_judged(criterion):
            continue
        # EVIDENCE, not ACCEPTANCE. The telemetry the criterion rests on never
        # arrived, or too few samples of it did — so nothing was measured, and
        # "nothing was measured" is not a verdict about the aircraft. Filing it
        # under `acceptance` is the same conflation this module exists to
        # prevent, one level down.
        return Failure(EVIDENCE, CODE_CRITERION_NOT_JUDGED,
                       detail=f"{criterion.get('label') or 'criterion'}: "
                              f"{criterion.get('text') or ''}",
                       source=f"expect[{index}]", procedure=procedure)

    # Failed, and none of the above. The runner aborted before it filled in a
    # step or a criterion — the abort text is all there is, and inventing a
    # finer category from it would be a guess.
    return Failure(PROCEDURE, CODE_STEP_FAILED,
                   detail=result.get("text") or "the procedure did not pass",
                   source="procedure", procedure=procedure)


# --------------------------------------------------------------------- runs
def classify_run(result: dict, manifest: Optional[dict] = None) -> Optional[Failure]:
    """Why a whole run failed, from its own `result.json`.

    Reads only the LAST attempt of each procedure, for the same reason
    `aggregate_status` does: the suite is allowed one retry, and that leniency
    is paid for in the `flaky` marker rather than by classifying a failure that
    the retry went on to clear.

    A run whose procedures all passed can still fail on its evidence. That is
    not a technicality — a flight nobody can prove happened is worth exactly as
    much as one that did not.

    `manifest` is the run's evidence manifest (v1.5) when one has been taken.
    It is what turns "the dataflash log is missing" into the general statement
    "a required artefact is missing", so a report that was expected and never
    written is caught by the same rule rather than by nobody.
    """
    # BEFORE THE PROCEDURES: DID THE ENVIRONMENT COME UP? (v1.7)
    # -----------------------------------------------------------
    # A start-up that stopped at a lifecycle rung produced no procedures at
    # all, or produced ones that timed out against a simulator that was not
    # there. The layer that launched already knows which rung it stopped on and
    # recorded it, so this reads that answer rather than reconstructing one
    # from the residue — the same reasoning that put `abort.kind` on a
    # procedure result in v1.6.1, applied one level out.
    #
    # An acceptance failure is deliberately NOT taken from here: whether the
    # aircraft met its criteria is a question about the flight, and the
    # procedure loop below has the measurement that answers it.
    lifecycle = result.get("lifecycle") or {}
    lifecycle_failure = lifecycle.get("failure") or {}
    if lifecycle_failure.get("category") and lifecycle_failure["category"] != ACCEPTANCE:
        return Failure(lifecycle_failure["category"], lifecycle_failure["code"],
                       detail=lifecycle_failure.get("detail")
                              or f"the simulation stopped at "
                                 f"{lifecycle_failure.get('phase')}",
                       source=f"lifecycle.{lifecycle_failure.get('phase')}")

    last: dict[tuple, dict] = {}
    for entry in result.get("procedures") or []:
        key = (entry.get("procedure"), entry.get("role"))
        last[key] = entry

    for entry in last.values():
        failure = classify_procedure(entry.get("result") or {})
        if failure is not None:
            return failure

    # The manifest generalises the dataflash rules below to every artefact a
    # run was expected to leave. Checked first because it is the broader
    # statement: "a required artefact is missing" covers the log and the report
    # and the fingerprint, and the specific checks after it stay for runs
    # recorded before v1.5, which carry no manifest.
    for problem in ((manifest or {}).get("missing_required") or []):
        return Failure(EVIDENCE, CODE_MISSING_ARTEFACT,
                       detail=f"the run was expected to produce '{problem}' "
                              f"and did not; see evidence.json",
                       source=f"evidence.{problem}")

    artefacts = result.get("artefacts") or {}
    check = artefacts.get("dataflash_check") or {}
    if artefacts.get("dataflash") and check and not check.get("complete"):
        return Failure(EVIDENCE, CODE_TRUNCATED_DATAFLASH,
                       detail=f"{artefacts['dataflash']}: "
                              f"{check.get('error') or 'no timestamped tail'}",
                       source="artefacts.dataflash_check")

    # A missing dataflash log is only a failure when the run had procedures to
    # prove. A session that was started and stopped without flying anything
    # asserted nothing, so there is nothing missing.
    if last and not artefacts.get("dataflash"):
        reason = artefacts.get("dataflash_absent_reason") or "no reason recorded"
        return Failure(EVIDENCE, CODE_NO_DATAFLASH,
                       detail=f"a procedure ran but no dataflash log was "
                              f"archived — {reason}",
                       source="artefacts.dataflash")

    if result.get("status") == "error":
        return Failure(INFRASTRUCTURE, CODE_RUNNER_ERROR,
                       detail="the run ended in an error state with no "
                              "classifiable procedure failure",
                       source="status")
    return None


def classify_comparison(comparison: dict) -> Optional[Failure]:
    """A regression comparison as a classified failure, or None if it passed.

    `incomparable` is deliberately EVIDENCE and not REGRESSION: two runs that
    do not line up have not shown that anything got worse, and reporting them
    as a regression is the mis-specified-baseline bug that `argazui compare`
    gives its own exit code to avoid.
    """
    verdict = comparison.get("verdict")
    if verdict == "regressed":
        degraded = comparison.get("degraded") or []
        return Failure(REGRESSION, CODE_METRIC_DEGRADED,
                       detail="degraded past threshold: " + ", ".join(degraded),
                       source="regression.json")
    if verdict == "incomparable":
        compat = comparison.get("compatibility") or {}
        reasons = [item.get("reason", "") for item in
                   (compat.get("blocking") or [])] or \
                  [f"{item.get('what')} {item.get('reason')}" for item in
                   (compat.get("configuration_drift") or [])]
        return Failure(EVIDENCE, CODE_NOT_COMPARABLE,
                       detail="; ".join(r for r in reasons if r)
                              or "the two runs do not line up",
                       source="regression.json")
    return None


def summarise(failures: list[Optional[Failure]]) -> dict[str, int]:
    """How many of each category, for a campaign or a suite."""
    counts: dict[str, int] = {}
    for failure in failures:
        if failure is None:
            continue
        counts[failure.category] = counts.get(failure.category, 0) + 1
    return counts
