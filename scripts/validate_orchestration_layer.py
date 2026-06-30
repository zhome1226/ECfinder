"""Validate Stage 2.4f orchestration board, queues, checkpoint, and reports."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ecfinder.orchestration.progress_report import write_reports
from ecfinder.orchestration.status_model import (
    ARTIFACT_REF_KEYS,
    CURRENT_STAGE_ALLOWED,
    OVERALL_ALLOWED,
    STAGES,
    validate_stage_status,
)
from ecfinder.state.common import read_json, read_jsonl


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "state"
REPORTS = ROOT / "reports"
BOARD = STATE / "source_status_board.jsonl"
EVENTS = STATE / "agent_run_events.jsonl"
ERRORS = STATE / "error_queue.jsonl"
RETRIES = STATE / "retry_queue.jsonl"
HANDOFFS = STATE / "manual_handoff_queue.jsonl"
CHECKPOINT = STATE / "orchestration_checkpoint.json"
SUMMARY = REPORTS / "stage2_4f_orchestration_summary.md"

LONG_TEXT_KEYS = {"stdout", "stderr", "abstract", "text", "full_text", "chunk_text", "evidence_text", "evidence_quote"}
EVENT_TYPES = {"start", "success", "skip", "failure", "retry_scheduled", "manual_handoff", "terminal_failure"}


def read_jsonl_strict(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise ValueError(f"missing JSONL file: {path}")
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            if "} {" in line:
                raise ValueError(f"{path}:{line_no} contains multiple JSON objects")
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_no} is not an object")
            rows.append(value)
    return rows


def require_repo_path(path_text: str, context: str) -> None:
    if not path_text:
        return
    path = ROOT / path_text
    if not path.exists():
        raise ValueError(f"missing referenced path in {context}: {path_text}")


def validate_board() -> list[dict[str, Any]]:
    records = read_jsonl_strict(BOARD)
    if not records:
        raise ValueError("source_status_board is empty")
    seen: set[str] = set()
    for record in records:
        source_id = record.get("source_id")
        if not source_id:
            raise ValueError("status board record missing source_id")
        if source_id in seen:
            raise ValueError(f"duplicate source_id in status board: {source_id}")
        seen.add(source_id)
        if record.get("overall_status") not in OVERALL_ALLOWED:
            raise ValueError(f"invalid overall_status for {source_id}: {record.get('overall_status')}")
        if record.get("current_stage") not in CURRENT_STAGE_ALLOWED:
            raise ValueError(f"invalid current_stage for {source_id}: {record.get('current_stage')}")
        validate_stage_status(record.get("stage_status", {}))
        refs = record.get("artifact_refs", {})
        if set(refs) != set(ARTIFACT_REF_KEYS):
            raise ValueError(f"artifact_refs key mismatch for {source_id}")
        for key, ref in refs.items():
            require_repo_path(ref, f"{source_id} {key}")
        for task_ref in record.get("task_refs", []):
            require_repo_path(task_ref, f"{source_id} task_ref")
        if record.get("overall_status") in {"validated", "manual_review", "rejected", "failed_terminal"}:
            if record.get("current_stage") not in {"done", "fulltext", "extract", "review"}:
                raise ValueError(f"completed source has wrong current_stage: {source_id}")
        for key in LONG_TEXT_KEYS:
            if key in record:
                raise ValueError(f"status board contains long text key {key}: {source_id}")
    return records


def validate_events() -> list[dict[str, Any]]:
    events = read_jsonl_strict(EVENTS)
    for event in events:
        for required in ["event_id", "timestamp", "batch_id", "source_id", "agent", "stage", "event_type"]:
            if not event.get(required):
                raise ValueError(f"event missing {required}: {event}")
        if event["stage"] not in STAGES:
            raise ValueError(f"invalid event stage: {event}")
        if event["event_type"] not in EVENT_TYPES:
            raise ValueError(f"invalid event_type: {event}")
        require_repo_path(event.get("artifact_ref", ""), f"event artifact {event['event_id']}")
        require_repo_path(event.get("task_ref", ""), f"event task {event['event_id']}")
    return events


def validate_errors() -> list[dict[str, Any]]:
    errors = read_jsonl_strict(ERRORS)
    for error in errors:
        for required in ["error_id", "timestamp", "source_id", "stage", "agent", "error_type", "next_action"]:
            if not error.get(required):
                raise ValueError(f"error missing {required}: {error}")
        if error["stage"] not in STAGES:
            raise ValueError(f"invalid error stage: {error}")
        if len(str(error.get("error_message_short", ""))) > 240:
            raise ValueError(f"error message too long: {error['error_id']}")
    return errors


def validate_retries() -> list[dict[str, Any]]:
    retries = read_jsonl_strict(RETRIES)
    for retry in retries:
        for required in ["retry_id", "source_id", "stage", "agent", "reason", "status"]:
            if not retry.get(required):
                raise ValueError(f"retry missing {required}: {retry}")
        if retry["stage"] not in STAGES:
            raise ValueError(f"invalid retry stage: {retry}")
        if int(retry.get("attempt", 0)) > int(retry.get("max_attempts", 0)):
            raise ValueError(f"retry attempt exceeds max: {retry}")
    return retries


def validate_handoffs() -> list[dict[str, Any]]:
    handoffs = read_jsonl_strict(HANDOFFS)
    for handoff in handoffs:
        for required in ["handoff_id", "source_id", "stage", "required_user_action", "status", "created_at"]:
            if not handoff.get(required):
                raise ValueError(f"handoff missing {required}: {handoff}")
        for _, ref in handoff.get("input_refs", {}).items():
            require_repo_path(ref, f"handoff input {handoff['handoff_id']}")
    return handoffs


def summary_from_board(records: list[dict[str, Any]], retries: list[dict[str, Any]], handoffs: list[dict[str, Any]], errors: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_sources": len(records),
        "completed_sources": sum(1 for row in records if row["overall_status"] in {"validated", "manual_review", "rejected", "failed_terminal"}),
        "validated_sources": sum(1 for row in records if row["overall_status"] == "validated"),
        "manual_review_sources": sum(1 for row in records if row["overall_status"] == "manual_review"),
        "failed_recoverable_sources": sum(1 for row in records if row["overall_status"] == "failed_recoverable"),
        "failed_terminal_sources": sum(1 for row in records if row["overall_status"] == "failed_terminal"),
        "metadata_done": sum(1 for row in records if row["stage_status"]["metadata"] == "done"),
        "fulltext_found": sum(1 for row in records if row["stage_status"]["fulltext"] == "done"),
        "fulltext_missing": sum(1 for row in records if row["stage_status"]["fulltext"] == "missing"),
        "parse_done": sum(1 for row in records if row["stage_status"]["parse"] == "done"),
        "extract_done": sum(1 for row in records if row["stage_status"]["extract"] == "done"),
        "review_done": sum(1 for row in records if row["stage_status"]["review"] == "done"),
        "retry_queue_size": len(retries),
        "manual_handoff_queue_size": len(handoffs),
        "error_queue_size": len(errors),
        "can_resume": True,
        "orchestration_validation_passed": True,
        "ready_for_next_batch": True,
    }


def parse_report(path: Path) -> dict[str, str]:
    pattern = re.compile(r"^([A-Za-z0-9_]+)\s*=\s*(.+?)\s*$")
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            values[match.group(1)] = match.group(2)
    return values


def validate_checkpoint(records: list[dict[str, Any]]) -> dict[str, Any]:
    checkpoint = read_json(CHECKPOINT)
    if checkpoint.get("total_sources") != len(records):
        raise ValueError("checkpoint total_sources mismatch")
    expected_completed = sum(
        1 for row in records if row["overall_status"] in {"validated", "manual_review", "rejected", "failed_terminal"}
    )
    if checkpoint.get("completed_sources") != expected_completed:
        raise ValueError("checkpoint completed_sources mismatch")
    if checkpoint.get("can_resume") is not True:
        raise ValueError("checkpoint can_resume must be true")
    return checkpoint


def validate_reports(expected: dict[str, Any]) -> None:
    write_reports(ROOT, validation_passed=True)
    report = parse_report(SUMMARY)
    for key, value in expected.items():
        expected_text = str(value).lower() if isinstance(value, bool) else str(value)
        if report.get(key) != expected_text:
            raise ValueError(f"summary mismatch for {key}: expected {expected_text}, got {report.get(key)}")
    for report_path in [
        REPORTS / "current_status_board.md",
        REPORTS / "current_error_summary.md",
        REPORTS / "current_manual_handoff.md",
        REPORTS / "stage2_4f_fault_tolerance_audit.md",
    ]:
        if not report_path.exists() or not report_path.read_text(encoding="utf-8").strip():
            raise ValueError(f"missing or empty report: {report_path}")


def run_cli_checks() -> None:
    commands = [
        [sys.executable, str(ROOT / "scripts" / "status_board.py")],
        [sys.executable, str(ROOT / "scripts" / "retry_failed_tasks.py"), "--dry-run"],
    ]
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, text=True, encoding="utf-8", capture_output=True, check=False)
        if result.returncode != 0:
            raise ValueError(f"command failed: {' '.join(command)}\n{result.stdout}\n{result.stderr}")


def main() -> int:
    records = validate_board()
    validate_events()
    errors = validate_errors()
    retries = validate_retries()
    handoffs = validate_handoffs()
    validate_checkpoint(records)
    run_cli_checks()
    summary = summary_from_board(records, retries, handoffs, errors)
    validate_reports(summary)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
