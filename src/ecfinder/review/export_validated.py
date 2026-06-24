"""Export natural-environment validated records and auxiliary evidence."""

from __future__ import annotations

import csv
import json
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


def write_validated_csv(path: Path, records: list[dict]) -> None:
    fields = [
        "record_id",
        "source_id",
        "doi",
        "title",
        "year",
        "journal",
        "chunk_id",
        "page",
        "section",
        "parent_name",
        "product_name",
        "setting_type",
        "environment_matrix",
        "review_status",
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
            writer.writerow(row_fn(record))


def _validated_row(record: dict) -> dict:
    conditions = record.get("conditions") or {}
    location = record.get("evidence_location") or {}
    return {
        "record_id": record.get("record_id"),
        "source_id": record.get("source_id"),
        "doi": record.get("doi"),
        "title": record.get("title"),
        "year": record.get("year"),
        "journal": record.get("journal"),
        "chunk_id": record.get("chunk_id"),
        "page": location.get("page"),
        "section": location.get("section"),
        "parent_name": (record.get("parent_compound") or {}).get("name"),
        "product_name": (record.get("product_compound") or {}).get("name"),
        "setting_type": conditions.get("setting_type"),
        "environment_matrix": conditions.get("environment_matrix"),
        "review_status": _record_status(record),
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
