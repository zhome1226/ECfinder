"""Pipeline report writers backed by real parsed files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ecfinder.pipeline.contracts import clean_database_counts
from ecfinder.pipeline.gates import GateResult
from ecfinder.pipeline.queues import queue_counts


def write_diagnosis_report(root: Path, clean_jsonl_ok: bool, clean_counts: dict[str, Any], notes: list[str]) -> None:
    path = root / "reports" / "stage2_2b_orchestrator_diagnosis.md"
    lines = [
        "# Stage 2.2b Orchestrator Diagnosis",
        "",
        "## Current State",
        "",
        "- legacy_reviewed_outputs_frozen = true",
        "- clean_database_source_of_truth = data/clean/",
        f"- clean_summary_claimed_records = {clean_counts.get('record_count', 'unknown')}",
        f"- clean_jsonl_strict_parse_ok = {str(clean_jsonl_ok).lower()}",
        "",
        "## Diagnosis",
        "",
        "- The legacy `data/reviewed/stage2_*` and `data/reviewed/pfas_transformation_records_validated.*` outputs are frozen and retained only as historical development artifacts.",
        "- `data/clean/` is now the source of truth for validated natural-environment PFAS transformation records, source counts, review queues, and downstream readiness decisions.",
        "- The current clean database summary claims 9 records; because of earlier serialization failures, this claim must be continuously checked against the real JSONL and CSV files.",
        "- Before this task, the workflow still depended on manual user re-entry for audit, review, and promotion decisions between stages.",
        "- Before this task, the project lacked one unified orchestrator with persisted state, hard validation gates, event logging, and a human-review queue.",
        "",
        "## Gate Observation",
        "",
    ]
    lines.extend(f"- {note}" for note in notes)
    lines.extend(
        [
            "",
            "## Required Direction",
            "",
            "- All future readiness reports must be generated from parsed clean files, not from hand-written counts.",
            "- Any failed gate must stop the pipeline, write `data/clean/error_queue.jsonl`, and mark `pipeline_state.status = failed`.",
            "- Codex semantic extraction/review must be represented through handoff queues rather than a fake in-script LLM client.",
            "",
        ]
    )
    _write(path, lines)


def write_contracts_report(root: Path) -> None:
    path = root / "reports" / "pipeline_contracts.md"
    lines = [
        "# Pipeline Contracts",
        "",
        "## JSONL Contract",
        "",
        "- Each non-empty line is exactly one complete JSON object.",
        "- Each line must parse with `json.loads(line)`.",
        "- A line containing multiple objects, such as `} {`, fails validation.",
        "- Objects split across true newline characters fail validation.",
        "- Empty objects `{}` are not allowed.",
        "",
        "## Clean Main Database Contract",
        "",
        "- `record_id`, `source_id`, `parent_compound.name`, `product_compound.name`, `conditions.setting_type`, and `evidence_quote` must be non-empty.",
        "- `doi` or `title` must be present.",
        "- `transformation.reaction_type` or `transformation.reaction_description` must be non-empty.",
        "- `review.review_status` must be one of `validated_high_confidence`, `validated_medium_confidence`, or `validated_low_confidence`.",
        "- `review.evidence_tier` must be one of `confirmed_product`, `probable_product`, or `tentative_product`.",
        "- `source_type` must be `primary_study` or explicitly primary evidence.",
        "",
        "## Natural Environment Boundary",
        "",
        "- The clean main database cannot contain activated sludge, wastewater treatment, WWTP, engineered treatment, AOP, electrochemical, plasma, ozonation, photocatalysis, hydrothermal, or incineration evidence.",
        "- Engineered biological treatment evidence belongs in auxiliary records, not the clean main database.",
        "",
        "## Manual Review Contract",
        "",
        "- Uncertain records must be placed in `data/clean/manual_review_queue.jsonl`.",
        "- Manual-review items must include `record_id`, `reason`, `blocking_fields`, `source_id`, `chunk_id`, `evidence_quote`, and `suggested_action`.",
        "",
        "## Report Consistency Contract",
        "",
        "- Counts in readiness reports must match real JSONL/CSV parsing results.",
        "- If report counts disagree with files, the report-consistency gate fails and no ready report may be produced.",
        "",
    ]
    _write(path, lines)


def write_preflight_report(
    root: Path,
    profile: str,
    state: dict[str, Any],
    gate_results: list[GateResult],
    validation_ok: bool,
    errors: list[str] | None = None,
) -> None:
    path = root / "reports" / "pipeline_preflight_report.md"
    counts: dict[str, Any] = {}
    try:
        counts.update(clean_database_counts(root))
    except Exception as exc:  # pragma: no cover - defensive report path
        counts["clean_count_error"] = str(exc)
    try:
        counts.update(queue_counts(root))
    except Exception as exc:  # pragma: no cover - defensive report path
        counts["queue_count_error"] = str(exc)
    lines = [
        "# Pipeline Preflight Report",
        "",
        f"- pipeline_version = {state.get('pipeline_version')}",
        f"- run_id = {state.get('run_id')}",
        f"- profile = {profile}",
        f"- status = {state.get('status')}",
        f"- validation_ok = {str(validation_ok).lower()}",
        f"- stage2_3_ready_or_not = {'ready_for_targeted_followup' if validation_ok else 'not_ready'}",
        "",
        "## Real File Counts",
        "",
    ]
    for key in sorted(counts):
        lines.append(f"- {key} = {counts[key]}")
    lines.extend(["", "## Gates", ""])
    for result in gate_results:
        lines.append(f"- {result.name} = {'passed' if result.passed else 'failed'}")
        for key in sorted(result.counts):
            lines.append(f"  - {result.name}.{key} = {result.counts[key]}")
        for error in result.errors:
            lines.append(f"  - error: {error}")
    lines.extend(["", "## Errors", ""])
    for error in errors or []:
        lines.append(f"- {error}")
    lines.append("")
    _write(path, lines)


def write_runbook(root: Path) -> None:
    path = root / "reports" / "pipeline_runbook.md"
    lines = [
        "# Pipeline Runbook",
        "",
        "## Standard Commands",
        "",
        "```bash",
        "python -m ecfinder.cli pipeline-preflight",
        "python -m ecfinder.cli pipeline-status",
        "python -m ecfinder.cli pipeline-run-targeted --max-sources 10",
        "```",
        "",
        "## Gate Rules",
        "",
        "- If `pipeline-preflight` fails, stop. Do not search, merge, or write a ready report.",
        "- Inspect `data/clean/error_queue.jsonl` and `reports/pipeline_preflight_report.md` for the exact failed gate and file-level reason.",
        "- Re-run `python -m ecfinder.cli pipeline-preflight` after repairing the cause.",
        "",
        "## Manual Review Queue",
        "",
        "- Pending uncertain records belong in `data/clean/manual_review_queue.jsonl`.",
        "- Codex should read each queue item, inspect the referenced source/chunk, and choose `reextract`, `manual_check_full_text`, `reject`, or `promote_after_confirmation`.",
        "- A record should not enter `pfas_natural_transformation_records_v1.jsonl` until the blocking fields are resolved and gates pass.",
        "",
        "## Error Queue",
        "",
        "- `data/clean/error_queue.jsonl` contains current blocking errors from the most recent failed run.",
        "- Fix the underlying file or report mismatch, then rerun preflight. A passing run clears the queue.",
        "",
        "## Stage Decisions",
        "",
        "- Stage 2.3 targeted follow-up is allowed only when all hard gates pass and the clean database remains the source of truth.",
        "- Stage 3 broad synthesis is not allowed merely because preflight passes; it requires broader source coverage, multiple parent classes, and enough validated records for synthesis.",
        "",
    ]
    _write(path, lines)


def _write(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
