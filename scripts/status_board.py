"""Render the current orchestration status board as markdown reports."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ecfinder.orchestration.progress_report import render_status_board, write_reports
from ecfinder.state.common import read_jsonl


ROOT = Path(__file__).resolve().parents[1]
BOARD_PATH = ROOT / "data" / "state" / "source_status_board.jsonl"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", default="")
    parser.add_argument("--stage", default="")
    parser.add_argument("--failed-or-manual-only", action="store_true")
    return parser.parse_args()


def filtered_records(batch_id: str, stage: str, failed_or_manual_only: bool) -> list[dict]:
    records = read_jsonl(BOARD_PATH)
    if batch_id:
        records = [record for record in records if record.get("batch_id") == batch_id]
    if stage:
        records = [record for record in records if record.get("current_stage") == stage]
    if failed_or_manual_only:
        records = [
            record
            for record in records
            if record.get("overall_status") in {"manual_review", "failed_recoverable", "failed_terminal"}
        ]
    return records


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    summary = write_reports(ROOT, validation_passed=False)
    records = filtered_records(args.batch_id, args.stage, args.failed_or_manual_only)
    print(render_status_board(records))
    print(
        json.dumps(
            {
                "displayed_sources": len(records),
                "total_sources": summary["total_sources"],
                "manual_review_sources": summary["manual_review_sources"],
                "failed_recoverable_sources": summary["failed_recoverable_sources"],
                "failed_terminal_sources": summary["failed_terminal_sources"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
