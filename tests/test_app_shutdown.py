from __future__ import annotations

import asyncio

import pytest

from argazui import app as appmod

pytestmark = pytest.mark.tier1


def test_stop_passes_wait_flag_to_run_finish():
    manager = appmod.Manager()

    class _Run:
        def __init__(self):
            self.wait = None
            self.run_id = "run-1"
            self.dir = "."

        def finish(self, wait=False):
            self.wait = wait
            return {"status": "passed"}

    class _Term:
        def is_alive(self):
            return False

        def stop_children(self, log=None):
            return []

    class _Mav:
        def stop(self):
            return None

    run = _Run()
    manager.run = run
    manager.sim = _Term()
    manager.shell = _Term()
    manager.mav = _Mav()

    manager.stop(wait_for_report=True)
    assert run.wait is True


def test_shutdown_waits_for_report_before_process_exit(monkeypatch):
    calls: list[bool] = []

    class _Stop:
        def stop(self):
            return None

    class _Close:
        def close(self):
            return None

    class _Mgr:
        active_model = {"id": "quad"}
        run = object()
        mav = _Stop()
        sim = _Close()
        shell = _Close()

        def stop(self, wait_for_report=False):
            calls.append(wait_for_report)
            return {"ok": True}

    monkeypatch.setattr(appmod, "mgr", _Mgr())
    asyncio.run(appmod._shutdown())

    assert calls == [True]
