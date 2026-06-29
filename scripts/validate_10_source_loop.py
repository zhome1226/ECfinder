"""Validate the Stage 2.3 10-source PFAS evidence loop outputs."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BATCH_DIR = ROOT / "data" / "batches"
RUNS_DIR = ROOT / "data" / "runs"
REPORTS_DIR = ROOT / "reports"
QUEUE_PATH = BATCH_DIR / "stage2_3_10source_queue.jsonl"
STATUS_PATH = BATCH_DIR / "stage2_3_10source_status.jsonl"
EVENTS_PATH = BATCH_DIR / "stage2_3_10source_events.jsonl"
CODEX_TASKS_PATH = BATCH_DIR / "stage2_3_codex_tasks.jsonl"
SUMMARY_PATH = REPORTS_DIR / "stage2_3_10source_loop_summary.md"
PERFORMANCE_PATH = REPORTS_DIR / "stage2_3_10source_query_performance.md"

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
FORBIDDEN_TERMS = ["activated sludge", "wastewater treatment", "wwtp"]


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


def require_record_fields(record: dict[str, Any], run_dir: Path) -> None:
    missing = []
    if not record.get("source_id"):
        missing.append("source_id")
    if not record.get("chunk_id"):
        missing.append("chunk_id")
    if not record.get("evidence_quote"):
        missing.append("evidence_quote")
    if not record.get("parent_compound", {}).get("name"):
        missing.append("parent_compound.name")
    if not record.get("product_compound", {}).get("name"):
        missing.append("product_compound.name")
    if not record.get("conditions"):
        missing.append("conditions")
    if missing:
        raise ValueError(f"{run_dir}/validated_records.jsonl record missing {missing}")

    text = json.dumps(record, ensure_ascii=False).lower()
    hits = [term for term in FORBIDDEN_TERMS if term in text]
    if hits:
        raise ValueError(f"{run_dir}/validated_records.jsonl contains forbidden boundary terms: {hits}")


def summarize_status(status_records: list[dict[str, Any]]) -> dict[str, int | bool]:
    codex_tasks = read_jsonl_strict(CODEX_TASKS_PATH)
    total_sources = len(status_records)
    metadata_success = sum(1 for record in status_records if record.get("metadata_status") == "success")
    summary: dict[str, int | bool] = {
        "total_sources": total_sources,
        "metadata_success": metadata_success,
        "screen_download": sum(
            1 for record in status_records if record.get("screen_decision") == "include_for_full_text_attempt"
        ),
        "download_success": sum(1 for record in status_records if record.get("full_text_downloaded") is True),
        "html_or_cache_used": sum(
            1
            for record in status_records
            if record.get("download_status") in {"downloaded_html", "downloaded_pdf", "local_cached_html"}
        ),
        "metadata_only": sum(1 for record in status_records if record.get("download_status") == "metadata_only"),
        "parsed_sources": sum(1 for record in status_records if int(record.get("parsed_chunks", 0)) > 0),
        "total_chunks": sum(int(record.get("parsed_chunks", 0)) for record in status_records),
        "candidate_records": sum(int(record.get("candidate_records", 0)) for record in status_records),
        "validated_records": sum(int(record.get("validated_records", 0)) for record in status_records),
        "manual_review_records": sum(int(record.get("manual_review_records", 0)) for record in status_records),
        "rejected_records": sum(int(record.get("rejected_records", 0)) for record in status_records),
        "failed_sources": sum(1 for record in status_records if record.get("status") == "failed"),
        "codex_tasks_created": len(codex_tasks),
    }
    cache_stats_path = ROOT / "data" / "state" / "cache_stats.json"
    if cache_stats_path.exists():
        cache_stats = json.loads(cache_stats_path.read_text(encoding="utf-8"))
        for key in [
            "metadata_cache_hits",
            "metadata_cache_misses",
            "screening_cache_hits",
            "screening_cache_misses",
            "parse_cache_hits",
            "parse_cache_misses",
            "extraction_cache_hits",
            "extraction_cache_misses",
            "review_cache_hits",
            "review_cache_misses",
            "tasks_created",
            "tokens_saved_estimate",
        ]:
            summary[key] = int(cache_stats.get(key, 0))
    summary["can_scale_to_30_sources"] = (
        total_sources == 10
        and metadata_success >= 8
        and all(record.get("status") not in {"", "unknown", None} for record in status_records)
        and all((ROOT / str(record.get("run_dir", "")) / "run_summary.md").exists() for record in status_records)
        and all(record.get("failure_reason") for record in status_records if record.get("status") == "failed")
        and all(task.get("input_files") and task.get("expected_output") and task.get("reason") for task in codex_tasks)
    )
    return summary


def validate_run_outputs(status_records: list[dict[str, Any]]) -> None:
    for status in status_records:
        for forbidden_key in ["stdout", "stderr", "abstract", "text", "evidence_quote"]:
            if forbidden_key in status:
                raise ValueError(f"batch status contains long text field: {forbidden_key}")
        if "artifact_refs" not in status:
            raise ValueError(f"batch status missing artifact_refs: {status.get('source_id')}")
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
        for record in read_jsonl_strict(run_dir / "validated_records.jsonl"):
            require_record_fields(record, run_dir)
        if status.get("status") == "failed" and not status.get("failure_reason"):
            raise ValueError(f"failed source has no failure_reason: {status.get('source_id')}")


def validate_reports(summary: dict[str, int | bool]) -> None:
    if not SUMMARY_PATH.exists():
        raise ValueError(f"missing report: {SUMMARY_PATH}")
    if not PERFORMANCE_PATH.exists():
        raise ValueError(f"missing report: {PERFORMANCE_PATH}")
    report_counts = parse_summary_counts(SUMMARY_PATH)
    for key, value in summary.items():
        expected = str(value).lower() if isinstance(value, bool) else str(value)
        actual = report_counts.get(key)
        if actual != expected:
            raise ValueError(f"report count mismatch for {key}: expected {expected}, got {actual}")


def main() -> int:
    queue = read_jsonl_strict(QUEUE_PATH)
    if len(queue) != 10:
        raise ValueError(f"queue must contain 10 sources; found {len(queue)}")
    for source in queue:
        if not source.get("status"):
            raise ValueError(f"queue source has no status: {source}")

    status_records = read_jsonl_strict(STATUS_PATH)
    if len(status_records) != 10:
        raise ValueError(f"status must contain 10 sources; found {len(status_records)}")
    read_jsonl_strict(EVENTS_PATH)
    read_jsonl_strict(CODEX_TASKS_PATH)
    validate_run_outputs(status_records)
    summary = summarize_status(status_records)
    validate_reports(summary)

    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
