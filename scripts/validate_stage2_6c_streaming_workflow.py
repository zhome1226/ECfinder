"""Validate Stage 2.6c streaming autonomous workflow outputs."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ecfinder.skills.skill_registry import SkillRegistry
from ecfinder.state.common import read_json, read_jsonl


ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "data" / "batches"
STATE = ROOT / "data" / "state"
REPORTS = ROOT / "reports"
SUMMARY = REPORTS / "stage2_6c_streaming_autonomous_summary.md"

FORBIDDEN_VALIDATED = {
    "activated sludge",
    "wastewater treatment",
    "wwtp",
    "advanced oxidation",
    "electrochemical",
    "plasma",
    "photocatalysis",
    "ozonation",
    "uv/persulfate",
    "hydrothermal",
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
    require(path)
    values: dict[str, str] = {}
    pattern = re.compile(r"^([A-Za-z0-9_]+)\s*=\s*(.*?)\s*$")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            values[match.group(1)] = match.group(2)
    return values


def as_int(values: dict[str, str], key: str) -> int:
    return int(values.get(key, "0"))


def as_bool(values: dict[str, str], key: str) -> bool:
    return values.get(key, "false") == "true"


def validate_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = read_jsonl(require(path))
    return rows


def validate_status_logic(status_rows: list[dict[str, Any]], screening_rows: list[dict[str, Any]]) -> None:
    status_by_source = {str(row.get("source_id", "")): row for row in status_rows}
    if len(status_by_source) != len(status_rows):
        raise ValueError("duplicate source_id in streaming source status")
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


def validate_synchronous_review(candidates: list[dict[str, Any]], reviewed: list[dict[str, Any]]) -> None:
    candidate_ids = {str(row.get("record_id", "")) for row in candidates}
    reviewed_ids = {str(row.get("record_id", "")) for row in reviewed}
    missing = candidate_ids - reviewed_ids
    if missing:
        raise ValueError(f"candidate records missing review: {sorted(missing)[:5]}")
    for row in reviewed:
        lineage = row.get("task_lineage", {})
        if lineage.get("synchronous") is not True:
            raise ValueError(f"reviewed record missing synchronous lineage: {row.get('record_id')}")
        if not row.get("database_write_ref"):
            raise ValueError(f"reviewed record missing database_write_ref: {row.get('record_id')}")


def validate_database_outputs(
    reviewed: list[dict[str, Any]],
    validated: list[dict[str, Any]],
    manual: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
    auxiliary: list[dict[str, Any]],
) -> None:
    terminal_ids = {str(row.get("record_id", "")) for row in [*validated, *manual, *auxiliary]}
    rejected_ids = {str(row.get("record_id", "")) for row in rejected}
    for row in reviewed:
        status = row.get("review", {}).get("review_status")
        record_id = str(row.get("record_id", ""))
        if status in {"validated", "manual_review", "auxiliary_engineered"} and record_id not in terminal_ids:
            raise ValueError(f"reviewed record not written to terminal output: {record_id}")
        if status == "rejected" and record_id not in rejected_ids:
            raise ValueError(f"rejected reviewed record missing rejected output: {record_id}")
    for row in validated:
        if row.get("review", {}).get("natural_environment_valid") is not True:
            raise ValueError(f"validated record lacks natural_environment_valid: {row.get('record_id')}")
        text = json.dumps(row, ensure_ascii=False).lower()
        hits = [term for term in FORBIDDEN_VALIDATED if term in text]
        if hits:
            raise ValueError(f"forbidden boundary in validated record {row.get('record_id')}: {hits}")


def validate_skill_invocations(events: list[dict[str, Any]]) -> None:
    registry_ids = {skill.skill_id for skill in SkillRegistry(ROOT).active()}
    if not events:
        raise ValueError("streaming event log is empty")
    for event in events:
        skill_id = str(event.get("skill_id", ""))
        if skill_id not in registry_ids:
            raise ValueError(f"event did not use registered skill: {event}")
        if event.get("long_context_passed") is not False:
            raise ValueError(f"long context violation in event: {event.get('event_id')}")
        if event.get("stage") == "screening" and event.get("fulltext_passed_to_screening") is not False:
            raise ValueError(f"screening received fulltext context: {event.get('event_id')}")


def validate_context_boundaries(screening_rows: list[dict[str, Any]], chunk_rows: list[dict[str, Any]], events: list[dict[str, Any]]) -> None:
    forbidden_screening_keys = {"pdf_path", "local_path", "full_text", "chunks", "chunks_ref", "text", "chunk_text"}
    for row in screening_rows:
        if forbidden_screening_keys & set(row):
            raise ValueError(f"screening decision contains forbidden fulltext keys: {row.get('source_id')}")
    extract_chunk_ids = {str(row.get("chunk_id", "")) for row in chunk_rows if row.get("relevance_decision") == "extract"}
    for event in events:
        if event.get("agent") == "ExtractionAgent":
            refs = event.get("input_refs", {})
            if "chunks_ref" not in refs:
                raise ValueError(f"extraction event missing chunks_ref: {event.get('event_id')}")
    if any(row.get("relevance_decision") == "skip" and row.get("chunk_id") in extract_chunk_ids for row in chunk_rows):
        raise ValueError("low relevance chunk also marked for extraction")


def validate_refs() -> None:
    for row in read_jsonl(STATE / "decision_cache.jsonl"):
        ref = str(row.get("decision_ref", ""))
        if ref and not (ROOT / ref).exists():
            raise ValueError(f"decision cache ref missing: {ref}")
    checkpoint = read_json(require(STATE / "stage2_6c_streaming_checkpoint.json"))
    if checkpoint.get("can_resume") is not True:
        raise ValueError("streaming checkpoint must allow resume")


def validate_no_raw_fulltext_tracked() -> None:
    result = subprocess.run(
        ["git", "ls-files", "data/local_fulltext"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    bad = [
        line
        for line in result.stdout.splitlines()
        if Path(line).suffix.lower() in {".pdf", ".html", ".htm", ".xhtml", ".sqlite"}
    ]
    if bad:
        raise ValueError(f"raw fulltext tracked by git: {bad[:5]}")


def validate_report_counts(summary: dict[str, str], rows: dict[str, list[dict[str, Any]]]) -> None:
    expected = {
        "sources_screened": len(rows["screening"]),
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
    if as_int(summary, "include_for_fulltext") != sum(1 for row in rows["screening"] if row.get("screening_decision") == "include_for_fulltext"):
        raise ValueError("include_for_fulltext summary mismatch")
    if not as_bool(summary, "workflow_streaming_success"):
        raise ValueError("workflow_streaming_success must be true")


def run_duplicate_validator() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_no_duplicate_work.py")],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(f"validate_no_duplicate_work.py failed: {result.stderr.strip() or result.stdout.strip()}")


def main() -> int:
    rows = {
        "status": validate_jsonl(STATE / "stage2_6c_streaming_source_status.jsonl"),
        "events": validate_jsonl(STATE / "stage2_6c_streaming_events.jsonl"),
        "screening": validate_jsonl(BATCH / "stage2_6c_streaming_screening_decisions.jsonl"),
        "chunks": validate_jsonl(BATCH / "stage2_6c_streaming_chunk_screening.jsonl"),
        "candidates": validate_jsonl(BATCH / "stage2_6c_streaming_candidate_records.jsonl"),
        "reviewed": validate_jsonl(BATCH / "stage2_6c_streaming_reviewed_records.jsonl"),
        "validated": validate_jsonl(BATCH / "stage2_6c_streaming_validated_records.jsonl"),
        "manual": validate_jsonl(BATCH / "stage2_6c_streaming_manual_review_records.jsonl"),
        "rejected": validate_jsonl(BATCH / "stage2_6c_streaming_rejected_records.jsonl"),
        "auxiliary": validate_jsonl(BATCH / "stage2_6c_streaming_auxiliary_records.jsonl"),
    }
    summary = parse_report(SUMMARY)
    validate_status_logic(rows["status"], rows["screening"])
    validate_synchronous_review(rows["candidates"], rows["reviewed"])
    validate_database_outputs(rows["reviewed"], rows["validated"], rows["manual"], rows["rejected"], rows["auxiliary"])
    validate_skill_invocations(rows["events"])
    validate_context_boundaries(rows["screening"], rows["chunks"], rows["events"])
    validate_refs()
    validate_no_raw_fulltext_tracked()
    validate_report_counts(summary, rows)
    run_duplicate_validator()
    output = {
        "workflow_streaming_success": True,
        "sources_screened": as_int(summary, "sources_screened"),
        "candidate_records": as_int(summary, "candidate_records"),
        "reviewed_records": as_int(summary, "reviewed_records"),
        "ready_for_next_streaming_batch": as_bool(summary, "ready_for_next_streaming_batch"),
        "ready_for_100_source_stream": as_bool(summary, "ready_for_100_source_stream"),
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
