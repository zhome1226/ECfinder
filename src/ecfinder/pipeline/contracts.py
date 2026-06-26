"""File contracts and strict readers for the clean PFAS pipeline."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


PIPELINE_VERSION = "stage2_2b_v1"

CLEAN_JSONL_FILES = [
    "data/clean/pfas_natural_transformation_records_v1.jsonl",
    "data/clean/pfas_natural_transformation_sources_v1.jsonl",
    "data/clean/pfas_natural_transformation_rejected_v1.jsonl",
    "data/clean/pfas_natural_transformation_manual_review_v1.jsonl",
    "data/clean/pfas_auxiliary_engineered_biological_v1.jsonl",
    "data/clean/manual_review_queue.jsonl",
    "data/clean/task_queue.jsonl",
    "data/clean/error_queue.jsonl",
]

REVIEW_STATUS_VALUES = {
    "validated_high_confidence",
    "validated_medium_confidence",
    "validated_low_confidence",
}

EVIDENCE_TIER_VALUES = {
    "confirmed_product",
    "probable_product",
    "tentative_product",
}

SOURCE_TYPE_VALUES = {
    "primary_study",
    "primary_evidence",
}

MAIN_DATABASE_REL = "data/clean/pfas_natural_transformation_records_v1.jsonl"
SOURCES_REL = "data/clean/pfas_natural_transformation_sources_v1.jsonl"
CSV_REL = "data/clean/pfas_natural_transformation_records_v1.csv"

FORBIDDEN_PATTERNS = {
    "activated sludge": re.compile(r"activated[-_\s]+sludge", re.IGNORECASE),
    "wastewater treatment": re.compile(r"wastewater[-_\s]+treatment", re.IGNORECASE),
    "WWTP": re.compile(r"\bWWTP\b", re.IGNORECASE),
    "bioreactor": re.compile(r"\bbioreactor\b", re.IGNORECASE),
    "engineered biological treatment": re.compile(r"engineered[-_\s]+biological[-_\s]+treatment", re.IGNORECASE),
    "engineered treatment": re.compile(r"engineered[-_\s]+treatment", re.IGNORECASE),
    "AOP": re.compile(r"\bAOP\b|advanced[-_\s]+oxidation", re.IGNORECASE),
    "electrochemical": re.compile(r"\belectrochemical\b", re.IGNORECASE),
    "plasma": re.compile(r"\bplasma\b", re.IGNORECASE),
    "ozonation": re.compile(r"\bozonation\b", re.IGNORECASE),
    "photocatalysis": re.compile(r"\bphotocatalysis\b|\bphotocatalytic\b", re.IGNORECASE),
    "hydrothermal": re.compile(r"\bhydrothermal\b", re.IGNORECASE),
    "incineration": re.compile(r"\bincineration\b|\bincinerat", re.IGNORECASE),
}


@dataclass
class JsonlReadResult:
    path: Path
    records: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def normalize_text_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: normalize_text_value(child) for key, child in value.items()}
    if isinstance(value, list):
        return [normalize_text_value(child) for child in value]
    if isinstance(value, str):
        return value.replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n")
    return value


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(normalize_text_value(record), ensure_ascii=False, sort_keys=True) + "\n")


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(normalize_text_value(record), ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl_strict(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        raise ValueError(f"Missing JSONL file: {path}")
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            if re.search(r"}\s*{", line):
                raise ValueError(f"{path}:{line_no} contains multiple JSON objects on one line")
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no} invalid JSONL: {exc}") from exc
            if not isinstance(obj, dict):
                raise ValueError(f"{path}:{line_no} JSONL line is not an object")
            if not obj:
                raise ValueError(f"{path}:{line_no} JSONL line is an empty object")
            records.append(obj)
    return records


def read_jsonl_result(path: Path) -> JsonlReadResult:
    try:
        return JsonlReadResult(path=path, records=read_jsonl_strict(path))
    except ValueError as exc:
        return JsonlReadResult(path=path, errors=[str(exc)])


def read_csv_rows(path: Path) -> tuple[list[dict[str, str]], list[str] | None]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        return rows, reader.fieldnames


def get_nested(record: dict[str, Any], dotted: str) -> Any:
    value: Any = record
    for part in dotted.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def has_value(record: dict[str, Any], dotted: str) -> bool:
    value = get_nested(record, dotted)
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return bool(value)


def evidence_quote(record: dict[str, Any]) -> str:
    direct = record.get("evidence_quote")
    if isinstance(direct, str) and direct.strip():
        return direct
    evidence = record.get("evidence") or {}
    quote = evidence.get("evidence_quote") if isinstance(evidence, dict) else None
    return quote if isinstance(quote, str) else ""


def transformation_has_description(record: dict[str, Any]) -> bool:
    transformation = record.get("transformation") or {}
    return bool(
        str(transformation.get("reaction_type") or "").strip()
        or str(transformation.get("reaction_description") or "").strip()
        or str(record.get("reaction_description") or "").strip()
    )


def record_text_for_boundary(record: dict[str, Any]) -> str:
    ignored_review_keys = {"review_reason", "reason", "exclusion_reason"}

    def walk(value: Any, parent_key: str = ""):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in ignored_review_keys:
                    continue
                yield from walk(child, key)
        elif isinstance(value, list):
            for child in value:
                yield from walk(child, parent_key)
        else:
            yield str(value)

    return " ".join(walk(record))


def clean_database_counts(root: Path) -> dict[str, Any]:
    records = read_jsonl_strict(root / MAIN_DATABASE_REL)
    sources = read_jsonl_strict(root / SOURCES_REL)
    csv_rows, csv_header = read_csv_rows(root / CSV_REL)
    manual_queue = read_jsonl_strict(root / "data/clean/manual_review_queue.jsonl")
    error_queue = read_jsonl_strict(root / "data/clean/error_queue.jsonl")
    task_queue = read_jsonl_strict(root / "data/clean/task_queue.jsonl")
    return {
        "record_count": len(records),
        "csv_data_rows": len(csv_rows),
        "csv_has_header": bool(csv_header),
        "source_count": len(sources),
        "confirmed_product_count": sum(
            1 for record in records if (record.get("review") or {}).get("evidence_tier") == "confirmed_product"
        ),
        "probable_product_count": sum(
            1 for record in records if (record.get("review") or {}).get("evidence_tier") == "probable_product"
        ),
        "tentative_product_count": sum(
            1 for record in records if (record.get("review") or {}).get("evidence_tier") == "tentative_product"
        ),
        "requires_manual_confirmation_count": sum(
            1 for record in records if (record.get("review") or {}).get("requires_manual_confirmation") is True
        ),
        "manual_review_queue_count": len(manual_queue),
        "error_queue_count": len(error_queue),
        "task_queue_count": len(task_queue),
    }
