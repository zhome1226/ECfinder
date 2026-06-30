"""Inspect retry queue entries without mutating source artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ecfinder.orchestration.recovery import dry_run_retry_plan


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.dry_run:
        raise SystemExit("retry execution is intentionally disabled; use --dry-run")
    plan = dry_run_retry_plan(ROOT)
    print(json.dumps({"dry_run": True, "retry_actions": len(plan), "plan": plan}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
