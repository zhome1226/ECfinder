"""Export natural-environment validated records and auxiliary evidence."""

from __future__ import annotations

import csv
import json
from copy import deepcopy
from pathlib import Path
from typing import Iterable

from ecfinder.utils.logging import read_jsonl, write_jsonl


ENGINEERED_TERMS = (
    "activated sludge",
    "activated-sludge",
    "wastewater treatment",
    "wastewater-treatment",
    "wwtp",
    "bioreactor",
    "engineered biological",
    "engineered biological treatment",
    "engineered treatment",
    "engineered wastewater",
    "sludge mixed liquor",
)

NATURAL_ALLOWED_SETTING_TYPES = {
    "field_natural_environment",
    "natural_attenuation_field_site",
    "environmental_microcosm_from_field_sample",
    "soil_microcosm",
    "sediment_microcosm",
    "groundwater_microcosm",
    "surface_water_microcosm",
    "wetland_microcosm",
    "marine_or_estuarine_microcosm",
    "AFFF_contaminated_groundwater_field_site",
    "contaminated_aquifer",
    "soil_microcosm_from_field_sample",
    "sediment_microcosm_from_field_sample",
    "groundwater_microcosm_from_field_sample",
    "surface_water_microcosm_from_field_sample",
    "wetland_microcosm_from_field_sample",
    "marine_or_estuarine_microcosm_from_field_sample",
    "atmospheric_or_soil_environmental_transformation",
}

AUX_REASON = (
    "Activated sludge is an engineered wastewater-treatment matrix and is not "
    "considered natural environmental transformation evidence."
)
AUX_USE = (
    "Useful as auxiliary evidence for precursor biotransformation mechanisms, "
    "but excluded from the natural-environment PFAS transformation database."
)
VALIDATED_STATUSES = {"validated_high_confidence", "validated_medium_confidence"}
REVIEW_ONLY_TERMS = (
    "review figure",
    "redrawn from",
    "adapted from",
    "reference list",
    "references section",
    "review-only",
)


def export_validated(root: str | Path) -> dict:
    repo_root = Path(root)
    codex_raw = list(read_jsonl(repo_root / "data" / "extracted" / "pfas_transformation_records_codex_raw.jsonl"))
    manual = list(read_jsonl(repo_root / "data" / "reviewed" / "manual_review_records.jsonl"))
    existing_rejected = list(read_jsonl(repo_root / "data" / "reviewed" / "rejected_records.jsonl"))

    natural_validated: list[dict] = []
    auxiliary: list[dict] = []
    rejected = list(existing_rejected)
    manual_out: list[dict] = []
    processed: set[str] = set()

    for record in [*codex_raw, *manual]:
        key = record.get("record_id") or json.dumps(record, sort_keys=True)
        if key in processed:
            continue
        processed.add(key)
        status = _record_status(record)
        if _should_export_auxiliary(record):
            auxiliary.append(_to_auxiliary(record))
        elif _is_engineered_biological(record):
            rejected.append(
                _to_rejection(
                    record,
                    "rejected_insufficient_evidence",
                    "Activated sludge or wastewater-treatment evidence is engineered biological evidence, and this record was not clear enough for auxiliary evidence.",
                )
            )
        elif status in VALIDATED_STATUSES and _is_natural_validated(record):
            natural_validated.append(record)
        elif status == "needs_manual_review" and _is_potential_natural_manual(record):
            manual_out.append(record)
        else:
            reject_status, reason = _rejection_for(record)
            rejected.append(_to_rejection(record, reject_status, reason))

    write_jsonl(repo_root / "data" / "reviewed" / "pfas_transformation_records_validated.jsonl", natural_validated)
    write_validated_csv(repo_root / "data" / "reviewed" / "pfas_transformation_records_validated.csv", natural_validated)
    write_jsonl(repo_root / "data" / "reviewed" / "auxiliary_engineered_biological_records.jsonl", auxiliary)
    write_auxiliary_csv(repo_root / "data" / "reviewed" / "auxiliary_engineered_biological_records.csv", auxiliary)
    write_jsonl(repo_root / "data" / "reviewed" / "manual_review_records.jsonl", manual_out)
    write_jsonl(repo_root / "data" / "reviewed" / "rejected_records.jsonl", _dedupe_rejections(rejected))

    return {
        "natural_validated": len(natural_validated),
        "auxiliary": len(auxiliary),
        "manual": len(manual_out),
        "rejected": len(_dedupe_rejections(rejected)),
    }


def merge_stage2_validated(root: str | Path) -> dict:
    """Normalize Stage 2 outputs and merge accepted records into the main database."""
    repo_root = Path(root)
    stage2_validated_path = repo_root / "data" / "reviewed" / "stage2_pfas_transformation_records_validated.jsonl"
    stage2_manual_path = repo_root / "data" / "reviewed" / "stage2_manual_review_records.jsonl"
    stage2_rejected_path = repo_root / "data" / "reviewed" / "stage2_rejected_records.jsonl"
    stage2_auxiliary_path = repo_root / "data" / "reviewed" / "stage2_auxiliary_records.jsonl"
    stage2_raw_path = repo_root / "data" / "extracted" / "stage2_pfas_transformation_records_raw.jsonl"

    stage2_validated = [_normalize_record(_with_stage2_quality_tier(record)) for record in _read_json_objects_loose(stage2_validated_path)]
    stage2_manual = [_normalize_record(record) for record in _read_json_objects_loose(stage2_manual_path)]
    stage2_rejected = [_normalize_record(record) for record in _read_json_objects_loose(stage2_rejected_path)]
    stage2_auxiliary = [_normalize_record(record) for record in _read_json_objects_loose(stage2_auxiliary_path)]
    stage2_raw = [_normalize_record(record) for record in _read_json_objects_loose(stage2_raw_path)]

    if not stage2_raw or {record.get("record_id") for record in stage2_raw} == {
        record.get("record_id") for record in stage2_validated
    }:
        stage2_raw = [deepcopy(record) for record in stage2_validated]
    else:
        tiered_by_id = {record.get("record_id"): record for record in stage2_validated}
        stage2_raw = [
            _normalize_record(_with_stage2_quality_tier(record)) if record.get("record_id") in tiered_by_id else _normalize_record(record)
            for record in stage2_raw
        ]

    natural_validated = _dedupe_records(stage2_validated)
    for index, record in enumerate(natural_validated, start=1):
        if _contains_engineered_terms(record):
            raise ValueError(f"Stage 2 validated record {index} contains excluded engineered-treatment context")
        if _record_status(record) not in VALIDATED_STATUSES or not _is_natural_validated(record):
            raise ValueError(f"Stage 2 validated record {index} does not satisfy natural-environment criteria")

    write_jsonl(stage2_validated_path, natural_validated)
    write_jsonl(stage2_manual_path, stage2_manual)
    write_jsonl(stage2_rejected_path, stage2_rejected)
    write_jsonl(stage2_auxiliary_path, stage2_auxiliary)
    write_jsonl(stage2_raw_path, stage2_raw)

    main_jsonl_path = repo_root / "data" / "reviewed" / "pfas_transformation_records_validated.jsonl"
    main_csv_path = repo_root / "data" / "reviewed" / "pfas_transformation_records_validated.csv"
    write_jsonl(main_jsonl_path, natural_validated)
    write_validated_csv(main_csv_path, natural_validated)
    write_validated_csv(
        repo_root / "data" / "reviewed" / "stage2_pfas_transformation_records_validated.csv",
        natural_validated,
    )

    return {
        "stage2_validated": len(natural_validated),
        "stage2_manual": len(stage2_manual),
        "stage2_rejected": len(stage2_rejected),
        "stage2_auxiliary": len(stage2_auxiliary),
        "main_validated": len(natural_validated),
        "confirmed_product_count": sum(
            1 for record in natural_validated if (record.get("review") or {}).get("evidence_tier") == "confirmed_product"
        ),
        "tentative_product_count": sum(
            1 for record in natural_validated if (record.get("review") or {}).get("evidence_tier") == "tentative_product"
        ),
    }


def _with_stage2_quality_tier(record: dict) -> dict:
    out = deepcopy(record)
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


def _normalize_record(record: dict) -> dict:
    return _normalize_value(deepcopy(record))


def _normalize_value(value):
    if isinstance(value, dict):
        return {key: _normalize_value(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_normalize_value(child) for child in value]
    if isinstance(value, str):
        return value.replace("\r\n", "\\n").replace("\r", "\\n").replace("\n", "\\n")
    return value


def _read_json_objects_loose(path: Path) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    text = path.read_text(encoding="utf-8")
    decoder = json.JSONDecoder()
    index = 0
    records: list[dict] = []
    while index < len(text):
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text):
            break
        value, end = decoder.raw_decode(text, index)
        if not isinstance(value, dict):
            raise ValueError(f"{path} contains a non-object JSON value")
        records.append(value)
        index = end
    return records


def _dedupe_records(records: Iterable[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for record in records:
        key = record.get("record_id") or json.dumps(record, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        out.append(record)
    return out


def _record_status(record: dict) -> str:
    review = record.get("review") or {}
    return review.get("review_status") or record.get("reviewer_status") or ""


def _condition_text(record: dict) -> str:
    conditions = record.get("conditions") or {}
    parts = [
        conditions.get("environment_matrix"),
        conditions.get("environment_type"),
        conditions.get("setting_type"),
        conditions.get("other_conditions"),
        record.get("evidence_quote"),
    ]
    return " ".join(str(part or "") for part in parts).lower()


def _is_engineered_biological(record: dict) -> bool:
    text = _condition_text(record)
    return any(term in text for term in ENGINEERED_TERMS)


def _contains_engineered_terms(record: dict) -> bool:
    text = _record_text(record)
    return any(term in text for term in ENGINEERED_TERMS)


def _should_export_auxiliary(record: dict) -> bool:
    return (
        _is_engineered_biological(record)
        and _record_status(record) in VALIDATED_STATUSES
        and _has_required_evidence_fields(record)
    )


def _is_natural_validated(record: dict) -> bool:
    conditions = record.get("conditions") or {}
    setting = conditions.get("setting_type")
    if setting not in NATURAL_ALLOWED_SETTING_TYPES:
        return False
    if _is_engineered_biological(record):
        return False
    return _has_required_evidence_fields(record)


def _has_required_evidence_fields(record: dict) -> bool:
    return bool(
        record.get("source_id")
        and record.get("chunk_id")
        and record.get("evidence_quote")
        and (record.get("parent_compound") or {}).get("name")
        and (record.get("product_compound") or {}).get("name")
    )


def _is_review_only(record: dict) -> bool:
    text = _condition_text(record)
    return any(term in text for term in REVIEW_ONLY_TERMS)


def _is_potential_natural_manual(record: dict) -> bool:
    conditions = record.get("conditions") or {}
    return (
        _record_status(record) == "needs_manual_review"
        and conditions.get("setting_type") in NATURAL_ALLOWED_SETTING_TYPES
        and not _is_engineered_biological(record)
        and not _is_review_only(record)
        and _has_required_evidence_fields(record)
    )


def _rejection_for(record: dict) -> tuple[str, str]:
    if _is_review_only(record):
        return (
            "rejected_reference_only",
            "Record is based on review/redrawn/reference-only evidence rather than primary source evidence.",
        )
    if not (record.get("product_compound") or {}).get("name"):
        return ("rejected_no_product", "Record does not identify a specific transformation product.")
    if not _has_required_evidence_fields(record):
        return ("rejected_insufficient_evidence", "Record is missing required provenance or evidence fields.")
    return ("rejected_no_natural_environment", "Record does not satisfy natural-environment main database criteria.")


def _to_auxiliary(record: dict) -> dict:
    aux = {
        "record_id": record.get("record_id"),
        "source_id": record.get("source_id"),
        "doi": record.get("doi"),
        "title": record.get("title"),
        "chunk_id": record.get("chunk_id"),
        "parent_compound": record.get("parent_compound"),
        "product_compound": record.get("product_compound"),
        "transformation": record.get("transformation"),
        "conditions": record.get("conditions"),
        "evidence_quote": record.get("evidence_quote"),
        "reason_not_in_main_database": AUX_REASON,
        "potential_use": AUX_USE,
        "review": {
            "review_status": "auxiliary_engineered_biological_evidence",
            "review_reason": AUX_REASON,
            "review_confidence": (record.get("review") or {}).get("review_confidence"),
        },
    }
    return aux


def _to_rejection(record: dict, status: str, reason: str) -> dict:
    return {
        "record_id": record.get("record_id"),
        "source_id": record.get("source_id"),
        "doi": record.get("doi"),
        "title": record.get("title"),
        "chunk_id": record.get("chunk_id"),
        "parent_compound": record.get("parent_compound"),
        "product_compound": record.get("product_compound"),
        "conditions": record.get("conditions"),
        "evidence_quote": record.get("evidence_quote"),
        "review": {"review_status": status, "review_reason": reason, "review_confidence": 0.9},
        "reviewer_status": status,
    }


def _dedupe_rejections(records: Iterable[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for record in records:
        key = record.get("record_id") or json.dumps(record, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        out.append(record)
    return out


def _record_text(record: dict) -> str:
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


def write_validated_csv(path: Path, records: list[dict]) -> None:
    fields = [
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
    _write_csv(path, records, fields, _validated_row)


def write_auxiliary_csv(path: Path, records: list[dict]) -> None:
    fields = [
        "record_id",
        "source_id",
        "doi",
        "title",
        "chunk_id",
        "parent_name",
        "product_name",
        "setting_type",
        "environment_matrix",
        "review_status",
        "reason_not_in_main_database",
        "potential_use",
        "evidence_quote",
    ]
    _write_csv(path, records, fields, _auxiliary_row)


def _write_csv(path: Path, records: list[dict], fields: list[str], row_fn) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            writer.writerow(_csv_safe_row(row_fn(record)))


def _csv_safe_row(row: dict) -> dict:
    return {
        key: value.replace("\r\n", "\\n").replace("\r", "\\n").replace("\n", "\\n")
        if isinstance(value, str)
        else value
        for key, value in row.items()
    }


def _validated_row(record: dict) -> dict:
    conditions = record.get("conditions") or {}
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
        "parent_name": (record.get("parent_compound") or {}).get("name"),
        "parent_synonyms": json.dumps((record.get("parent_compound") or {}).get("synonyms") or [], ensure_ascii=False),
        "parent_class": (record.get("parent_compound") or {}).get("compound_class"),
        "product_name": (record.get("product_compound") or {}).get("name"),
        "product_synonyms": json.dumps((record.get("product_compound") or {}).get("synonyms") or [], ensure_ascii=False),
        "product_class": (record.get("product_compound") or {}).get("compound_class"),
        "reaction_type": (record.get("transformation") or {}).get("reaction_type"),
        "reaction_description": (record.get("transformation") or {}).get("reaction_description"),
        "setting_type": conditions.get("setting_type"),
        "environment_matrix": conditions.get("environment_matrix"),
        "environment_type": conditions.get("environment_type"),
        "redox_condition": conditions.get("redox_condition"),
        "microbial_condition": conditions.get("microbial_condition"),
        "duration": conditions.get("duration"),
        "identification_confidence": (record.get("evidence") or {}).get("identification_confidence"),
        "evidence_tier": review.get("evidence_tier"),
        "requires_manual_confirmation": review.get("requires_manual_confirmation"),
        "main_database_use": review.get("main_database_use"),
        "review_status": _record_status(record),
        "review_confidence": review.get("review_confidence"),
        "evidence_quote": record.get("evidence_quote"),
    }


def _auxiliary_row(record: dict) -> dict:
    conditions = record.get("conditions") or {}
    return {
        "record_id": record.get("record_id"),
        "source_id": record.get("source_id"),
        "doi": record.get("doi"),
        "title": record.get("title"),
        "chunk_id": record.get("chunk_id"),
        "parent_name": (record.get("parent_compound") or {}).get("name"),
        "product_name": (record.get("product_compound") or {}).get("name"),
        "setting_type": conditions.get("setting_type"),
        "environment_matrix": conditions.get("environment_matrix"),
        "review_status": (record.get("review") or {}).get("review_status"),
        "reason_not_in_main_database": record.get("reason_not_in_main_database"),
        "potential_use": record.get("potential_use"),
        "evidence_quote": record.get("evidence_quote"),
    }
