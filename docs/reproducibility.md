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

Four of these fields decide whether two runs may be compared on their numbers.
Each is a thing that changes what the aircraft or the test *is*, as opposed to
how well it did:

- `model.config_hash`
- `procedure_hash`
- `ardupilot.commit`
- `ardupilot.firmware_commit`

A difference in any of them makes a comparison `incomparable` unless it is
overridden explicitly. So does an *unknown* value on either side: that is not a
claim that the runs differ, it is a statement that nothing here can show they
are the same.

## Two passes per run

The manifest is captured twice, for the same reason `versions.txt` is written
twice: the firmware string only exists once the dataflash log has been parsed.
The first pass runs at STOP, so a session that produced no log still says what
it ran on; the second replaces it once the log has been read.
