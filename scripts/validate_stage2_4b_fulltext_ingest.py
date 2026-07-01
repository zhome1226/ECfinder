"""Validate Stage 2.4b local full-text ingest outputs."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ecfinder.state.common import read_jsonl, sha256_file


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "data" / "local_fulltext" / "stage2_4b" / "fulltext_manifest.jsonl"
BATCH_DIR = ROOT / "data" / "batches"
REPORTS_DIR = ROOT / "reports"
STATE_DIR = ROOT / "data" / "state"

STATUS_PATH = BATCH_DIR / "stage2_4b_fulltext_ingest_status.jsonl"
VALIDATED_PATH = BATCH_DIR / "stage2_4b_validated_records.jsonl"
MANUAL_PATH = BATCH_DIR / "stage2_4b_manual_review_records.jsonl"
REJECTED_PATH = BATCH_DIR / "stage2_4b_rejected_records.jsonl"
CODEX_TASKS_PATH = BATCH_DIR / "stage2_4b_codex_tasks.jsonl"
ZOTERO_STATUS_PATH = BATCH_DIR / "stage2_4b_zotero_attachment_status.jsonl"
SUMMARY_PATH = REPORTS_DIR / "stage2_4b_fulltext_ingest_summary.md"

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

FORBIDDEN_TERMS = [
    "activated sludge",
    "wastewater treatment",
    "wwtp",
    "engineered treatment",
    "engineered biological treatment",
    "aop",
    "electrochemical",
    "plasma",
    "photocatalysis",
    "ozonation",
    "hydrothermal",
    "incineration",
]

LONG_STATUS_KEYS = {"stdout", "stderr", "abstract", "text", "full_text", "chunk_text", "evidence_quote"}


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
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no} invalid JSONL: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"{path}:{line_no} is not a JSON object")
            records.append(record)
    return records


def require_repo_path(path_text: str, context: str) -> Path:
    if not path_text:
        raise ValueError(f"missing referenced path in {context}")
    path = ROOT / path_text
    if not path.exists():
        raise ValueError(f"missing referenced path in {context}: {path_text}")
    return path


def parse_summary(path: Path) -> dict[str, str]:
    if not path.exists():
        raise ValueError(f"missing report: {path}")
    counts: dict[str, str] = {}
    pattern = re.compile(r"^([A-Za-z0-9_]+)\s*=\s*(.+?)\s*$")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            counts[match.group(1)] = match.group(2)
    return counts


def local_path_exists(path_text: str) -> bool:
    if not path_text:
        return False
    path = Path(path_text)
    if not path.is_absolute():
        path = ROOT / path
    return path.exists() and path.is_file()


def validate_manifest() -> list[dict[str, Any]]:
    records = read_jsonl_strict(MANIFEST_PATH)
    if len(records) != 12:
        raise ValueError(f"manifest must contain 12 high-priority targets; found {len(records)}")
    seen: set[str] = set()
    valid_file_types = {"pdf", "html", "si"}
    for record in records:
        source_id = record.get("source_id")
        if not source_id:
            raise ValueError("manifest record missing source_id")
        if source_id in seen:
            raise ValueError(f"duplicate manifest source_id: {source_id}")
        seen.add(source_id)
        if not record.get("doi") and not record.get("title"):
            raise ValueError(f"manifest target missing DOI/title: {source_id}")
        if record.get("status") == "missing_fulltext" and record.get("file_type") is None:
            pass
        elif record.get("file_type") not in valid_file_types:
            raise ValueError(f"invalid file_type for {source_id}: {record.get('file_type')}")
        if not record.get("status"):
            raise ValueError(f"manifest target missing status: {source_id}")
    return records


def validate_zotero_attachment_status(manifest: list[dict[str, Any]]) -> None:
    if not ZOTERO_STATUS_PATH.exists():
        return
    rows = read_jsonl_strict(ZOTERO_STATUS_PATH)
    if len(rows) != len(manifest):
        raise ValueError(f"Zotero attachment status count mismatch: expected {len(manifest)}, got {len(rows)}")
    manifest_by_source = {row["source_id"]: row for row in manifest}
    for row in rows:
        source_id = row.get("source_id")
        if source_id not in manifest_by_source:
            raise ValueError(f"Zotero status source not in manifest: {source_id}")
        diagnosis = row.get("diagnosis")
        if diagnosis not in {
            "zotero_attachment_synced",
            "zotero_item_missing",
            "zotero_item_without_attachment",
            "zotero_attachment_file_missing",
            "zotero_attachment_unsupported_type",
        }:
            raise ValueError(f"invalid Zotero attachment diagnosis for {source_id}: {diagnosis}")
        if row.get("accepted_attachment_count", 0):
            manifest_row = manifest_by_source[source_id]
            if not manifest_row.get("local_path") or not manifest_row.get("sha256"):
                raise ValueError(f"Zotero-synced source missing manifest local_path/sha256: {source_id}")
            if not local_path_exists(str(manifest_row["local_path"])):
                raise ValueError(f"Zotero-synced local path missing: {source_id}")
            path = ROOT / str(manifest_row["local_path"])
            if sha256_file(path) != manifest_row["sha256"]:
                raise ValueError(f"Zotero-synced manifest sha mismatch: {source_id}")
        elif manifest_by_source[source_id].get("status") != "missing_fulltext":
            raise ValueError(f"unsynced Zotero source must remain missing_fulltext: {source_id}")


def validate_raw_fulltext_not_committed() -> None:
    result = subprocess.run(
        [
            "git",
            "ls-files",
            "data/local_fulltext/stage2_4b/pdf",
            "data/local_fulltext/stage2_4b/html",
            "data/local_fulltext/stage2_4b/si",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(f"git ls-files failed: {result.stderr.strip()}")
    tracked = [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]
    bad = [path for path in tracked if not path.endswith("/.gitkeep")]
    if bad:
        raise ValueError(f"raw local full-text files are tracked by Git: {bad}")


def validate_run_outputs(statuses: list[dict[str, Any]]) -> None:
    for status in statuses:
        for key in LONG_STATUS_KEYS:
            if key in status:
                raise ValueError(f"status contains long text field {key}: {status.get('source_id')}")
        run_dir = ROOT / str(status.get("run_dir", ""))
        if not run_dir.exists():
            raise ValueError(f"missing run directory: {run_dir}")
        for name in ["source_metadata.json", "screening.json", "download_status.json", "run_summary.md"]:
            if not (run_dir / name).exists():
                raise ValueError(f"missing run output: {run_dir / name}")
        read_json(run_dir / "source_metadata.json")
        read_json(run_dir / "screening.json")
        download = read_json(run_dir / "download_status.json")
        if status.get("local_fulltext_found"):
            if not local_path_exists(str(status.get("local_path", ""))):
                raise ValueError(f"status says local fulltext exists but path is missing: {status.get('source_id')}")
            if not status.get("fulltext_sha256"):
                raise ValueError(f"ingested source missing fulltext sha256: {status.get('source_id')}")
        else:
            if download.get("status") != "missing_local_fulltext":
                raise ValueError(f"missing source not clearly marked: {status.get('source_id')}")
        for name in RUN_JSONL_OUTPUTS:
            read_jsonl_strict(run_dir / name)
        for record in read_jsonl_strict(run_dir / "validated_records.jsonl"):
            validate_record_boundary(record, run_dir)


def validate_record_boundary(record: dict[str, Any], run_dir: Path) -> None:
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
        raise ValueError(f"{run_dir}/validated_records.jsonl missing required fields: {missing}")
    text = json.dumps(record, ensure_ascii=False).lower()
    hits = [term for term in FORBIDDEN_TERMS if term in text]
    if hits:
        raise ValueError(f"{run_dir}/validated_records.jsonl contains forbidden natural-boundary terms: {hits}")


def validate_tasks() -> list[dict[str, Any]]:
    tasks = read_jsonl_strict(CODEX_TASKS_PATH)
    seen: set[str] = set()
    registry = {record.get("task_id"): record.get("task_path", "") for record in read_jsonl_strict(TASK_REGISTRY_PATH)}
    for task in tasks:
        task_id = task.get("task_id")
        if not task_id:
            raise ValueError("Codex task missing task_id")
        if task_id in seen:
            raise ValueError(f"duplicate Codex task: {task_id}")
        seen.add(task_id)
        if not task.get("input_refs"):
            raise ValueError(f"Codex task missing input_refs: {task_id}")
        if not task.get("expected_output"):
            raise ValueError(f"Codex task missing expected_output: {task_id}")
        payload_ref = task.get("task_payload_ref", "")
        payload_path = require_repo_path(payload_ref, f"task payload {task_id}")
        payload = read_json(payload_path)
        for prompt_ref in payload.get("prompt_refs", []):
            require_repo_path(prompt_ref, f"task prompt {task_id}")
        require_repo_path(payload.get("schema_ref", ""), f"task schema {task_id}")
        for _, ref in payload.get("input_refs", {}).items():
            if ref:
                require_repo_path(ref, f"task input {task_id}")
        if task_id not in registry:
            raise ValueError(f"Codex task missing task_registry entry: {task_id}")
        require_repo_path(registry[task_id], f"task registry {task_id}")
    return tasks


def validate_state_refs(statuses: list[dict[str, Any]]) -> None:
    source_registry = read_jsonl_strict(SOURCE_REGISTRY_PATH)
    source_ids = {record.get("source_id") for record in source_registry}
    artifact_index = read_jsonl_strict(ARTIFACT_INDEX_PATH)
    for status in statuses:
        source_id = status.get("source_id")
        if source_id not in source_ids:
            raise ValueError(f"source_registry missing {source_id}")
        for ref in status.get("artifact_refs", {}).values():
            if not ref:
                continue
            path = require_repo_path(ref, f"artifact ref {source_id}")
            digest = sha256_file(path)
            matches = [record for record in artifact_index if record.get("path") == ref or record.get("sha256") == digest]
            if not matches:
                raise ValueError(f"artifact_index missing ref or sha for {source_id}: {ref}")
            if not any(record.get("sha256") == digest for record in matches):
                raise ValueError(f"artifact hash mismatch for {source_id}: {ref}")
    decisions = read_jsonl_strict(DECISION_CACHE_PATH)
    decision_ids = [record.get("decision_id") for record in decisions]
    if len(decision_ids) != len(set(decision_ids)):
        raise ValueError("decision_cache contains duplicate decision_id values")


def summarize(statuses: list[dict[str, Any]], tasks: list[dict[str, Any]]) -> dict[str, Any]:
    manifest_rows = read_jsonl_strict(MANIFEST_PATH)
    validated = read_jsonl_strict(VALIDATED_PATH)
    manual = read_jsonl_strict(MANUAL_PATH)
    rejected = read_jsonl_strict(REJECTED_PATH)
    source_count_with_validated = len({record.get("source_id") for record in validated if record.get("source_id")})
    local_found = sum(1 for status in statuses if status.get("local_fulltext_found"))
    parsed_sources = sum(1 for status in statuses if int(status.get("parsed_chunks", 0)) > 0)
    if local_found == 0:
        can_scale = False
        if any(row.get("status") == "missing_fulltext" and row.get("rescue_attempted") for row in manifest_rows):
            reason = "insufficient_campus_fulltext_access"
        else:
            reason = "no local fulltext provided"
    elif parsed_sources >= 5 and len(validated) >= 5 and source_count_with_validated >= 2:
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
        "manual_review_records": len(manual),
        "rejected_records": len(rejected),
        "codex_tasks_created": len(tasks),
        "new_validated_records_beyond_stage2_4": len(validated),
        "source_count_with_validated_records": source_count_with_validated,
        "remaining_manual_targets": sum(1 for status in statuses if status.get("next_action") == "manual_full_text_check"),
        "can_scale_to_100_sources": can_scale,
        "reason": reason,
    }


def validate_summary(summary: dict[str, Any]) -> None:
    report_counts = parse_summary(SUMMARY_PATH)
    for key, value in summary.items():
        expected = str(value).lower() if isinstance(value, bool) else str(value)
        actual = report_counts.get(key)
        if actual != expected:
            raise ValueError(f"summary mismatch for {key}: expected {expected}, got {actual}")
    if summary["can_scale_to_100_sources"] and not (
        summary["parsed_sources"] >= 5
        and summary["new_validated_records_beyond_stage2_4"] >= 5
        and summary["source_count_with_validated_records"] >= 2
    ):
        raise ValueError("can_scale_to_100_sources=true without meeting Stage 2.4b evidence criteria")


def main() -> int:
    manifest = validate_manifest()
    validate_zotero_attachment_status(manifest)
    validate_raw_fulltext_not_committed()
    statuses = read_jsonl_strict(STATUS_PATH)
    if len(statuses) != 12:
        raise ValueError(f"Stage 2.4b status must contain 12 sources; found {len(statuses)}")
    for path in [VALIDATED_PATH, MANUAL_PATH, REJECTED_PATH]:
        for record in read_jsonl_strict(path):
            if path == VALIDATED_PATH:
                validate_record_boundary(record, path.parent)
    validate_run_outputs(statuses)
    tasks = validate_tasks()
    validate_state_refs(statuses)
    summary = summarize(statuses, tasks)
    validate_summary(summary)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
