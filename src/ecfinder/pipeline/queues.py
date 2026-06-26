"""Pipeline task, manual-review, and error queues."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ecfinder.pipeline.contracts import append_jsonl, read_jsonl_strict, write_jsonl
from ecfinder.pipeline.state import utc_now


TASK_QUEUE_REL = "data/clean/task_queue.jsonl"
MANUAL_REVIEW_QUEUE_REL = "data/clean/manual_review_queue.jsonl"
ERROR_QUEUE_REL = "data/clean/error_queue.jsonl"


def queue_path(root: Path, rel: str) -> Path:
    return root / rel


def ensure_queues(root: Path) -> None:
    for rel in [TASK_QUEUE_REL, MANUAL_REVIEW_QUEUE_REL, ERROR_QUEUE_REL]:
        path = queue_path(root, rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text("", encoding="utf-8")


def clear_error_queue(root: Path) -> None:
    write_jsonl(queue_path(root, ERROR_QUEUE_REL), [])


def append_error(
    root: Path,
    run_id: str,
    step: str,
    reason: str,
    details: list[str] | None = None,
    related_files: list[str] | None = None,
) -> dict[str, Any]:
    record = {
        "error_id": f"error_{utc_now().replace(':', '').replace('-', '')}",
        "run_id": run_id,
        "step": step,
        "reason": reason,
        "details": details or [],
        "related_files": related_files or [],
        "status": "open",
        "timestamp": utc_now(),
    }
    append_jsonl(queue_path(root, ERROR_QUEUE_REL), record)
    return record


def append_task(root: Path, task: dict[str, Any]) -> None:
    task.setdefault("status", "pending")
    task.setdefault("created_at", utc_now())
    append_jsonl(queue_path(root, TASK_QUEUE_REL), task)


def append_manual_review(root: Path, record: dict[str, Any]) -> None:
    record.setdefault("status", "pending")
    record.setdefault("created_at", utc_now())
    append_jsonl(queue_path(root, MANUAL_REVIEW_QUEUE_REL), record)


def queue_counts(root: Path) -> dict[str, int]:
    ensure_queues(root)
    counts = {}
    for key, rel in [
        ("task_queue_count", TASK_QUEUE_REL),
        ("manual_review_queue_count", MANUAL_REVIEW_QUEUE_REL),
        ("error_queue_count", ERROR_QUEUE_REL),
    ]:
        counts[key] = len(read_jsonl_strict(queue_path(root, rel)))
    return counts
