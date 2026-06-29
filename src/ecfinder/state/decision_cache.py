"""Decision cache for screen/extract/review agent outputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import read_jsonl, sha256_text, utc_now, write_jsonl


CACHE_PATH = Path("data/state/decision_cache.jsonl")


def decision_id(task_type: str, input_hash: str, prompt_version: str, schema_version: str) -> str:
    return sha256_text("|".join([task_type, input_hash, prompt_version, schema_version]))[:24]


def find_decision(
    path: Path,
    task_type: str,
    input_hash: str,
    prompt_version: str,
    schema_version: str,
) -> dict[str, Any] | None:
    target_id = decision_id(task_type, input_hash, prompt_version, schema_version)
    for record in read_jsonl(path):
        if record.get("decision_id") == target_id and record.get("valid", True):
            return record
    return None


def upsert_decision(
    path: Path,
    task_type: str,
    input_hash: str,
    prompt_version: str,
    schema_version: str,
    decision_ref: str,
    decision_summary: str,
    confidence: float | None,
) -> dict[str, Any]:
    record = {
        "decision_id": decision_id(task_type, input_hash, prompt_version, schema_version),
        "task_type": task_type,
        "input_hash": input_hash,
        "prompt_version": prompt_version,
        "schema_version": schema_version,
        "decision_ref": decision_ref,
        "decision_summary": decision_summary,
        "confidence": confidence,
        "created_at": utc_now(),
        "valid": True,
    }
    records = [item for item in read_jsonl(path) if item.get("decision_id") != record["decision_id"]]
    records.append(record)
    write_jsonl(path, records)
    return record
