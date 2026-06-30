"""Validate Stage 2.4 controlled 30-source loop outputs."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ecfinder.state.common import read_jsonl, sha256_file


ROOT = Path(__file__).resolve().parents[1]
BATCH_DIR = ROOT / "data" / "batches"
REPORTS_DIR = ROOT / "reports"
STATE_DIR = ROOT / "data" / "state"
QUEUE_PATH = BATCH_DIR / "stage2_4_30source_queue.jsonl"
STATUS_PATH = BATCH_DIR / "stage2_4_30source_status.jsonl"
EVENTS_PATH = BATCH_DIR / "stage2_4_30source_events.jsonl"
CODEX_TASKS_PATH = BATCH_DIR / "stage2_4_codex_tasks.jsonl"
VALIDATED_BATCH_PATH = BATCH_DIR / "stage2_4_validated_records.jsonl"
MANUAL_BATCH_PATH = BATCH_DIR / "stage2_4_manual_review_records.jsonl"
REJECTED_BATCH_PATH = BATCH_DIR / "stage2_4_rejected_records.jsonl"
SUMMARY_PATH = REPORTS_DIR / "stage2_4_30source_loop_summary.md"
SOURCE_REGISTRY_PATH = STATE_DIR / "source_registry.jsonl"
ARTIFACT_INDEX_PATH = STATE_DIR / "artifact_index.jsonl"
DECISION_CACHE_PATH = STATE_DIR / "decision_cache.jsonl"
TASK_REGISTRY_PATH = STATE_DIR / "task_registry.jsonl"

RUN_JSONL_OUTPUTS = [
    "chunks.jsonl",
    "candidate_records.jsonl",
    "reviewed_records.jsonl",
    "validated_records.jsonl",
    "manual_review_records.jsonl",
    "rejected_records.jsonl",
]
RUN_REQUIRED_FILES = [
    "source_metadata.json",
    "screening.json",
    "download_status.json",
    *RUN_JSONL_OUTPUTS,
    "run_summary.md",
]
FORBIDDEN_VALIDATED_TERMS = [
    "activated sludge",
    "wastewater treatment",
    "wwtp",
    "engineered treatment",
    "electrochemical",
    "plasma",
    "photocatalysis",
    "ozonation",
    "hydrothermal",
    "incineration",
]
LONG_TEXT_FIELDS = {"stdout", "stderr", "abstract", "text", "full_text", "chunk_text", "evidence_text", "evidence_quote"}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"missing JSON file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl_strict(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise ValueError(f"missing JSONL file: {path}")
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            if "} {" in line:
                raise ValueError(f"{path}:{line_no} contains multiple JSON objects on one line")
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no} invalid JSONL: {exc}") from exc
            if not isinstance(obj, dict):
                raise ValueError(f"{path}:{line_no} is not a JSON object")
            records.append(obj)
    return records


def parse_summary_counts(path: Path) -> dict[str, str]:
    if not path.exists():
        raise ValueError(f"missing summary report: {path}")
    counts: dict[str, str] = {}
    pattern = re.compile(r"^([A-Za-z0-9_]+)\s*=\s*(.+?)\s*$")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            counts[match.group(1)] = match.group(2)
    return counts


def require_path(path_text: str, context: str) -> Path:
    if not path_text:
        raise ValueError(f"missing path in {context}")
    path = ROOT / path_text
    if not path.exists():
        raise ValueError(f"missing referenced path in {context}: {path_text}")
    return path


def validate_queue() -> list[dict[str, Any]]:
    queue = read_jsonl_strict(QUEUE_PATH)
    if len(queue) != 30:
        raise ValueError(f"queue must contain 30 sources; found {len(queue)}")
    seen: set[str] = set()
    for source in queue:
        source_id = source.get("source_id")
        if not source_id:
            raise ValueError("queue source missing source_id")
        if source_id in seen:
            raise ValueError(f"duplicate source_id: {source_id}")
        seen.add(source_id)
        if not source.get("doi") and not source.get("title"):
            raise ValueError(f"queue source missing DOI/title: {source_id}")
        if not source.get("status"):
            raise ValueError(f"queue source missing status: {source_id}")
    return queue


def require_validated_record_fields(record: dict[str, Any], run_dir: Path) -> None:
    missing = []
    if not record.get("source_id"):
        missing.append("source_id")
    if not record.get("chunk_id"):
        missing.append("chunk_id")
    if not record.get("evidence_quote"):
        missing.append("evidence_quote")
    if not record.get("parent_compound", {}).get("name"):
        missing.append("parent")
    if not record.get("product_compound", {}).get("name"):
        missing.append("product")
    if not record.get("conditions"):
        missing.append("condition")
    if missing:
        raise ValueError(f"{run_dir}/validated_records.jsonl record missing {missing}")
    text = json.dumps(record, ensure_ascii=False).lower()
    hits = [term for term in FORBIDDEN_VALIDATED_TERMS if term in text]
    if hits:
        raise ValueError(f"{run_dir}/validated_records.jsonl contains forbidden boundary terms: {hits}")


def validate_status_records() -> list[dict[str, Any]]:
    records = read_jsonl_strict(STATUS_PATH)
    if len(records) != 30:
        raise ValueError(f"status must contain 30 sources; found {len(records)}")
    for status in records:
        for key in LONG_TEXT_FIELDS:
            if key in status:
                raise ValueError(f"status contains long text field {key}: {status.get('source_id')}")
        if status.get("status") in {"", "unknown", None}:
            raise ValueError(f"status has unknown state: {status.get('source_id')}")
        if status.get("status") == "failed" and not status.get("failure_reason"):
            raise ValueError(f"failed source missing failure_reason: {status.get('source_id')}")
        if status.get("download_status") == "metadata_only" and not status.get("next_action"):
            raise ValueError(f"metadata-only source missing next_action: {status.get('source_id')}")
        if "artifact_refs" not in status:
            raise ValueError(f"status missing artifact_refs: {status.get('source_id')}")
        run_dir = ROOT / str(status.get("run_dir", ""))
        if not run_dir.exists():
            raise ValueError(f"missing run directory: {run_dir}")
        for name in RUN_REQUIRED_FILES:
            if not (run_dir / name).exists():
                raise ValueError(f"missing run output: {run_dir / name}")
        read_json(run_dir / "source_metadata.json")
        read_json(run_dir / "screening.json")
        read_json(run_dir / "download_status.json")
        for name in RUN_JSONL_OUTPUTS:
            read_jsonl_strict(run_dir / name)
        for validated in read_jsonl_strict(run_dir / "validated_records.jsonl"):
            require_validated_record_fields(validated, run_dir)
    return records


def validate_task_refs() -> None:
    tasks = read_jsonl_strict(CODEX_TASKS_PATH)
    registry = read_jsonl_strict(TASK_REGISTRY_PATH)
    registry_paths = {record.get("task_id"): record.get("task_path", "") for record in registry}
    for task in tasks:
        if not task.get("input_refs"):
            raise ValueError(f"task missing input_refs: {task.get('task_id')}")
        if not task.get("expected_output"):
            raise ValueError(f"task missing expected_output: {task.get('task_id')}")
        payload_ref = task.get("task_payload_ref", "")
        payload_path = require_path(payload_ref, f"batch task {task.get('task_id')}")
        payload = read_json(payload_path)
        for prompt_ref in payload.get("prompt_refs", []):
            require_path(prompt_ref, f"task prompt {payload.get('task_id')}")
        require_path(payload.get("schema_ref", ""), f"task schema {payload.get('task_id')}")
        if task.get("task_id") not in registry_paths:
            raise ValueError(f"task missing registry entry: {task.get('task_id')}")
        require_path(registry_paths[task.get("task_id")], f"task registry {task.get('task_id')}")


def validate_artifact_index() -> None:
    for record in read_jsonl_strict(ARTIFACT_INDEX_PATH):
        path = require_path(record.get("path", ""), f"artifact {record.get('artifact_id')}")
        if sha256_file(path) != record.get("sha256"):
            raise ValueError(f"artifact hash mismatch: {record.get('artifact_id')}")


def summarize_status(records: list[dict[str, Any]]) -> dict[str, Any]:
    tasks = read_jsonl_strict(CODEX_TASKS_PATH)
    cache_stats = read_json(ROOT / "data" / "state" / "cache_stats.json")
    metadata_only = sum(1 for record in records if record.get("download_status") == "metadata_only")
    return {
        "candidate_records": sum(int(record.get("candidate_records", 0)) for record in records),
        "codex_tasks_created": len(tasks),
        "database_coverage_still_insufficient": metadata_only >= 20,
        "download_cache_hits": int(cache_stats.get("download_cache_hits", 0)),
        "download_cache_misses": int(cache_stats.get("download_cache_misses", 0)),
        "download_success": sum(1 for record in records if record.get("full_text_downloaded") is True),
        "extraction_cache_hits": int(cache_stats.get("extraction_cache_hits", 0)),
        "extraction_cache_misses": int(cache_stats.get("extraction_cache_misses", 0)),
        "failed_sources": sum(1 for record in records if record.get("status") == "failed"),
        "html_or_cache_used": sum(
            1 for record in records if record.get("download_status") in {"downloaded_html", "downloaded_pdf", "local_cached_html"}
        ),
        "manual_review_records": sum(int(record.get("manual_review_records", 0)) for record in records),
        "metadata_cache_hits": int(cache_stats.get("metadata_cache_hits", 0)),
        "metadata_cache_misses": int(cache_stats.get("metadata_cache_misses", 0)),
        "metadata_only": metadata_only,
        "metadata_success": sum(1 for record in records if record.get("metadata_status") == "success"),
        "new_validated_records_beyond_stage2_3": max(0, sum(int(record.get("validated_records", 0)) for record in records) - 4),
        "parse_cache_hits": int(cache_stats.get("parse_cache_hits", 0)),
        "parse_cache_misses": int(cache_stats.get("parse_cache_misses", 0)),
        "parsed_sources": sum(1 for record in records if int(record.get("parsed_chunks", 0)) > 0),
        "rejected_records": sum(int(record.get("rejected_records", 0)) for record in records),
        "review_cache_hits": int(cache_stats.get("review_cache_hits", 0)),
        "review_cache_misses": int(cache_stats.get("review_cache_misses", 0)),
        "screen_download": sum(1 for record in records if record.get("screen_decision") == "include_for_full_text_attempt"),
        "screening_cache_hits": int(cache_stats.get("screening_cache_hits", 0)),
        "screening_cache_misses": int(cache_stats.get("screening_cache_misses", 0)),
        "tasks_created": int(cache_stats.get("tasks_created", 0)),
        "tokens_saved_estimate": int(cache_stats.get("tokens_saved_estimate", 0)),
        "total_chunks": sum(int(record.get("parsed_chunks", 0)) for record in records),
        "total_sources": len(records),
        "validated_records": sum(int(record.get("validated_records", 0)) for record in records),
    }


def validate_reports(summary: dict[str, Any]) -> None:
    report_counts = parse_summary_counts(SUMMARY_PATH)
    for key, value in summary.items():
        expected = str(value).lower() if isinstance(value, bool) else str(value)
        actual = report_counts.get(key)
        if actual != expected:
            raise ValueError(f"report count mismatch for {key}: expected {expected}, got {actual}")
    can_scale = report_counts.get("can_scale_to_100_sources", "")
    if can_scale not in {"true", "false", "true_for_workflow_only"}:
        raise ValueError(f"invalid can_scale_to_100_sources value: {can_scale}")


def main() -> int:
    validate_queue()
    records = validate_status_records()
    read_jsonl_strict(EVENTS_PATH)
    read_jsonl_strict(VALIDATED_BATCH_PATH)
    read_jsonl_strict(MANUAL_BATCH_PATH)
    read_jsonl_strict(REJECTED_BATCH_PATH)
    read_jsonl_strict(SOURCE_REGISTRY_PATH)
    read_jsonl_strict(DECISION_CACHE_PATH)
    validate_task_refs()
    validate_artifact_index()
    summary = summarize_status(records)
    validate_reports(summary)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
