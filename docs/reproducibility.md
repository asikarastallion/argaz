# Configuration & reproducibility

Every run captures a machine-readable manifest of what produced it:
`runs/<id>/fingerprint.json`, also embedded in `result.json` and rendered as
the **Environment** section of `report.md`.

## Why a manifest and not just versions.txt

`versions.txt` already answered "which software?" as a flat list of strings for
a human to read. That is enough to look at and not enough to compare.

Two runs of the same model can differ by an ArduPilot commit, an edited
procedure, a changed parameter file or a different Gazebo. Unless each run
states all of them in a form a program can line up, a comparison between them
is a guess wearing a table. The fingerprint is what lets
[Regression](regression.md) say *"these two are comparable"* instead of
assuming it.

## Fields

| field | what it records |
|---|---|
| `argaz` | ArgazUI version, the repository commit, `git describe`, and whether the tree had uncommitted changes |
| `ardupilot.commit` | HEAD of the configured ArduPilot checkout |
| `ardupilot.firmware` | what the binary says about itself, from the log's `VER`/`MSG` record |
| `ardupilot.firmware_commit` | the commit hash embedded in that string |
| `ardupilot.firmware_matches_checkout` | `true`, `false`, or `null` when there is nothing to compare |
| `sitl_models` | HEAD of the SITL_Models checkout, when it is one |
| `gazebo.version` | the first line of `gz sim --version` |
| `ros.distro` | `ROS_DISTRO` as the server saw it |
| `runtime` | Python, the interpreter path, pymavlink, the platform |
| `model.config_hash` | SHA-256 over the model's registry entry **and every parameter file it names** |
| `procedure_hash` | SHA-256 over every procedure that ran, from the verbatim YAML the run recorded |
| `procedures[]` | per procedure: its id, its declared schema, and its own hash |
| `config` | the resolved ArgazUI configuration — roots, ports, config file |
| `unknown[]` | every field that could not be determined, each with a reason |

### `firmware_matches_checkout` has three answers

`null` is a real third answer and not a soft "no". A report generated from a
log alone, with no checkout available, genuinely cannot say whether the binary
matches a source tree — and must not claim a match. When it is `false`, the run
was flown by a stale binary and comparing it against another run is meaningless
until that is resolved; the flight report raises it as an advisory rather than
leaving it for someone to notice.

## Unknown is an answer, and it comes with a reason

No field is ever filled in with something plausible. A component that cannot be
identified is `null`, and the reason appears in `unknown`:

```json
{"field": "sitl_models.commit", "reason": "/opt/SITL_Models is not a git checkout"}
{"field": "gazebo.version", "reason": "unavailable: [Errno 2] No such file or directory: 'gz'"}
```

A fingerprint that quietly omitted the field would read exactly like one taken
on a machine where the component was fine. The whole point of the manifest is
that those two situations must not look the same.

## Why content hashes as well as commits

Commits only move at a commit boundary. The two inputs that change most often
move no version number at all when they do:

- **the procedures that were executed**, hashed from the YAML the run recorded
  verbatim — not from the file on disk, which may already have been edited
  since;
- **the model's parameter files**, because a changed `.param` changes the
  aircraft without changing any commit anywhere.

## Identity fields

These fields decide whether two runs may be compared on their numbers. Each is
a thing that changes what the aircraft or the test *is*, as opposed to how well
it did:

| field | what a change in it means |
|---|---|
| `model.config_hash` | the registry entry or a parameter file changed — a different aircraft |
| `procedure_hash` | the flow or an acceptance criterion changed — a different test |
| `ardupilot.commit` | a different ArduPilot checkout |
| `ardupilot.firmware_commit` | a different binary actually flew |
| `ardupilot.dirty_digest` | different uncommitted changes in ArduPilot |
| `gazebo.version` | a different simulator — half the physics |

A difference in any of them makes a comparison `incomparable` unless it is
overridden explicitly. So does an *unknown* value on either side: that is not a
claim that the runs differ, it is a statement that nothing here can show they
are the same.

The last two were added by the v1.6 corrective release. Both were already
captured and neither was compared, so two runs across a Gazebo upgrade — or
across two different sets of uncommitted ArduPilot changes — reported
themselves as the same configuration.

`argaz.dirty_digest` is captured and deliberately **not** compared, for the
same reason `argaz.commit` is not: ArgazUI's own source is the harness rather
than the aircraft, and comparing one without the other would be half a rule.

### A component that is absent from both runs is not a difference

An unknown identity field is normally reported as a difference — nothing shows
the two runs are the same, which is exactly what a comparison must not be made
silently across. That reading is wrong when the component is absent from the
environment entirely: tier 1 has no Gazebo by design, so both runs report
`null` for the same structural reason and the field discriminates nothing.

`gazebo.version` is therefore exempt when it is unknown on **both** sides, and
only then; unknown on one side remains a real asymmetry and is still reported.
The exemption is a named set (`OPTIONAL_IDENTITY`), not a general rule —
`ardupilot.firmware_commit` is also null on both sides of a tier-1 comparison,
and that has always been, and remains, incomparable.

### Why `dirty` is a digest and not a flag

A commit does not identify a working tree. `dirty: true` says a tree had edits
and cannot say *which*, so two runs flown from two different states of work in
progress had the same identity — while two runs flown minutes apart from ONE
dirty tree are perfectly comparable and must not be refused. A boolean cannot
express both; a content digest of the uncommitted work can. A clean checkout
reports the literal `clean`, which is a determination rather than the absence
of one, so it is not `null`.

The digest covers the diff of tracked files and the NAMES of untracked ones.
Untracked content is deliberately not hashed: it can be an entire build tree,
and the cost of reading it would land on every run to catch a case that
`model.config_hash` already covers.

## Two passes per run

The manifest is captured twice, for the same reason `versions.txt` is written
twice: the firmware string only exists once the dataflash log has been parsed.
The first pass runs at STOP, so a session that produced no log still says what
it ran on; the second replaces it once the log has been read.
