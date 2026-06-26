"""Hard validation gates for the clean PFAS pipeline."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ecfinder.pipeline.contracts import (
    CLEAN_JSONL_FILES,
    CSV_REL,
    EVIDENCE_TIER_VALUES,
    FORBIDDEN_PATTERNS,
    MAIN_DATABASE_REL,
    REVIEW_STATUS_VALUES,
    SOURCE_TYPE_VALUES,
    clean_database_counts,
    evidence_quote,
    has_value,
    read_csv_rows,
    read_jsonl_strict,
    record_text_for_boundary,
    transformation_has_description,
)
from ecfinder.pipeline.exceptions import PipelineGateError
from ecfinder.pipeline.queues import ensure_queues


@dataclass
class GateResult:
    name: str
    passed: bool
    counts: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    input_files: list[str] = field(default_factory=list)


def run_gate_or_raise(result: GateResult) -> GateResult:
    if not result.passed:
        raise PipelineGateError(result.name, result.errors)
    return result


def preflight_gate(root: Path) -> GateResult:
    errors: list[str] = []
    input_files = [
        "data/clean",
        "reports/legacy_stage2_output_freeze_notice.md",
        "data/clean/schema_clean_v1.yaml",
        "scripts/build_clean_database_v1.py",
        "scripts/validate_clean_database_v1.py",
        "data/clean/pipeline_state.json",
    ]
    required_paths = [
        root / "data" / "clean",
        root / "reports" / "legacy_stage2_output_freeze_notice.md",
        root / "data" / "clean" / "schema_clean_v1.yaml",
        root / "scripts" / "build_clean_database_v1.py",
        root / "scripts" / "validate_clean_database_v1.py",
    ]
    for path in required_paths:
        if not path.exists():
            errors.append(f"Missing required path: {path}")
    try:
        ensure_queues(root)
        state_path = root / "data" / "clean" / "pipeline_state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        if state_path.exists():
            with state_path.open("a", encoding="utf-8"):
                pass
        else:
            state_path.write_text("{}\n", encoding="utf-8")
    except OSError as exc:
        errors.append(f"Pipeline state is not writable: {exc}")
    return GateResult(
        name="preflight",
        passed=not errors,
        errors=errors,
        input_files=input_files,
        counts={"required_paths_checked": len(required_paths)},
    )


def jsonl_integrity_gate(root: Path) -> GateResult:
    errors: list[str] = []
    counts: dict[str, Any] = {}
    ensure_queues(root)
    for rel in CLEAN_JSONL_FILES:
        path = root / rel
        try:
            records = read_jsonl_strict(path)
            counts[f"{Path(rel).name}_count"] = len(records)
        except ValueError as exc:
            errors.append(str(exc))
            counts[f"{Path(rel).name}_count"] = 0
    return GateResult(
        name="jsonl_integrity",
        passed=not errors,
        errors=errors,
        counts=counts,
        input_files=CLEAN_JSONL_FILES,
    )


def clean_database_integrity_gate(root: Path) -> GateResult:
    errors: list[str] = []
    records_path = root / MAIN_DATABASE_REL
    csv_path = root / CSV_REL
    try:
        records = read_jsonl_strict(records_path)
    except ValueError as exc:
        records = []
        errors.append(str(exc))
    try:
        csv_rows, csv_header = read_csv_rows(csv_path)
    except OSError as exc:
        csv_rows = []
        csv_header = None
        errors.append(f"CSV read failed: {exc}")

    seen_ids: set[str] = set()
    duplicate_ids: set[str] = set()
    for index, record in enumerate(records, start=1):
        record_id = str(record.get("record_id") or "").strip()
        if not record_id:
            errors.append(f"{records_path}:{index} missing record_id")
        elif record_id in seen_ids:
            duplicate_ids.add(record_id)
        seen_ids.add(record_id)
        if not has_value(record, "source_id"):
            errors.append(f"{record_id or index} missing source_id")
        if not (has_value(record, "doi") or has_value(record, "title")):
            errors.append(f"{record_id or index} missing doi/title")
        if not has_value(record, "parent_compound.name"):
            errors.append(f"{record_id or index} missing parent_compound.name")
        if not has_value(record, "product_compound.name"):
            errors.append(f"{record_id or index} missing product_compound.name")
        if not transformation_has_description(record):
            errors.append(f"{record_id or index} missing transformation reaction_type/reaction_description")
        if not has_value(record, "conditions.setting_type"):
            errors.append(f"{record_id or index} missing conditions.setting_type")
        if not evidence_quote(record).strip():
            errors.append(f"{record_id or index} missing evidence_quote")
        review = record.get("review") or {}
        review_status = review.get("review_status")
        evidence_tier = review.get("evidence_tier")
        if review_status not in REVIEW_STATUS_VALUES:
            errors.append(f"{record_id or index} invalid review.review_status: {review_status}")
        if evidence_tier not in EVIDENCE_TIER_VALUES:
            errors.append(f"{record_id or index} invalid review.evidence_tier: {evidence_tier}")
        source_type = record.get("source_type")
        if source_type not in SOURCE_TYPE_VALUES:
            errors.append(f"{record_id or index} invalid source_type: {source_type}")
    for record_id in sorted(duplicate_ids):
        errors.append(f"Duplicate record_id: {record_id}")
    if not csv_header:
        errors.append(f"CSV has no header: {csv_path}")
    if len(csv_rows) != len(records):
        errors.append(f"CSV row count {len(csv_rows)} does not match JSONL record count {len(records)}")

    counts = _record_counts(records)
    counts.update(
        {
            "record_count": len(records),
            "csv_data_rows": len(csv_rows),
            "duplicate_record_count": len(duplicate_ids),
        }
    )
    return GateResult(
        name="clean_database_integrity",
        passed=not errors,
        errors=errors,
        counts=counts,
        input_files=[MAIN_DATABASE_REL, CSV_REL],
    )


def natural_environment_boundary_gate(root: Path) -> GateResult:
    errors: list[str] = []
    records = read_jsonl_strict(root / MAIN_DATABASE_REL)
    offending_records: list[dict[str, Any]] = []
    for record in records:
        text = record_text_for_boundary(record)
        hits = [term for term, pattern in FORBIDDEN_PATTERNS.items() if pattern.search(text)]
        if hits:
            record_id = record.get("record_id") or "unknown"
            errors.append(f"{record_id} contains forbidden clean-main term(s): {', '.join(hits)}")
            offending_records.append({"record_id": record_id, "terms": hits})
    return GateResult(
        name="natural_environment_boundary",
        passed=not errors,
        errors=errors,
        counts={
            "record_count": len(records),
            "offending_record_count": len(offending_records),
        },
        input_files=[MAIN_DATABASE_REL],
    )


def report_consistency_gate(root: Path) -> GateResult:
    errors: list[str] = []
    counts = clean_database_counts(root)
    boundary_flags = _boundary_flags(root)
    expected: dict[str, Any] = {
        "clean_database_records": counts["record_count"],
        "clean_database_sources": counts["source_count"],
        "record_count": counts["record_count"],
        "csv_data_rows": counts["csv_data_rows"],
        "source_count": counts["source_count"],
        "clean_database_total_records": counts["record_count"],
        "clean_database_source_count": counts["source_count"],
        "confirmed_product_count": counts["confirmed_product_count"],
        "probable_product_count": counts["probable_product_count"],
        "tentative_product_count": counts["tentative_product_count"],
        "requires_manual_confirmation_count": counts["requires_manual_confirmation_count"],
        "activated_sludge_in_clean_main": boundary_flags["activated sludge"],
        "wastewater_treatment_in_clean_main": boundary_flags["wastewater treatment"],
        "wwtp_in_clean_main": boundary_flags["WWTP"],
    }
    stage2_2_expected = _stage2_2_counts(root)
    expected.update(stage2_2_expected)

    report_rels = [
        "reports/clean_database_v1_summary.md",
        "reports/clean_database_v1_validation.md",
        "reports/stage2_2_targeted_followup_summary.md",
    ]
    comparisons = 0
    for rel in report_rels:
        path = root / rel
        if not path.exists():
            errors.append(f"Missing report for consistency gate: {path}")
            continue
        values = parse_report_key_values(path)
        for key, actual in values.items():
            if key not in expected:
                continue
            comparisons += 1
            if not _same_report_value(actual, expected[key]):
                errors.append(f"{rel}: {key} = {actual!r} does not match real file value {expected[key]!r}")
    return GateResult(
        name="report_consistency",
        passed=not errors,
        errors=errors,
        counts={**counts, **stage2_2_expected, "report_count_comparisons": comparisons},
        input_files=report_rels + [MAIN_DATABASE_REL, CSV_REL],
    )


def stage_readiness_gate(root: Path) -> GateResult:
    errors: list[str] = []
    counts = clean_database_counts(root)
    if counts["record_count"] < 8:
        errors.append("Clean database has fewer than 8 records; not ready for targeted follow-up.")
    if counts["source_count"] < 2:
        errors.append("Clean database has fewer than 2 sources; not ready for targeted follow-up.")
    return GateResult(
        name="stage_readiness",
        passed=not errors,
        errors=errors,
        counts=counts,
        input_files=[MAIN_DATABASE_REL],
    )


def run_all_gates(root: Path, include_stage_readiness: bool = True) -> list[GateResult]:
    gate_functions = [
        preflight_gate,
        jsonl_integrity_gate,
        clean_database_integrity_gate,
        natural_environment_boundary_gate,
        report_consistency_gate,
    ]
    if include_stage_readiness:
        gate_functions.append(stage_readiness_gate)
    results: list[GateResult] = []
    for gate_function in gate_functions:
        result = gate_function(root)
        results.append(result)
        run_gate_or_raise(result)
    return results


def parse_report_key_values(path: Path) -> dict[str, Any]:
    values: dict[str, Any] = {}
    pattern = re.compile(r"^\s*[-*]?\s*([A-Za-z0-9_]+)\s*(?:=|:)\s*(.+?)\s*$")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if not match:
            continue
        key, raw_value = match.groups()
        raw_value = raw_value.strip().strip("`")
        values[key] = _parse_scalar(raw_value)
    return values


def _parse_scalar(value: str) -> Any:
    lower = value.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?\d+\.\d+", value):
        return float(value)
    return value


def _same_report_value(actual: Any, expected: Any) -> bool:
    if isinstance(expected, bool):
        return actual is expected
    if isinstance(expected, int) and not isinstance(expected, bool):
        return actual == expected
    return str(actual) == str(expected)


def _record_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    return {
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
    }


def _boundary_flags(root: Path) -> dict[str, bool]:
    records = read_jsonl_strict(root / MAIN_DATABASE_REL)
    text = "\n".join(record_text_for_boundary(record) for record in records)
    return {term: bool(pattern.search(text)) for term, pattern in FORBIDDEN_PATTERNS.items()}


def _stage2_2_counts(root: Path) -> dict[str, int]:
    clean = root / "data" / "clean"

    def count_jsonl(name: str) -> int:
        path = clean / name
        if not path.exists():
            return 0
        return len(read_jsonl_strict(path))

    downloads = read_jsonl_strict(clean / "stage2_2_download_status.jsonl") if (clean / "stage2_2_download_status.jsonl").exists() else []
    return {
        "priority_doi_attempts": len(downloads),
        "priority_doi_full_text_success": sum(
            1 for item in downloads if item.get("download_status") == "open_full_text_success"
        ),
        "download_success": sum(1 for item in downloads if item.get("download_status") == "open_full_text_success"),
        "parsed_sources": sum(1 for item in downloads if item.get("parsed") is True),
        "additional_search_candidates": count_jsonl("stage2_2_search_results.jsonl"),
        "screened_sources": count_jsonl("stage2_2_screened_sources.jsonl"),
        "raw_candidate_records": count_jsonl("stage2_2_candidate_records_raw.jsonl"),
        "new_validated_records": count_jsonl("stage2_2_validated_records.jsonl"),
        "new_manual_review_records": count_jsonl("stage2_2_manual_review_records.jsonl"),
        "new_rejected_records": count_jsonl("stage2_2_rejected_records.jsonl"),
        "new_auxiliary_records": count_jsonl("stage2_2_auxiliary_records.jsonl"),
    }
