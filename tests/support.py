"""Shared helpers for the tier-1 suite: a booted SITL wired to ArgazUI.

WHY THIS IS NOT IN conftest.py
------------------------------
It used to be, and tests imported it as `from conftest import boot`. That works
only for as long as exactly one `conftest.py` is reachable as a top-level
module — and there are two, `tests/` and `tests/e2e/`, both on the path. Which
one wins depends on collection order, so the suite passed on a developer
machine and failed inside the tier-1 image with

    ImportError: cannot import name 'boot' from 'conftest'
                 (/opt/argaz/tests/e2e/conftest.py)

Helpers live in named modules now. `conftest.py` holds fixtures and hooks,
which pytest loads by path and never by import, so nothing collides.
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

from argazui.mavlink_link import MavlinkLink                 # noqa: E402
from argazui.procrunner import probe_capabilities            # noqa: E402
from argazui.runs import RunRecorder                         # noqa: E402

import sitl as sitl_mod                                      # noqa: E402

# Where the suite writes its run directories. Separate from the interactive
# runs/ tree by default so a test sweep does not bury a real flight, but the
# format is identical and `argazui report` reads either.
TEST_RUNS_ROOT = Path(os.environ.get("ARGAZ_TEST_RUNS", ROOT / "runs" / "tests"))

def _tier_of_this_run() -> str:
    """Which tier this pytest invocation is running, from its own -m filter.

    WHY THE RECORD IS PER TIER
    --------------------------
    `suite.json` was ONE file that every run overwrote. Running tier 1 after
    tier 2 therefore destroyed the tier-2 record — and because
    `argazui fleet validate` reads model eligibility from exactly that record,
    a fleet that had been validated by a real flight silently reverted to
    "untested" partway through v1.3's phase 5. Nothing was wrong with the
    fleet; the evidence had been deleted by an unrelated test run.

    CI never hit this because each workflow uploads its own artefact. A
    developer's machine has one directory, so the tiers have to name
    themselves.
    """
    marker = ""
    argv = sys.argv
    for index, arg in enumerate(argv):
        if arg == "-m" and index + 1 < len(argv):
            marker = argv[index + 1]
        elif arg.startswith("-m") and len(arg) > 2:
            marker = arg[2:]
    for tier in ("fleet_gazebo", "fleet_sitl", "tier2", "tier1", "e2e"):
        if tier in marker:
            return tier
    return "mixed"


# Machine-readable outcome of one suite run. `docs/status.md` is generated from
# these and nothing else, so a test that did not execute cannot appear there
# as a pass.
#
# One file PER TIER: a tier-1 run must not be able to delete a tier-2 result.
SUITE_REPORT = Path(os.environ.get(
    "ARGAZ_TEST_REPORT",
    TEST_RUNS_ROOT / _tier_of_this_run() / "suite.json"))


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
         extra_params: Optional[list[Path]] = None,
         mirror_port: int = 0) -> Vehicle:
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
                       on_log=lambda text: recorder.console(text.encode()),
                       mirror_port=mirror_port)
    link.start(vehicle=model["vehicle"])

    vehicle = Vehicle(sitl, link, recorder, model)

    def _teardown() -> None:
        link.stop()
        sitl.stop()
        recorder.finish(wait=True)

    request.addfinalizer(_teardown)

    if not link.wait_ready(timeout=sitl_mod.CONNECT_TIMEOUT):
        pytest.fail(f"no MAVLink heartbeat from {sitl.connection} within "
                    f"{sitl_mod.CONNECT_TIMEOUT:.0f}s\n{sitl.tail()}")
    return vehicle


def read_result(recorder: RunRecorder) -> dict:
    """The run's own result.json, as anything else would read it."""
    path = recorder.dir / "result.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
