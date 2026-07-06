"""Validate Stage 2.7 production autonomous daemon outputs."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "data" / "batches"
STATE = ROOT / "data" / "state"
REPORTS = ROOT / "reports"
SUMMARY = REPORTS / "stage2_7_production_daemon_summary.md"
DRY_RUN_REPORT = REPORTS / "stage2_7_daemon_discovery_dry_run.md"

STAGE2_7_BATCH_FILES = {
    "screening": BATCH / "stage2_7_screening_decisions.jsonl",
    "chunks": BATCH / "stage2_7_chunk_screening.jsonl",
    "candidates": BATCH / "stage2_7_candidate_records.jsonl",
    "reviewed": BATCH / "stage2_7_reviewed_records.jsonl",
    "validated": BATCH / "stage2_7_validated_records.jsonl",
    "manual": BATCH / "stage2_7_manual_review_records.jsonl",
    "rejected": BATCH / "stage2_7_rejected_records.jsonl",
    "auxiliary": BATCH / "stage2_7_auxiliary_records.jsonl",
}
STAGE2_7_STATE_FILES = {
    "status": STATE / "stage2_7_library_source_status.jsonl",
    "events": STATE / "stage2_7_daemon_events.jsonl",
    "blocked": STATE / "stage2_7_blocked_external_queue.jsonl",
    "manual_queue": STATE / "stage2_7_manual_screen_queue.jsonl",
    "deferred": STATE / "stage2_7_deferred_queue.jsonl",
    "completed": STATE / "stage2_7_completed_sources.jsonl",
}
REQUIRED_REPORT_FIELDS = {
    "stage2_7_production_daemon_summary.md": {
        "batch_id",
        "library_total_sources",
        "new_sources_screened",
        "runnable_sources_discovered_after_run",
        "safe_stop_triggered",
        "ended_because",
        "no_runnable_sources_remain",
        "workflow_production_daemon_success",
        "ready_for_unattended_long_run",
        "reason",
    },
    "stage2_7_production_daemon_status_board.md": {"source_id", "overall", "next_action"},
    "stage2_7_runnable_source_audit.md": {"library_total_sources", "runnable_sources_discovered"},
    "stage2_7_blocked_source_audit.md": {"blocked_external_sources"},
    "stage2_7_completed_source_audit.md": {"sources_excluded_this_run", "manual_screen_sources"},
    "stage2_7_token_budget_audit.md": {"screening_cache_hits", "estimated_total_tokens"},
    "stage2_7_skill_invocation_audit.md": {"skill_invocation_audit_passed", "skill_invocations"},
    "stage2_7_synchronous_review_audit.md": {"candidate_records", "reviewed_records"},
    "stage2_7_database_write_audit.md": {"database_records_written"},
    "stage2_7_strict_jsonl_audit.md": {"strict_jsonl_audit_passed"},
    "stage2_7_jsonl_serialization_repair_audit.md": {"all_targets_strict_jsonl"},
    "stage2_7_daemon_discovery_dry_run.md": {"runnable_sources_remaining", "would_continue"},
}
FORBIDDEN_VALIDATED = {
    "activated sludge",
    "wwtp",
    "wastewater treatment",
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
    text = require(path).read_text(encoding="utf-8")
    if len(text.strip()) == 0:
        raise ValueError(f"empty report: {path}")
    for line in text.splitlines():
        match = pattern.match(line)
        if match:
            values[match.group(1)] = match.group(2)
    return values


def as_int(values: dict[str, str], key: str) -> int:
    return int(values.get(key, "0"))


def as_bool(values: dict[str, str], key: str) -> bool:
    return values.get(key, "false") == "true"


def report_status(values: dict[str, str], key: str) -> str:
    return values.get(key, "").strip().lower()


def has_raw_newline(value: Any) -> bool:
    if isinstance(value, dict):
        return any("\n" in str(key) or "\r" in str(key) or has_raw_newline(child) for key, child in value.items())
    if isinstance(value, list):
        return any(has_raw_newline(child) for child in value)
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
            if has_raw_newline(obj):
                raise ValueError(f"{path}:{line_no} contains raw CR/LF inside parsed string")
            rows.append(obj)
    return rows


def load_stage2_7() -> dict[str, list[dict[str, Any]]]:
    rows = {name: strict_jsonl(path) for name, path in STAGE2_7_BATCH_FILES.items()}
    rows.update({name: strict_jsonl(path) for name, path in STAGE2_7_STATE_FILES.items()})
    return rows


def validate_previous_strict_jsonl() -> None:
    for prefix in ["stage2_6c_streaming", "stage2_6d_streaming", "stage2_6e_streaming", "stage2_6f_streaming"]:
        for path in [
            STATE / f"{prefix}_source_status.jsonl",
            STATE / f"{prefix}_events.jsonl",
            BATCH / f"{prefix}_screening_decisions.jsonl",
            BATCH / f"{prefix}_chunk_screening.jsonl",
            BATCH / f"{prefix}_candidate_records.jsonl",
            BATCH / f"{prefix}_reviewed_records.jsonl",
            BATCH / f"{prefix}_validated_records.jsonl",
            BATCH / f"{prefix}_manual_review_records.jsonl",
            BATCH / f"{prefix}_rejected_records.jsonl",
            BATCH / f"{prefix}_auxiliary_records.jsonl",
        ]:
            strict_jsonl(path)


def validate_required_reports() -> None:
    for name, required_fields in REQUIRED_REPORT_FIELDS.items():
        path = REPORTS / name
        text = require(path).read_text(encoding="utf-8")
        meaningful_lines = [line for line in text.splitlines() if line.strip() and not line.strip().startswith("#")]
        if len(text.strip()) < 40 or not meaningful_lines:
            raise ValueError(f"report has no effective audit content: {path}")
        missing = [field for field in required_fields if field not in text]
        if missing:
            raise ValueError(f"report {path} missing required fields: {missing}")


def validate_files_and_docs() -> None:
    for path in [
        ROOT / "scripts" / "repair_stage2_7_jsonl_serialization.py",
        ROOT / "scripts" / "run_production_autonomous_daemon.py",
        ROOT / "src" / "ecfinder" / "orchestration" / "production_daemon.py",
        ROOT / "src" / "ecfinder" / "orchestration" / "runnable_source_discovery.py",
        ROOT / "src" / "ecfinder" / "orchestration" / "autonomous_loop.py",
        ROOT / "src" / "ecfinder" / "orchestration" / "safe_stop.py",
        ROOT / "src" / "ecfinder" / "orchestration" / "checkpointing.py",
        ROOT / "src" / "ecfinder" / "orchestration" / "library_progress.py",
        ROOT / "docs" / "PRODUCTION_AUTONOMOUS_WORKFLOW.md",
        ROOT / "docs" / "OPERATION_MANUAL.md",
        REPORTS / "stage2_7_runnable_source_audit.md",
        REPORTS / "stage2_7_skill_manager_recommendations.md",
    ]:
        require(path)
    readme = require(ROOT / "README.md").read_text(encoding="utf-8")
    if "PRODUCTION_AUTONOMOUS_WORKFLOW.md" not in readme or "OPERATION_MANUAL.md" not in readme:
        raise ValueError("README does not point to the production autonomous workflow docs")


def source_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("source_id", "")),
        str(row.get("zotero_item_key", "")),
        str(row.get("doi", "")).strip().lower(),
    )


def validate_no_duplicate_completed_reprocessing(current_status: list[dict[str, Any]]) -> None:
    previous_terminal_ids: set[str] = set()
    previous_terminal_keys: set[str] = set()
    previous_terminal_dois: set[str] = set()
    for prefix in ["stage2_6c_streaming", "stage2_6d_streaming", "stage2_6e_streaming", "stage2_6f_streaming"]:
        for row in strict_jsonl(STATE / f"{prefix}_source_status.jsonl"):
            if row.get("overall_status") not in {"validated", "rejected", "auxiliary", "completed_no_records", "excluded"}:
                continue
            source_id, key, doi = source_key(row)
            if source_id:
                previous_terminal_ids.add(source_id)
            if key:
                previous_terminal_keys.add(key)
            if doi:
                previous_terminal_dois.add(doi)
    for row in current_status:
        source_id, key, doi = source_key(row)
        if (source_id and source_id in previous_terminal_ids) or (key and key in previous_terminal_keys) or (doi and doi in previous_terminal_dois):
            raise ValueError(f"Stage 2.7 reprocessed previously completed source: {source_id or key or doi}")


def validate_status_logic(rows: dict[str, list[dict[str, Any]]]) -> None:
    status = rows["status"]
    status_by_source = {str(row.get("source_id", "")): row for row in status}
    if len(status_by_source) != len(status):
        raise ValueError("duplicate source_id in Stage 2.7 source status")
    chunk_sources = {str(row.get("source_id", "")) for row in rows["chunks"]}
    for decision in rows["screening"]:
        source_id = str(decision.get("source_id", ""))
        row = status_by_source.get(source_id)
        if not row:
            raise ValueError(f"screening decision missing source status: {source_id}")
        if decision.get("screening_decision") == "include_for_fulltext":
            if row.get("fulltext_status") not in {"found", "missing", "deferred", "failed"}:
                raise ValueError(f"include source did not check fulltext: {source_id}")
        if decision.get("screening_decision") == "exclude":
            if row.get("parse_status") != "not_started" or row.get("extraction_status") != "not_started":
                raise ValueError(f"excluded source was parsed or extracted: {source_id}")
        if decision.get("screening_decision") == "manual_screen":
            if row.get("extraction_status") != "not_started":
                raise ValueError(f"manual_screen source was automatically extracted: {source_id}")
    for row in status:
        source_id = str(row.get("source_id", ""))
        if row.get("fulltext_status") == "missing" and row.get("overall_status") != "blocked_external":
            raise ValueError(f"missing fulltext source is not blocked_external: {source_id}")
        if row.get("fulltext_status") == "found":
            if row.get("parse_status") not in {"done", "skipped"}:
                raise ValueError(f"fulltext_found source not parsed/chunked: {source_id}")
            if row.get("parse_status") in {"done", "skipped"} and source_id not in chunk_sources and row.get("next_action") != "no_high_relevance_chunks":
                raise ValueError(f"parsed source missing chunk relevance rows: {source_id}")


def validate_context_and_events(rows: dict[str, list[dict[str, Any]]]) -> None:
    forbidden_screening_keys = {"pdf_path", "local_path", "full_text", "chunks", "chunks_ref", "text", "chunk_text"}
    for row in rows["screening"]:
        if forbidden_screening_keys & set(row):
            raise ValueError(f"screening row contains fulltext context: {row.get('source_id')}")
        if row.get("input_fields") != ["source_id", "doi", "title", "abstract", "year", "journal", "keywords"]:
            raise ValueError(f"screening input fields changed: {row.get('source_id')}")
    extract_sources = {str(row.get("source_id", "")) for row in rows["chunks"] if row.get("relevance_decision") == "extract"}
    for event in rows["events"]:
        if event.get("long_context_passed") is not False:
            raise ValueError(f"long context violation: {event.get('event_id')}")
        if event.get("stage") == "screening" and event.get("fulltext_passed_to_screening") is not False:
            raise ValueError(f"fulltext passed to screening: {event.get('event_id')}")
        if event.get("agent") == "ParseAgent":
            refs = event.get("input_refs", {})
            if "chunks_ref" not in refs or "full_text" in refs or "local_path" in refs:
                raise ValueError(f"parse event contains invalid refs: {event.get('event_id')}")
        if event.get("agent") == "ExtractionAgent" and str(event.get("source_id", "")) not in extract_sources:
            raise ValueError(f"extraction source has no high-relevance chunk: {event.get('source_id')}")


def validate_synchronous_review_and_database(rows: dict[str, list[dict[str, Any]]]) -> None:
    candidate_ids = {str(row.get("record_id", "")) for row in rows["candidates"]}
    reviewed_ids = {str(row.get("record_id", "")) for row in rows["reviewed"]}
    if candidate_ids - reviewed_ids:
        raise ValueError(f"unreviewed candidate records: {sorted(candidate_ids - reviewed_ids)[:5]}")
    terminal_ids = {str(row.get("record_id", "")) for row in [*rows["validated"], *rows["manual"], *rows["auxiliary"]]}
    rejected_ids = {str(row.get("record_id", "")) for row in rows["rejected"]}
    for row in rows["reviewed"]:
        lineage = row.get("task_lineage", {})
        if lineage.get("synchronous") is not True:
            raise ValueError(f"reviewed record missing synchronous lineage: {row.get('record_id')}")
        if not row.get("database_write_ref"):
            raise ValueError(f"reviewed record missing database write ref: {row.get('record_id')}")
        status = row.get("review", {}).get("review_status")
        record_id = str(row.get("record_id", ""))
        if status in {"validated", "manual_review", "auxiliary_engineered"} and record_id not in terminal_ids:
            raise ValueError(f"reviewed record not written to terminal database file: {record_id}")
        if status == "rejected" and record_id not in rejected_ids:
            raise ValueError(f"rejected reviewed record missing rejected output: {record_id}")


def validate_boundaries(validated: list[dict[str, Any]]) -> None:
    for row in validated:
        text = json.dumps(row, ensure_ascii=False).lower()
        hits = [term for term in FORBIDDEN_VALIDATED if term in text]
        if hits:
            raise ValueError(f"forbidden natural boundary in validated record {row.get('record_id')}: {hits}")
        if row.get("review", {}).get("natural_environment_valid") is not True:
            raise ValueError(f"validated record is not natural_environment_valid: {row.get('record_id')}")


def validate_report_counts(summary: dict[str, str], rows: dict[str, list[dict[str, Any]]]) -> None:
    expected = {
        "new_sources_seen": len(rows["status"]),
        "new_sources_screened": len(rows["screening"]),
        "processed_sources": len(rows["status"]),
        "screened_sources": len(rows["screening"]),
        "sources_completed_this_run": sum(1 for row in rows["status"] if row.get("overall_status") in {"validated", "rejected", "auxiliary", "completed_no_records"}),
        "sources_excluded_this_run": sum(1 for row in rows["status"] if row.get("overall_status") == "excluded"),
        "manual_screen_sources": sum(1 for row in rows["status"] if row.get("overall_status") == "manual_screen"),
        "blocked_external_sources": sum(1 for row in rows["status"] if row.get("overall_status") == "blocked_external"),
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
        "pending_tasks_remaining": 0,
    }
    for key, value in expected.items():
        if as_int(summary, key) != value:
            raise ValueError(f"summary count mismatch for {key}: expected {value}, got {summary.get(key)}")
    if as_int(summary, "long_context_violations") != 0 or as_int(summary, "fulltext_context_violations") != 0:
        raise ValueError("context violations must be zero")
    if as_int(summary, "duplicate_work_violations") != 0:
        raise ValueError("duplicate work violations must be zero")
    if as_int(summary, "boundary_violations") != 0:
        raise ValueError("boundary violations must be zero")
    if as_int(summary, "candidate_records") != as_int(summary, "reviewed_records"):
        raise ValueError("candidate_records must equal reviewed_records")
    ended_because = summary.get("ended_because", "")
    ready = as_bool(summary, "ready_for_unattended_long_run")
    no_runnable = as_bool(summary, "no_runnable_sources_remain")
    runnable_after = as_int(summary, "runnable_sources_discovered_after_run")
    workflow_status = report_status(summary, "workflow_production_daemon_success")
    if ended_because == "max_new_screen_reached" and ready:
        raise ValueError("max_new_screen_reached cannot be ready_for_unattended_long_run")
    if runnable_after > 0 and no_runnable:
        raise ValueError("runnable sources remain but no_runnable_sources_remain is true")
    if runnable_after > 0 and ready:
        raise ValueError("runnable sources remain but ready_for_unattended_long_run is true")
    if workflow_status not in {"true", "partial"}:
        raise ValueError("workflow_production_daemon_success must be true or partial")
    if workflow_status == "partial":
        if not as_bool(summary, "safe_stop_triggered") or runnable_after <= 0 or ready:
            raise ValueError("partial workflow status requires safe stop, remaining runnable sources, and ready=false")
        if summary.get("reason") != "safety_limit_reached_before_library_exhausted_and_no_fulltext_extraction_verified":
            raise ValueError("partial Stage 2.7 summary has the wrong reason")
    if as_bool(summary, "ready_for_unattended_long_run") and as_int(summary, "checkpoint_count") < 1:
        raise ValueError("ready_for_unattended_long_run requires checkpoint_count >= 1")


def validate_status_board_consistency(status_rows: list[dict[str, Any]]) -> None:
    board = require(REPORTS / "stage2_7_production_daemon_status_board.md").read_text(encoding="utf-8").splitlines()
    data_lines = [line for line in board if line.startswith("| ") and not line.startswith("| ---") and "source_id" not in line]
    if len(data_lines) != len(status_rows):
        raise ValueError("status board row count does not match source status JSONL")


def validate_discovery_dry_run(summary: dict[str, str]) -> None:
    dry_run = parse_report(DRY_RUN_REPORT)
    remaining = as_int(dry_run, "runnable_sources_remaining")
    would_continue = as_bool(dry_run, "would_continue")
    if remaining > 0 and not would_continue:
        raise ValueError("dry-run discovery found runnable sources but would_continue is false")
    if remaining == 0 and would_continue:
        raise ValueError("dry-run discovery found no runnable sources but would_continue is true")
    if remaining != as_int(summary, "runnable_sources_discovered_after_run"):
        raise ValueError("dry-run remaining runnable count does not match summary runnable_sources_discovered_after_run")


def validate_no_raw_fulltext_tracked() -> None:
    result = subprocess.run(["git", "ls-files"], cwd=ROOT, text=True, capture_output=True, check=False)
    bad = [
        line
        for line in result.stdout.splitlines()
        if Path(line).suffix.lower() in {".pdf", ".html", ".htm", ".xhtml", ".sqlite"}
    ]
    if bad:
        raise ValueError(f"raw fulltext tracked by git: {bad[:10]}")


def main() -> int:
    validate_files_and_docs()
    validate_previous_strict_jsonl()
    rows = load_stage2_7()
    summary = parse_report(SUMMARY)
    validate_required_reports()
    validate_no_duplicate_completed_reprocessing(rows["status"])
    validate_status_logic(rows)
    validate_context_and_events(rows)
    validate_synchronous_review_and_database(rows)
    validate_boundaries(rows["validated"])
    validate_report_counts(summary, rows)
    validate_status_board_consistency(rows["status"])
    validate_discovery_dry_run(summary)
    validate_no_raw_fulltext_tracked()
    output = {
        "new_sources_screened": as_int(summary, "new_sources_screened"),
        "ready_for_unattended_long_run": as_bool(summary, "ready_for_unattended_long_run"),
        "runnable_sources_discovered_after_run": as_int(summary, "runnable_sources_discovered_after_run"),
        "workflow_production_daemon_success": summary.get("workflow_production_daemon_success", ""),
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
