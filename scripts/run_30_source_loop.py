"""Run the Stage 2.4 controlled 30-source PFAS evidence loop."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "run_batch_source_loop.py"),
        "--queue",
        "data/batches/stage2_4_30source_queue.jsonl",
        "--batch-id",
        "stage2_4",
        "--max-sources",
        "30",
    ]
    return subprocess.run(command, cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
