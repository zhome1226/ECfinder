"""Strict validation for the clean PFAS natural-transformation database."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLEAN_DIR = ROOT / "data" / "clean"
RECORDS_JSONL = CLEAN_DIR / "pfas_natural_transformation_records_v1.jsonl"
RECORDS_CSV = CLEAN_DIR / "pfas_natural_transformation_records_v1.csv"
SOURCES_JSONL = CLEAN_DIR / "pfas_natural_transformation_sources_v1.jsonl"
VALIDATION_REPORT = ROOT / "reports" / "clean_database_v1_validation.md"

FORBIDDEN = {
    "activated_sludge_in_clean_main": re.compile(r"activated[- ]sludge", re.I),
    "wastewater_treatment_in_clean_main": re.compile(r"wastewater[- ]treatment", re.I),
    "wwtp_in_clean_main": re.compile(r"\bWWTP\b", re.I),
}


def read_jsonl_strict(path: Path) -> list[dict]:
    records: list[dict] = []
    if not path.exists():
        raise ValueError(f"Missing JSONL file: {path}")
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            if re.search(r"}\s*{", line):
                raise ValueError(f"{path}:{line_no} has multiple JSON objects on one line")
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no} invalid JSONL: {exc}") from exc
            if not isinstance(obj, dict):
                raise ValueError(f"{path}:{line_no} JSONL line is not an object")
            records.append(obj)
    return records


def validate_clean_database(root: Path = ROOT, write_report: bool = True) -> dict:
    records_path = root / "data" / "clean" / "pfas_natural_transformation_records_v1.jsonl"
    csv_path = root / "data" / "clean" / "pfas_natural_transformation_records_v1.csv"
    sources_path = root / "data" / "clean" / "pfas_natural_transformation_sources_v1.jsonl"
    report_path = root / "reports" / "clean_database_v1_validation.md"

    errors: list[str] = []
    try:
        records = read_jsonl_strict(records_path)
        jsonl_parse_ok = True
    except ValueError as exc:
        records = []
        jsonl_parse_ok = False
        errors.append(str(exc))

    try:
        sources = read_jsonl_strict(sources_path)
    except ValueError as exc:
        sources = []
        errors.append(str(exc))

    try:
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            csv_rows = list(reader)
            csv_parse_ok = bool(reader.fieldnames)
    except OSError as exc:
        csv_rows = []
        csv_parse_ok = False
        errors.append(str(exc))

    text = "\n".join(json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records)
    forbidden_flags = {name: bool(pattern.search(text)) for name, pattern in FORBIDDEN.items()}
    record_ids = [record.get("record_id") for record in records]
    duplicate_record_count = len(record_ids) - len(set(record_ids))
    missing_parent_count = sum(1 for record in records if not (record.get("parent_compound") or {}).get("name"))
    missing_product_count = sum(1 for record in records if not (record.get("product_compound") or {}).get("name"))
    missing_evidence_quote_count = sum(1 for record in records if not record.get("evidence_quote"))
    confirmed_product_count = sum(
        1 for record in records if (record.get("review") or {}).get("evidence_tier") == "confirmed_product"
    )
    probable_product_count = sum(
        1 for record in records if (record.get("review") or {}).get("evidence_tier") == "probable_product"
    )
    tentative_product_count = sum(
        1 for record in records if (record.get("review") or {}).get("evidence_tier") == "tentative_product"
    )
    requires_manual_confirmation_count = sum(
        1 for record in records if (record.get("review") or {}).get("requires_manual_confirmation") is True
    )

    if len(csv_rows) != len(records):
        errors.append("CSV data row count does not match clean JSONL record count")
    if duplicate_record_count:
        errors.append("Duplicate record_id values found")
    if missing_parent_count:
        errors.append("Records missing parent_compound.name")
    if missing_product_count:
        errors.append("Records missing product_compound.name")
    if missing_evidence_quote_count:
        errors.append("Records missing evidence_quote")
    for name, flag in forbidden_flags.items():
        if flag:
            errors.append(f"Forbidden engineered-treatment term found: {name}")

    validation_ok = jsonl_parse_ok and csv_parse_ok and not errors
    result = {
        "jsonl_parse_ok": jsonl_parse_ok,
        "csv_parse_ok": csv_parse_ok,
        "record_count": len(records),
        "csv_data_rows": len(csv_rows),
        "source_count": len(sources),
        "confirmed_product_count": confirmed_product_count,
        "probable_product_count": probable_product_count,
        "tentative_product_count": tentative_product_count,
        "requires_manual_confirmation_count": requires_manual_confirmation_count,
        "activated_sludge_in_clean_main": forbidden_flags["activated_sludge_in_clean_main"],
        "wastewater_treatment_in_clean_main": forbidden_flags["wastewater_treatment_in_clean_main"],
        "wwtp_in_clean_main": forbidden_flags["wwtp_in_clean_main"],
        "missing_parent_count": missing_parent_count,
        "missing_product_count": missing_product_count,
        "missing_evidence_quote_count": missing_evidence_quote_count,
        "duplicate_record_count": duplicate_record_count,
        "validation_ok": validation_ok,
        "errors": errors,
    }
    if write_report:
        write_validation_report(report_path, result)
    return result


def write_validation_report(path: Path, result: dict) -> None:
    lines = [
        "# Clean Database v1 Validation",
        "",
        f"- jsonl_parse_ok = {str(result['jsonl_parse_ok']).lower()}",
        f"- csv_parse_ok = {str(result['csv_parse_ok']).lower()}",
        f"- record_count = {result['record_count']}",
        f"- csv_data_rows = {result['csv_data_rows']}",
        f"- source_count = {result['source_count']}",
        f"- confirmed_product_count = {result['confirmed_product_count']}",
        f"- probable_product_count = {result['probable_product_count']}",
        f"- tentative_product_count = {result['tentative_product_count']}",
        f"- requires_manual_confirmation_count = {result['requires_manual_confirmation_count']}",
        f"- activated_sludge_in_clean_main = {str(result['activated_sludge_in_clean_main']).lower()}",
        f"- wastewater_treatment_in_clean_main = {str(result['wastewater_treatment_in_clean_main']).lower()}",
        f"- wwtp_in_clean_main = {str(result['wwtp_in_clean_main']).lower()}",
        f"- missing_parent_count = {result['missing_parent_count']}",
        f"- missing_product_count = {result['missing_product_count']}",
        f"- missing_evidence_quote_count = {result['missing_evidence_quote_count']}",
        f"- duplicate_record_count = {result['duplicate_record_count']}",
        f"- validation_ok = {str(result['validation_ok']).lower()}",
        "",
        "## Errors",
        "",
        *(f"- {error}" for error in result["errors"]),
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    result = validate_clean_database()
    for key, value in result.items():
        if key != "errors":
            print(f"{key}: {value}")
    if result["errors"]:
        print("errors:")
        for error in result["errors"]:
            print(f"- {error}")
    return 0 if result["validation_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
