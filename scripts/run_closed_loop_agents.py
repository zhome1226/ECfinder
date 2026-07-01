"""Run the autonomous closed-loop multi-agent executor."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ecfinder.orchestration.closed_loop_executor import ClosedLoopExecutor


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-id", default="stage2_4j")
    parser.add_argument("--until-idle", action="store_true")
    parser.add_argument("--max-cycles", type=int, default=50)
    args = parser.parse_args()
    executor = ClosedLoopExecutor(ROOT, args.batch_id, max_cycles=args.max_cycles)
    executor.run_until_idle()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
