# Evidence manifest

Every run writes `evidence.json`: what it was **expected** to leave behind, and
what actually happened to each artefact.

## Why

A run directory is a pile of files. Whether it is a *complete* pile used to be
something a reader worked out by remembering what ought to be in one — and the
failure mode is quiet. A report that was never generated, a plot directory that
is empty, a parameter dump the analysis skipped: every one of those leaves a
directory that looks fine, and every one of them means a claim somewhere rests
on evidence nobody can open.

## Three levels of expectation

| level | meaning |
|---|---|
| `required` | the run is not evidence without it. Absent → an [`evidence` failure](failure-classification.md). |
| `conditional` | required only when a stated condition held |
| `optional` | absent is fine — **but only with a stated reason** |

### The conditional one

The dataflash log is required *if the vehicle armed*, and not otherwise.
ArduPilot ships `LOG_DISARMED=0`, so a session that never armed writes no log
and nothing was lost. Demanding one would report a healthy run as missing its
evidence.

The manifest records both levels: `level_declared` (`conditional`) and `level`
as applied to this run (`required`, because the vehicle armed). A reviewer needs
both — "required because the vehicle armed" and "required always" are different
statements about the same row.

### The optional one, which is the point

An optional artefact that is absent **with no reason recorded** is listed as
`absent_unexplained`.

> "There are no plots because matplotlib is not installed" and "there are no
> plots" are different facts, and only the first is an answer.

This is the same rule the project applies to a metric that could not be
measured and to a [fingerprint](reproducibility.md) field that could not be
read. Absence with a reason is evidence; absence without one is a gap.

## What is recorded per artefact

| field | |
|---|---|
| `path` | relative to the run directory |
| `type` | MIME type, or `directory` |
| `level` / `level_declared` | as applied to this run, and as declared |
| `exists` | whether it is actually there |
| `size_bytes` | |
| `hash` | `sha256:…`, or `null` with `hash_absent_reason` |
| `producer` | which module wrote it |
| `producer_schema` | that module's schema version |
| `absent_reason` | why it is not there, when it is not |
| `purpose` | what it is for, in a sentence |

The **producer** matters as much as the hash. A `result.json` written by schema
3 and one written by schema 5 are both valid and carry different fields, and a
reviewer comparing two runs has to see which they are looking at without
opening either.

## Two things are deliberately not hashed

**`result.json`** is rewritten when the flight report completes — the advisory
count, the metrics and the build record only exist once the dataflash log has
been read. A hash taken at any one of those moments is wrong at the others, and
a hash that is *sometimes* wrong is worse than an honest absence: it would fail
an integrity check for a run that is perfectly intact. Its presence, size and
schema are recorded instead.

**The copy embedded in the flight report** carries no hashes at all. The report
is itself one of the artefacts the manifest describes, so a manifest inside it
is taken before its own last write. Keeping the digests there would mean two
documents disagreeing about the digest of a third, for no reason but the order
they were written in. They live in exactly one place: `evidence.json`.

That is also why the manifest is captured **twice** — once after the report is
written, and once more after section 7 has been filled in. Nothing embedded in
the report carries a hash, so both captures embed identical content and the
second pass changes only the digests, which is where they belong.

Files above 256 MB are recorded present and unhashed, with the size stated. A
hash nobody waited for is not a hash.

## Reading it

```bash
python3 -c "import json;print(json.load(open('runs/<id>/evidence.json'))['complete'])"
python3 -m argazui trace runs/<id>      # includes the manifest's problems
```

In the browser, the run sheet shows a **Evidence manifest** block above the
report — complete, or naming what is missing.

`report.md` section 7 renders the same table.

## What a complete manifest does and does not mean

Complete means every **required** artefact is in the directory. It does not
mean the run passed, it does not mean the artefacts are correct, and it does
not mean anything about the aircraft. It means the evidence for whatever the
run does claim is actually there to be read.

The evidence manifest was added in ArgazUI v1.5.
