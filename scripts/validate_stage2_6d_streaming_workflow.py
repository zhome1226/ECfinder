"""Validate Stage 2.6d resumed streaming autonomous workflow outputs."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "data" / "batches"
STATE = ROOT / "data" / "state"
REPORTS = ROOT / "reports"
PREFIX = "stage2_6d_streaming"
PREVIOUS_PREFIX = "stage2_6c_streaming"
SUMMARY = REPORTS / f"{PREFIX}_autonomous_summary.md"

FORBIDDEN_VALIDATED = {
    "activated sludge",
    "wastewater treatment",
    "wwtp",
    "engineered biological treatment",
    "pure culture only",
    "pure culture",
    "advanced oxidation",
    "electrochemical",
    "plasma",
    "photocatalysis",
    "ozonation",
    "uv/persulfate",
    "incineration",
    "analytical method only",
    "occurrence only",
    "toxicity only",
    "review only",
}


def require(path: Path) -> Path:
    if not path.exists():
        raise ValueError(f"missing required file: {path}")
    return path


def parse_report(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    pattern = re.compile(r"^([A-Za-z0-9_]+)\s*=\s*(.*?)\s*$")
    for line in require(path).read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            values[match.group(1)] = match.group(2)
    return values


def as_int(values: dict[str, str], key: str) -> int:
    return int(values.get(key, "0"))


def as_bool(values: dict[str, str], key: str) -> bool:
    return values.get(key, "false") == "true"


def value_has_raw_newline(value: Any) -> bool:
    if isinstance(value, dict):
        return any("\n" in str(key) or "\r" in str(key) or value_has_raw_newline(child) for key, child in value.items())
    if isinstance(value, list):
        return any(value_has_raw_newline(child) for child in value)
    return isinstance(value, str) and ("\n" in value or "\r" in value)


def strict_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with require(path).open("r", encoding="utf-8", newline="") as handle:
        for line_no, raw in enumerate(handle, start=1):
            if not raw.strip():
                continue
            if "} {" in raw:
                raise ValueError(f"{path}:{line_no} contains multiple JSON objects on one physical line")
            if raw.count("\n") != 1 or "\r" in raw:
                raise ValueError(f"{path}:{line_no} has non-normalized physical line ending")
            obj = json.loads(raw.rstrip("\n"))
            if not isinstance(obj, dict):
                raise ValueError(f"{path}:{line_no} is not a JSON object")
            if value_has_raw_newline(obj):
                raise ValueError(f"{path}:{line_no} contains raw CR/LF inside parsed string")
            rows.append(obj)
    return rows


def load_prefix(prefix: str) -> dict[str, list[dict[str, Any]]]:
    return {
        "status": strict_jsonl(STATE / f"{prefix}_source_status.jsonl"),
        "events": strict_jsonl(STATE / f"{prefix}_events.jsonl"),
        "screening": strict_jsonl(BATCH / f"{prefix}_screening_decisions.jsonl"),
        "chunks": strict_jsonl(BATCH / f"{prefix}_chunk_screening.jsonl"),
        "candidates": strict_jsonl(BATCH / f"{prefix}_candidate_records.jsonl"),
        "reviewed": strict_jsonl(BATCH / f"{prefix}_reviewed_records.jsonl"),
        "validated": strict_jsonl(BATCH / f"{prefix}_validated_records.jsonl"),
        "manual": strict_jsonl(BATCH / f"{prefix}_manual_review_records.jsonl"),
        "rejected": strict_jsonl(BATCH / f"{prefix}_rejected_records.jsonl"),
        "auxiliary": strict_jsonl(BATCH / f"{prefix}_auxiliary_records.jsonl"),
    }


def validate_status_logic(status_rows: list[dict[str, Any]], screening_rows: list[dict[str, Any]]) -> None:
    status_by_source = {str(row.get("source_id", "")): row for row in status_rows}
    if len(status_by_source) != len(status_rows):
        raise ValueError("duplicate source_id in stage2_6d source status")
    for decision in screening_rows:
        source_id = str(decision.get("source_id", ""))
        status = status_by_source.get(source_id)
        if not status:
            raise ValueError(f"screened source missing status row: {source_id}")
        if decision.get("screening_decision") == "include_for_fulltext":
            if status.get("fulltext_status") not in {"found", "missing", "deferred", "failed"}:
                raise ValueError(f"include source did not check fulltext: {source_id}")
            if status.get("fulltext_status") == "missing" and status.get("overall_status") != "blocked_external":
                raise ValueError(f"missing fulltext source not blocked_external: {source_id}")
        if decision.get("screening_decision") == "exclude":
            if status.get("parse_status") != "not_started" or status.get("extraction_status") != "not_started":
                raise ValueError(f"excluded source was parsed or extracted: {source_id}")
        if decision.get("screening_decision") == "manual_screen":
            if status.get("extraction_status") != "not_started":
                raise ValueError(f"manual_screen source was extracted automatically: {source_id}")


def validate_synchronous_review(rows: dict[str, list[dict[str, Any]]]) -> None:
    candidate_ids = {str(row.get("record_id", "")) for row in rows["candidates"]}
    reviewed_ids = {str(row.get("record_id", "")) for row in rows["reviewed"]}
    missing = candidate_ids - reviewed_ids
    if missing:
        raise ValueError(f"candidate records missing review: {sorted(missing)[:5]}")
    terminal_ids = {str(row.get("record_id", "")) for row in [*rows["validated"], *rows["manual"], *rows["auxiliary"]]}
    rejected_ids = {str(row.get("record_id", "")) for row in rows["rejected"]}
    for row in rows["reviewed"]:
        lineage = row.get("task_lineage", {})
        if lineage.get("synchronous") is not True:
            raise ValueError(f"reviewed record missing synchronous lineage: {row.get('record_id')}")
        if not row.get("database_write_ref"):
            raise ValueError(f"reviewed record missing database_write_ref: {row.get('record_id')}")
        status = row.get("review", {}).get("review_status")
        record_id = str(row.get("record_id", ""))
        if status in {"validated", "manual_review", "auxiliary_engineered"} and record_id not in terminal_ids:
            raise ValueError(f"reviewed record not written to terminal output: {record_id}")
        if status == "rejected" and record_id not in rejected_ids:
            raise ValueError(f"rejected reviewed record missing rejected output: {record_id}")


def validate_boundaries(validated: list[dict[str, Any]]) -> None:
    for row in validated:
        text = json.dumps(row, ensure_ascii=False).lower()
        hits = [term for term in FORBIDDEN_VALIDATED if term in text]
        if hits:
            raise ValueError(f"forbidden boundary in validated record {row.get('record_id')}: {hits}")
        if row.get("review", {}).get("natural_environment_valid") is not True:
            raise ValueError(f"validated record lacks natural_environment_valid: {row.get('record_id')}")


def validate_no_duplicate_reprocessing(previous_rows: dict[str, list[dict[str, Any]]], current_rows: dict[str, list[dict[str, Any]]]) -> None:
    previous_sources = {str(row.get("source_id", "")) for row in previous_rows["status"] if row.get("source_id")}
    for row in strict_jsonl(STATE / "source_registry.jsonl"):
        refs = [
            str(row.get("candidate_records_ref", "")),
            str(row.get("reviewed_records_ref", "")),
            str(row.get("validated_records_ref", "")),
            str(row.get("rejected_records_ref", "")),
        ]
        if any(refs) and not any("stage2_6d_streaming" in ref for ref in refs):
            previous_sources.add(str(row.get("source_id", "")))
    current_sources = {str(row.get("source_id", "")) for row in current_rows["status"] if row.get("source_id")}
    overlap = previous_sources & current_sources
    if overlap:
        raise ValueError(f"stage2_6d reprocessed previous stage2_6c sources: {sorted(overlap)[:10]}")


def validate_context(rows: dict[str, list[dict[str, Any]]]) -> None:
    forbidden_screening_keys = {"pdf_path", "local_path", "full_text", "chunks", "chunks_ref", "text", "chunk_text"}
    for row in rows["screening"]:
        if forbidden_screening_keys & set(row):
            raise ValueError(f"screening decision contains forbidden fulltext keys: {row.get('source_id')}")
    for event in rows["events"]:
        if event.get("long_context_passed") is not False:
            raise ValueError(f"long context violation in event: {event.get('event_id')}")
        if event.get("stage") == "screening" and event.get("fulltext_passed_to_screening") is not False:
            raise ValueError(f"screening received fulltext context: {event.get('event_id')}")


def validate_report_counts(summary: dict[str, str], rows: dict[str, list[dict[str, Any]]], previous_rows: dict[str, list[dict[str, Any]]]) -> None:
    previous_screened = len({str(row.get("source_id", "")) for row in previous_rows["status"] if row.get("screening_status") in {"done", "cache_hit"} and row.get("source_id")})
    expected = {
        "previous_sources_screened": previous_screened,
        "new_sources_screened": len(rows["screening"]),
        "cumulative_sources_screened": previous_screened + len(rows["screening"]),
        "sources_screened": len(rows["screening"]),
        "include_for_fulltext": sum(1 for row in rows["screening"] if row.get("screening_decision") == "include_for_fulltext"),
        "manual_screen": sum(1 for row in rows["screening"] if row.get("screening_decision") == "manual_screen"),
        "exclude": sum(1 for row in rows["screening"] if row.get("screening_decision") == "exclude"),
        "fulltext_found": sum(1 for row in rows["status"] if row.get("fulltext_status") == "found"),
        "fulltext_missing": sum(1 for row in rows["status"] if row.get("fulltext_status") == "missing"),
        "candidate_records": len(rows["candidates"]),
        "reviewed_records": len(rows["reviewed"]),
        "validated_records": len(rows["validated"]),
        "manual_review_records": len(rows["manual"]),
        "rejected_records": len(rows["rejected"]),
        "auxiliary_records": len(rows["auxiliary"]),
        "pending_tasks_remaining": 0,
    }
    for key, value in expected.items():
        if as_int(summary, key) != value:
            raise ValueError(f"summary count mismatch for {key}: expected {value}, got {summary.get(key)}")
    if not as_bool(summary, "workflow_streaming_success"):
        raise ValueError("workflow_streaming_success must be true")
    if not as_bool(summary, "ready_for_next_streaming_batch"):
        raise ValueError("ready_for_next_streaming_batch must be true")
    if not as_bool(summary, "strict_jsonl_audit_passed"):
        raise ValueError("strict_jsonl_audit_passed must be true")
    if as_int(summary, "long_context_violations") != 0 or as_int(summary, "fulltext_context_violations") != 0:
        raise ValueError("context violations must be zero")


def validate_no_raw_fulltext_tracked() -> None:
    result = subprocess.run(["git", "ls-files"], cwd=ROOT, text=True, capture_output=True, check=False)
    bad = [line for line in result.stdout.splitlines() if Path(line).suffix.lower() in {".pdf", ".html", ".htm", ".xhtml", ".sqlite"}]
    if bad:
        raise ValueError(f"raw fulltext tracked by git: {bad[:10]}")


def main() -> int:
    rows = load_prefix(PREFIX)
    previous_rows = load_prefix(PREVIOUS_PREFIX)
    summary = parse_report(SUMMARY)
    validate_status_logic(rows["status"], rows["screening"])
    validate_synchronous_review(rows)
    validate_boundaries(rows["validated"])
    validate_no_duplicate_reprocessing(previous_rows, rows)
    validate_context(rows)
    validate_report_counts(summary, rows, previous_rows)
    validate_no_raw_fulltext_tracked()
    output = {
        "new_sources_screened": as_int(summary, "new_sources_screened"),
        "candidate_records": len(rows["candidates"]),
        "reviewed_records": len(rows["reviewed"]),
        "ready_for_larger_streaming_batch": as_bool(summary, "ready_for_larger_streaming_batch"),
        "workflow_streaming_success": as_bool(summary, "workflow_streaming_success"),
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
