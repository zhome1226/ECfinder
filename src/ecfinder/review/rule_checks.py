"""Rule-based review checks for extracted transformation records."""

from __future__ import annotations

import csv
from pathlib import Path

from ecfinder.extract.schema import validate_record_shape
from ecfinder.utils.logging import read_jsonl, write_jsonl


def review_record(record: dict, chunk: dict | None = None) -> dict:
    reasons = validate_record_shape(record)
    quote = record.get("evidence_quote") or ""
    chunk_text = (chunk or {}).get("text") or ""
    if quote and chunk_text and quote.lower() not in chunk_text.lower():
        reasons.append("evidence_quote_not_found_in_chunk")
    if not record.get("natural_environment_context"):
        reasons.append("missing_natural_environment_context")
    confidence = float(record.get("confidence") or 0)
    if reasons:
        decision = "needs_reextract" if confidence >= 0.4 else "rejected"
    elif confidence < 0.7:
        decision = "needs_reextract"
        reasons.append("confidence_below_accept_threshold")
    else:
        decision = "accepted"
    reviewed = dict(record)
    reviewed.update({"reviewer_status": decision, "review_reasons": reasons})
    return reviewed


def review_records(root: str | Path) -> tuple[list[dict], list[dict]]:
    repo_root = Path(root)
    chunks = {chunk.get("chunk_id"): chunk for chunk in read_jsonl(repo_root / "data" / "interim" / "chunks.jsonl")}
    accepted = []
    rejected = []
    for record in read_jsonl(repo_root / "data" / "extracted" / "pfas_transformation_records_raw.jsonl"):
        reviewed = review_record(record, chunks.get(record.get("chunk_id")))
        if reviewed["reviewer_status"] == "accepted":
            accepted.append(reviewed)
        else:
            rejected.append(reviewed)
    write_jsonl(repo_root / "data" / "reviewed" / "pfas_transformation_records_validated.jsonl", accepted)
    write_jsonl(repo_root / "data" / "reviewed" / "rejected_records.jsonl", rejected)
    write_csv(repo_root / "data" / "reviewed" / "pfas_transformation_records_validated.csv", accepted)
    return accepted, rejected


def write_csv(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "record_id",
        "source_id",
        "chunk_id",
        "doi",
        "parent_name",
        "product_name",
        "transformation_process",
        "matrix",
        "condition_type",
        "natural_environment_context",
        "evidence_quote",
        "confidence",
        "reviewer_status",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)
