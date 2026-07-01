"""Discover runnable closed-loop agent tasks without reading raw full text."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ecfinder.orchestration.task_executor import discover_stage2_4j_tasks, write_runnable_report


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-id", default="stage2_4j")
    args = parser.parse_args()
    runnable = discover_stage2_4j_tasks(ROOT, args.batch_id)
    write_runnable_report(ROOT, args.batch_id, runnable)
    print(json.dumps({"batch_id": args.batch_id, "runnable_tasks": len(runnable)}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
