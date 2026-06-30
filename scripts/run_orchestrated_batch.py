"""Build a fault-tolerant orchestration board for an existing source queue."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ecfinder.orchestration.progress_report import write_reports
from ecfinder.orchestration.status_board import build_board


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--queue", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    queue_path = ROOT / args.queue
    if not queue_path.exists():
        raise SystemExit(f"missing queue: {queue_path}")
    result = build_board(ROOT, args.batch_id, queue_path)
    summary = write_reports(ROOT, validation_passed=False)
    payload = {
        "batch_id": args.batch_id,
        "sources": len(result["records"]),
        "events": len(result["events"]),
        "errors": len(result["errors"]),
        "retries": len(result["retries"]),
        "manual_handoffs": len(result["handoffs"]),
        "can_resume": result["checkpoint"]["can_resume"],
        "ready_for_next_batch": summary["ready_for_next_batch"],
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
