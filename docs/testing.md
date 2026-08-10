# Development and testing

## The rule the suite is built on

The tests run the **same** procedure YAML the UI buttons run, through the
**same** `ProcedureRunner`, against a **real** SITL binary, and they record
their results into the **same** `runs/` directories the interface produces.

There is no second implementation of a takeoff and no simulated autopilot
anywhere in the suite. That equivalence is the whole reason it exists: a green
test means a working button.

## Markers

| marker | needs | may claim |
|---|---|---|
| `tier1` | a built SITL binary. Also covers the pure-unit tests, which need nothing. | procedure logic, the API, the page |
| `tier2` | SITL **and** Gazebo **and** the model assets | one specific model |
| `e2e` | the server as a process, plus headless Chromium | what a user's browser sees |
| `container_only` | the tier image | reported as *unverified* when skipped elsewhere |

```bash
python3 -m pytest tests/ -m tier1 -q
python3 -m pytest tests/ -m tier2 -q -k skywalker
python3 -m pytest tests/ -m e2e -q
python3 -m pytest tests/test_temporal_criteria.py -q    # no vehicle, milliseconds
```

Install the test dependencies with `pip install -r argazui/requirements-test.txt`,
then `python3 -m playwright install chromium` for the e2e layer.

## Skips are not passes

Missing binary, missing Gazebo, missing model: the test **skips**, with a
reason, and the status generator records the model as `untested`. Nothing in
this suite ever reports success for something it did not fly.

Each run writes `runs/tests/suite.json` recording every phase — including a
skip during setup, which collapsing to `report.passed` would count as nothing
at all. "Nothing at all" is exactly the gap a status table fills in with a
guess.

The terminal summary names what the environment did **not** verify before
anyone reads a total, because a green summary line is read as "everything
works".

## One retry, and it is never silent

A procedure is allowed one retry: SITL genuinely is timing-sensitive on a
loaded machine, and an EKF that has not settled can refuse an arm that would
succeed ten seconds later. The retry costs something — `mark_flaky` makes the
run report as `flaky` in [status.md](status.md) rather than `passed`, and every
attempt stays in `result.json`. Retrying quietly until green is precisely the
behaviour this project exists to prevent.

## Off-nominal tests, and where each half lives

Fault injection is verified in two places on purpose, because the two questions
are different and only one of them needs an aircraft.

| file | proves |
|---|---|
| `tests/test_faults.py` | the *mechanism*: it probes before it writes, restores what it changed, drops the packets it claims to, and refuses a declaration that would inject nothing. Uses a recording stand-in link; runs in milliseconds. |
| `tests/test_tier1_faults.py` | the mechanism against a *real* ArduPilot: the parameter exists, the write is accepted, the aircraft is degraded for the declared window, the value comes back, and the run record separates the injection from the response from the verdict. |
| `tests/test_tier2_models.py` | one off-nominal scenario on a *real airframe in Gazebo* — the one thing tier 1 cannot show. |

The tier-1 fault tests assert `applied is True` before they assert the outcome.
Without that, a scenario whose fault silently failed to inject would pass as a
nominal flight under an off-nominal name — which is the failure the fail-closed
rule exists to prevent, so the test has to check that the rule held rather than
assume it.

## Campaign tests, and why two runs

`tests/test_campaign.py` builds run directories rather than flying them. The
cases that matter are the ones a real campaign produces rarely and at the worst
moment — a flaky run that must not become a pass, an iteration that never
started, a procedure edited half way through — and constructing those is exact
and takes milliseconds.

`tests/test_tier1_campaign.py` flies a real one, with **two** iterations rather
than the default five. Two is the smallest number that can show what that test
is for: that the runs are genuinely independent, with separate directories,
separate logs and separate indices. It is not a repeatability measurement and
does not claim to be one — the spread it would report from two runs is exactly
the one `campaign.statistics` refuses to print.

It also generates each iteration's flight report rather than skipping it. The
report is what fills in the firmware identity, and without it the campaign's
own consistency check correctly reports every iteration as "firmware unknown on
at least one side" — a true answer to a question the test was not asking.

## Experiment tests, and why one run per arm

The same split, one layer up. `tests/test_experiments.py` is mostly *refusals*,
because an experiment file is read once and then produces a document somebody
reviews as evidence — and every mistake the validator lets through becomes a
sentence in that document which is confidently wrong. None of them crash. All
of them render.

`tests/test_experiment_analysis.py` is the arithmetic over run directories, the
order the verdict is decided in, and what the document refuses to print.

`tests/test_tier1_experiment.py` flies a real two-arm experiment with **one**
run per arm. It exists to check the one thing neither of the others can: that
what comes out is two *ordinary* run directories, each with its own dataflash
log and fingerprint, each stamped with **both** its campaign and its
experiment, and that the analysis finds them by reading the runs alone. It is
not a controlled comparison — n=1 on both sides is exactly the case the
analysis marks `indicative` rather than `measured`, and the test asserts that
it does.

## Why there is no `pytest-timeout`

Every flight is already bounded from two directions: each procedure carries its
own `timeout:` ceiling, and `tests/sitl.py` gives up if SITL never opens its
port. The CI jobs set `timeout-minutes` on top. Adding a plugin to repeat that
would be a dependency for nothing.

## The e2e layer, and why it exists

Every tier-1 test drives `RunRecorder` and `ProcedureRunner` directly. That is
the right way to test procedure logic, and it is why they were all green while
the application was unusable in a browser: FastAPI, the WebSocket and the page
were never exercised at all. A user found that regression.

So the e2e tests do only what a user does — start the server as a process, open
the page in headless Chromium, assert on what the browser sees. **First of all,
that the console is clean.** An "e2e test" that drove the page without watching
the console would have passed straight through the regression it exists to
catch: the page looked populated, and the only evidence was an uncaught
`TypeError`.

Each e2e server runs from a throwaway copy of `argazui/`, so tests that need
genuine drift — an edited `.py`, a touched procedure — create it without ever
writing into the checkout.

## A failing test that is kept failing

`sitl_tailsitter` fails tier 1, deliberately. The frame arms, changes mode,
obeys the throttle and climbs past 20 m while tumbling; ArduPilot's own test
suite lists it as *"unstable in hover; unflyable in cruise"* and skips it.
Tuning the airframe until our own test passes would prove nothing, and marking
it `xfail` would make the failure invisible. See the comment in
`tests/test_tier1_procedures.py`.

## Adding a test

Put pure evaluator tests beside their subject
(`tests/test_temporal_criteria.py`, `tests/test_regression.py`) and mark them
`tier1` — the marker says which CI job runs them, not that they need a vehicle.
Tests that need a booted SITL use `support.boot()`, which is the test-side
equivalent of pressing START: same `MavlinkLink`, same `RunRecorder`, same
capability probe, with only the transport different.
