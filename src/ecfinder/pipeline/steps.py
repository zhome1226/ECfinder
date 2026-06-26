"""Pipeline step placeholders and Codex handoff task builders.

The Stage 2.2b orchestrator intentionally does not call a fake LLM client.
Semantic extraction and review work is represented as queueable handoff tasks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ecfinder.pipeline.contracts import read_jsonl_strict
from ecfinder.pipeline.queues import append_task


def create_targeted_followup_handoff_tasks(root: Path, max_sources: int) -> dict[str, Any]:
    """Create pending Codex review tasks from existing manual-review evidence.

    This does not search for new literature. It only converts already-known clean
    manual-review records into explicit queue items for a future Codex pass.
    """

    source_path = root / "data" / "clean" / "stage2_2_manual_review_records.jsonl"
    if not source_path.exists():
        return {"tasks_created": 0, "source_records_seen": 0}
    manual_records = read_jsonl_strict(source_path)
    tasks_created = 0
    for record in manual_records[: max(0, max_sources)]:
        source_id = record.get("source_id") or ""
        record_id = record.get("record_id") or source_id
        append_task(
            root,
            {
                "task_id": f"task_review_{record_id}",
                "task_type": "codex_review",
                "record_id": record_id,
                "source_id": source_id,
                "chunk_id": record.get("chunk_id") or "",
                "prompt_file": "prompts/review_transformation_records.md",
                "input_ref": "data/clean/stage2_2_manual_review_records.jsonl",
                "output_expected": "data/clean/stage_next_reviewed_records.jsonl",
                "status": "pending",
            },
        )
        tasks_created += 1
    return {"tasks_created": tasks_created, "source_records_seen": len(manual_records)}
