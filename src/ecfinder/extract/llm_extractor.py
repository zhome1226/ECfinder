"""LLM extraction wrapper and deterministic response validation."""

from __future__ import annotations

import json
from pathlib import Path

from ecfinder.extract.record_normalizer import normalize_name
from ecfinder.extract.schema import assign_record_id, validate_record_shape
from ecfinder.utils.logging import read_jsonl, write_jsonl


def parse_llm_records(response_text: str) -> list[dict]:
    payload = json.loads(response_text)
    records = payload.get("records", []) if isinstance(payload, dict) else []
    normalized = []
    for record in records:
        record = dict(record)
        record["parent_normalized"] = normalize_name(record.get("parent_name"))
        record["product_normalized"] = normalize_name(record.get("product_name"))
        assign_record_id(record)
        record["schema_errors"] = validate_record_shape(record)
        record.setdefault("reviewer_status", "unreviewed")
        normalized.append(record)
    return normalized


def extract_from_chunks_stub(root: str | Path) -> list[dict]:
    """Create an empty extraction file when no LLM runtime is configured."""
    repo_root = Path(root)
    _ = list(read_jsonl(repo_root / "data" / "interim" / "chunks.jsonl"))
    records: list[dict] = []
    write_jsonl(repo_root / "data" / "extracted" / "pfas_transformation_records_raw.jsonl", records)
    return records
