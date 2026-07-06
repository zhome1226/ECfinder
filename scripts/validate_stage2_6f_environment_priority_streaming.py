"""Validate Stage 2.6f environment-prioritized streaming outputs."""

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
PREFIX = "stage2_6f_streaming"
SUMMARY = REPORTS / f"{PREFIX}_autonomous_summary.md"
QUEUE = BATCH / "stage2_6f_environment_priority_queue.jsonl"
VERIFY_REPORT = REPORTS / "stage2_6e_commit_blob_jsonl_verification.md"

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


def source_keys(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("source_id", "")),
        str(row.get("zotero_item_key", "")),
        str(row.get("doi", "")).strip().lower(),
    )


def validate_stage2_6e_blob_report() -> None:
    values = parse_report(VERIFY_REPORT)
    if values.get("all_targets_strict_jsonl") != "true":
        raise ValueError("Stage 2.6e commit blob verification did not pass strict JSONL")
    if values.get("all_sha256_match") != "true":
        raise ValueError("Stage 2.6e commit blob verification did not pass sha256 matching")
    if int(values.get("targets", "0")) != 10:
        raise ValueError("Stage 2.6e commit blob verification target count mismatch")


def validate_queue(queue: list[dict[str, Any]]) -> None:
    if not queue:
        raise ValueError("stage2_6f environment priority queue is empty")
    previous_score = None
    for row in queue:
        if row.get("status") != "pending_streaming":
            raise ValueError(f"queue item not pending_streaming: {row.get('source_id')}")
        if row.get("previous_screening_decision") == "exclude":
            raise ValueError(f"previous exclude source entered queue: {row.get('source_id')}")
        if row.get("previous_overall_status") in {"validated", "rejected", "auxiliary", "completed_no_records", "excluded"}:
            raise ValueError(f"previous completed source entered queue: {row.get('source_id')}")
        if int(row.get("environment_score", 0)) <= 0 or int(row.get("transformation_score", 0)) <= 0:
            raise ValueError(f"queue item lacks environment/transformation score: {row.get('source_id')}")
        if int(row.get("priority_score", 0)) < 100:
            raise ValueError(f"queue item below inclusion threshold: {row.get('source_id')}")
        sort_key = (
            int(row.get("priority_score", 0)),
            bool(row.get("has_pdf_or_html_attachment")),
            row.get("previous_screening_decision") == "include_for_fulltext",
            int(row.get("environment_score", 0)),
            int(row.get("transformation_score", 0)),
        )
        if previous_score is not None and sort_key > previous_score:
            raise ValueError("environment priority queue is not sorted by configured priority")
        previous_score = sort_key


def validate_status_logic(rows: dict[str, list[dict[str, Any]]]) -> None:
    status_by_source = {str(row.get("source_id", "")): row for row in rows["status"]}
    if len(status_by_source) != len(rows["status"]):
        raise ValueError("duplicate source_id in stage2_6f source status")
    chunk_sources = {str(row.get("source_id", "")) for row in rows["chunks"]}
    for decision in rows["screening"]:
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
    for status in rows["status"]:
        source_id = str(status.get("source_id", ""))
        if status.get("fulltext_status") == "found":
            if status.get("parse_status") not in {"done", "skipped"}:
                raise ValueError(f"fulltext_found source was not parsed/chunked: {source_id}")
            if status.get("parse_status") in {"done", "skipped"} and source_id not in chunk_sources and status.get("next_action") != "no_high_relevance_chunks":
                raise ValueError(f"parsed source missing chunk relevance screening: {source_id}")


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


def validate_no_duplicate_reprocessing(current_rows: dict[str, list[dict[str, Any]]], queue: list[dict[str, Any]]) -> None:
    allowed_ids = {str(row.get("source_id", "")) for row in queue if row.get("allow_manual_rescreen") is True and row.get("source_id")}
    allowed_keys = {str(row.get("zotero_item_key", "")) for row in queue if row.get("allow_manual_rescreen") is True and row.get("zotero_item_key")}
    allowed_dois = {str(row.get("doi", "")).strip().lower() for row in queue if row.get("allow_manual_rescreen") is True and row.get("doi")}
    previous_ids: set[str] = set()
    previous_keys: set[str] = set()
    previous_dois: set[str] = set()
    for prefix in ["stage2_6c_streaming", "stage2_6d_streaming", "stage2_6e_streaming"]:
        for row in strict_jsonl(STATE / f"{prefix}_source_status.jsonl"):
            source_id, zotero_key, doi = source_keys(row)
            if row.get("overall_status") == "manual_screen":
                continue
            if source_id:
                previous_ids.add(source_id)
            if zotero_key:
                previous_keys.add(zotero_key)
            if doi:
                previous_dois.add(doi)
    for row in strict_jsonl(STATE / "source_registry.jsonl"):
        refs = " ".join(str(row.get(key, "")) for key in ["reviewed_records_ref", "validated_records_ref", "rejected_records_ref", "candidate_records_ref"])
        if "stage2_6f_streaming" in refs:
            continue
        if row.get("status") not in {"validated", "rejected", "auxiliary", "manual_review"}:
            continue
        source_id, zotero_key, doi = source_keys(row)
        if source_id:
            previous_ids.add(source_id)
        if zotero_key:
            previous_keys.add(zotero_key)
        if doi:
            previous_dois.add(doi)
    previous_ids -= allowed_ids
    previous_keys -= allowed_keys
    previous_dois -= allowed_dois
    for row in current_rows["status"]:
        source_id, zotero_key, doi = source_keys(row)
        if (source_id and source_id in previous_ids) or (zotero_key and zotero_key in previous_keys) or (doi and doi in previous_dois):
            raise ValueError(f"stage2_6f reprocessed previous/completed source: {source_id or zotero_key or doi}")


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


def validate_report_counts(summary: dict[str, str], rows: dict[str, list[dict[str, Any]]], queue: list[dict[str, Any]]) -> None:
    previous_screened = len(
        {
            str(row.get("source_id", ""))
            for prefix in ["stage2_6c_streaming", "stage2_6d_streaming", "stage2_6e_streaming"]
            for row in strict_jsonl(STATE / f"{prefix}_source_status.jsonl")
            if row.get("screening_status") in {"done", "cache_hit"} and row.get("source_id")
        }
    )
    expected = {
        "priority_queue_size": len(queue),
        "metadata_sources_seen": len(queue),
        "previous_sources_screened": previous_screened,
        "new_sources_screened": len(rows["screening"]),
        "cumulative_sources_screened": previous_screened + len(rows["screening"]),
        "sources_with_pdf_or_html_attachment_in_queue": sum(1 for row in queue if row.get("has_pdf_or_html_attachment")),
        "environment_priority_sources": sum(1 for row in queue if int(row.get("environment_score", 0) or 0) > 0 and int(row.get("transformation_score", 0) or 0) > 0),
        "previous_include_sources": sum(1 for row in queue if row.get("previous_screening_decision") == "include_for_fulltext"),
        "manual_rescreen_sources": sum(1 for row in queue if row.get("allow_manual_rescreen") is True),
        "include_for_fulltext": sum(1 for row in rows["screening"] if row.get("screening_decision") == "include_for_fulltext"),
        "manual_screen": sum(1 for row in rows["screening"] if row.get("screening_decision") == "manual_screen"),
        "exclude": sum(1 for row in rows["screening"] if row.get("screening_decision") == "exclude"),
        "fulltext_found": sum(1 for row in rows["status"] if row.get("fulltext_status") == "found"),
        "fulltext_missing": sum(1 for row in rows["status"] if row.get("fulltext_status") == "missing"),
        "sources_parsed": sum(1 for row in rows["status"] if row.get("parse_status") in {"done", "skipped"}),
        "chunks_created": len(rows["chunks"]),
        "sources_extracted": sum(1 for row in rows["status"] if row.get("extraction_status") == "done"),
        "candidate_records": len(rows["candidates"]),
        "reviewed_records": len(rows["reviewed"]),
        "validated_records": len(rows["validated"]),
        "manual_review_records": len(rows["manual"]),
        "rejected_records": len(rows["rejected"]),
        "auxiliary_records": len(rows["auxiliary"]),
        "database_records_written": len(rows["validated"]) + len(rows["manual"]) + len(rows["rejected"]) + len(rows["auxiliary"]),
        "blocked_external_sources": sum(1 for row in rows["status"] if row.get("overall_status") == "blocked_external"),
        "pending_tasks_remaining": 0,
    }
    for key, value in expected.items():
        if as_int(summary, key) != value:
            raise ValueError(f"summary count mismatch for {key}: expected {value}, got {summary.get(key)}")
    if not as_bool(summary, "workflow_streaming_success"):
        raise ValueError("workflow_streaming_success must be true")
    if not as_bool(summary, "ready_for_next_streaming_batch"):
        raise ValueError("ready_for_next_streaming_batch must be true")
    if as_int(summary, "long_context_violations") != 0 or as_int(summary, "fulltext_context_violations") != 0:
        raise ValueError("context violations must be zero")
    chain_expected = (
        expected["new_sources_screened"] > 0
        and expected["pending_tasks_remaining"] == 0
        and as_int(summary, "long_context_violations") == 0
        and as_int(summary, "fulltext_context_violations") == 0
        and as_bool(summary, "strict_jsonl_audit_passed")
        and as_bool(summary, "no_duplicate_source_reprocessing")
    )
    ready_larger_expected = (
        chain_expected
        and expected["sources_extracted"] >= 1
        and expected["candidate_records"] >= 1
        and expected["reviewed_records"] == expected["candidate_records"]
        and expected["database_records_written"] >= expected["reviewed_records"]
    )
    if as_bool(summary, "environment_priority_chain_verified") != chain_expected:
        raise ValueError("environment_priority_chain_verified does not match readiness criteria")
    if as_bool(summary, "ready_for_larger_environment_stream") != ready_larger_expected:
        raise ValueError("ready_for_larger_environment_stream does not match readiness criteria")


def validate_no_raw_fulltext_tracked() -> None:
    result = subprocess.run(["git", "ls-files"], cwd=ROOT, text=True, capture_output=True, check=False)
    bad = [line for line in result.stdout.splitlines() if Path(line).suffix.lower() in {".pdf", ".html", ".htm", ".xhtml", ".sqlite"}]
    if bad:
        raise ValueError(f"raw fulltext tracked by git: {bad[:10]}")


def main() -> int:
    validate_stage2_6e_blob_report()
    queue = strict_jsonl(QUEUE)
    validate_queue(queue)
    for prefix in ["stage2_6c_streaming", "stage2_6d_streaming", "stage2_6e_streaming"]:
        load_prefix(prefix)
    rows = load_prefix(PREFIX)
    summary = parse_report(SUMMARY)
    validate_status_logic(rows)
    validate_synchronous_review(rows)
    validate_boundaries(rows["validated"])
    validate_no_duplicate_reprocessing(rows, queue)
    validate_context(rows)
    validate_report_counts(summary, rows, queue)
    validate_no_raw_fulltext_tracked()
    output = {
        "candidate_records": len(rows["candidates"]),
        "environment_priority_chain_verified": as_bool(summary, "environment_priority_chain_verified"),
        "priority_queue_size": len(queue),
        "ready_for_larger_environment_stream": as_bool(summary, "ready_for_larger_environment_stream"),
        "workflow_streaming_success": as_bool(summary, "workflow_streaming_success"),
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
