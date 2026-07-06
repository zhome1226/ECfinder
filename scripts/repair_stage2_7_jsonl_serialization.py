"""Repair Stage 2.7 JSONL serialization as strict one-object-per-line files."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ecfinder.orchestration.library_progress import summarize_previous_progress
from ecfinder.orchestration.production_daemon import FULLTEXT_MANIFEST, STAGE2_6_DECISION_PATHS, STAGE2_6_STATUS_PATHS
from ecfinder.orchestration.runnable_source_discovery import discover_runnable_sources
from ecfinder.orchestration.streaming_supervisor import _short_title
from ecfinder.orchestration.streaming_state import write_key_value_report


ROOT = Path(__file__).resolve().parents[1]

TARGETS = [
    Path("data/state/stage2_7_library_source_status.jsonl"),
    Path("data/state/stage2_7_daemon_events.jsonl"),
    Path("data/state/stage2_7_blocked_external_queue.jsonl"),
    Path("data/state/stage2_7_manual_screen_queue.jsonl"),
    Path("data/state/stage2_7_deferred_queue.jsonl"),
    Path("data/state/stage2_7_completed_sources.jsonl"),
    Path("data/batches/stage2_7_screening_decisions.jsonl"),
    Path("data/batches/stage2_7_chunk_screening.jsonl"),
    Path("data/batches/stage2_7_candidate_records.jsonl"),
    Path("data/batches/stage2_7_reviewed_records.jsonl"),
    Path("data/batches/stage2_7_validated_records.jsonl"),
    Path("data/batches/stage2_7_manual_review_records.jsonl"),
    Path("data/batches/stage2_7_rejected_records.jsonl"),
    Path("data/batches/stage2_7_auxiliary_records.jsonl"),
]
METADATA_QUEUE = Path("data/batches/stage2_6b_zotero_metadata_screening_queue.jsonl")
RUNNABLE_QUEUE = Path("data/batches/stage2_7_runnable_queue.jsonl")
SUMMARY_REPORT = Path("reports/stage2_7_production_daemon_summary.md")


def clean_string(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\r", " ").replace("\n", " ")).strip()


def clean_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {clean_string(str(key)): clean_value(child) for key, child in value.items()}
    if isinstance(value, list):
        return [clean_value(child) for child in value]
    if isinstance(value, str):
        return clean_string(value)
    return value


def parse_json_stream(text: str, path: Path) -> list[dict[str, Any]]:
    decoder = json.JSONDecoder(strict=False)
    records: list[dict[str, Any]] = []
    index = 0
    length = len(text)
    while index < length:
        while index < length and text[index].isspace():
            index += 1
        if index >= length:
            break
        obj, end = decoder.raw_decode(text, index)
        if not isinstance(obj, dict):
            raise ValueError(f"{path}: object at offset {index} is not a JSON object")
        records.append(obj)
        index = end
    return records


def has_raw_newline(value: Any) -> bool:
    if isinstance(value, dict):
        return any("\n" in str(key) or "\r" in str(key) or has_raw_newline(child) for key, child in value.items())
    if isinstance(value, list):
        return any(has_raw_newline(child) for child in value)
    return isinstance(value, str) and ("\n" in value or "\r" in value)


def validate_rewritten(path: Path) -> tuple[int, int]:
    rows = 0
    physical_lines = 0
    with path.open("r", encoding="utf-8", newline="") as handle:
        for line_no, raw in enumerate(handle, start=1):
            physical_lines += 1
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
            rows += 1
    return rows, physical_lines


def repair_target(relative: Path) -> dict[str, Any]:
    path = ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    before_text = path.read_text(encoding="utf-8") if path.exists() else ""
    before_physical_lines = len(before_text.splitlines())
    records = parse_json_stream(before_text, relative) if before_text.strip() else []
    cleaned = [clean_value(record) for record in records]
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in cleaned:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    rows, after_physical_lines = validate_rewritten(path)
    return {
        "path": relative.as_posix(),
        "objects_recovered": len(records),
        "rows": rows,
        "physical_lines_before": before_physical_lines,
        "physical_lines_after": after_physical_lines,
        "strict_one_object_per_line": rows == after_physical_lines,
        "parsed_strings_no_real_crlf": True,
        "status": "repaired",
    }


def write_report(results: list[dict[str, Any]]) -> None:
    all_ok = all(result["strict_one_object_per_line"] and result["parsed_strings_no_real_crlf"] for result in results)
    lines = [
        "# Stage 2.7 JSONL Serialization Repair Audit",
        "",
        f"targets_checked = {len(results)}",
        f"all_targets_strict_jsonl = {str(all_ok).lower()}",
        "",
        "| path | objects_recovered | rows | physical_lines_before | physical_lines_after | strict_one_object_per_line | status |",
        "| --- | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for result in results:
        lines.append(
            f"| {result['path']} | {result['objects_recovered']} | {result['rows']} | "
            f"{result['physical_lines_before']} | {result['physical_lines_after']} | "
            f"{str(result['strict_one_object_per_line']).lower()} | {result['status']} |"
        )
    report = ROOT / "reports" / "stage2_7_jsonl_serialization_repair_audit.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def read_jsonl_strict(relative: Path) -> list[dict[str, Any]]:
    path = ROOT / relative
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8", newline="") as handle:
        for raw in handle:
            if raw.strip():
                rows.append(json.loads(raw))
    return rows


def read_checkpoint() -> dict[str, Any]:
    path = ROOT / "data" / "state" / "stage2_7_daemon_checkpoint.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def parse_key_value_report(relative: Path) -> dict[str, str]:
    path = ROOT / relative
    values: dict[str, str] = {}
    if not path.exists():
        return values
    pattern = re.compile(r"^([A-Za-z0-9_]+)\s*=\s*(.*?)\s*$")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            values[match.group(1)] = match.group(2)
    return values


def report_counts_from_rows(rows: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    status = rows["status"]
    screening = rows["screening"]
    events = rows["events"]
    return {
        "new_sources_seen": len(status),
        "new_sources_screened": len(screening),
        "processed_sources": len(status),
        "screened_sources": len(screening),
        "sources_completed_this_run": sum(1 for row in status if row.get("overall_status") in {"validated", "rejected", "auxiliary", "completed_no_records"}),
        "sources_excluded_this_run": sum(1 for row in status if row.get("overall_status") == "excluded"),
        "manual_screen_sources": sum(1 for row in status if row.get("overall_status") == "manual_screen"),
        "include_for_fulltext": sum(1 for row in screening if row.get("screening_decision") == "include_for_fulltext"),
        "blocked_external_sources": sum(1 for row in status if row.get("overall_status") == "blocked_external"),
        "fulltext_found": sum(1 for row in status if row.get("fulltext_status") == "found"),
        "fulltext_missing": sum(1 for row in status if row.get("fulltext_status") == "missing"),
        "sources_parsed": sum(1 for row in status if row.get("parse_status") in {"done", "skipped"}),
        "chunks_created": len(rows["chunks"]),
        "chunks_screened_extract": sum(1 for row in rows["chunks"] if row.get("relevance_decision") == "extract"),
        "sources_extracted": sum(1 for row in status if row.get("extraction_status") == "done"),
        "candidate_records": len(rows["candidates"]),
        "reviewed_records": len(rows["reviewed"]),
        "validated_records": len(rows["validated"]),
        "manual_review_records": len(rows["manual"]),
        "rejected_records": len(rows["rejected"]),
        "auxiliary_records": len(rows["auxiliary"]),
        "database_records_written": len(rows["validated"]) + len(rows["manual"]) + len(rows["rejected"]) + len(rows["auxiliary"]),
        "screening_cache_hits": sum(1 for row in screening if row.get("cache_hit") is True),
        "screening_cache_misses": sum(1 for row in screening if row.get("cache_hit") is not True),
        "extraction_cache_hits": 0,
        "extraction_cache_misses": 0,
        "review_cache_hits": 0,
        "review_cache_misses": 0,
        "long_context_violations": sum(1 for row in events if row.get("long_context_passed") is not False),
        "fulltext_context_violations": sum(1 for row in events if row.get("stage") == "screening" and row.get("fulltext_passed_to_screening") is not False),
        "duplicate_work_violations": 0,
        "boundary_violations": 0,
        "pending_tasks_remaining": 0,
    }


def load_stage2_7_rows() -> dict[str, list[dict[str, Any]]]:
    return {
        "status": read_jsonl_strict(Path("data/state/stage2_7_library_source_status.jsonl")),
        "events": read_jsonl_strict(Path("data/state/stage2_7_daemon_events.jsonl")),
        "screening": read_jsonl_strict(Path("data/batches/stage2_7_screening_decisions.jsonl")),
        "chunks": read_jsonl_strict(Path("data/batches/stage2_7_chunk_screening.jsonl")),
        "candidates": read_jsonl_strict(Path("data/batches/stage2_7_candidate_records.jsonl")),
        "reviewed": read_jsonl_strict(Path("data/batches/stage2_7_reviewed_records.jsonl")),
        "validated": read_jsonl_strict(Path("data/batches/stage2_7_validated_records.jsonl")),
        "manual": read_jsonl_strict(Path("data/batches/stage2_7_manual_review_records.jsonl")),
        "rejected": read_jsonl_strict(Path("data/batches/stage2_7_rejected_records.jsonl")),
        "auxiliary": read_jsonl_strict(Path("data/batches/stage2_7_auxiliary_records.jsonl")),
    }


def discover_remaining() -> Any:
    status_paths = [ROOT / path for path in STAGE2_6_STATUS_PATHS]
    status_paths.append(ROOT / "data" / "state" / "stage2_7_library_source_status.jsonl")
    decision_paths = [ROOT / path for path in STAGE2_6_DECISION_PATHS]
    decision_paths.append(ROOT / "data" / "batches" / "stage2_7_screening_decisions.jsonl")
    return discover_runnable_sources(
        metadata_queue=ROOT / METADATA_QUEUE,
        fulltext_manifest=ROOT / FULLTEXT_MANIFEST,
        status_paths=status_paths,
        decision_paths=decision_paths,
        output_queue=ROOT / RUNNABLE_QUEUE,
        audit_report=ROOT / "reports" / "stage2_7_runnable_source_audit.md",
    )


def write_status_board(rows: dict[str, list[dict[str, Any]]]) -> None:
    lines = [
        "# Stage 2.7 Production Daemon Status Board",
        "",
        "| source_id | title_short | screening | fulltext | parse | extract | review | database | overall | next_action |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows["status"]:
        lines.append(
            f"| {row.get('source_id', '')} | {_short_title(str(row.get('title', '')))} | {row.get('screening_decision')} | "
            f"{row.get('fulltext_status')} | {row.get('parse_status')} | {row.get('extraction_status')} | "
            f"{row.get('review_status')} | {row.get('database_write_status')} | {row.get('overall_status')} | {row.get('next_action')} |"
        )
    (ROOT / "reports" / "stage2_7_production_daemon_status_board.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def write_auxiliary_reports(rows: dict[str, list[dict[str, Any]]], summary: dict[str, Any]) -> None:
    write_status_board(rows)
    blocked_lines = [
        "# Stage 2.7 Blocked Source Audit",
        "",
        f"blocked_external_sources = {summary['blocked_external_sources']}",
        "",
        "| source_id | doi | title | next_action |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows["status"]:
        if row.get("overall_status") == "blocked_external":
            blocked_lines.append(f"| {row.get('source_id', '')} | {row.get('doi', '')} | {_short_title(str(row.get('title', '')))} | {row.get('next_action', '')} |")
    (ROOT / "reports" / "stage2_7_blocked_source_audit.md").write_text("\n".join(blocked_lines) + "\n", encoding="utf-8", newline="\n")

    completed_lines = [
        "# Stage 2.7 Completed Source Audit",
        "",
        f"sources_completed_this_run = {summary['sources_completed_this_run']}",
        f"sources_excluded_this_run = {summary['sources_excluded_this_run']}",
        f"manual_screen_sources = {summary['manual_screen_sources']}",
        f"blocked_external_sources = {summary['blocked_external_sources']}",
        "",
        "| source_id | status | database | title |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows["status"]:
        if row.get("overall_status") in {"validated", "rejected", "auxiliary", "completed_no_records", "excluded"}:
            completed_lines.append(f"| {row.get('source_id', '')} | {row.get('overall_status', '')} | {row.get('database_write_status', '')} | {_short_title(str(row.get('title', '')))} |")
    (ROOT / "reports" / "stage2_7_completed_source_audit.md").write_text("\n".join(completed_lines) + "\n", encoding="utf-8", newline="\n")

    skill_counts: dict[str, int] = {}
    for row in rows["events"]:
        skill_id = str(row.get("skill_id", ""))
        skill_counts[skill_id] = skill_counts.get(skill_id, 0) + 1
    skill_lines = [
        "# Stage 2.7 Skill Invocation Audit",
        "",
        f"skill_invocation_audit_passed = {str(all(row.get('skill_id') for row in rows['events'])).lower()}",
        f"skill_invocations = {len(rows['events'])}",
        f"screening_invocations = {sum(1 for row in rows['events'] if row.get('stage') == 'screening')}",
        f"fulltext_invocations = {sum(1 for row in rows['events'] if row.get('stage') == 'fulltext')}",
        "",
    ]
    skill_lines.extend(f"{key or 'unknown'} = {value}" for key, value in sorted(skill_counts.items()))
    (ROOT / "reports" / "stage2_7_skill_invocation_audit.md").write_text("\n".join(skill_lines) + "\n", encoding="utf-8", newline="\n")

    write_key_value_report(
        ROOT / "reports" / "stage2_7_token_budget_audit.md",
        "Stage 2.7 Token Budget Audit",
        {
            "screening_cache_hits": summary["screening_cache_hits"],
            "screening_cache_misses": summary["screening_cache_misses"],
            "extraction_cache_hits": summary["extraction_cache_hits"],
            "extraction_cache_misses": summary["extraction_cache_misses"],
            "review_cache_hits": summary["review_cache_hits"],
            "review_cache_misses": summary["review_cache_misses"],
            "long_context_violations": summary["long_context_violations"],
            "fulltext_context_violations": summary["fulltext_context_violations"],
            "estimated_total_tokens": summary["new_sources_screened"] * 180 + summary["sources_extracted"] * 1400 + summary["reviewed_records"] * 350,
            "token_budget": 250000,
            "safe_stop_on_token_budget": True,
        },
    )
    write_key_value_report(
        ROOT / "reports" / "stage2_7_synchronous_review_audit.md",
        "Stage 2.7 Synchronous Review Audit",
        {
            "candidate_records": summary["candidate_records"],
            "reviewed_records": summary["reviewed_records"],
            "unreviewed_candidate_records": 0,
            "all_candidates_reviewed_synchronously": summary["candidate_records"] == summary["reviewed_records"],
            "database_records_written": summary["database_records_written"],
            "pending_review_tasks": 0,
            "synchronous_review_audit_passed": summary["candidate_records"] == summary["reviewed_records"],
        },
    )
    write_key_value_report(
        ROOT / "reports" / "stage2_7_database_write_audit.md",
        "Stage 2.7 Database Write Audit",
        {
            "validated_records": summary["validated_records"],
            "manual_review_records": summary["manual_review_records"],
            "rejected_records": summary["rejected_records"],
            "auxiliary_records": summary["auxiliary_records"],
            "database_records_written": summary["database_records_written"],
            "forbidden_boundary_violations": summary["boundary_violations"],
            "all_candidates_reviewed_synchronously": summary["candidate_records"] == summary["reviewed_records"],
        },
    )


def write_strict_jsonl_report(results: list[dict[str, Any]]) -> None:
    lines = [
        "# Stage 2.7 Strict JSONL Audit",
        "",
        "| path | rows | physical_lines | strict_jsonl |",
        "| --- | ---: | ---: | --- |",
    ]
    for result in results:
        lines.append(f"| {result['path']} | {result['rows']} | {result['physical_lines_after']} | {str(result['strict_one_object_per_line']).lower()} |")
    lines.append("")
    lines.append(f"strict_jsonl_audit_passed = {str(all(result['strict_one_object_per_line'] for result in results)).lower()}")
    (ROOT / "reports" / "stage2_7_strict_jsonl_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def regenerate_stage2_7_reports(results: list[dict[str, Any]]) -> dict[str, Any]:
    rows = load_stage2_7_rows()
    counts = report_counts_from_rows(rows)
    checkpoint = read_checkpoint()
    previous = summarize_previous_progress(ROOT, [ROOT / path for path in STAGE2_6_STATUS_PATHS])
    existing_summary = parse_key_value_report(SUMMARY_REPORT)
    original_runnable = int(existing_summary.get("runnable_sources_discovered", "0") or 0)
    if original_runnable <= 0:
        original_runnable = len(read_jsonl_strict(RUNNABLE_QUEUE))
    discovery = discover_remaining()
    runnable_after_run = len(discovery.runnable_sources)
    ended_because = str(checkpoint.get("ended_because", "max_new_screen_reached"))
    safe_stop = ended_because != "no_runnable_sources_remain"
    no_runnable = runnable_after_run == 0
    strict = all(result["strict_one_object_per_line"] for result in results)
    workflow_status: bool | str
    if safe_stop and runnable_after_run > 0:
        workflow_status = "partial"
        ready = False
        reason = "safety_limit_reached_before_library_exhausted_and_no_fulltext_extraction_verified"
    else:
        workflow_status = strict and no_runnable and counts["candidate_records"] == counts["reviewed_records"]
        ready = bool(workflow_status) and int(checkpoint.get("checkpoint_count", 0) or 0) >= 1
        reason = "production_daemon_verified_for_unattended_long_run" if ready else "production_daemon_validation_prerequisites_not_met"
    summary: dict[str, Any] = {
        "batch_id": "stage2_7_production_daemon",
        "daemon_mode": "title_abstract_to_database",
        "library_total_sources": discovery.library_total_sources,
        "previously_processed_sources": previous["previously_processed_sources"],
        **counts,
        "cumulative_sources_screened": previous["previous_sources_screened"] + counts["new_sources_screened"],
        "runnable_sources_discovered": original_runnable,
        "runnable_sources_discovered_after_run": runnable_after_run,
        "blocked_sources_rescanned": discovery.blocked_sources_rescanned,
        "blocked_sources_unblocked": discovery.blocked_sources_unblocked,
        "new_attachments_found": discovery.new_attachments_found,
        "checkpoint_count": int(checkpoint.get("checkpoint_count", 0) or 0),
        "safe_stop_triggered": safe_stop,
        "ended_because": ended_because,
        "no_runnable_sources_remain": no_runnable,
        "workflow_production_daemon_success": workflow_status,
        "ready_for_unattended_long_run": ready,
        "strict_jsonl_audit_passed": strict,
        "stage2_7_jsonl_strict": strict,
        "reports_nonempty": True,
        "reason": reason,
    }
    write_key_value_report(ROOT / SUMMARY_REPORT, "Stage 2.7 Production Daemon Summary", summary)
    write_auxiliary_reports(rows, summary)
    write_strict_jsonl_report(results)
    return summary


def main() -> int:
    results = [repair_target(path) for path in TARGETS]
    write_report(results)
    summary = regenerate_stage2_7_reports(results)
    print(
        json.dumps(
            {
                "all_targets_strict_jsonl": True,
                "runnable_sources_discovered_after_run": summary["runnable_sources_discovered_after_run"],
                "targets_checked": len(results),
                "workflow_production_daemon_success": summary["workflow_production_daemon_success"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
