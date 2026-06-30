"""Build source status board, event logs, queues, and checkpoint files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ecfinder.state.common import read_jsonl, relative_path, sha256_text, utc_now, write_json, write_jsonl

from .agent_steps import derive_status_record, load_existing_status
from .fault_tolerance import missing_fulltext_error
from .status_model import STAGES


STATE_FILES = {
    "board": "source_status_board.jsonl",
    "events": "agent_run_events.jsonl",
    "errors": "error_queue.jsonl",
    "retries": "retry_queue.jsonl",
    "handoffs": "manual_handoff_queue.jsonl",
    "checkpoint": "orchestration_checkpoint.json",
}


def state_path(root: Path, key: str) -> Path:
    return root / "data" / "state" / STATE_FILES[key]


def build_event(
    batch_id: str,
    source_id: str,
    agent: str,
    stage: str,
    event_type: str,
    status_before: str,
    status_after: str,
    artifact_ref: str = "",
    task_ref: str = "",
    error_ref: str = "",
    message: str = "",
) -> dict[str, Any]:
    event_key = sha256_text("|".join([batch_id, source_id, stage, event_type, status_after, artifact_ref, task_ref, error_ref]))[:16]
    return {
        "event_id": f"{batch_id}_{source_id}_{stage}_{event_type}_{event_key}",
        "timestamp": utc_now(),
        "batch_id": batch_id,
        "source_id": source_id,
        "agent": agent,
        "stage": stage,
        "event_type": event_type,
        "status_before": status_before,
        "status_after": status_after,
        "artifact_ref": artifact_ref,
        "task_ref": task_ref,
        "error_ref": error_ref,
        "message": message,
    }


def error_record(batch_id: str, record: dict[str, Any]) -> dict[str, Any]:
    base = record["last_error"] or missing_fulltext_error(record["source_id"])
    return {
        "error_id": f"{batch_id}_{record['source_id']}_{base['stage']}_{base['error_type']}",
        "timestamp": utc_now(),
        **base,
    }


def manual_handoff_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "handoff_id": f"{record['batch_id']}_{record['source_id']}_provide_fulltext",
        "source_id": record["source_id"],
        "stage": "fulltext",
        "reason": "lawful full text was not available in local cache or Zotero lookup",
        "required_user_action": "provide_fulltext",
        "input_refs": {
            "metadata_ref": record["artifact_refs"].get("metadata_ref", ""),
            "download_ref": record["artifact_refs"].get("download_ref", ""),
        },
        "suggested_action": "place authorized PDF/HTML in data/local_fulltext/stage2_4b and rerun ingest",
        "priority": "high",
        "status": "pending",
        "created_at": utc_now(),
    }


def retry_record_from_error(error: dict[str, Any]) -> dict[str, Any] | None:
    if not error.get("retryable"):
        return None
    return {
        "retry_id": f"{error['source_id']}_{error['stage']}_retry_1",
        "source_id": error["source_id"],
        "stage": error["stage"],
        "agent": error["agent"],
        "reason": error["error_message_short"],
        "attempt": 1,
        "max_attempts": 2,
        "retry_policy": "immediate",
        "status": "pending",
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }


def build_board(root: Path, batch_id: str, queue_path: Path) -> dict[str, Any]:
    queue = read_jsonl(queue_path)
    task_registry = read_jsonl(root / "data" / "state" / "task_registry.jsonl")
    existing_status = load_existing_status(root, "stage2_4" if batch_id == "stage2_4e" else batch_id)
    records = [derive_status_record(source, batch_id, existing_status.get(source["source_id"]), task_registry) for source in queue]

    events: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    retries: list[dict[str, Any]] = []
    handoffs: list[dict[str, Any]] = []
    for record in records:
        for stage in STAGES:
            status_after = record["stage_status"][stage]
            artifact_key = {
                "metadata": "metadata_ref",
                "screening": "screening_ref",
                "fulltext": "download_ref",
                "parse": "chunks_ref",
                "chunk": "chunks_ref",
                "extract": "candidate_records_ref",
                "review": "reviewed_records_ref",
            }[stage]
            if status_after in {"done", "skipped"}:
                event_type = "success" if status_after == "done" else "skip"
                message = "artifact exists" if status_after == "done" else "stage skipped because source is metadata-only"
                events.append(
                    build_event(
                        batch_id,
                        record["source_id"],
                        agent_for_stage(stage),
                        stage,
                        event_type,
                        "pending",
                        status_after,
                        artifact_ref=record["artifact_refs"].get(artifact_key, ""),
                        message=message,
                    )
                )
            elif status_after == "manual_required":
                events.append(
                    build_event(
                        batch_id,
                        record["source_id"],
                        agent_for_stage(stage),
                        stage,
                        "manual_handoff",
                        "pending",
                        status_after,
                        task_ref=record["task_refs"][0] if record["task_refs"] else "",
                        message="manual task required; no automatic extraction or review was fabricated",
                    )
                )
        if record["overall_status"] == "manual_review" and record["current_stage"] == "fulltext":
            error = error_record(batch_id, record)
            errors.append(error)
            handoffs.append(manual_handoff_record(record))
            retry = retry_record_from_error(error)
            if retry:
                retries.append(retry)
            events.append(
                build_event(
                    batch_id,
                    record["source_id"],
                    "Orchestrator",
                    "fulltext",
                    "manual_handoff",
                    "missing",
                    "manual_required",
                    error_ref=error["error_id"],
                    message="full text missing; batch continues with manual handoff",
                )
            )

    write_jsonl(state_path(root, "board"), records)
    write_jsonl(state_path(root, "events"), events)
    write_jsonl(state_path(root, "errors"), errors)
    write_jsonl(state_path(root, "retries"), retries)
    write_jsonl(state_path(root, "handoffs"), handoffs)
    checkpoint = checkpoint_payload(batch_id, records)
    write_json(state_path(root, "checkpoint"), checkpoint)
    return {"records": records, "events": events, "errors": errors, "retries": retries, "handoffs": handoffs, "checkpoint": checkpoint}


def agent_for_stage(stage: str) -> str:
    return {
        "metadata": "SearchAgent",
        "screening": "SearchAgent",
        "fulltext": "DownloadAgent",
        "parse": "ParseAgent",
        "chunk": "ChunkAgent",
        "extract": "ExtractionAgent",
        "review": "ReviewAgent",
    }[stage]


def checkpoint_payload(batch_id: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [record for record in records if record["overall_status"] in {"validated", "manual_review", "rejected", "failed_terminal"}]
    return {
        "batch_id": batch_id,
        "last_run_started_at": utc_now(),
        "last_run_finished_at": utc_now(),
        "total_sources": len(records),
        "completed_sources": len(completed),
        "in_progress_sources": sum(1 for record in records if record["overall_status"] == "in_progress"),
        "manual_required_sources": sum(1 for record in records if record["overall_status"] == "manual_review"),
        "failed_recoverable_sources": sum(1 for record in records if record["overall_status"] == "failed_recoverable"),
        "failed_terminal_sources": sum(1 for record in records if record["overall_status"] == "failed_terminal"),
        "can_resume": True,
    }


def artifact_ref_exists(root: Path, ref: str) -> bool:
    return not ref or (root / ref).exists()


def relative_or_empty(root: Path, path: Path | None) -> str:
    return relative_path(root, path) if path else ""
