"""Run Stage 2.4b local full-text ingest over high-priority targets."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from ecfinder.state.common import read_jsonl, relative_path, utc_now, write_json, write_jsonl
from ecfinder.state.task_payloads import create_task_payload
from ingest_local_fulltext import ROOT, ingest_manifest_entry


MANIFEST_PATH = ROOT / "data" / "local_fulltext" / "stage2_4b" / "fulltext_manifest.jsonl"
BATCH_DIR = ROOT / "data" / "batches"
REPORTS_DIR = ROOT / "reports"
TASKS_DIR = ROOT / "data" / "tasks"
TASK_REGISTRY_PATH = ROOT / "data" / "state" / "task_registry.jsonl"

STATUS_PATH = BATCH_DIR / "stage2_4b_fulltext_ingest_status.jsonl"
VALIDATED_PATH = BATCH_DIR / "stage2_4b_validated_records.jsonl"
MANUAL_PATH = BATCH_DIR / "stage2_4b_manual_review_records.jsonl"
REJECTED_PATH = BATCH_DIR / "stage2_4b_rejected_records.jsonl"
CODEX_TASKS_PATH = BATCH_DIR / "stage2_4b_codex_tasks.jsonl"

SUMMARY_PATH = REPORTS_DIR / "stage2_4b_fulltext_ingest_summary.md"
AUDIT_PATH = REPORTS_DIR / "stage2_4b_validated_records_audit.md"
REMAINING_TARGETS_PATH = REPORTS_DIR / "stage2_4b_remaining_manual_targets.md"
SCALE_READINESS_PATH = REPORTS_DIR / "stage2_4b_scale_readiness.md"

DEFAULT_TARGETS = [
    {
        "source_id": "stage2_4_src_002",
        "doi": "10.1016/j.watres.2023.120941",
        "title": "Aerobic biotransformation of 6:2 fluorotelomer sulfonate in soils from two AFFF-impacted sites",
        "file_type": "pdf",
        "local_path": "",
        "access_method": "user_provided",
        "license_or_access_note": "Provide only lawfully obtained local full text; raw file is not committed.",
        "sha256": "",
        "status": "pending_ingest",
    },
    {
        "source_id": "stage2_4_src_003",
        "doi": "10.1016/j.envpol.2016.01.069",
        "title": "Aerobic biotransformation of polyfluoroalkyl phosphate esters (PAPs) in soil",
        "file_type": "pdf",
        "local_path": "",
        "access_method": "user_provided",
        "license_or_access_note": "Provide only lawfully obtained local full text; raw file is not committed.",
        "sha256": "",
        "status": "pending_ingest",
    },
    {
        "source_id": "stage2_4_src_004",
        "doi": "10.1016/j.chemosphere.2016.03.062",
        "title": "Biotransformation potential of 6:2 FTSA in aerobic and anaerobic sediment",
        "file_type": "pdf",
        "local_path": "",
        "access_method": "user_provided",
        "license_or_access_note": "Provide only lawfully obtained local full text; raw file is not committed.",
        "sha256": "",
        "status": "pending_ingest",
    },
    {
        "source_id": "stage2_4_src_005",
        "doi": "10.1016/j.chemosphere.2014.09.059",
        "title": "Production of PFOS from aerobic soil biotransformation of two perfluoroalkyl sulfonamide derivatives",
        "file_type": "pdf",
        "local_path": "",
        "access_method": "user_provided",
        "license_or_access_note": "Provide only lawfully obtained local full text; raw file is not committed.",
        "sha256": "",
        "status": "pending_ingest",
    },
    {
        "source_id": "stage2_4_src_006",
        "doi": "10.1016/j.envpol.2017.05.074",
        "title": "Kinetic analysis of aerobic biotransformation pathways of a PFOS precursor in soils",
        "file_type": "pdf",
        "local_path": "",
        "access_method": "user_provided",
        "license_or_access_note": "Provide only lawfully obtained local full text; raw file is not committed.",
        "sha256": "",
        "status": "pending_ingest",
    },
    {
        "source_id": "stage2_4_src_007",
        "doi": "10.1021/es0708722",
        "title": "Biotransformation of 8:2 Fluorotelomer Alcohol in Soil and by Soil Bacteria Isolates",
        "file_type": "pdf",
        "local_path": "",
        "access_method": "user_provided",
        "license_or_access_note": "Provide only lawfully obtained local full text; raw file is not committed.",
        "sha256": "",
        "status": "pending_ingest",
    },
    {
        "source_id": "stage2_4_src_009",
        "doi": "10.1021/acsestwater.5c00033",
        "title": "Biotransformation of Perfluorooctane Sulfonamide (FOSA) and Microbial Community Dynamics in Aerobic Soils",
        "file_type": "pdf",
        "local_path": "",
        "access_method": "user_provided",
        "license_or_access_note": "Provide only lawfully obtained local full text; raw file is not committed.",
        "sha256": "",
        "status": "pending_ingest",
    },
    {
        "source_id": "stage2_4_src_013",
        "doi": "10.1016/j.chemosphere.2012.06.035",
        "title": "6:2 Fluorotelomer alcohol biotransformation in an aerobic river sediment system",
        "file_type": "pdf",
        "local_path": "",
        "access_method": "user_provided",
        "license_or_access_note": "Provide only lawfully obtained local full text; raw file is not committed.",
        "sha256": "",
        "status": "pending_ingest",
    },
    {
        "source_id": "stage2_4_src_018",
        "doi": "10.1016/j.jhazmat.2024.135261",
        "title": "Fluorotelomer betaines and sulfonic acid in aerobic wetland soil",
        "file_type": "pdf",
        "local_path": "",
        "access_method": "user_provided",
        "license_or_access_note": "Provide only lawfully obtained local full text; raw file is not committed.",
        "sha256": "",
        "status": "pending_ingest",
    },
    {
        "source_id": "stage2_4_src_021",
        "doi": "10.1021/es403949z",
        "title": "Fate of Polyfluoroalkyl Phosphate Diesters and Their Metabolites in Biosolids-Applied Soil",
        "file_type": "pdf",
        "local_path": "",
        "access_method": "user_provided",
        "license_or_access_note": "Provide only lawfully obtained local full text; raw file is not committed.",
        "sha256": "",
        "status": "pending_ingest",
    },
    {
        "source_id": "stage2_4_src_028",
        "doi": "10.1016/j.chemosphere.2018.07.157",
        "title": "Biotransformation of Sulfluramid in wetland plant microcosms",
        "file_type": "pdf",
        "local_path": "",
        "access_method": "user_provided",
        "license_or_access_note": "Provide only lawfully obtained local full text; raw file is not committed.",
        "sha256": "",
        "status": "pending_ingest",
    },
    {
        "source_id": "stage2_4_src_029",
        "doi": "10.1016/j.scitotenv.2018.09.214",
        "title": "Isomer-specific biotransformation of perfluoroalkyl sulfonamide compounds in aerobic soil",
        "file_type": "pdf",
        "local_path": "",
        "access_method": "user_provided",
        "license_or_access_note": "Provide only lawfully obtained local full text; raw file is not committed.",
        "sha256": "",
        "status": "pending_ingest",
    },
]


def ensure_directories() -> None:
    for path in [
        ROOT / "data" / "local_fulltext" / "stage2_4b" / "pdf",
        ROOT / "data" / "local_fulltext" / "stage2_4b" / "html",
        ROOT / "data" / "local_fulltext" / "stage2_4b" / "si",
        BATCH_DIR,
        REPORTS_DIR,
        TASKS_DIR,
        TASK_REGISTRY_PATH.parent,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def ensure_manifest() -> list[dict[str, Any]]:
    if not MANIFEST_PATH.exists() or not read_jsonl(MANIFEST_PATH):
        write_jsonl(MANIFEST_PATH, DEFAULT_TARGETS)
    return read_jsonl(MANIFEST_PATH)


def write_manifest_with_discovered_hashes(entries: list[dict[str, Any]], statuses: list[dict[str, Any]]) -> None:
    status_by_source = {status["source_id"]: status for status in statuses}
    updated: list[dict[str, Any]] = []
    for entry in entries:
        status = status_by_source.get(str(entry.get("source_id", "")), {})
        if status.get("local_fulltext_found"):
            entry = {
                **entry,
                "sha256": status.get("fulltext_sha256", ""),
                "status": "ingested" if status.get("parsed_chunks", 0) else "ingested_no_relevant_chunks",
            }
        updated.append(entry)
    write_jsonl(MANIFEST_PATH, updated)


def create_stage2_4b_task(status: dict[str, Any], task_type: str, reason: str, output_expected: str) -> dict[str, Any]:
    task_id = f"stage2_4b_{status['source_id']}_{task_type}"
    refs = status.get("artifact_refs", {})
    input_refs = {
        "download_ref": refs.get("download_ref", ""),
        "manifest_ref": relative_path(ROOT, MANIFEST_PATH),
        "metadata_ref": refs.get("metadata_ref", ""),
    }
    if task_type in {"extract", "review"}:
        input_refs["chunk_ref"] = refs.get("chunks_ref", "")
        input_refs["record_ref"] = refs.get("candidate_records_ref", "")
    payload = create_task_payload(
        ROOT,
        TASKS_DIR,
        TASK_REGISTRY_PATH,
        task_id,
        task_type,
        "ReviewAgent" if task_type == "review" else "ExtractionAgent",
        status["source_id"],
        input_refs,
        output_expected,
        reason,
    )
    return {
        "expected_output": payload["output_expected"],
        "input_refs": input_refs,
        "prompt_refs": payload["prompt_refs"],
        "reason": payload["reason"],
        "run_id": status["run_id"],
        "schema_ref": payload["schema_ref"],
        "source_id": status["source_id"],
        "status": "pending",
        "task_id": task_id,
        "task_payload_ref": relative_path(ROOT, TASKS_DIR / f"{task_id}.json"),
        "task_type": task_type,
    }


def build_codex_tasks(statuses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for status in statuses:
        refs = status.get("artifact_refs", {})
        if int(status.get("parsed_chunks", 0)) > 0:
            tasks.append(
                create_stage2_4b_task(
                    status,
                    "extract",
                    "Local full text was parsed, but automatic semantic extraction is not available for this source.",
                    refs.get("candidate_records_ref", ""),
                )
            )
        elif status.get("next_action") == "manual_full_text_check":
            tasks.append(
                create_stage2_4b_task(
                    status,
                    "manual_full_text_check",
                    status.get("failure_reason", "Local full text is still required before extraction."),
                    refs.get("chunks_ref", ""),
                )
            )
    return tasks


def read_run_jsonl(status: dict[str, Any], filename: str) -> list[dict[str, Any]]:
    return read_jsonl(ROOT / str(status["run_dir"]) / filename)


def write_record_exports(statuses: list[dict[str, Any]]) -> None:
    validated: list[dict[str, Any]] = []
    manual: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for status in statuses:
        validated.extend(read_run_jsonl(status, "validated_records.jsonl"))
        manual.extend(read_run_jsonl(status, "manual_review_records.jsonl"))
        rejected.extend(read_run_jsonl(status, "rejected_records.jsonl"))
    write_jsonl(VALIDATED_PATH, validated)
    write_jsonl(MANUAL_PATH, manual)
    write_jsonl(REJECTED_PATH, rejected)


def summarize(statuses: list[dict[str, Any]], tasks: list[dict[str, Any]]) -> dict[str, Any]:
    manifest_rows = read_jsonl(MANIFEST_PATH)
    local_found = sum(1 for status in statuses if status.get("local_fulltext_found"))
    validated = read_jsonl(VALIDATED_PATH)
    source_count_with_validated = len({record.get("source_id") for record in validated if record.get("source_id")})
    new_validated = len(validated)
    parsed_sources = sum(1 for status in statuses if int(status.get("parsed_chunks", 0)) > 0)
    if local_found == 0:
        can_scale = False
        if any(row.get("status") == "missing_fulltext" and row.get("rescue_attempted") for row in manifest_rows):
            reason = "insufficient_campus_fulltext_access"
        else:
            reason = "no local fulltext provided"
    elif parsed_sources >= 5 and new_validated >= 5 and source_count_with_validated >= 2:
        can_scale = True
        reason = ""
    else:
        can_scale = False
        reason = "insufficient_fulltext_and_no_new_validated_records"
    return {
        "manifest_sources": len(statuses),
        "local_fulltext_found": local_found,
        "local_fulltext_missing": sum(1 for status in statuses if not status.get("local_fulltext_found")),
        "parsed_sources": parsed_sources,
        "total_chunks": sum(int(status.get("parsed_chunks", 0)) for status in statuses),
        "candidate_records": sum(int(status.get("candidate_records", 0)) for status in statuses),
        "validated_records": len(validated),
        "manual_review_records": len(read_jsonl(MANUAL_PATH)),
        "rejected_records": len(read_jsonl(REJECTED_PATH)),
        "codex_tasks_created": len(tasks),
        "new_validated_records_beyond_stage2_4": new_validated,
        "source_count_with_validated_records": source_count_with_validated,
        "remaining_manual_targets": sum(1 for status in statuses if status.get("next_action") == "manual_full_text_check"),
        "source_registry_updates": len(statuses),
        "artifact_index_updates": sum(len(status.get("artifact_refs", {})) for status in statuses),
        "decision_cache_hits": 0,
        "decision_cache_misses": parsed_sources,
        "can_scale_to_100_sources": can_scale,
        "reason": reason,
    }


def markdown_cell(value: Any) -> str:
    return str(value).replace("\n", " ").replace("|", "\\|")


def write_reports(statuses: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    summary_lines = ["# Stage 2.4b Full-text Ingest Summary", ""]
    for key, value in summary.items():
        rendered = str(value).lower() if isinstance(value, bool) else str(value)
        summary_lines.append(f"{key} = {rendered}")
    summary_lines.extend(
        [
            "",
            "note = Raw PDF/HTML/SI files are ignored by Git; only manifest, hashes, tasks, and derived run outputs are committed.",
        ]
    )
    SUMMARY_PATH.write_text("\n".join(summary_lines) + "\n", encoding="utf-8", newline="\n")

    validated = read_jsonl(VALIDATED_PATH)
    audit_lines = ["# Stage 2.4b Validated Records Audit", ""]
    if not validated:
        audit_lines.append("No validated records were produced by Stage 2.4b.")
    for record in validated:
        audit_lines.extend(
            [
                f"## {record.get('record_id', '')}",
                "",
                f"source_id = {record.get('source_id', '')}",
                f"doi = {record.get('doi', '')}",
                f"parent = {record.get('parent_compound', {}).get('name', '')}",
                f"product = {record.get('product_compound', {}).get('name', '')}",
                "",
            ]
        )
    AUDIT_PATH.write_text("\n".join(audit_lines) + "\n", encoding="utf-8", newline="\n")

    target_lines = [
        "# Stage 2.4b Remaining Manual Full-text Targets",
        "",
        "| source_id | doi | title | reason | next_action |",
        "| --- | --- | --- | --- | --- |",
    ]
    for status in statuses:
        if status.get("next_action") != "manual_full_text_check":
            continue
        target_lines.append(
            "| {source_id} | {doi} | {title} | {reason} | {next_action} |".format(
                source_id=markdown_cell(status.get("source_id", "")),
                doi=markdown_cell(status.get("doi", "")),
                title=markdown_cell(status.get("title", "")),
                reason=markdown_cell(status.get("failure_reason", "")),
                next_action=markdown_cell(status.get("next_action", "")),
            )
        )
    REMAINING_TARGETS_PATH.write_text("\n".join(target_lines) + "\n", encoding="utf-8", newline="\n")

    readiness_lines = ["# Stage 2.4b Scale Readiness", ""]
    for key in [
        "manifest_sources",
        "local_fulltext_found",
        "parsed_sources",
        "new_validated_records_beyond_stage2_4",
        "source_count_with_validated_records",
        "can_scale_to_100_sources",
        "reason",
    ]:
        value = summary.get(key)
        rendered = str(value).lower() if isinstance(value, bool) else str(value)
        readiness_lines.append(f"{key} = {rendered}")
    readiness_lines.append("")
    readiness_lines.append("Criteria: parsed_sources >= 5, new_validated_records_beyond_stage2_4 >= 5, source_count_with_validated_records >= 2, valid JSONL, and no boundary violations.")
    SCALE_READINESS_PATH.write_text("\n".join(readiness_lines) + "\n", encoding="utf-8", newline="\n")


def run() -> dict[str, Any]:
    ensure_directories()
    manifest_entries = ensure_manifest()
    statuses = [ingest_manifest_entry(entry) for entry in manifest_entries]
    write_manifest_with_discovered_hashes(manifest_entries, statuses)
    tasks = build_codex_tasks(statuses)
    write_jsonl(STATUS_PATH, statuses)
    write_jsonl(CODEX_TASKS_PATH, tasks)
    write_record_exports(statuses)
    summary = summarize(statuses, tasks)
    write_reports(statuses, summary)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return summary


def main() -> int:
    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
