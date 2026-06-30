"""Derive orchestrated stage outcomes from existing batch artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ecfinder.state.common import read_jsonl

from .fault_tolerance import missing_fulltext_error
from .status_model import empty_stage_status, make_status_record


def rows_by_source(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row.get("source_id", "")): row for row in rows if row.get("source_id")}


def task_refs_for_source(task_registry: list[dict[str, Any]], source_id: str) -> list[str]:
    refs = []
    for task in task_registry:
        if task.get("source_id") == source_id and task.get("task_path"):
            refs.append(str(task["task_path"]))
    return sorted(set(refs))


def derive_status_record(
    source: dict[str, Any],
    batch_id: str,
    existing_status: dict[str, Any] | None,
    task_registry: list[dict[str, Any]],
) -> dict[str, Any]:
    status = existing_status or {}
    source_id = str(source.get("source_id", ""))
    stage_status = empty_stage_status()
    artifact_refs = status.get("artifact_refs", {})
    task_refs = task_refs_for_source(task_registry, source_id)

    metadata_done = status.get("metadata_status") == "success" or bool(artifact_refs.get("metadata_ref"))
    screening_done = bool(status.get("screen_decision")) or bool(artifact_refs.get("screening_ref"))
    has_fulltext = bool(status.get("full_text_available")) or status.get("download_status") in {
        "local_cached_html",
        "downloaded_html",
        "downloaded_pdf",
    }
    metadata_only = status.get("download_status") == "metadata_only"
    parsed_chunks = int(status.get("parsed_chunks", 0) or status.get("counts", {}).get("parsed_chunks", 0) or 0)
    candidate_records = int(status.get("candidate_records", 0) or 0)
    reviewed_records = int(status.get("reviewed_records", 0) or 0)
    validated_records = int(status.get("validated_records", 0) or 0)
    rejected_records = int(status.get("rejected_records", 0) or 0)

    stage_status["metadata"] = "done" if metadata_done else "pending"
    stage_status["screening"] = "done" if screening_done else "pending"
    stage_status["fulltext"] = "done" if has_fulltext else "missing" if metadata_only else "pending"
    stage_status["parse"] = "done" if parsed_chunks > 0 else "skipped" if metadata_only else "pending"
    stage_status["chunk"] = "done" if parsed_chunks > 0 else "skipped" if metadata_only else "pending"
    stage_status["extract"] = "done" if candidate_records > 0 else "manual_required" if metadata_only else "pending"
    stage_status["review"] = "done" if reviewed_records > 0 or validated_records > 0 else "manual_required" if metadata_only else "pending"

    last_error = None
    if metadata_only:
        last_error = missing_fulltext_error(source_id)

    if validated_records > 0:
        overall_status = "validated"
        current_stage = "done"
        next_action = "validated_records_ready_for_audit"
    elif rejected_records > 0:
        overall_status = "rejected"
        current_stage = "done"
        next_action = "review_rejected_records"
    elif metadata_only:
        overall_status = "manual_review"
        current_stage = "fulltext"
        next_action = "provide_fulltext_or_zotero_mapping"
    else:
        overall_status = "in_progress"
        current_stage = "metadata"
        next_action = "continue_orchestration"

    return make_status_record(
        source=source,
        batch_id=batch_id,
        overall_status=overall_status,
        current_stage=current_stage,
        stage_status=stage_status,
        artifact_refs=artifact_refs,
        task_refs=task_refs,
        last_error=last_error,
        next_action=next_action,
    )


def load_existing_status(root: Path, batch_id: str) -> dict[str, dict[str, Any]]:
    candidate = root / "data" / "batches" / f"{batch_id}_30source_status.jsonl"
    if candidate.exists():
        return rows_by_source(read_jsonl(candidate))
    if batch_id == "stage2_4e":
        fallback = root / "data" / "batches" / "stage2_4_30source_status.jsonl"
        return rows_by_source(read_jsonl(fallback))
    return {}
