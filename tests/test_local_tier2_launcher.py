"""The documented local Tier 2 entry point must stay portable and reviewable."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


pytestmark = pytest.mark.tier1


def test_local_tier2_launcher_is_valid_bash_and_has_no_machine_path():
    root = Path(__file__).resolve().parents[1]
    launcher = root / "docker" / "run-tier2.sh"
    result = subprocess.run(["bash", "-n", str(launcher)], capture_output=True,
                            text=True, check=False)
    assert result.returncode == 0, result.stderr

    text = launcher.read_text(encoding="utf-8")
    assert "/home/" not in text
    assert 'root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"' in text
    assert "--network host" in text
    assert '"$root/runs:/opt/argaz/runs"' in text
    assert '"$root/argazui:/opt/argaz/argazui:ro"' in text
    assert '"$root/argazui/run:/opt/argaz/argazui/run"' in text
    assert "GZ_PARTITION" in text
