"""Validate Stage 2.4j available-first Zotero ingest outputs."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from stage2_4j_common import AUDIT_JSONL, AVAILABLE_MANIFEST, BATCH_DIR, REPORTS_DIR, ROOT, SYNC_STATUS, parse_summary, read_jsonl


STATUS_PATH = BATCH_DIR / "stage2_4j_available_fulltext_ingest_status.jsonl"
VALIDATED_PATH = BATCH_DIR / "stage2_4j_validated_records.jsonl"
MANUAL_PATH = BATCH_DIR / "stage2_4j_manual_review_records.jsonl"
REJECTED_PATH = BATCH_DIR / "stage2_4j_rejected_records.jsonl"
CODEX_TASKS_PATH = BATCH_DIR / "stage2_4j_codex_tasks.jsonl"
SUMMARY_PATH = REPORTS_DIR / "stage2_4j_available_fulltext_ingest_summary.md"
AUDIT_SUMMARY_PATH = REPORTS_DIR / "stage2_4j_zotero_scope_audit_summary.md"

FORBIDDEN = ["activated sludge", "wastewater treatment", "wwtp", "engineered treatment", "aop", "plasma", "photocatalysis", "ozonation", "incineration"]


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"missing JSON file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl_strict(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise ValueError(f"missing JSONL: {path}")
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        if "} {" in line:
            raise ValueError(f"{path}:{line_no} contains multiple JSON objects")
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_no} is not an object")
        rows.append(value)
    return rows


def validate_raw_fulltext_not_committed() -> None:
    result = subprocess.run(
        ["git", "ls-files", "data/local_fulltext/stage2_4j/pdf", "data/local_fulltext/stage2_4j/html", "data/local_fulltext/stage2_4j/si"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(result.stderr.strip())
    bad = [line for line in result.stdout.splitlines() if line.strip() and not line.strip().replace("\\", "/").endswith("/.gitkeep")]
    if bad:
        raise ValueError(f"raw Stage 2.4j fulltext tracked by Git: {bad}")


def validate_manifest() -> list[dict[str, Any]]:
    manifest = read_jsonl_strict(AVAILABLE_MANIFEST)
    for row in manifest:
        if row.get("status") in {"pending_ingest", "manual_screen"}:
            path = ROOT / str(row.get("local_path", ""))
            if not path.exists():
                raise ValueError(f"manifest local_path missing: {row.get('source_id')} {row.get('local_path')}")
            if not row.get("sha256"):
                raise ValueError(f"manifest row missing sha256: {row.get('source_id')}")
        if row.get("match_tier") not in {"A", "B", "C", "D"}:
            raise ValueError(f"invalid match_tier: {row}")
    return manifest


def validate_runs(statuses: list[dict[str, Any]]) -> None:
    for row in statuses:
        run_dir = ROOT / str(row.get("run_dir", ""))
        if not run_dir.exists():
            raise ValueError(f"missing run dir: {run_dir}")
        for name in ["source_metadata.json", "screening.json", "download_status.json", "run_summary.md"]:
            if not (run_dir / name).exists():
                raise ValueError(f"missing run output: {run_dir / name}")
        for name in ["chunks.jsonl", "candidate_records.jsonl", "reviewed_records.jsonl", "validated_records.jsonl", "manual_review_records.jsonl", "rejected_records.jsonl"]:
            records = read_jsonl_strict(run_dir / name)
            if name == "chunks.jsonl":
                for chunk in records:
                    if len(str(chunk.get("text", ""))) > 20000:
                        raise ValueError(f"committed chunk too large: {chunk.get('chunk_id')}")


def validate_validated_records() -> None:
    for record in read_jsonl_strict(VALIDATED_PATH):
        for field in ["source_id", "chunk_id", "evidence_quote"]:
            if not record.get(field):
                raise ValueError(f"validated record missing {field}")
        text = json.dumps(record, ensure_ascii=False).lower()
        hits = [term for term in FORBIDDEN if term in text]
        if hits:
            raise ValueError(f"validated record violates boundary: {hits}")


def validate_tasks() -> None:
    for task in read_jsonl_strict(CODEX_TASKS_PATH):
        if not task.get("task_id") or not task.get("input_refs") or not task.get("expected_output"):
            raise ValueError(f"invalid Codex task: {task}")
        payload = ROOT / str(task.get("task_payload_ref", ""))
        if not payload.exists():
            raise ValueError(f"missing task payload: {payload}")


def validate_summary(manifest: list[dict[str, Any]], statuses: list[dict[str, Any]]) -> dict[str, Any]:
    summary = parse_summary(SUMMARY_PATH)
    expected = {
        "available_fulltext_sources": len(manifest),
        "tier_a_sources": sum(1 for row in manifest if row.get("match_tier") == "A"),
        "tier_b_sources": sum(1 for row in manifest if row.get("match_tier") == "B"),
        "tier_c_manual_screen_sources": sum(1 for row in manifest if row.get("match_tier") == "C"),
        "parsed_sources": sum(1 for row in statuses if int(row.get("parsed_chunks", 0)) > 0),
        "total_chunks": sum(int(row.get("parsed_chunks", 0)) for row in statuses),
        "codex_tasks_created": len(read_jsonl_strict(CODEX_TASKS_PATH)),
    }
    for key, value in expected.items():
        if summary.get(key) != str(value):
            raise ValueError(f"summary mismatch for {key}: expected {value}, got {summary.get(key)}")
    if summary.get("can_continue_without_missing_targets") != "true":
        raise ValueError("can_continue_without_missing_targets must be true")
    return {**expected, "reason": summary.get("reason", "")}


def run_external_validator(script: str) -> None:
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / script)], cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise ValueError(f"{script} failed: {result.stderr.strip() or result.stdout.strip()}")


def main() -> int:
    audit = read_jsonl_strict(AUDIT_JSONL)
    if not audit:
        raise ValueError("Zotero scope audit is empty")
    read_jsonl_strict(SYNC_STATUS)
    manifest = validate_manifest()
    statuses = read_jsonl_strict(STATUS_PATH)
    validate_runs(statuses)
    validate_validated_records()
    read_jsonl_strict(MANUAL_PATH)
    read_jsonl_strict(REJECTED_PATH)
    validate_tasks()
    validate_raw_fulltext_not_committed()
    if any("sci-hub" in json.dumps(row, ensure_ascii=False).lower() or "pirate" in json.dumps(row, ensure_ascii=False).lower() for row in manifest):
        raise ValueError("forbidden source indicator found")
    if not AUDIT_SUMMARY_PATH.exists():
        raise ValueError("missing audit summary")
    summary = validate_summary(manifest, statuses)
    run_external_validator("validate_state_cache_layer.py")
    run_external_validator("validate_supervisor_workflow.py")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
