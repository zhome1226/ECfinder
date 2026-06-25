"""Validate reviewed ECfinder outputs."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from ecfinder.review.export_validated import ENGINEERED_TERMS, NATURAL_ALLOWED_SETTING_TYPES


REVIEWED_JSONL_FILES = (
    "data/reviewed/pfas_transformation_records_validated.jsonl",
    "data/reviewed/auxiliary_engineered_biological_records.jsonl",
    "data/reviewed/manual_review_records.jsonl",
    "data/reviewed/rejected_records.jsonl",
    "data/reviewed/reextraction_attempts.jsonl",
)

STAGE2_JSONL_FILES = (
    "data/reviewed/stage2_pfas_transformation_records_validated.jsonl",
    "data/reviewed/stage2_manual_review_records.jsonl",
    "data/reviewed/stage2_rejected_records.jsonl",
    "data/reviewed/stage2_auxiliary_records.jsonl",
    "data/extracted/stage2_pfas_transformation_records_raw.jsonl",
)


def validate_outputs(root: str | Path) -> dict:
    repo_root = Path(root)
    validated_path = repo_root / "data" / "reviewed" / "pfas_transformation_records_validated.jsonl"
    validated_csv = repo_root / "data" / "reviewed" / "pfas_transformation_records_validated.csv"
    auxiliary_path = repo_root / "data" / "reviewed" / "auxiliary_engineered_biological_records.jsonl"
    auxiliary_csv = repo_root / "data" / "reviewed" / "auxiliary_engineered_biological_records.csv"

    jsonl_records: dict[str, list[dict]] = {}
    parse_errors: list[str] = []
    for rel in REVIEWED_JSONL_FILES:
        records, file_errors = _read_jsonl_checked(repo_root / rel)
        jsonl_records[rel] = records
        parse_errors.extend(file_errors)

    validated = jsonl_records["data/reviewed/pfas_transformation_records_validated.jsonl"]
    auxiliary = jsonl_records["data/reviewed/auxiliary_engineered_biological_records.jsonl"]
    manual = jsonl_records["data/reviewed/manual_review_records.jsonl"]
    rejected = jsonl_records["data/reviewed/rejected_records.jsonl"]
    reextract = jsonl_records["data/reviewed/reextraction_attempts.jsonl"]
    validated_csv_count = _csv_count(validated_csv)
    auxiliary_csv_count = _csv_count(auxiliary_csv)
    errors: list[str] = []
    errors.extend(parse_errors)
    validated_text = "\n".join(_joined_record_text(record) for record in validated)
    validated_contains_activated_sludge = "activated sludge" in validated_text or "activated-sludge" in validated_text
    validated_contains_wastewater_treatment = (
        "wastewater treatment" in validated_text
        or "wastewater-treatment" in validated_text
        or "wwtp" in validated_text
    )

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

    for index, record in enumerate(auxiliary, start=1):
        review = record.get("review") or {}
        if review.get("review_status") != "auxiliary_engineered_biological_evidence":
            errors.append(f"auxiliary row {index} has invalid review.review_status")
        for field in ["reason_not_in_main_database", "potential_use", "source_id", "chunk_id", "evidence_quote"]:
            if not record.get(field):
                errors.append(f"auxiliary row {index} missing {field}")
        if not (record.get("parent_compound") or {}).get("name"):
            errors.append(f"auxiliary row {index} missing parent_compound.name")
        if not (record.get("product_compound") or {}).get("name"):
            errors.append(f"auxiliary row {index} missing product_compound.name")

    if validated_csv_count != len(validated):
        errors.append("validated CSV row count does not match JSONL")
    if auxiliary_csv_count != len(auxiliary):
        errors.append("auxiliary CSV row count does not match JSONL")

    if not any(any(term in _joined_record_text(record) for term in ENGINEERED_TERMS) for record in auxiliary) and auxiliary:
        errors.append("auxiliary file has records but none contain engineered biological context")
    if validated_contains_activated_sludge:
        errors.append("validated JSONL contains activated sludge")
    if validated_contains_wastewater_treatment:
        errors.append("validated JSONL contains wastewater treatment or WWTP")

    csv_row_count_ok = validated_csv_count == len(validated) and auxiliary_csv_count == len(auxiliary)
    jsonl_parse_ok = not parse_errors

    return {
        "validated_count": len(validated),
        "validated_jsonl_count": len(validated),
        "validated_csv_data_row_count": validated_csv_count,
        "auxiliary_count": len(auxiliary),
        "auxiliary_jsonl_count": len(auxiliary),
        "auxiliary_csv_data_row_count": auxiliary_csv_count,
        "manual_review_count": len(manual),
        "rejected_count": len(rejected),
        "reextraction_attempt_count": len(reextract),
        "validated_contains_activated_sludge": validated_contains_activated_sludge,
        "validated_contains_wastewater_treatment": validated_contains_wastewater_treatment,
        "jsonl_parse_ok": jsonl_parse_ok,
        "csv_row_count_ok": csv_row_count_ok,
        "errors": errors,
        "ok": not errors,
        "validation_ok": not errors,
        "zero_validated_reason": "No records met natural-environment criteria." if not validated else "",
        "stage2_ready_or_not": "ready_for_targeted_stage2_search" if not errors else "not_ready_fix_outputs_first",
    }


def validate_stage2_outputs(root: str | Path) -> dict:
    repo_root = Path(root)
    jsonl_records: dict[str, list[dict]] = {}
    parse_errors: list[str] = []
    for rel in STAGE2_JSONL_FILES:
        records, file_errors = _read_jsonl_checked(repo_root / rel)
        jsonl_records[rel] = records
        parse_errors.extend(file_errors)

    stage2_validated = jsonl_records["data/reviewed/stage2_pfas_transformation_records_validated.jsonl"]
    stage2_manual = jsonl_records["data/reviewed/stage2_manual_review_records.jsonl"]
    stage2_rejected = jsonl_records["data/reviewed/stage2_rejected_records.jsonl"]
    stage2_auxiliary = jsonl_records["data/reviewed/stage2_auxiliary_records.jsonl"]
    stage2_raw = jsonl_records["data/extracted/stage2_pfas_transformation_records_raw.jsonl"]
    main_validated, main_parse_errors = _read_jsonl_checked(
        repo_root / "data" / "reviewed" / "pfas_transformation_records_validated.jsonl"
    )
    parse_errors.extend(main_parse_errors)
    main_csv_rows = _csv_count(repo_root / "data" / "reviewed" / "pfas_transformation_records_validated.csv")

    errors: list[str] = []
    errors.extend(parse_errors)
    expected_counts = {
        "stage2 validated record count": (len(stage2_validated), 4),
        "stage2 manual review record count": (len(stage2_manual), 2),
        "stage2 rejected record count": (len(stage2_rejected), 11),
        "main database validated record count": (len(main_validated), 4),
        "main database CSV data row count": (main_csv_rows, 4),
    }
    for label, (actual, expected) in expected_counts.items():
        if actual != expected:
            errors.append(f"{label} expected {expected}, got {actual}")

    main_text = "\n".join(_joined_record_text(record) for record in main_validated)
    main_contains_activated_sludge = "activated sludge" in main_text or "activated-sludge" in main_text
    main_contains_wastewater_treatment = (
        "wastewater treatment" in main_text
        or "wastewater-treatment" in main_text
        or "wwtp" in main_text
    )
    if main_contains_activated_sludge:
        errors.append("main database contains activated sludge")
    if main_contains_wastewater_treatment:
        errors.append("main database contains wastewater treatment or WWTP")

    for index, record in enumerate(main_validated, start=1):
        text = _joined_record_text(record)
        for term in ENGINEERED_TERMS:
            if term in text:
                errors.append(f"main database row {index} contains excluded engineered term: {term}")
        for field in ["source_id", "chunk_id", "doi", "evidence_quote"]:
            if not record.get(field):
                errors.append(f"main database row {index} missing {field}")
        if not (record.get("parent_compound") or {}).get("name"):
            errors.append(f"main database row {index} missing parent_compound.name")
        if not (record.get("product_compound") or {}).get("name"):
            errors.append(f"main database row {index} missing product_compound.name")
        if not (record.get("conditions") or {}).get("setting_type"):
            errors.append(f"main database row {index} missing conditions.setting_type")

    confirmed = [
        record
        for record in main_validated
        if (record.get("review") or {}).get("evidence_tier") == "confirmed_product"
    ]
    tentative = [
        record
        for record in main_validated
        if (record.get("review") or {}).get("evidence_tier") == "tentative_product"
    ]
    if len(confirmed) != 1:
        errors.append(f"confirmed_product count expected 1, got {len(confirmed)}")
    if len(tentative) != 3:
        errors.append(f"tentative_product count expected 3, got {len(tentative)}")
    for record in tentative:
        review = record.get("review") or {}
        if review.get("requires_manual_confirmation") is not True:
            errors.append(f"tentative record {record.get('record_id')} missing requires_manual_confirmation=true")
        if review.get("main_database_use") != "tentative_evidence":
            errors.append(f"tentative record {record.get('record_id')} missing main_database_use=tentative_evidence")
    for record in confirmed:
        review = record.get("review") or {}
        if review.get("requires_manual_confirmation") is not False:
            errors.append(f"confirmed record {record.get('record_id')} should not require manual confirmation")
        if review.get("main_database_use") != "core_evidence":
            errors.append(f"confirmed record {record.get('record_id')} missing main_database_use=core_evidence")

    jsonl_parse_ok = not parse_errors
    main_database_merge_ok = len(main_validated) == 4 and main_csv_rows == 4 and not errors
    return {
        "stage2_validated_jsonl_count": len(stage2_validated),
        "stage2_manual_review_count": len(stage2_manual),
        "stage2_rejected_count": len(stage2_rejected),
        "stage2_auxiliary_count": len(stage2_auxiliary),
        "stage2_raw_count": len(stage2_raw),
        "main_database_validated_count": len(main_validated),
        "main_database_csv_rows": main_csv_rows,
        "jsonl_parse_ok": jsonl_parse_ok,
        "main_database_merge_ok": main_database_merge_ok,
        "activated_sludge_excluded_from_main": not main_contains_activated_sludge,
        "wastewater_treatment_excluded_from_main": not main_contains_wastewater_treatment,
        "confirmed_product_count": len(confirmed),
        "tentative_product_count": len(tentative),
        "errors": errors,
        "ok": not errors,
        "validation_ok": not errors,
        "stage2_2_ready_or_not": "ready_for_targeted_followup" if not errors else "not_ready_fix_stage2_outputs_first",
    }


def _read_jsonl_checked(path: Path) -> tuple[list[dict], list[str]]:
    records: list[dict] = []
    errors: list[str] = []
    if not path.exists():
        errors.append(f"missing JSONL file: {path}")
        return records, errors
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError as exc:
                errors.append(f"{path}:{line_number} invalid JSONL: {exc.msg}")
                continue
            if not isinstance(value, dict):
                errors.append(f"{path}:{line_number} JSONL line is not an object")
                continue
            records.append(value)
    return records, errors


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
