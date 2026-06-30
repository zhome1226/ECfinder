"""Status model constants and constructors for orchestrated source batches."""

from __future__ import annotations

from typing import Any

from ecfinder.state.common import utc_now


STAGES = ["metadata", "screening", "fulltext", "parse", "chunk", "extract", "review"]

STAGE_ALLOWED = {
    "metadata": {"pending", "running", "done", "skipped", "failed", "retry_pending"},
    "screening": {"pending", "running", "done", "skipped", "failed", "retry_pending"},
    "fulltext": {"pending", "running", "done", "missing", "failed", "retry_pending"},
    "parse": {"pending", "running", "done", "skipped", "failed", "retry_pending"},
    "chunk": {"pending", "running", "done", "skipped", "failed", "retry_pending"},
    "extract": {"pending", "running", "done", "skipped", "failed", "manual_required", "retry_pending"},
    "review": {"pending", "running", "done", "skipped", "failed", "manual_required", "retry_pending"},
}

OVERALL_ALLOWED = {
    "in_progress",
    "validated",
    "manual_review",
    "rejected",
    "failed_recoverable",
    "failed_terminal",
}

CURRENT_STAGE_ALLOWED = {"metadata", "screening", "fulltext", "parse", "chunk", "extract", "review", "done"}

ARTIFACT_REF_KEYS = [
    "metadata_ref",
    "screening_ref",
    "download_ref",
    "chunks_ref",
    "candidate_records_ref",
    "reviewed_records_ref",
    "validated_records_ref",
    "manual_review_ref",
    "rejected_records_ref",
]


def empty_stage_status() -> dict[str, str]:
    return {
        "metadata": "pending",
        "screening": "pending",
        "fulltext": "pending",
        "parse": "pending",
        "chunk": "pending",
        "extract": "pending",
        "review": "pending",
    }


def empty_retry_count() -> dict[str, int]:
    return {stage: 0 for stage in STAGES}


def normalize_artifact_refs(refs: dict[str, Any] | None) -> dict[str, str]:
    refs = refs or {}
    return {key: str(refs.get(key, "") or "") for key in ARTIFACT_REF_KEYS}


def make_status_record(
    source: dict[str, Any],
    batch_id: str,
    overall_status: str,
    current_stage: str,
    stage_status: dict[str, str],
    artifact_refs: dict[str, Any] | None,
    task_refs: list[str] | None,
    last_error: dict[str, Any] | None,
    next_action: str,
) -> dict[str, Any]:
    return {
        "source_id": str(source.get("source_id", "")),
        "doi": str(source.get("doi", "") or ""),
        "title": str(source.get("title", "") or ""),
        "batch_id": batch_id,
        "overall_status": overall_status,
        "current_stage": current_stage,
        "stage_status": stage_status,
        "artifact_refs": normalize_artifact_refs(artifact_refs),
        "task_refs": task_refs or [],
        "retry_count": empty_retry_count(),
        "last_error": last_error,
        "next_action": next_action,
        "updated_at": utc_now(),
    }


def validate_stage_status(stage_status: dict[str, str]) -> None:
    for stage in STAGES:
        value = stage_status.get(stage)
        if value not in STAGE_ALLOWED[stage]:
            raise ValueError(f"invalid stage status for {stage}: {value}")
