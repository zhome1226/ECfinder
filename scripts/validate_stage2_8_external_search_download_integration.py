"""Validate Stage 2.8 external search/download integration."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ecfinder.skills.skill_registry import SkillRegistry


ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "data" / "batches"
STATE = ROOT / "data" / "state"
REPORTS = ROOT / "reports"

STAGE2_8_BATCH_FILES = {
    "screening": BATCH / "stage2_8_screening_decisions.jsonl",
    "chunks": BATCH / "stage2_8_chunk_screening.jsonl",
    "candidates": BATCH / "stage2_8_candidate_records.jsonl",
    "reviewed": BATCH / "stage2_8_reviewed_records.jsonl",
    "validated": BATCH / "stage2_8_validated_records.jsonl",
    "manual": BATCH / "stage2_8_manual_review_records.jsonl",
    "rejected": BATCH / "stage2_8_rejected_records.jsonl",
    "auxiliary": BATCH / "stage2_8_auxiliary_records.jsonl",
}
STAGE2_8_STATE_FILES = {
    "status": STATE / "stage2_8_source_status.jsonl",
    "events": STATE / "stage2_8_events.jsonl",
    "external_fulltext": STATE / "stage2_8_external_fulltext_resolution.jsonl",
    "inventory": STATE / "stage2_8_existing_agent_skill_inventory.jsonl",
}
STAGE2_8_DISCOVERY_FILES = {
    "external_candidates": BATCH / "stage2_8_external_metadata_candidates.jsonl",
    "external_deduped": BATCH / "stage2_8_external_metadata_deduped.jsonl",
    "new_sources": BATCH / "stage2_8_external_metadata_new_sources.jsonl",
}
REQUIRED_REPORTS = [
    "stage2_8_existing_agent_skill_inventory.md",
    "stage2_8_external_metadata_discovery_summary.md",
    "stage2_8_external_fulltext_resolution_summary.md",
    "stage2_8_external_daemon_summary.md",
    "stage2_8_skill_integration_audit.md",
    "stage2_8_external_dedup_audit.md",
    "stage2_8_search_download_skill_audit.md",
    "stage2_8_strict_jsonl_audit.md",
]
STAGE2_7_NONEMPTY_REPORTS = [
    "stage2_7_production_daemon_summary.md",
    "stage2_7_token_budget_audit.md",
    "stage2_7_database_write_audit.md",
    "stage2_7_synchronous_review_audit.md",
    "stage2_7_strict_jsonl_audit.md",
    "stage2_7_blocked_source_audit.md",
]
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
    text = require(path).read_text(encoding="utf-8")
    if len(text.strip()) == 0:
        raise ValueError(f"empty report: {path}")
    values: dict[str, str] = {}
    pattern = re.compile(r"^([A-Za-z0-9_]+)\s*=\s*(.*?)\s*$")
    for line in text.splitlines():
        match = pattern.match(line)
        if match:
            values[match.group(1)] = match.group(2)
    return values


def as_int(values: dict[str, str], key: str) -> int:
    return int(values.get(key, "0") or 0)


def as_bool(values: dict[str, str], key: str) -> bool:
    return values.get(key, "false").strip().lower() == "true"


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
                raise ValueError(f"{path}:{line_no} contains multiple JSON objects")
            if raw.count("\n") != 1 or "\r" in raw:
                raise ValueError(f"{path}:{line_no} has non-normalized physical line ending")
            obj = json.loads(raw.rstrip("\n"))
            if not isinstance(obj, dict):
                raise ValueError(f"{path}:{line_no} is not a JSON object")
            if has_raw_newline(obj):
                raise ValueError(f"{path}:{line_no} contains raw CR/LF inside parsed string")
            rows.append(obj)
    return rows


def normalize_doi(value: Any) -> str:
    doi = str(value or "").strip().lower()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
    return doi


def normalize_title(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def dedup_key(row: dict[str, Any]) -> str:
    doi = normalize_doi(row.get("doi"))
    if doi:
        return f"doi:{doi}"
    title = normalize_title(row.get("title"))
    return f"title:{title}" if title else ""


def validate_reports_nonempty() -> None:
    for name in REQUIRED_REPORTS + STAGE2_7_NONEMPTY_REPORTS:
        path = require(REPORTS / name)
        text = path.read_text(encoding="utf-8")
        meaningful = [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
        if len(text.strip()) < 40 or not meaningful:
            raise ValueError(f"report has no effective audit content: {path}")


def validate_inventory() -> dict[str, int]:
    rows = strict_jsonl(STAGE2_8_STATE_FILES["inventory"])
    by_path = {str(row.get("path", "")): row for row in rows}
    for required in ["agents/SearchAgent.md", "agents/DownloadAgent.md"]:
        if required not in by_path:
            raise ValueError(f"legacy agent was not inventoried: {required}")
        if by_path[required].get("migration_action") != "merge_with_existing":
            raise ValueError(f"legacy agent was not merged with active skills: {required}")
    return {
        "existing_agents_found": sum(1 for row in rows if row.get("item_type") == "agent_md"),
        "existing_skills_found": sum(1 for row in rows if row.get("item_type") == "skill"),
        "agents_converted_or_merged": sum(1 for row in rows if row.get("migration_action") == "merge_with_existing"),
    }


def validate_registry() -> dict[str, bool]:
    registry = SkillRegistry(ROOT)
    status = registry.validate()
    if status["skills_missing_contracts"] != 0:
        raise ValueError(f"skill registry has missing contracts: {status['missing_contracts']}")
    external_search = registry.by_agent("ExternalSearchAgent")
    external_download = registry.by_agent("ExternalDownloadAgent")
    if not external_search or external_search.skill_id != "external_metadata_discovery_v1":
        raise ValueError("external_metadata_discovery_v1 is not registered as ExternalSearchAgent")
    if not external_download or external_download.skill_id != "external_fulltext_resolution_v1":
        raise ValueError("external_fulltext_resolution_v1 is not registered as ExternalDownloadAgent")
    for skill in [external_search, external_download]:
        if skill.status != "active":
            raise ValueError(f"external skill is not active: {skill.skill_id}")
    return {"external_search_skill_registered": True, "external_download_skill_registered": True}


def validate_strict_jsonl_sets() -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = {}
    for name, path in {**STAGE2_8_BATCH_FILES, **STAGE2_8_STATE_FILES, **STAGE2_8_DISCOVERY_FILES}.items():
        rows[name] = strict_jsonl(path)
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
    return rows


def validate_external_dedup(rows: dict[str, list[dict[str, Any]]]) -> None:
    zotero_keys = {dedup_key(row) for row in strict_jsonl(BATCH / "stage2_6b_zotero_metadata_screening_queue.jsonl") if dedup_key(row)}
    new_keys: set[str] = set()
    for row in rows["new_sources"]:
        key = dedup_key(row)
        if not key:
            raise ValueError(f"external new source missing dedup key: {row.get('external_source_id')}")
        if key in zotero_keys:
            raise ValueError(f"external new source duplicates Zotero: {key}")
        if key in new_keys:
            raise ValueError(f"duplicate external new source: {key}")
        new_keys.add(key)


def validate_stage2_7_fixed() -> tuple[bool, bool]:
    summary = parse_report(REPORTS / "stage2_7_production_daemon_summary.md")
    ready = as_bool(summary, "ready_for_unattended_long_run")
    no_runnable = as_bool(summary, "no_runnable_sources_remain")
    runnable_after = as_int(summary, "runnable_sources_discovered_after_run")
    ended = summary.get("ended_because", "")
    logic_fixed = True
    if ended == "max_new_screen_reached" and (ready or no_runnable):
        logic_fixed = False
    if runnable_after > 0 and (ready or no_runnable):
        logic_fixed = False
    reports_fixed = all((REPORTS / name).exists() and len((REPORTS / name).read_text(encoding="utf-8").strip()) > 40 for name in STAGE2_7_NONEMPTY_REPORTS)
    if not logic_fixed:
        raise ValueError("Stage 2.7 readiness logic is still incorrect")
    if not reports_fixed:
        raise ValueError("Stage 2.7 required audit reports are still empty")
    return logic_fixed, reports_fixed


def validate_context_and_workflow(rows: dict[str, list[dict[str, Any]]], summary: dict[str, str]) -> None:
    forbidden_screening_keys = {"pdf_path", "local_path", "full_text", "fulltext", "chunks", "chunks_ref", "text", "chunk_text"}
    status_by_source = {str(row.get("source_id", "")): row for row in rows["status"]}
    if len(status_by_source) != len(rows["status"]):
        raise ValueError("duplicate source_id in Stage 2.8 source status")
    for row in rows["screening"]:
        if forbidden_screening_keys & set(row):
            raise ValueError(f"screening row contains fulltext context: {row.get('source_id')}")
        if row.get("input_fields") != ["source_id", "doi", "title", "abstract", "year", "journal", "keywords"]:
            raise ValueError(f"screening input fields changed: {row.get('source_id')}")
    include_sources = {str(row.get("source_id", "")) for row in rows["screening"] if row.get("screening_decision") == "include_for_fulltext"}
    for event in rows["events"]:
        if event.get("long_context_passed") is not False:
            raise ValueError(f"long context violation: {event.get('event_id')}")
        if event.get("stage") == "screening" and event.get("fulltext_passed_to_screening") is not False:
            raise ValueError(f"fulltext passed to screening: {event.get('event_id')}")
        if event.get("agent") == "ExternalDownloadAgent" and str(event.get("source_id", "")) not in include_sources:
            raise ValueError(f"external fulltext checked before include decision: {event.get('source_id')}")
    for row in rows["external_fulltext"]:
        if row.get("paywall_bypass_used") is not False:
            raise ValueError(f"external fulltext resolution used paywall bypass: {row.get('source_id')}")
        if row.get("raw_fulltext_committed") is not False:
            raise ValueError(f"external fulltext resolution committed raw fulltext: {row.get('source_id')}")
    candidate_ids = {str(row.get("record_id", "")) for row in rows["candidates"]}
    reviewed_ids = {str(row.get("record_id", "")) for row in rows["reviewed"]}
    if candidate_ids - reviewed_ids:
        raise ValueError(f"unreviewed candidates: {sorted(candidate_ids - reviewed_ids)[:5]}")
    terminal_ids = {str(row.get("record_id", "")) for row in [*rows["validated"], *rows["manual"], *rows["auxiliary"], *rows["rejected"]]}
    for row in rows["reviewed"]:
        if str(row.get("record_id", "")) not in terminal_ids:
            raise ValueError(f"reviewed record missing terminal database write: {row.get('record_id')}")
        if not row.get("database_write_ref"):
            raise ValueError(f"reviewed record missing database_write_ref: {row.get('record_id')}")
    for row in rows["validated"]:
        text = json.dumps(row, ensure_ascii=False).lower()
        hits = [term for term in FORBIDDEN_VALIDATED if term in text]
        if hits:
            raise ValueError(f"forbidden natural boundary in validated record {row.get('record_id')}: {hits}")
    if as_int(summary, "long_context_violations") != 0 or as_int(summary, "fulltext_context_violations") != 0:
        raise ValueError("summary context violations must be zero")
    if as_int(summary, "duplicate_work_violations") != 0:
        raise ValueError("summary duplicate work violations must be zero")
    if as_int(summary, "boundary_violations") != 0:
        raise ValueError("summary boundary violations must be zero")


def validate_report_counts(rows: dict[str, list[dict[str, Any]]], summary: dict[str, str]) -> None:
    discovery = parse_report(REPORTS / "stage2_8_external_metadata_discovery_summary.md")
    expected = {
        "external_candidates_found": as_int(discovery, "total_external_candidates"),
        "duplicates_against_zotero": as_int(discovery, "duplicates_against_zotero"),
        "new_unique_external_sources": len(rows["new_sources"]),
        "external_sources_screened": sum(1 for row in rows["screening"] if row.get("source_origin") == "external_search"),
        "include_for_fulltext": sum(1 for row in rows["screening"] if row.get("screening_decision") == "include_for_fulltext"),
        "manual_screen": sum(1 for row in rows["screening"] if row.get("screening_decision") == "manual_screen"),
        "exclude": sum(1 for row in rows["screening"] if row.get("screening_decision") == "exclude"),
        "fulltext_found": sum(1 for row in rows["status"] if row.get("fulltext_status") == "found"),
        "fulltext_missing": sum(1 for row in rows["status"] if row.get("fulltext_status") == "missing"),
        "sources_parsed": sum(1 for row in rows["status"] if row.get("parse_status") in {"done", "skipped"}),
        "sources_extracted": sum(1 for row in rows["status"] if row.get("extraction_status") == "done"),
        "candidate_records": len(rows["candidates"]),
        "reviewed_records": len(rows["reviewed"]),
        "validated_records": len(rows["validated"]),
        "rejected_records": len(rows["rejected"]),
        "auxiliary_records": len(rows["auxiliary"]),
        "database_records_written": len(rows["validated"]) + len(rows["manual"]) + len(rows["rejected"]) + len(rows["auxiliary"]),
        "pending_tasks_remaining": 0,
    }
    for key, value in expected.items():
        if as_int(summary, key) != value:
            raise ValueError(f"Stage 2.8 summary mismatch for {key}: expected {value}, got {summary.get(key)}")
    success = summary.get("stage2_8_external_search_download_integration_success", "").lower()
    if success not in {"true", "partial"}:
        raise ValueError("Stage 2.8 integration success must be true or partial")
    ready = as_bool(summary, "ready_for_expanded_external_literature_run")
    if as_int(summary, "new_unique_external_sources") > 0 and as_int(summary, "external_sources_screened") > 0:
        if not ready:
            raise ValueError("ready_for_expanded_external_literature_run should be true after external discovery and screening pass")
    if success == "partial" and summary.get("reason") != "external_adapter_unavailable_but_skill_integration_and_daemon_contract_ready":
        raise ValueError("partial Stage 2.8 success has the wrong reason")


def validate_no_raw_fulltext_tracked() -> None:
    result = subprocess.run(["git", "ls-files"], cwd=ROOT, text=True, capture_output=True, check=False)
    bad = [
        line
        for line in result.stdout.splitlines()
        if Path(line).suffix.lower() in {".pdf", ".html", ".htm", ".xhtml"}
    ]
    if bad:
        raise ValueError(f"raw PDF/HTML/SI-like fulltext is tracked by git: {bad[:10]}")


def main() -> int:
    validate_reports_nonempty()
    inventory_counts = validate_inventory()
    registry_flags = validate_registry()
    rows = validate_strict_jsonl_sets()
    validate_external_dedup(rows)
    stage2_7_logic, stage2_7_reports = validate_stage2_7_fixed()
    summary = parse_report(REPORTS / "stage2_8_external_daemon_summary.md")
    validate_context_and_workflow(rows, summary)
    validate_report_counts(rows, summary)
    validate_no_raw_fulltext_tracked()
    output = {
        **inventory_counts,
        **registry_flags,
        "external_query_families": as_int(summary, "external_query_families"),
        "external_candidates_found": as_int(summary, "external_candidates_found"),
        "duplicates_against_zotero": as_int(summary, "duplicates_against_zotero"),
        "new_unique_external_sources": as_int(summary, "new_unique_external_sources"),
        "external_sources_screened": as_int(summary, "external_sources_screened"),
        "stage2_7_readiness_logic_fixed": stage2_7_logic,
        "stage2_7_empty_reports_fixed": stage2_7_reports,
        "stage2_8_external_search_download_integration_success": summary.get("stage2_8_external_search_download_integration_success", ""),
        "ready_for_expanded_external_literature_run": as_bool(summary, "ready_for_expanded_external_literature_run"),
        "reason": summary.get("reason", ""),
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
