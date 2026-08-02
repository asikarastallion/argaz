"""Shared fixtures for the ArgazUI regression suite.

WHAT THESE TESTS ARE FOR
------------------------
They run the *same* procedure YAML the UI buttons run, through the *same*
`ProcedureRunner`, against a *real* SITL binary, and they record their results
into the *same* `runs/` directories the UI produces. There is no second
implementation of a takeoff and no simulated autopilot, so a green test means
a working button. That equivalence is the whole reason the suite exists.

TIERS
-----
`tier1`  SITL's own frames, no Gazebo. Verifies procedure logic: capability
         probing picks the right procedure, acceptance criteria are evaluated
         against measured state, declared overrides are applied and restored,
         and a run directory comes out complete and parseable.

         **Tier 1 makes no claim about any Gazebo model.** A green tier-1 run
         does not mean "Skywalker X8 works"; it means the plane procedure works
         on SITL's plane frame. Blurring that would make the status table a
         lie, which is the exact failure this whole version exists to fix.

`tier2`  Gazebo + the real model set. This is the only tier whose results may
         be reported against a model in `docs/status.md`.

SKIPS ARE NOT PASSES
--------------------
Missing binary, missing Gazebo, missing model: the test skips, and the status
generator records the model as `untested`. Nothing here ever reports success
for something it did not fly.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

import pytest

# The package lives in argazui/, one level below the repository root.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "argazui"))

from argazui import paths                                    # noqa: E402
from argazui.mavlink_link import MavlinkLink                 # noqa: E402
from argazui.procrunner import probe_capabilities            # noqa: E402
from argazui.runs import RunRecorder                         # noqa: E402

import sitl as sitl_mod                                      # noqa: E402

# Where the suite writes its run directories. Separate from the interactive
# runs/ tree by default so a test sweep does not bury a real flight, but the
# format is identical and `argazui report` reads either.
TEST_RUNS_ROOT = Path(os.environ.get("ARGAZ_TEST_RUNS", ROOT / "runs" / "tests"))


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "tier1: real SITL, no Gazebo — verifies procedure logic only")
    config.addinivalue_line(
        "markers", "tier2: real SITL + Gazebo — the only tier that verifies a model")


@pytest.fixture(scope="session")
def runs_root() -> Path:
    TEST_RUNS_ROOT.mkdir(parents=True, exist_ok=True)
    return TEST_RUNS_ROOT


class Vehicle:
    """A booted SITL plus the ArgazUI link and recorder wired to it.

    This is the test-side equivalent of pressing START in the browser: same
    `MavlinkLink`, same `RunRecorder`, same capability probe. Only the
    transport differs — TCP straight to SITL instead of MAVProxy's UDP fan-out
    — and `MavlinkLink` was built to take either.
    """

    def __init__(self, sitl, link: MavlinkLink, recorder: RunRecorder,
                 model: dict) -> None:
        self.sitl = sitl
        self.link = link
        self.recorder = recorder
        self.model = model
        self._caps: Optional[dict] = None

    @property
    def capabilities(self) -> dict:
        if self._caps is None:
            self._caps = probe_capabilities(self.link, vehicle=self.model["vehicle"])
        return self._caps

    def wait_prearm(self, timeout: float = sitl_mod.PREARM_TIMEOUT) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.link.state.prearm_known and self.link.state.prearm_ok:
                return True
            time.sleep(0.5)
        return False


def boot(request, runs_root: Path, model: dict, frame: str,
         extra_params: Optional[list[Path]] = None) -> Vehicle:
    """Starts SITL for `model`, connects, and registers teardown.

    Teardown order matters and mirrors the UI's STOP: the link is closed, then
    SITL is asked to exit so it flushes its dataflash log, and only then is the
    run finalised — otherwise the `.BIN` copied into the run directory would be
    truncated.
    """
    work_dir = Path(request.config.rootpath) / "argazui" / "run" / f"test_{model['id']}"
    recorder = RunRecorder(model=model, root=runs_root, work_dir=work_dir,
                           launch_commands=[f"# pytest: {request.node.name}"])

    try:
        sitl = sitl_mod.start(model["vehicle"], frame, work_dir,
                              extra_params=extra_params)
    except sitl_mod.SitlUnavailable as exc:
        recorder.event({"kind": "skipped", "reason": str(exc)})
        recorder.finish(report=False)
        pytest.skip(str(exc))

    link = MavlinkLink(connection=sitl.connection, on_event=recorder.event,
                       on_log=lambda text: recorder.console(text.encode()))
    link.start(vehicle=model["vehicle"])

    vehicle = Vehicle(sitl, link, recorder, model)

    def _teardown() -> None:
        link.stop()
        sitl.stop()
        recorder.finish()

    request.addfinalizer(_teardown)

    if not link.wait_ready(timeout=sitl_mod.CONNECT_TIMEOUT):
        pytest.fail(f"no MAVLink heartbeat from {sitl.connection} within "
                    f"{sitl_mod.CONNECT_TIMEOUT:.0f}s\n{sitl.tail()}")
    return vehicle


def read_result(recorder: RunRecorder) -> dict:
    """The run's own result.json, as anything else would read it."""
    path = recorder.dir / "result.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
