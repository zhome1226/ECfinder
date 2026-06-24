"""Extraction schema validation and record IDs."""

from __future__ import annotations

from ecfinder.utils.hashing import stable_id


REQUIRED_FIELDS = [
    "source_id",
    "chunk_id",
    "parent_name",
    "product_name",
    "transformation_process",
    "natural_environment_context",
    "evidence_quote",
    "evidence_location",
]


def validate_record_shape(record: dict) -> list[str]:
    errors = []
    for field in REQUIRED_FIELDS:
        if not record.get(field):
            errors.append(f"missing:{field}")
    evidence_location = record.get("evidence_location")
    if evidence_location and not evidence_location.get("section"):
        errors.append("missing:evidence_location.section")
    quote = record.get("evidence_quote") or ""
    if quote and len(quote) < 20:
        errors.append("evidence_quote_too_short")
    if len(quote) > 500:
        errors.append("evidence_quote_too_long")
    return errors


def assign_record_id(record: dict) -> dict:
    if not record.get("record_id"):
        record["record_id"] = stable_id(
            "rec",
            record.get("source_id"),
            record.get("chunk_id"),
            record.get("parent_name"),
            record.get("product_name"),
            record.get("evidence_quote"),
        )
    return record
