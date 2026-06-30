"""Retry queue helpers for orchestration recovery."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ecfinder.state.common import read_jsonl


def dry_run_retry_plan(root: Path) -> list[dict[str, Any]]:
    retry_path = root / "data" / "state" / "retry_queue.jsonl"
    rows = read_jsonl(retry_path)
    plan: list[dict[str, Any]] = []
    for row in rows:
        if row.get("status") == "pending":
            plan.append(
                {
                    "retry_id": row.get("retry_id", ""),
                    "source_id": row.get("source_id", ""),
                    "stage": row.get("stage", ""),
                    "agent": row.get("agent", ""),
                    "attempt": row.get("attempt", 0),
                    "max_attempts": row.get("max_attempts", 0),
                    "action": "would_retry",
                }
            )
    return plan
