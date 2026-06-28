from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "ecfinder.cli", *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )


def test_pipeline_preflight_runs() -> None:
    run_cli("pipeline-preflight")


def test_pipeline_validate_clean_runs() -> None:
    run_cli("pipeline-validate-clean")


def test_pipeline_status_runs() -> None:
    result = run_cli("pipeline-status")
    assert "status: completed" in result.stdout
    assert "record_count: 9" in result.stdout
