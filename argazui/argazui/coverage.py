"""Coverage: what has been exercised, and — the useful half — what has not.

WHY NOT A TEST COUNT
--------------------
A test count goes up when someone adds a test and never goes down when someone
adds an aircraft, a procedure or a criterion nobody runs. It measures effort,
not reach, and a project that watches it will eventually be proud of a suite
that covers less than it did last month.

So coverage here is measured over **named things that could be exercised**, in
four dimensions, and every dimension reports the items it did *not* reach by
name. A percentage with no list under it is an invitation to stop reading; the
list is the deliverable.

    models       registry entries flown in Gazebo by tier 2
    procedures   procedure files that some run actually executed
    criteria     acceptance criteria that some run actually EVALUATED
    faults       fault kinds and declared scenario faults actually injected
    experiments  declared experiments, and the arms of them that were flown

WHAT "EVALUATED" MEANS, AND WHY IT IS STRICTER THAN "RAN"
---------------------------------------------------------
A criterion the procedure never reached — because an earlier step failed, or
because the telemetry it rests on never arrived — is *not* covered. It produced
no information about the aircraft. Counting it because it appears in a
`result.json` would let a run that aborted at step two report full criterion
coverage, which is the exact shape of the unearned claim this project exists to
remove.

NO DATABASE, AGAIN
------------------
Computed from the procedure files, the model registry and the run directories,
every time. Nothing is stored and nothing accumulates, so a coverage figure can
never be higher than the evidence currently on disk supports.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from . import experiments as experimentlib
from . import faults as faultlib
from . import mechanisms
from . import paths
from . import procedures as procs
from . import trace

SCHEMA = 1

MODELS, PROCEDURES, CRITERIA, FAULTS, EXPERIMENTS = (
    "models", "procedures", "criteria", "faults", "experiments")
DIMENSIONS = (MODELS, PROCEDURES, CRITERIA, FAULTS, EXPERIMENTS)

LABELS: dict[str, dict[str, str]] = {
    MODELS: {"en": "Model coverage", "tr": "Model kapsami"},
    PROCEDURES: {"en": "Procedure coverage", "tr": "Prosedur kapsami"},
    CRITERIA: {"en": "Acceptance-criterion coverage",
               "tr": "Kabul kriteri kapsami"},
    FAULTS: {"en": "Fault and scenario coverage",
             "tr": "Ariza ve senaryo kapsami"},
    EXPERIMENTS: {"en": "Experiment coverage", "tr": "Deney kapsami"},
}

WHAT: dict[str, dict[str, str]] = {
    MODELS: {
        "en": "Registry entries that tier 2 has flown in Gazebo. Tier 1 does "
              "not count: it flies SITL's own generic frames and says nothing "
              "about an airframe.",
        "tr": "Katman 2'nin Gazebo'da ucurdugu kayit defteri girdileri. Katman 1 "
              "sayilmaz: SITL'in kendi genel govdelerini ucurur ve bir hava "
              "araci hakkinda hicbir sey soylemez."},
    PROCEDURES: {
        "en": "Procedure files that some recorded run actually executed.",
        "tr": "Kayitli bir kosunun gercekten calistirdigi prosedur dosyalari."},
    CRITERIA: {
        "en": "Acceptance criteria that were actually evaluated. A criterion "
              "the procedure never reached is not covered — it produced no "
              "information about the aircraft.",
        "tr": "Gercekten degerlendirilmis kabul kriterleri. Prosedurun hic "
              "ulasamadigi bir kriter kapsanmis sayilmaz — arac hakkinda hicbir "
              "bilgi uretmemistir."},
    FAULTS: {
        "en": "Fault kinds the code implements, and the faults scenarios "
              "declare, that some run actually injected.",
        "tr": "Kodun uyguladigi ariza turleri ve senaryolarin beyan ettigi "
              "arizalardan bir kosuda gercekten enjekte edilmis olanlar."},
    EXPERIMENTS: {
        "en": "Declared experiments, and each arm of them, that some recorded "
              "run actually flew. An arm is listed on its own because an "
              "experiment half of whose arms were flown has answered nothing "
              "— a comparison needs both sides.",
        "tr": "Beyan edilmis deneyler ve kayitli bir kosunun gercekten "
              "ucurdugu kollari. Kollar ayri ayri listelenir cunku kollarinin "
              "yarisi ucurulmus bir deney hicbir seyi yanitlamamistir — bir "
              "karsilastirma iki tarafi da ister."},
}


def _pct(covered: int, total: int) -> Optional[float]:
    """None rather than 100% when there is nothing to cover.

    A dimension with no items is not fully covered; it is empty, and the two
    read identically as a percentage.
    """
    return None if not total else round(covered / total, 4)


def _dimension(name: str, declared: list[dict], covered: set) -> dict:
    items = []
    for entry in declared:
        items.append({**entry, "covered": entry["id"] in covered})
    return {
        "dimension": name,
        "label": LABELS[name]["en"],
        "declared": len(items),
        "covered": sum(1 for item in items if item["covered"]),
        "fraction": _pct(sum(1 for item in items if item["covered"]), len(items)),
        "items": items,
        # The half of the report that is worth reading.
        "uncovered": [item["id"] for item in items if not item["covered"]],
    }


# --------------------------------------------------------------- declarations
def declared_models(registry: Optional[dict] = None) -> list[dict]:
    if registry is None:
        try:
            registry = json.loads(paths.MODELS_JSON.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            registry = {"models": []}
    return [{"id": model.get("id", "?"),
             "what": f"{model.get('name', '')} "
                     f"({model.get('vehicle_class', '?')})".strip()}
            for model in registry.get("models") or []]


def declared_procedures(directory: Optional[Path] = None) -> list[dict]:
    everything = procs.load_all(directory)
    return [{"id": pid, "what": f"{proc.label('en')} [{proc.role}]"}
            for pid, proc in sorted(everything.items())]


def declared_criteria(directory: Optional[Path] = None) -> list[dict]:
    """Every acceptance criterion in every procedure, by identifier.

    Only the procedure-level `expect:` block. A fault's own criteria are
    counted under fault coverage, because they are only reachable by injecting
    the fault and reporting them here would make a nominal run look as though
    it had covered them.
    """
    out: list[dict] = []
    for pid, proc in sorted(procs.load_all(directory).items()):
        for index, criterion in enumerate(proc.expect):
            out.append({
                "id": trace.criterion_id(pid, index, criterion.id),
                "what": criterion.label("en"),
                "procedure": pid,
                "declared_id": bool(criterion.id),
            })
    return out


def declared_faults(directory: Optional[Path] = None) -> list[dict]:
    """The fault kinds the code implements, plus each scenario's own faults.

    Both, because they answer different questions. A kind with no scenario
    behind it is a mechanism nobody has pointed at an aircraft; a declared
    fault that no run injected is a scenario nobody has flown.
    """
    out: list[dict] = [
        {"id": kind, "what": f"mechanism: {faultlib.label_for(kind)}",
         "scope": "mechanism"}
        for kind in faultlib.KINDS
    ]
    for pid, proc in sorted(procs.load_all(directory).items()):
        for fault in proc.failures:
            out.append({"id": trace.fault_id(pid, fault.id),
                        "what": f"{fault.kind} on {fault.target}",
                        "scope": "scenario", "procedure": pid})
    return out


def declared_experiments(directory: Optional[Path] = None) -> list[dict]:
    """Every experiment, plus each of its arms, by identifier.

    Both, because they answer different questions — the same shape fault
    coverage has. An experiment nobody ran is a question this project asked
    and never answered; an *arm* nobody ran is worse than that, because the
    experiment looks flown and its comparison has one side missing.
    """
    out: list[dict] = []
    for eid, experiment in sorted(experimentlib.load_all(directory).items()):
        out.append({"id": eid, "what": experiment.label("en"),
                    "scope": "experiment"})
        for arm in experiment.arms:
            out.append({"id": f"{eid}{trace.SEP}{arm.id}",
                        "what": f"{arm.procedure_id} × {arm.runs} "
                                f"[{arm.role}]",
                        "scope": "arm", "experiment": eid})
    return out


# ------------------------------------------------------------------ evidence
def _runs_under(roots: list[Path]) -> list[dict]:
    out: list[dict] = []
    for root in roots:
        root = Path(root)
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("result.json")):
            try:
                out.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
    return out


def _tier2_models(roots: list[Path]) -> set:
    """Models a tier-2 test actually flew, from the suite records.

    Read from `suite.json` rather than from the runs, because a run directory
    alone cannot say which tier produced it — and treating a tier-1 run as
    model coverage is precisely the conflation `docs/status.md` exists to
    prevent.
    """
    covered: set = set()
    for root in roots:
        root = Path(root)
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("suite.json")):
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for test in document.get("tests") or []:
                if "tier2" not in (test.get("markers") or []):
                    continue
                if test.get("outcome") == "skipped":
                    # A skip is not coverage. It is the absence of it.
                    continue
                nodeid = test.get("nodeid", "")
                if "[" in nodeid and nodeid.rstrip().endswith("]"):
                    covered.add(nodeid.rsplit("[", 1)[1].rstrip("]").strip())
    return covered


def _experiments_flown(runs: list[dict]) -> set:
    """Experiments and arms some recorded run actually flew.

    Read from the run's own experiment stamp, not from the documents under
    `runs/experiments/`. A document can be written for an experiment run that
    was cancelled after its first arm, and coverage has to be about what flew.
    """
    covered: set = set()
    for result in runs:
        stamp = result.get("experiment") or {}
        identifier, arm = stamp.get("id"), stamp.get("arm")
        if not identifier:
            continue
        covered.add(identifier)
        if arm:
            covered.add(f"{identifier}{trace.SEP}{arm}")
    return covered


def _exercised(runs: list[dict]) -> tuple[set, set, set, int]:
    """(procedures executed, criteria evaluated, faults injected, unattributable).

    The last number counts criteria that were evaluated by a run recorded
    before v1.5, which carries no criterion identifiers. They are NOT guessed
    into place by position: the procedure may have been edited since, and a
    coverage figure inflated by a guess is the kind of unearned claim this
    whole project is a reaction to. They are counted and reported instead, so
    a 0% first reading after an upgrade has a stated reason rather than looking
    like a project that tests nothing.
    """
    procedures: set = set()
    criteria: set = set()
    injected: set = set()
    unattributable = 0

    for result in runs:
        for entry in result.get("procedures") or []:
            pid = entry.get("procedure")
            if not pid:
                continue
            procedures.add(pid)
            outcome = entry.get("result") or {}
            for criterion in outcome.get("expect") or []:
                if not trace._was_evaluated(criterion):
                    continue
                identifier = criterion.get("criterion_id")
                if not identifier:
                    unattributable += 1
                    continue
                criteria.add(identifier)
            for fault in outcome.get("faults") or []:
                if not fault.get("applied"):
                    # Fail-closed: a fault that was never injected covers
                    # nothing, and the scenario it belongs to was not flown.
                    continue
                injected.add(fault.get("fault"))
                if fault.get("id"):
                    injected.add(trace.fault_id(pid, fault["id"]))
    return procedures, criteria, injected, unattributable


# ------------------------------------------------------------------- report
def collect(runs_roots: Optional[list[Path]] = None,
            procedures_dir: Optional[Path] = None,
            registry: Optional[dict] = None,
            experiments_dir: Optional[Path] = None) -> dict:
    """The coverage document, computed from what is currently on disk."""
    roots = [Path(r) for r in (runs_roots or [paths.RUNS_DIR])]
    runs = _runs_under(roots)
    executed, evaluated, injected, unattributable = _exercised(runs)
    flown = _experiments_flown(runs)

    from datetime import datetime, timezone
    return {
        "schema": SCHEMA,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "runs_read": len(runs),
        "roots": [str(r) for r in roots],
        # Criteria that were evaluated by a run recorded before criterion
        # identifiers existed. Reported rather than attributed by position.
        "unattributable_criteria": unattributable,
        "dimensions": [
            _dimension(MODELS, declared_models(registry), _tier2_models(roots)),
            _dimension(PROCEDURES, declared_procedures(procedures_dir), executed),
            _dimension(CRITERIA, declared_criteria(procedures_dir), evaluated),
            _dimension(FAULTS, declared_faults(procedures_dir), injected),
            _dimension(EXPERIMENTS, declared_experiments(experiments_dir), flown),
        ],
        # Per-mechanism states beside the per-dimension fractions (v1.7).
        # Computed from the same run directories in a separate pass rather than
        # threaded through `_exercised`: the two ask different questions of the
        # same evidence, and one function answering both would answer neither
        # clearly. Deliberately NOT a sixth dimension — it is not a fraction,
        # and forcing it into one would lose the states.
        "mechanism_matrix": mechanisms.collect(roots, procedures_dir),
    }


def by_dimension(document: dict, name: str) -> dict:
    for dimension in document.get("dimensions") or []:
        if dimension["dimension"] == name:
            return dimension
    return {}


def render(document: dict) -> str:
    """The coverage report as a document a reviewer reads."""
    out: list[str] = []
    add = out.append

    add("# Coverage")
    add("")
    add("<!-- GENERATED FILE — DO NOT EDIT BY HAND.")
    add(f"     Generated:  {document['generated_utc']}")
    add(f"     Source:     {', '.join(document['roots'])}")
    add("     Regenerate: python3 -m argazui coverage --runs runs "
        "--out docs/coverage.md")
    add("     Any edit here is overwritten by the next CI run. -->")
    add("")
    add(f"Computed from **{document['runs_read']}** recorded run(s) and the "
        f"procedure files in this checkout, at **{document['generated_utc']}**.")
    add("")
    add("**This is not a test count.** A test count goes up when somebody adds "
        "a test and never goes down when somebody adds an aircraft, a "
        "procedure or a criterion nobody runs. Every dimension below is "
        "measured over named things that could be exercised, and every one of "
        "them lists what it did not reach.")
    add("")

    add("| Dimension | Covered | Declared | |")
    add("|---|---:|---:|---|")
    for dimension in document["dimensions"]:
        fraction = ("—" if dimension["fraction"] is None
                    else f"{dimension['fraction'] * 100:.0f}%")
        add(f"| {dimension['label']} | {dimension['covered']} "
            f"| {dimension['declared']} | {fraction} |")
    add("")

    for dimension in document["dimensions"]:
        name = dimension["dimension"]
        add(f"## {dimension['label']}")
        add("")
        add(WHAT[name]["en"])
        add("")
        if name == CRITERIA and document.get("unattributable_criteria"):
            add(f"**{document['unattributable_criteria']} evaluated "
                f"criterion result(s) could not be attributed to a declared "
                f"criterion.** They come from runs recorded before criterion "
                f"identifiers existed (ArgazUI v1.5). They are not matched by "
                f"position — the procedure may have been edited since, and a "
                f"coverage figure inflated by a guess is the thing this "
                f"project exists to remove. Fly the procedures once more to "
                f"cover them.")
            add("")
        if not dimension["declared"]:
            add("Nothing is declared in this dimension, so there is nothing to "
                "cover. That is not the same as full coverage, and it is not "
                "reported as a percentage.")
            add("")
            continue
        if not dimension["uncovered"]:
            add(f"All {dimension['declared']} covered.")
            add("")
        else:
            add(f"**{len(dimension['uncovered'])} of {dimension['declared']} "
                f"not covered:**")
            add("")
            add("| Item | What it is |")
            add("|---|---|")
            for item in dimension["items"]:
                if item["covered"]:
                    continue
                add(f"| `{item['id']}` | {item.get('what', '')} |")
            add("")

    add("## What a covered item does and does not mean")
    add("")
    add("Covered means *some recorded run exercised this and produced a "
        "result*. It does not mean the result was a pass, it does not mean the "
        "item was exercised recently, and it does not mean it was exercised "
        "more than once — see [status.md](status.md) for verdicts and "
        "[campaigns.md](campaigns.md) for repetition.")
    add("")
    add("An **uncovered** item is the more useful entry. It is something this "
        "project declares and has never run, which is exactly the gap a "
        "verification claim must not be read across.")
    add("")

    # THE MATRIX, IN THE SAME DOCUMENT AND NOT A SECOND ONE (v1.7)
    # ------------------------------------------------------------
    # "Covered" is one bit, and the fractions above are the right summary of
    # it. What they cannot say is whether a declared mechanism is even
    # EXECUTABLE, or whether a run that exercised one ever judged the result —
    # and those are the two questions that separate a mechanism this project
    # has proven from one it has merely written down. The matrix answers them
    # per mechanism, here, rather than in a report of its own that would drift
    # from this one within a release.
    matrix = document.get("mechanism_matrix")
    if matrix:
        add(mechanisms.render(matrix))
    return "\n".join(out).rstrip() + "\n"


def generate(runs_roots: list[Path], out: Path,
             procedures_dir: Optional[Path] = None,
             experiments_dir: Optional[Path] = None) -> str:
    document = collect(runs_roots, procedures_dir,
                       experiments_dir=experiments_dir)
    text = render(document)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return text
