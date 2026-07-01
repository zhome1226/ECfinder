"""Ingest available Zotero full text first for Stage 2.4j."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from ecfinder.state.artifact_index import index_artifact
from ecfinder.state.common import (
    doi_hash,
    normalized_title_hash,
    read_jsonl,
    relative_path,
    sha256_file,
    sha256_text,
    utc_now,
    write_json,
    write_jsonl,
)
from ecfinder.state.source_registry import upsert_source
from ecfinder.state.task_payloads import create_task_payload
from ingest_local_fulltext import parse_local_file
from stage2_4j_common import AVAILABLE_MANIFEST, BATCH_DIR, REPORTS_DIR, ROOT, TARGETS_12, write_summary


RUNS_DIR = ROOT / "data" / "runs"
STATE_DIR = ROOT / "data" / "state"
TASKS_DIR = ROOT / "data" / "tasks"
ARTIFACT_INDEX_PATH = STATE_DIR / "artifact_index.jsonl"
SOURCE_REGISTRY_PATH = STATE_DIR / "source_registry.jsonl"
TASK_REGISTRY_PATH = STATE_DIR / "task_registry.jsonl"

STATUS_PATH = BATCH_DIR / "stage2_4j_available_fulltext_ingest_status.jsonl"
VALIDATED_PATH = BATCH_DIR / "stage2_4j_validated_records.jsonl"
MANUAL_PATH = BATCH_DIR / "stage2_4j_manual_review_records.jsonl"
REJECTED_PATH = BATCH_DIR / "stage2_4j_rejected_records.jsonl"
CODEX_TASKS_PATH = BATCH_DIR / "stage2_4j_codex_tasks.jsonl"

SUMMARY_PATH = REPORTS_DIR / "stage2_4j_available_fulltext_ingest_summary.md"
AUDIT_PATH = REPORTS_DIR / "stage2_4j_validated_records_audit.md"
MANUAL_TARGETS_PATH = REPORTS_DIR / "stage2_4j_manual_review_targets.md"
SCALE_PATH = REPORTS_DIR / "stage2_4j_scale_readiness.md"

RUN_JSONL_OUTPUTS = [
    "chunks.jsonl",
    "candidate_records.jsonl",
    "reviewed_records.jsonl",
    "validated_records.jsonl",
    "manual_review_records.jsonl",
    "rejected_records.jsonl",
]
ARTIFACT_FILES = {
    "metadata": "source_metadata.json",
    "screening": "screening.json",
    "download": "download_status.json",
    "chunks": "chunks.jsonl",
    "candidate_records": "candidate_records.jsonl",
    "reviewed_records": "reviewed_records.jsonl",
    "validated_records": "validated_records.jsonl",
    "manual_review": "manual_review_records.jsonl",
    "rejected_records": "rejected_records.jsonl",
}
SCHEMA_BY_ARTIFACT_TYPE = {
    "metadata": "schemas/source_metadata.schema.json",
    "screening": "schemas/screening_decision.schema.json",
    "download": "",
    "chunks": "schemas/chunk.schema.json",
    "candidate_records": "schemas/transformation_record.schema.json",
    "reviewed_records": "schemas/transformation_record.schema.json",
    "validated_records": "schemas/transformation_record.schema.json",
    "manual_review": "schemas/review_decision.schema.json",
    "rejected_records": "schemas/review_decision.schema.json",
}


def resolve_repo_path(path_text: str) -> Path:
    path = Path(path_text)
    if not path.is_absolute():
        path = ROOT / path
    return path


def purge_stage2_4j_state() -> None:
    """Remove stale Stage 2.4j refs from registries before regenerating outputs."""
    if SOURCE_REGISTRY_PATH.exists():
        source_records = [
            row
            for row in read_jsonl(SOURCE_REGISTRY_PATH)
            if not str(row.get("source_id", "")).startswith("zotero_stage2_4j_src_")
        ]
        write_jsonl(SOURCE_REGISTRY_PATH, source_records)
    if ARTIFACT_INDEX_PATH.exists():
        artifact_records = []
        for row in read_jsonl(ARTIFACT_INDEX_PATH):
            source_id = str(row.get("source_id", ""))
            path = str(row.get("path", ""))
            producer = str(row.get("producer", ""))
            if source_id.startswith("zotero_stage2_4j_src_") or path.startswith("data/runs/stage2_4j_") or producer == "Stage2_4jAvailableFulltextIngest":
                continue
            artifact_records.append(row)
        write_jsonl(ARTIFACT_INDEX_PATH, artifact_records)
    if TASK_REGISTRY_PATH.exists():
        task_records = [
            row
            for row in read_jsonl(TASK_REGISTRY_PATH)
            if not str(row.get("task_id", "")).startswith("stage2_4j_")
        ]
        write_jsonl(TASK_REGISTRY_PATH, task_records)


def run_dir(source_id: str) -> Path:
    return RUNS_DIR / f"stage2_4j_{source_id}"


def make_chunks(blocks: list[dict[str, str]], entry: dict[str, Any]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    source_id = str(entry.get("source_id", ""))
    title = str(entry.get("title", ""))
    doi = str(entry.get("doi", ""))
    for idx, block in enumerate(blocks, start=1):
        text = " ".join(str(block.get("text", "")).split())
        if not text:
            continue
        chunk_id = f"stage2_4j_{source_id}_chunk_{idx:03d}"
        chunks.append(
            {
                "chunk_id": chunk_id,
                "source_id": source_id,
                "doi": doi,
                "title": title,
                "section": block.get("section", "zotero_fulltext_block"),
                "section_id": block.get("section_id", f"block_{idx:03d}"),
                "text": text,
                "word_count": len(text.split()),
                "char_count": len(text),
                "text_hash": sha256_text(text),
            }
        )
    return chunks


def index_run_artifacts(source_id: str, path: Path) -> dict[str, str]:
    refs: dict[str, str] = {}
    for artifact_type, filename in ARTIFACT_FILES.items():
        artifact_path = path / filename
        if not artifact_path.exists():
            continue
        artifact = index_artifact(
            ROOT,
            ARTIFACT_INDEX_PATH,
            source_id,
            artifact_type,
            artifact_path,
            "Stage2_4jAvailableFulltextIngest",
            SCHEMA_BY_ARTIFACT_TYPE.get(artifact_type, ""),
        )
        refs[f"{artifact_type}_ref"] = artifact["path"]
    return refs


def write_run_summary(path: Path, status: dict[str, Any]) -> None:
    lines = [
        "# Stage 2.4j Available Zotero Full-text Run",
        "",
        f"run_id = {status.get('run_id', '')}",
        f"source_id = {status.get('source_id', '')}",
        f"source_origin = {status.get('source_origin', '')}",
        f"doi = {status.get('doi', '')}",
        f"title = {status.get('title', '')}",
        f"match_tier = {status.get('match_tier', '')}",
        f"local_fulltext_found = {str(bool(status.get('local_fulltext_found'))).lower()}",
        f"parsed_chunks = {status.get('parsed_chunks', 0)}",
        f"candidate_records = {status.get('candidate_records', 0)}",
        f"validated_records = {status.get('validated_records', 0)}",
        f"manual_review_records = {status.get('manual_review_records', 0)}",
        f"next_action = {status.get('next_action', '')}",
        f"failure_reason = {status.get('failure_reason', '')}",
    ]
    (path / "run_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def upsert_registry(entry: dict[str, Any], refs: dict[str, str], chunks: list[dict[str, Any]], fulltext_hash: str) -> None:
    source_id = str(entry.get("source_id", ""))
    title = str(entry.get("title", ""))
    metadata_ref = refs.get("metadata_ref", "")
    chunks_ref = refs.get("chunks_ref", "")
    metadata_path = ROOT / metadata_ref if metadata_ref else None
    chunks_path = ROOT / chunks_ref if chunks_ref else None
    source = {
        "authors": [],
        "candidate_records_ref": refs.get("candidate_records_ref", ""),
        "chunks_ref": chunks_ref,
        "doi": entry.get("doi", ""),
        "download_ref": refs.get("download_ref", ""),
        "hashes": {
            "chunks_hash": sha256_file(chunks_path) if chunks_path and chunks_path.exists() else "",
            "doi_hash": doi_hash(str(entry.get("doi", ""))),
            "fulltext_hash": fulltext_hash,
            "metadata_hash": sha256_file(metadata_path) if metadata_path and metadata_path.exists() else "",
            "title_hash": normalized_title_hash(title),
        },
        "journal": "",
        "manual_review_ref": refs.get("manual_review_ref", ""),
        "metadata_ref": metadata_ref,
        "rejected_records_ref": refs.get("rejected_records_ref", ""),
        "reviewed_records_ref": refs.get("reviewed_records_ref", ""),
        "screening_ref": refs.get("screening_ref", ""),
        "source_id": source_id,
        "source_origin": entry.get("source_origin", "zotero_existing_library"),
        "status": "chunked" if chunks else "manual_review",
        "title": title,
        "title_normalized": " ".join(title.lower().split()),
        "validated_records_ref": refs.get("validated_records_ref", ""),
        "year": "",
    }
    upsert_source(SOURCE_REGISTRY_PATH, source)


def create_codex_task(entry: dict[str, Any], refs: dict[str, str], run_id: str) -> dict[str, Any]:
    task_id = f"stage2_4j_{entry['source_id']}_extract"
    input_refs = {
        "metadata_ref": refs.get("metadata_ref", ""),
        "chunks_ref": refs.get("chunks_ref", ""),
        "download_ref": refs.get("download_ref", ""),
    }
    payload = create_task_payload(
        ROOT,
        TASKS_DIR,
        TASK_REGISTRY_PATH,
        task_id,
        "extract",
        "ExtractionAgent",
        str(entry["source_id"]),
        input_refs,
        refs.get("candidate_records_ref", ""),
        "Available Zotero full text was parsed; semantic PFAS transformation extraction requires Codex review.",
    )
    return {
        "task_id": task_id,
        "source_id": entry["source_id"],
        "run_id": run_id,
        "task_type": "extract",
        "input_refs": input_refs,
        "prompt_refs": payload["prompt_refs"],
        "schema_ref": payload["schema_ref"],
        "expected_output": payload["output_expected"],
        "reason": payload["reason"],
        "status": "pending",
        "task_payload_ref": relative_path(ROOT, TASKS_DIR / f"{task_id}.json"),
    }


def ingest_entry(entry: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    source_id = str(entry.get("source_id", ""))
    run_id = f"stage2_4j_{source_id}"
    path = run_dir(source_id)
    path.mkdir(parents=True, exist_ok=True)
    local_path = resolve_repo_path(str(entry.get("local_path", "")))
    local_found = local_path.exists() and local_path.is_file()
    fulltext_hash = sha256_file(local_path) if local_found else ""
    blocks: list[dict[str, str]] = []
    warning = ""
    if local_found:
        blocks, warning = parse_local_file(entry, local_path)
    chunks = make_chunks(blocks, entry) if blocks else []
    metadata = {
        "source_id": source_id,
        "source_origin": entry.get("source_origin", "zotero_existing_library"),
        "zotero_item_key": entry.get("zotero_item_key", ""),
        "doi": entry.get("doi", ""),
        "title": entry.get("title", ""),
        "metadata_retrieved": False,
        "provider": "zotero_existing_library",
    }
    screening = {
        "source_id": source_id,
        "decision": "include_available_fulltext" if entry.get("status") == "pending_ingest" else "manual_screen",
        "match_tier": entry.get("match_tier", ""),
        "priority": entry.get("priority", ""),
        "reason": "Available Zotero attachment selected by Stage 2.4j scope audit.",
    }
    download = {
        "source_id": source_id,
        "doi": entry.get("doi", ""),
        "file_type": entry.get("file_type", ""),
        "full_text_available": local_found,
        "full_text_downloaded": False,
        "full_text_path": entry.get("local_path", ""),
        "fulltext_sha256": fulltext_hash,
        "original_zotero_path": entry.get("original_zotero_path", ""),
        "status": "ingested" if chunks else ("parse_failed_or_no_relevant_text" if local_found else "missing_local_fulltext"),
        "reason": warning or ("Available Zotero full text parsed." if chunks else "No relevant text chunks parsed."),
        "text_source_mode": f"zotero_{entry.get('file_type', 'fulltext')}",
        "checked_at": utc_now(),
    }
    write_json(path / "source_metadata.json", metadata)
    write_json(path / "screening.json", screening)
    write_json(path / "download_status.json", download)
    write_jsonl(path / "chunks.jsonl", chunks)
    for name in RUN_JSONL_OUTPUTS[1:]:
        write_jsonl(path / name, [])
    status = {
        "source_id": source_id,
        "source_origin": entry.get("source_origin", "zotero_existing_library"),
        "doi": entry.get("doi", ""),
        "title": entry.get("title", ""),
        "run_id": run_id,
        "run_dir": relative_path(ROOT, path),
        "match_tier": entry.get("match_tier", ""),
        "priority": entry.get("priority", ""),
        "local_fulltext_found": local_found,
        "parsed_chunks": len(chunks),
        "candidate_records": 0,
        "reviewed_records": 0,
        "validated_records": 0,
        "manual_review_records": 0,
        "rejected_records": 0,
        "next_action": "codex_extract_review" if chunks else "manual_screen",
        "failure_reason": "" if chunks else download["reason"],
        "updated_at": utc_now(),
    }
    write_run_summary(path, status)
    refs = index_run_artifacts(source_id, path)
    status["artifact_refs"] = refs
    upsert_registry(entry, refs, chunks, fulltext_hash)
    task = create_codex_task(entry, refs, run_id) if chunks else None
    return status, task


def write_reports(statuses: list[dict[str, Any]], tasks: list[dict[str, Any]], manifest: list[dict[str, Any]]) -> dict[str, Any]:
    validated: list[dict[str, Any]] = []
    manual: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    write_jsonl(VALIDATED_PATH, validated)
    write_jsonl(MANUAL_PATH, manual)
    write_jsonl(REJECTED_PATH, rejected)
    parsed_sources = sum(1 for row in statuses if int(row.get("parsed_chunks", 0)) > 0)
    available_sources = len(manifest)
    blocked_missing = len(read_jsonl(ROOT / "data" / "state" / "blocked_external_queue.jsonl"))
    summary = {
        "available_fulltext_sources": available_sources,
        "tier_a_sources": sum(1 for row in manifest if row.get("match_tier") == "A"),
        "tier_b_sources": sum(1 for row in manifest if row.get("match_tier") == "B"),
        "tier_c_manual_screen_sources": sum(1 for row in manifest if row.get("match_tier") == "C"),
        "parsed_sources": parsed_sources,
        "total_chunks": sum(int(row.get("parsed_chunks", 0)) for row in statuses),
        "candidate_records": 0,
        "validated_records": 0,
        "manual_review_records": 0,
        "rejected_records": 0,
        "codex_tasks_created": len(tasks),
        "blocked_missing_fulltext_sources": blocked_missing,
        "new_validated_records_from_available_zotero": 0,
        "can_continue_without_missing_targets": True,
        "database_ready_for_100_sources": False,
        "reason": "available_fulltext_ingested_pending_codex_review" if parsed_sources else "no_available_fulltext",
    }
    write_summary(SUMMARY_PATH, "Stage 2.4j Available Full-text Ingest Summary", summary)
    audit_lines = ["# Stage 2.4j Validated Records Audit", "", "No validated records were produced automatically by Stage 2.4j."]
    AUDIT_PATH.write_text("\n".join(audit_lines) + "\n", encoding="utf-8", newline="\n")
    manual_lines = [
        "# Stage 2.4j Manual Review Targets",
        "",
        "| source_id | title | next_action | reason |",
        "| --- | --- | --- | --- |",
    ]
    for row in statuses:
        if row.get("next_action"):
            manual_lines.append(f"| {row['source_id']} | {str(row.get('title', '')).replace('|', '/')} | {row['next_action']} | {str(row.get('failure_reason', '')).replace('|', '/')} |")
    MANUAL_TARGETS_PATH.write_text("\n".join(manual_lines) + "\n", encoding="utf-8", newline="\n")
    scale = {
        "can_continue_without_missing_targets": True,
        "database_ready_for_100_sources": False,
        "reason": summary["reason"],
    }
    write_summary(SCALE_PATH, "Stage 2.4j Scale Readiness", scale)
    return summary


def main() -> int:
    purge_stage2_4j_state()
    manifest = [row for row in read_jsonl(AVAILABLE_MANIFEST) if row.get("status") == "pending_ingest"]
    statuses: list[dict[str, Any]] = []
    tasks: list[dict[str, Any]] = []
    for entry in manifest:
        status, task = ingest_entry(entry)
        statuses.append(status)
        if task:
            tasks.append(task)
    write_jsonl(STATUS_PATH, statuses)
    write_jsonl(CODEX_TASKS_PATH, tasks)
    summary = write_reports(statuses, tasks, read_jsonl(AVAILABLE_MANIFEST))
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
