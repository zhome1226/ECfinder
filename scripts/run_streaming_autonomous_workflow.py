"""Run Stage 2.6c streaming autonomous workflow."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ecfinder.orchestration.streaming_supervisor import run_streaming_supervisor


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run streaming title/abstract-to-reviewed-database workflow.")
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--metadata-queue", required=True)
    parser.add_argument("--mode", required=True, choices=["title_abstract_to_database"])
    parser.add_argument("--until-idle", action="store_true")
    parser.add_argument("--max-screen", type=int, default=100)
    parser.add_argument("--max-fulltext", type=int, default=20)
    parser.add_argument("--max-extract-sources", type=int, default=10)
    args = parser.parse_args()
    summary = run_streaming_supervisor(
        ROOT,
        args.batch_id,
        ROOT / args.metadata_queue,
        args.max_screen,
        args.max_fulltext,
        args.max_extract_sources,
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
