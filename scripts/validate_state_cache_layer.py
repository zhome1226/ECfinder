"""Validate Stage 2.4-pre persistent state/cache/task layer."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ecfinder.state.common import read_jsonl, sha256_file, write_json


ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "data" / "state"
SOURCE_REGISTRY = STATE_DIR / "source_registry.jsonl"
ARTIFACT_INDEX = STATE_DIR / "artifact_index.jsonl"
DECISION_CACHE = STATE_DIR / "decision_cache.jsonl"
TASK_REGISTRY = STATE_DIR / "task_registry.jsonl"
CACHE_STATS = STATE_DIR / "cache_stats.json"
STATUS_PATH = ROOT / "data" / "batches" / "stage2_3_10source_status.jsonl"

LONG_TEXT_FIELDS = {"stdout", "stderr", "abstract", "text", "full_text", "chunk_text", "evidence_text"}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"missing JSON file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def require_path(path_text: str, context: str) -> Path:
    if not path_text:
        raise ValueError(f"missing path in {context}")
    path = ROOT / path_text
    if not path.exists():
        raise ValueError(f"missing referenced path in {context}: {path_text}")
    return path


def validate_source_registry() -> list[dict[str, Any]]:
    records = read_jsonl(SOURCE_REGISTRY)
    if not records:
        raise ValueError("source_registry has no records")
    seen: set[str] = set()
    for record in records:
        source_id = record.get("source_id")
        if not source_id:
            raise ValueError("source_registry record missing source_id")
        if source_id in seen:
            raise ValueError(f"duplicate source_id in source_registry: {source_id}")
        seen.add(source_id)
        if not record.get("metadata_ref"):
            raise ValueError(f"source_registry record missing metadata_ref: {source_id}")
        require_path(record["metadata_ref"], f"source_registry {source_id}")
        hashes = record.get("hashes", {})
        if "doi_hash" not in hashes or "title_hash" not in hashes:
            raise ValueError(f"source_registry record missing hashes: {source_id}")
    return records


def validate_artifact_index() -> list[dict[str, Any]]:
    records = read_jsonl(ARTIFACT_INDEX)
    if not records:
        raise ValueError("artifact_index has no records")
    for record in records:
        artifact_id = record.get("artifact_id")
        path = require_path(record.get("path", ""), f"artifact_index {artifact_id}")
        actual_hash = sha256_file(path)
        if actual_hash != record.get("sha256"):
            raise ValueError(f"artifact hash mismatch for {artifact_id}: {record.get('path')}")
        if record.get("valid") is not True:
            raise ValueError(f"artifact marked invalid: {artifact_id}")
        schema_ref = record.get("schema_ref", "")
        if schema_ref:
            require_path(schema_ref, f"artifact schema {artifact_id}")
    return records


def validate_decision_cache() -> list[dict[str, Any]]:
    records = read_jsonl(DECISION_CACHE)
    for record in records:
        if not record.get("decision_id"):
            raise ValueError("decision_cache record missing decision_id")
        require_path(record.get("decision_ref", ""), f"decision_cache {record.get('decision_id')}")
        if not record.get("prompt_version") or not record.get("schema_version"):
            raise ValueError(f"decision_cache missing versions: {record.get('decision_id')}")
    return records


def validate_task_registry() -> list[dict[str, Any]]:
    records = read_jsonl(TASK_REGISTRY)
    for record in records:
        path = require_path(record.get("task_path", ""), f"task_registry {record.get('task_id')}")
        payload = read_json(path)
        for prompt_ref in payload.get("prompt_refs", []):
            require_path(prompt_ref, f"task prompt {payload.get('task_id')}")
        require_path(payload.get("schema_ref", ""), f"task schema {payload.get('task_id')}")
        for _, ref in payload.get("input_refs", {}).items():
            if ref:
                require_path(ref, f"task input {payload.get('task_id')}")
    return records


def validate_batch_status() -> list[dict[str, Any]]:
    records = read_jsonl(STATUS_PATH)
    for record in records:
        for key in LONG_TEXT_FIELDS:
            if key in record:
                raise ValueError(f"batch status contains long text field {key}: {record.get('source_id')}")
        refs = record.get("artifact_refs", {})
        if not refs:
            raise ValueError(f"batch status missing artifact_refs: {record.get('source_id')}")
        for _, ref in refs.items():
            if ref:
                require_path(ref, f"batch artifact ref {record.get('source_id')}")
    return records


def validate_cache_stats(
    source_records: list[dict[str, Any]],
    artifact_records: list[dict[str, Any]],
    decision_records: list[dict[str, Any]],
    task_records: list[dict[str, Any]],
) -> dict[str, Any]:
    stats = read_json(CACHE_STATS) if CACHE_STATS.exists() else {}
    expected_keys = [
        "metadata_cache_hits",
        "metadata_cache_misses",
        "screening_cache_hits",
        "screening_cache_misses",
        "parse_cache_hits",
        "parse_cache_misses",
        "extraction_cache_hits",
        "extraction_cache_misses",
        "review_cache_hits",
        "review_cache_misses",
        "tasks_created",
        "tokens_saved_estimate",
    ]
    for key in expected_keys:
        stats[key] = int(stats.get(key, 0))
    stats.update(
        {
            "source_registry_records": len(source_records),
            "artifact_index_records": len(artifact_records),
            "decision_cache_records": len(decision_records),
            "task_registry_records": len(task_records),
        }
    )
    write_json(CACHE_STATS, stats)
    return stats


def main() -> int:
    source_records = validate_source_registry()
    artifact_records = validate_artifact_index()
    decision_records = validate_decision_cache()
    task_records = validate_task_registry()
    validate_batch_status()
    stats = validate_cache_stats(source_records, artifact_records, decision_records, task_records)
    print(json.dumps(stats, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
