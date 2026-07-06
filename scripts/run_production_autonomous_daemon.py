"""Run Stage 2.7 production autonomous daemon."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ecfinder.orchestration.production_daemon import run_production_daemon


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_METADATA_QUEUE = ROOT / "data" / "batches" / "stage2_6b_zotero_metadata_screening_queue.jsonl"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run production autonomous PFAS literature daemon.")
    parser.add_argument("--library", required=True, choices=["zotero"])
    parser.add_argument("--mode", required=True, choices=["title_abstract_to_database"])
    parser.add_argument("--until-library-exhausted", action="store_true")
    parser.add_argument("--checkpoint-every", type=int, default=25)
    parser.add_argument("--rescan-zotero-attachments-every-cycle", action="store_true")
    parser.add_argument("--max-wall-minutes", type=int, default=None)
    parser.add_argument("--max-records", type=int, default=None)
    parser.add_argument("--max-new-screen", type=int, default=300)
    parser.add_argument("--max-new-fulltext", type=int, default=80)
    parser.add_argument("--max-new-extract-sources", type=int, default=40)
    parser.add_argument("--safe-stop-on-token-budget", action="store_true")
    parser.add_argument("--token-budget", type=int, default=None)
    parser.add_argument("--stop-file", type=Path, default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--metadata-queue", type=Path, default=DEFAULT_METADATA_QUEUE)
    args = parser.parse_args()
    metadata_queue = args.metadata_queue if args.metadata_queue.is_absolute() else ROOT / args.metadata_queue
    summary = run_production_daemon(
        ROOT,
        batch_id="stage2_7_production_daemon",
        metadata_queue=metadata_queue,
        library=args.library,
        mode=args.mode,
        until_library_exhausted=args.until_library_exhausted,
        checkpoint_every=args.checkpoint_every,
        rescan_zotero_attachments_every_cycle=args.rescan_zotero_attachments_every_cycle,
        max_wall_minutes=args.max_wall_minutes,
        max_records=args.max_records,
        max_new_screen=args.max_new_screen,
        max_new_fulltext=args.max_new_fulltext,
        max_new_extract_sources=args.max_new_extract_sources,
        safe_stop_on_token_budget=args.safe_stop_on_token_budget,
        token_budget=args.token_budget,
        stop_file=args.stop_file,
        resume=args.resume,
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
