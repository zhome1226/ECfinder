"""Validate reviewed ECfinder outputs."""

from __future__ import annotations

import csv
from pathlib import Path

from ecfinder.review.export_validated import ENGINEERED_TERMS, NATURAL_ALLOWED_SETTING_TYPES
from ecfinder.utils.logging import read_jsonl


def validate_outputs(root: str | Path) -> dict:
    repo_root = Path(root)
    validated_path = repo_root / "data" / "reviewed" / "pfas_transformation_records_validated.jsonl"
    validated_csv = repo_root / "data" / "reviewed" / "pfas_transformation_records_validated.csv"
    auxiliary_path = repo_root / "data" / "reviewed" / "auxiliary_engineered_biological_records.jsonl"
    auxiliary_csv = repo_root / "data" / "reviewed" / "auxiliary_engineered_biological_records.csv"

    validated = list(read_jsonl(validated_path))
    auxiliary = list(read_jsonl(auxiliary_path))
    errors: list[str] = []

    for index, record in enumerate(validated, start=1):
        text = _joined_record_text(record)
        for term in ENGINEERED_TERMS:
            if term in text:
                errors.append(f"validated row {index} contains excluded engineered term: {term}")
        for field in ["source_id", "chunk_id", "evidence_quote"]:
            if not record.get(field):
                errors.append(f"validated row {index} missing {field}")
        if not (record.get("parent_compound") or {}).get("name"):
            errors.append(f"validated row {index} missing parent_compound.name")
        if not (record.get("product_compound") or {}).get("name"):
            errors.append(f"validated row {index} missing product_compound.name")
        if not (record.get("conditions") or {}).get("setting_type"):
            errors.append(f"validated row {index} missing conditions.setting_type")
        elif (record.get("conditions") or {}).get("setting_type") not in NATURAL_ALLOWED_SETTING_TYPES:
            errors.append(f"validated row {index} has non-natural setting_type")

    if _csv_count(validated_csv) != len(validated):
        errors.append("validated CSV row count does not match JSONL")
    if _csv_count(auxiliary_csv) != len(auxiliary):
        errors.append("auxiliary CSV row count does not match JSONL")

    if not any(any(term in _joined_record_text(record) for term in ENGINEERED_TERMS) for record in auxiliary) and auxiliary:
        errors.append("auxiliary file has records but none contain engineered biological context")

    return {
        "validated_count": len(validated),
        "auxiliary_count": len(auxiliary),
        "errors": errors,
        "ok": not errors,
        "zero_validated_reason": "No records met natural-environment criteria." if not validated else "",
    }


def _joined_record_text(record: dict) -> str:
    return " ".join(str(value) for value in _walk_values(record)).lower()


def _walk_values(value):
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_values(child)
    else:
        yield value


def _csv_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8", newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))
