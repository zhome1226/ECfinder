"""Compatibility wrapper for the Stage 2 supervisor/orchestration validator."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "validate_orchestration_layer.py")], cwd=ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())
