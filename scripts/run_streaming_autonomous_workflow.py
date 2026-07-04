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
    parser.add_argument("--resume-from", default="")
    parser.add_argument("--max-new-screen", type=int)
    parser.add_argument("--max-new-fulltext", type=int)
    parser.add_argument("--max-new-extract-sources", type=int)
    parser.add_argument("--output-prefix", default="")
    args = parser.parse_args()
    output_prefix = args.output_prefix
    if not output_prefix:
        output_prefix = "stage2_6d_streaming" if args.batch_id.startswith("stage2_6d") else "stage2_6c_streaming"
    summary = run_streaming_supervisor(
        ROOT,
        args.batch_id,
        ROOT / args.metadata_queue,
        args.max_new_screen if args.max_new_screen is not None else args.max_screen,
        args.max_new_fulltext if args.max_new_fulltext is not None else args.max_fulltext,
        args.max_new_extract_sources if args.max_new_extract_sources is not None else args.max_extract_sources,
        output_prefix=output_prefix,
        resume_from=ROOT / args.resume_from if args.resume_from else None,
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
