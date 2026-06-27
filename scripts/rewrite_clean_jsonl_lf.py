"""Rewrite the clean natural-transformation JSONL/CSV with LF serialization."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import build_clean_database_v1 as clean_builder


ROOT = Path(__file__).resolve().parents[1]
CLEAN_DIR = ROOT / "data" / "clean"
RECORDS_JSONL = CLEAN_DIR / "pfas_natural_transformation_records_v1.jsonl"
RECORDS_CSV = CLEAN_DIR / "pfas_natural_transformation_records_v1.csv"
SOURCES_JSONL = CLEAN_DIR / "pfas_natural_transformation_sources_v1.jsonl"
STAGE2_2_VALIDATED = CLEAN_DIR / "stage2_2_validated_records.jsonl"


def normalize_strings(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: normalize_strings(child) for key, child in value.items()}
    if isinstance(value, list):
        return [normalize_strings(child) for child in value]
    if isinstance(value, str):
        return value.replace("\r\n", "\\n").replace("\r", "\\n").replace("\n", "\\n")
    return value


def read_jsonl_strict(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    text = path.read_text(encoding="utf-8")
    for line_no, line in enumerate(text.split("\n"), start=1):
        if not line.strip():
            continue
        if "} {" in line:
            raise ValueError(f"{path}:{line_no} contains multiple JSON objects on one line")
        obj = json.loads(line)
        if not isinstance(obj, dict):
            raise ValueError(f"{path}:{line_no} is not a JSON object")
        records.append(obj)
    return records


def merge_records() -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for record in clean_builder.seed_records():
        merged[record["record_id"]] = record
    for record in read_jsonl_strict(STAGE2_2_VALIDATED):
        merged[record["record_id"]] = record
    if len(merged) != 9:
        raise ValueError(f"Expected 9 clean records after rebuild, found {len(merged)}")
    return [normalize_strings(merged[record_id]) for record_id in sorted(merged)]


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=clean_builder.CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        for record in records:
            writer.writerow(normalize_strings(clean_builder.csv_row(record)))


def main() -> int:
    records = merge_records()
    write_jsonl(RECORDS_JSONL, records)
    write_csv(RECORDS_CSV, records)
    write_jsonl(SOURCES_JSONL, clean_builder.source_records(records))
    print(f"clean_records_written {len(records)}")
    print(f"clean_jsonl {RECORDS_JSONL.relative_to(ROOT).as_posix()}")
    print(f"clean_csv {RECORDS_CSV.relative_to(ROOT).as_posix()}")
    print(f"clean_sources {SOURCES_JSONL.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
