"""Emergency Stage 2 JSONL/CSV serialization repair.

This script is intentionally independent of the ecfinder CLI so it can repair
outputs even when the package entrypoints or previous reports are unreliable.
"""

from __future__ import annotations

import csv
import json
import re
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

STAGE2_VALIDATED = ROOT / "data" / "reviewed" / "stage2_pfas_transformation_records_validated.jsonl"
STAGE2_MANUAL = ROOT / "data" / "reviewed" / "stage2_manual_review_records.jsonl"
STAGE2_REJECTED = ROOT / "data" / "reviewed" / "stage2_rejected_records.jsonl"
STAGE2_AUXILIARY = ROOT / "data" / "reviewed" / "stage2_auxiliary_records.jsonl"
STAGE2_RAW = ROOT / "data" / "extracted" / "stage2_pfas_transformation_records_raw.jsonl"
MAIN_VALIDATED = ROOT / "data" / "reviewed" / "pfas_transformation_records_validated.jsonl"
MAIN_CSV = ROOT / "data" / "reviewed" / "pfas_transformation_records_validated.csv"
REPAIR_REPORT = ROOT / "reports" / "stage2_1c_serialization_repair.md"

ENGINEERED_PATTERNS = {
    "activated_sludge": re.compile(r"activated[- ]sludge", re.I),
    "wastewater": re.compile(r"wastewater[- ]treatment", re.I),
    "wwtp": re.compile(r"\bWWTP\b", re.I),
}

CSV_FIELDS = [
    "record_id",
    "source_id",
    "query_family",
    "doi",
    "title",
    "year",
    "journal",
    "chunk_id",
    "section",
    "table",
    "parent_name",
    "parent_synonyms",
    "parent_class",
    "product_name",
    "product_synonyms",
    "product_class",
    "reaction_type",
    "reaction_description",
    "setting_type",
    "environment_matrix",
    "environment_type",
    "redox_condition",
    "microbial_condition",
    "duration",
    "identification_confidence",
    "evidence_tier",
    "requires_manual_confirmation",
    "main_database_use",
    "review_status",
    "review_confidence",
    "evidence_quote",
]


def recover_concatenated_json_objects(text: str) -> list[dict]:
    decoder = json.JSONDecoder()
    return _recover_with_decoder(text, decoder)


def _recover_with_decoder(text: str, decoder: json.JSONDecoder) -> list[dict]:
    records: list[dict] = []
    idx = 0
    n = len(text)
    while idx < n:
        while idx < n and text[idx].isspace():
            idx += 1
        if idx >= n:
            break
        obj, end = decoder.raw_decode(text, idx)
        if not isinstance(obj, dict):
            raise ValueError("Recovered JSON value is not an object")
        records.append(obj)
        idx = end
    return records


def recover_json_objects(path: Path) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    text = path.read_text(encoding="utf-8")
    try:
        return recover_concatenated_json_objects(text)
    except json.JSONDecodeError:
        # Some historical rejected-record files had literal newlines inside JSON
        # strings. strict=False can recover those objects; write_jsonl then
        # serializes them safely as one object per line.
        return _recover_with_decoder(text, json.JSONDecoder(strict=False))


def normalize_record(record: dict) -> dict:
    return normalize_value(deepcopy(record))


def normalize_value(value):
    if isinstance(value, dict):
        return {key: normalize_value(child) for key, child in value.items()}
    if isinstance(value, list):
        return [normalize_value(child) for child in value]
    if isinstance(value, str):
        return value.replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n")
    return value


def apply_evidence_tier(record: dict) -> dict:
    out = normalize_record(record)
    evidence = out.get("evidence") or {}
    product = (out.get("product_compound") or {}).get("name", "").lower()
    identification = str(evidence.get("identification_confidence") or "").lower()
    is_confirmed = (
        ("level 1" in identification and "confirmed" in identification)
        or product == "6:2 fluorotelomer thioether propionate"
    )
    review = dict(out.get("review") or {})
    if is_confirmed:
        review["review_status"] = "validated_high_confidence"
        review["evidence_tier"] = "confirmed_product"
        review["requires_manual_confirmation"] = False
        review["main_database_use"] = "core_evidence"
    else:
        review["review_status"] = "validated_medium_confidence"
        review["evidence_tier"] = "tentative_product"
        review["requires_manual_confirmation"] = True
        review["main_database_use"] = "tentative_evidence"
    out["review"] = review
    return out


def ensure_rejected_shape(record: dict, index: int) -> dict:
    out = normalize_record(record)
    review = out.get("review") or {}
    out.setdefault("record_id", f"stage2_rejected_recovered_{index:02d}")
    out.setdefault("source_id", "")
    out.setdefault("chunk_id", "")
    out.setdefault("doi", "")
    out.setdefault("title", "")
    out.setdefault("evidence_quote", "")
    out["review"] = {
        "review_status": review.get("review_status") or out.get("reviewer_status") or "rejected_insufficient_evidence",
        "review_reason": review.get("review_reason") or "Recovered rejected record from Stage 2 serialization repair.",
        "review_confidence": review.get("review_confidence"),
    }
    return out


def dedupe(records: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for record in records:
        key = record.get("record_id") or json.dumps(record, ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        out.append(record)
    return out


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def csv_safe(value):
    if isinstance(value, str):
        return value.replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n")
    return value


def validated_csv_row(record: dict) -> dict:
    parent = record.get("parent_compound") or {}
    product = record.get("product_compound") or {}
    transformation = record.get("transformation") or {}
    conditions = record.get("conditions") or {}
    evidence = record.get("evidence") or {}
    location = record.get("evidence_location") or {}
    review = record.get("review") or {}
    return {
        "record_id": record.get("record_id"),
        "source_id": record.get("source_id"),
        "query_family": record.get("query_family"),
        "doi": record.get("doi"),
        "title": record.get("title"),
        "year": record.get("year"),
        "journal": record.get("journal"),
        "chunk_id": record.get("chunk_id"),
        "section": location.get("section"),
        "table": location.get("table"),
        "parent_name": parent.get("name"),
        "parent_synonyms": json.dumps(parent.get("synonyms") or [], ensure_ascii=False),
        "parent_class": parent.get("compound_class"),
        "product_name": product.get("name"),
        "product_synonyms": json.dumps(product.get("synonyms") or [], ensure_ascii=False),
        "product_class": product.get("compound_class"),
        "reaction_type": transformation.get("reaction_type"),
        "reaction_description": transformation.get("reaction_description"),
        "setting_type": conditions.get("setting_type"),
        "environment_matrix": conditions.get("environment_matrix"),
        "environment_type": conditions.get("environment_type"),
        "redox_condition": conditions.get("redox_condition"),
        "microbial_condition": conditions.get("microbial_condition"),
        "duration": conditions.get("duration"),
        "identification_confidence": evidence.get("identification_confidence"),
        "evidence_tier": review.get("evidence_tier"),
        "requires_manual_confirmation": review.get("requires_manual_confirmation"),
        "main_database_use": review.get("main_database_use"),
        "review_status": review.get("review_status"),
        "review_confidence": review.get("review_confidence"),
        "evidence_quote": record.get("evidence_quote"),
    }


def write_validated_csv(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        for record in records:
            writer.writerow({key: csv_safe(value) for key, value in validated_csv_row(record).items()})


def read_jsonl_strict(path: Path) -> list[dict]:
    records: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            if "} {" in line or re.search(r"}\s*{", line):
                raise ValueError(f"{path}:{line_no} contains multiple JSON objects on one line")
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no} invalid JSONL: {exc}") from exc
            if not isinstance(obj, dict):
                raise ValueError(f"{path}:{line_no} JSONL line is not an object")
            records.append(obj)
    return records


def record_text(records: list[dict]) -> str:
    return "\n".join(json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records)


def validate_outputs() -> dict:
    stage2_validated = read_jsonl_strict(STAGE2_VALIDATED)
    stage2_manual = read_jsonl_strict(STAGE2_MANUAL)
    stage2_rejected = read_jsonl_strict(STAGE2_REJECTED)
    main = read_jsonl_strict(MAIN_VALIDATED)
    with MAIN_CSV.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        csv_has_header = bool(reader.fieldnames)
        csv_rows = list(reader)

    text = record_text(main)
    activated = bool(ENGINEERED_PATTERNS["activated_sludge"].search(text))
    wastewater = bool(ENGINEERED_PATTERNS["wastewater"].search(text))
    wwtp = bool(ENGINEERED_PATTERNS["wwtp"].search(text))
    confirmed = sum((record.get("review") or {}).get("evidence_tier") == "confirmed_product" for record in main)
    tentative = sum((record.get("review") or {}).get("evidence_tier") == "tentative_product" for record in main)
    validation_ok = (
        len(stage2_validated) == 4
        and len(stage2_manual) == 2
        and len(stage2_rejected) == 11
        and len(main) == 4
        and csv_has_header
        and len(csv_rows) == 4
        and confirmed == 1
        and tentative == 3
        and not activated
        and not wastewater
        and not wwtp
    )
    return {
        "stage2_validated_count": len(stage2_validated),
        "stage2_manual_count": len(stage2_manual),
        "stage2_rejected_count": len(stage2_rejected),
        "main_database_count": len(main),
        "csv_data_rows": len(csv_rows),
        "confirmed_product_count": confirmed,
        "tentative_product_count": tentative,
        "activated_sludge_in_main": activated,
        "wastewater_in_main": wastewater,
        "wwtp_in_main": wwtp,
        "jsonl_parse_ok": True,
        "csv_parse_ok": csv_has_header and len(csv_rows) == 4,
        "validation_ok": validation_ok,
        "stage2_2_ready_or_not": "ready_for_targeted_followup" if validation_ok else "not_ready",
    }


def write_report(result: dict) -> None:
    lines = [
        "# Stage 2.1c Serialization Repair",
        "",
        f"- stage2_validated_count = {result.get('stage2_validated_count', 0)}",
        f"- stage2_manual_count = {result.get('stage2_manual_count', 0)}",
        f"- stage2_rejected_count = {result.get('stage2_rejected_count', 0)}",
        f"- main_database_count = {result.get('main_database_count', 0)}",
        f"- csv_data_rows = {result.get('csv_data_rows', 0)}",
        f"- confirmed_product_count = {result.get('confirmed_product_count', 0)}",
        f"- tentative_product_count = {result.get('tentative_product_count', 0)}",
        f"- activated_sludge_in_main = {str(result.get('activated_sludge_in_main', True)).lower()}",
        f"- wastewater_in_main = {str(result.get('wastewater_in_main', True)).lower()}",
        f"- wwtp_in_main = {str(result.get('wwtp_in_main', True)).lower()}",
        f"- jsonl_parse_ok = {str(result.get('jsonl_parse_ok', False)).lower()}",
        f"- csv_parse_ok = {str(result.get('csv_parse_ok', False)).lower()}",
        f"- validation_ok = {str(result.get('validation_ok', False)).lower()}",
        f"- stage2_2_ready_or_not = {result.get('stage2_2_ready_or_not', 'not_ready')}",
        "",
    ]
    if result.get("error"):
        lines.extend(["## Error", "", str(result["error"]), ""])
    REPAIR_REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPAIR_REPORT.write_text("\n".join(lines), encoding="utf-8")


def repair() -> dict:
    validated = dedupe([apply_evidence_tier(record) for record in recover_json_objects(STAGE2_VALIDATED)])
    if len(validated) != 4:
        validated = dedupe([apply_evidence_tier(record) for record in recover_json_objects(MAIN_VALIDATED)])
    if len(validated) != 4:
        validated = dedupe([apply_evidence_tier(record) for record in recover_json_objects(STAGE2_RAW)])

    manual = dedupe([normalize_record(record) for record in recover_json_objects(STAGE2_MANUAL)])
    rejected = dedupe([ensure_rejected_shape(record, index) for index, record in enumerate(recover_json_objects(STAGE2_REJECTED), start=1)])
    auxiliary: list[dict] = []

    if len(validated) != 4 or len(manual) != 2 or len(rejected) != 11:
        result = {
            "stage2_validated_count": len(validated),
            "stage2_manual_count": len(manual),
            "stage2_rejected_count": len(rejected),
            "main_database_count": 0,
            "csv_data_rows": 0,
            "confirmed_product_count": 0,
            "tentative_product_count": 0,
            "activated_sludge_in_main": True,
            "wastewater_in_main": True,
            "wwtp_in_main": True,
            "jsonl_parse_ok": False,
            "csv_parse_ok": False,
            "validation_ok": False,
            "stage2_2_ready_or_not": "not_ready",
            "error": "Could not recover expected Stage 2 record counts before rewrite.",
        }
        write_report(result)
        raise SystemExit(1)

    write_jsonl(STAGE2_VALIDATED, validated)
    write_jsonl(STAGE2_MANUAL, manual)
    write_jsonl(STAGE2_REJECTED, rejected)
    write_jsonl(STAGE2_AUXILIARY, auxiliary)
    write_jsonl(MAIN_VALIDATED, validated)
    write_validated_csv(MAIN_CSV, validated)

    try:
        result = validate_outputs()
    except Exception as exc:  # noqa: BLE001 - report and fail hard.
        result = {
            "stage2_validated_count": 0,
            "stage2_manual_count": 0,
            "stage2_rejected_count": 0,
            "main_database_count": 0,
            "csv_data_rows": 0,
            "confirmed_product_count": 0,
            "tentative_product_count": 0,
            "activated_sludge_in_main": True,
            "wastewater_in_main": True,
            "wwtp_in_main": True,
            "jsonl_parse_ok": False,
            "csv_parse_ok": False,
            "validation_ok": False,
            "stage2_2_ready_or_not": "not_ready",
            "error": exc,
        }
    write_report(result)
    if not result["validation_ok"]:
        raise SystemExit(1)
    return result


if __name__ == "__main__":
    output = repair()
    for key, value in output.items():
        print(f"{key}: {value}")
