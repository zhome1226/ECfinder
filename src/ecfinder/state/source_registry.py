"""Persistent source registry keyed by DOI or normalized title."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import doi_hash, normalized_title_hash, read_jsonl, utc_now, write_jsonl


REGISTRY_PATH = Path("data/state/source_registry.jsonl")


def load_registry(path: Path = REGISTRY_PATH) -> list[dict[str, Any]]:
    return read_jsonl(path)


def source_key(source: dict[str, Any]) -> tuple[str, str]:
    doi = str(source.get("doi", "")).strip().lower()
    if doi:
        return ("doi", doi_hash(doi))
    return ("title", normalized_title_hash(str(source.get("title", ""))))


def upsert_source(path: Path, source: dict[str, Any]) -> dict[str, Any]:
    records = load_registry(path)
    key_type, key_hash = source_key(source)
    updated = {
        **source,
        "last_updated": utc_now(),
    }
    found = False
    merged_records: list[dict[str, Any]] = []
    for record in records:
        record_key_type, record_key_hash = source_key(record)
        if record_key_type == key_type and record_key_hash == key_hash:
            merged = {**record, **updated}
            merged_records.append(merged)
            updated = merged
            found = True
        else:
            merged_records.append(record)
    if not found:
        merged_records.append(updated)
    write_jsonl(path, merged_records)
    return updated
