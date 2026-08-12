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
| `sitl_models.pin.identity` | different model assets — a different airframe |

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

## The pinned model environment

`ardupilot` has been pinned by SHA in both Dockerfiles since the first tier
image, and the reason is written there: an image that tracked a branch would
fly a different autopilot on every build, and no two CI results could be
compared. `SITL_Models` — the source of every airframe, world, mesh and
parameter file tier 2 exists to verify — was cloned at HEAD, so half the
environment was still moving.

The fingerprint has recorded `sitl_models.commit` since v1.3, so drift was
*visible after the fact*. That is not reproducibility: it tells a reader that
the experiment they are looking at cannot be repeated, which is later than they
needed to know.

### The declaration

```toml
[model_environment]
repository = "https://github.com/ArduPilot/SITL_Models.git"
revision   = "25bc38ed8c6c0345840159a8cbc0b02781d52f3c"
```

`ARGAZ_SITL_MODELS_REF` overrides it, following the same precedence chain every
other setting uses. `docker/Dockerfile.tier2` fetches that exact SHA and
asserts it at build time, and the suite checks that the two declarations agree
— two statements of one fact drift, and this one would drift silently.

**`revision` must be an exact commit SHA or an immutable tag.** `HEAD`, `main`,
`master`, `latest` and `current` are refused outright, because they name
whatever is there today, which is the one thing a pin may not mean. A
declaration naming one of them is a configuration error, not a pin.

### The six states

| state | meaning | usable | reproducible |
|---|---|:-:|:-:|
| `pinned` | declared, resolved, and they are the same | yes | **yes** |
| `unpinned` | nothing is declared; the run records the absence | yes | no |
| `modified` | the declared revision, with uncommitted edits on top | yes | no |
| `mismatch` | declared and resolved, and they differ | **no** | no |
| `unresolved` | declared, and the checkout cannot say what it is | **no** | no |
| `invalid` | the declaration names something that moves | **no** | no |

Two thresholds, because there are two questions. *Is the declaration being
honoured?* and *is this environment reproducible?* are not the same, and
collapsing them makes the check either useless or unusable.

`unpinned` is usable because a developer working without a declaration has
violated nothing — the run records the absence rather than inventing a pin.
`modified` is usable for the same reason `dirty` became a digest: the declared
revision *was* obtained, the edits on top of it are hashed into the identity,
so two runs with the same edits are still the same experiment. Refusing every
working tree with edits would make the mechanism unusable during exactly the
work it is most wanted for.

`python3 -m argazui doctor --release` demands `pinned` and nothing else, and
`tier2.yml` runs it before a single model is launched.

### The failure is an environment failure

A revision that cannot be obtained **does not fall back to HEAD**. The run
fails as a configuration problem, at the environment layer, before anything
flies — so no model is ever recorded `failed` for it, and no aircraft is
blamed for a checkout. See [Simulation lifecycle](simulation-lifecycle.md).

Nothing fetches, checks out or pulls. `modelenv.reconcile_command()` prints the
`git checkout` a person would run; it never runs it. A tool that rearranged its
own inputs so a check would pass has removed the check.

### What a run records

Inside the existing fingerprint, not in a second store:

```json
"sitl_models": {
  "commit": "25bc38ed8c6c0345840159a8cbc0b02781d52f3c",
  "pin": {
    "repository":      "https://github.com/ArduPilot/SITL_Models.git",
    "revision":        "25bc38ed8c6c0345840159a8cbc0b02781d52f3c",
    "revision_kind":   "commit",
    "resolved_commit": "25bc38ed8c6c0345840159a8cbc0b02781d52f3c",
    "identity":        "sha256:f12cd220cd53e7587ba770a49da0774e",
    "state": "pinned", "ok": true, "reproducible": true, "reason": ""
  }
}
```

`identity` is what the comparison uses rather than `commit`, because it folds
in the working-tree digest — the same reasoning that made `dirty_digest` an
identity field rather than `dirty`.

### A declared override is part of the aircraft

**The rule: the third-party checkout stays as upstream published it, and
project-specific vehicle configuration belongs in Argaz's declared override
layer.** A value Argaz needs and upstream does not set is Argaz's to declare,
not upstream's file to edit. An edit made in the checkout changes what flies
without changing any hash, and it exists only on the machine that made it.

`sitl_param_overrides` in `models.json` is written into a second
`--add-param-file` at every launch, applied after the model's own file so it
wins. It exists for parameters that can only take effect at boot and that the
upstream file gets wrong or leaves out — `swan_k1_hwing` needs `EK3_ENABLE=1`
because its file asks for `AHRS_EKF_TYPE=3` and leaves EK3 off.

`alti_transition_quad` is the second case. Upstream's
`Gazebo/config/alti_transition_quad.param` carries 33 `Q_*` parameters and
omits `Q_ENABLE`, the master switch that turns the QuadPlane subsystem on —
every other quadplane in that checkout sets it explicitly
(`skycat_tvbs`, `skywalker_x8_quad`, `swan_k1_hwing` all `Q_ENABLE 1`;
`wsc_aircraft` sets `Q_ENABLE 0` because it is a plane). Without it ArduPlane
ignores all 33 and the aircraft flies as a fixed wing under a VTOL's name.

For a while this repository carried it as an **uncommitted edit to the
third-party checkout**, which is the worst of the available places: it changed
what flew, it was invisible to `model.config_hash`, and it made the model
environment permanently `modified`. It is now declared in `models.json`, which
is versioned, reviewable and hashed.

Which is why `sitl_param_overrides` is in `MODEL_RECORD_KEYS`. It was applied
and not archived, so it was not in `model.config_hash` either: two runs flown
with different overrides — a quadplane and the fixed wing the same file
describes without them — compared as one configuration. Archiving it fixes both
halves at once, because the hash is taken over exactly what is archived. A
field the run does not store must not identify it, and a field that changes the
aircraft must be stored.

## Process and port isolation

Two runs that shared a port did not share an experiment. A crashed server used
to leave `gz sim`, SITL and MAVProxy holding 14550, and the next START bound
`udpin:14550` beside them and could receive the *previous* vehicle's telemetry
— a run whose evidence came from an aircraft nobody in it launched.

Every run now declares a boundary before it starts anything, and checks it
again after it stops:

```json
"isolation": {
  "session_id": 481923,
  "ports": {"mavlink": 14550, "script_mavlink": 14551, "plotjuggler": 14552},
  "conflicts_at_start": [],
  "released": true,
  "survivors": []
}
```

Ownership is established by the kernel — session id, process group id, and the
socket inode a port is held by — and never by a process name. A holder that
this run did not start is **reported and never signalled**: a developer running
their own SITL on 14550 in another terminal gets a clear message, not a dead
process. `pkill -f` is still never used, and the ownership layer has no way to
signal anything at all.

`released: true` is the claim that cleanup worked, and it is checked rather
than assumed — the processes are gone according to `/proc`, and the ports are
free according to a real bind.

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
