"""Artifact index for reusable intermediate files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import read_jsonl, relative_path, sha256_file, utc_now, write_jsonl


INDEX_PATH = Path("data/state/artifact_index.jsonl")


def load_index(path: Path = INDEX_PATH) -> list[dict[str, Any]]:
    return read_jsonl(path)


def record_count(path: Path) -> int | None:
    if path.suffix != ".jsonl":
        return None
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            count += 1
    return count


def artifact_id(source_id: str, artifact_type: str, digest: str) -> str:
    return f"{source_id}_{artifact_type}_{digest[:16]}"


def index_artifact(
    root: Path,
    index_path: Path,
    source_id: str,
    artifact_type: str,
    path: Path,
    producer: str,
    schema_ref: str,
) -> dict[str, Any]:
    digest = sha256_file(path)
    indexed = load_index(index_path)
    rel = relative_path(root, path)
    record = {
        "artifact_id": artifact_id(source_id, artifact_type, digest),
        "source_id": source_id,
        "artifact_type": artifact_type,
        "path": rel,
        "sha256": digest,
        "created_at": utc_now(),
        "producer": producer,
        "schema_ref": schema_ref,
        "record_count": record_count(path),
        "valid": True,
    }
    output: list[dict[str, Any]] = []
    replaced = False
    for existing in indexed:
        same_path = existing.get("path") == rel
        same_artifact_id = existing.get("artifact_id") == record["artifact_id"]
        if same_path or same_artifact_id:
            existing = {**existing, **record, "valid": True}
            replaced = True
        output.append(existing)
    if not replaced:
        output.append(record)
    write_jsonl(index_path, output)
    return record
