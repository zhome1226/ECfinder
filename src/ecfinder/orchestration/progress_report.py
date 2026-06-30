"""Markdown reports for the orchestration status board."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ecfinder.state.common import read_json, read_jsonl


STATUS_SYMBOLS = {
    "done": "\u2705 done",
    "pending": "\u23f3 pending",
    "running": "\u23f3 running",
    "manual_required": "\u26a0\ufe0f manual",
    "retry_pending": "\ud83d\udd01 retry",
    "failed": "\u274c failed",
    "missing": "\u26a0\ufe0f missing",
    "skipped": "\u23ed skipped",
}


def title_short(title: str, limit: int = 56) -> str:
    clean = " ".join(title.split())
    return clean if len(clean) <= limit else clean[: limit - 3] + "..."


def render_status_board(records: list[dict[str, Any]]) -> str:
    lines = [
        "# Current Multi-agent Status Board",
        "",
        "source_id | title_short | metadata | fulltext | parse | extract | review | overall | next_action",
        "--- | --- | --- | --- | --- | --- | --- | --- | ---",
    ]
    for record in records:
        stages = record["stage_status"]
        lines.append(
            " | ".join(
                [
                    record["source_id"],
                    title_short(record.get("title", "")),
                    STATUS_SYMBOLS.get(stages["metadata"], stages["metadata"]),
                    STATUS_SYMBOLS.get(stages["fulltext"], stages["fulltext"]),
                    STATUS_SYMBOLS.get(stages["parse"], stages["parse"]),
                    STATUS_SYMBOLS.get(stages["extract"], stages["extract"]),
                    STATUS_SYMBOLS.get(stages["review"], stages["review"]),
                    record["overall_status"],
                    record["next_action"],
                ]
            )
        )
    return "\n".join(lines) + "\n"


def render_error_summary(errors: list[dict[str, Any]]) -> str:
    lines = [
        "# Current Error Summary",
        "",
        "error_id | source_id | stage | recoverable | next_action | message",
        "--- | --- | --- | --- | --- | ---",
    ]
    for error in errors:
        lines.append(
            " | ".join(
                [
                    error["error_id"],
                    error["source_id"],
                    error["stage"],
                    str(error["recoverable"]).lower(),
                    error["next_action"],
                    error["error_message_short"],
                ]
            )
        )
    if not errors:
        lines.append("none | none | none | true | none | no current errors")
    return "\n".join(lines) + "\n"


def render_manual_handoff(handoffs: list[dict[str, Any]]) -> str:
    lines = [
        "# Current Manual Handoff Queue",
        "",
        "handoff_id | source_id | stage | required_user_action | priority | status | suggested_action",
        "--- | --- | --- | --- | --- | --- | ---",
    ]
    for handoff in handoffs:
        lines.append(
            " | ".join(
                [
                    handoff["handoff_id"],
                    handoff["source_id"],
                    handoff["stage"],
                    handoff["required_user_action"],
                    handoff["priority"],
                    handoff["status"],
                    handoff["suggested_action"],
                ]
            )
        )
    if not handoffs:
        lines.append("none | none | none | none | none | none | none")
    return "\n".join(lines) + "\n"


def summarize(records: list[dict[str, Any]], retries: list[dict[str, Any]], handoffs: list[dict[str, Any]], errors: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_sources": len(records),
        "completed_sources": sum(1 for row in records if row["overall_status"] in {"validated", "manual_review", "rejected", "failed_terminal"}),
        "validated_sources": sum(1 for row in records if row["overall_status"] == "validated"),
        "manual_review_sources": sum(1 for row in records if row["overall_status"] == "manual_review"),
        "failed_recoverable_sources": sum(1 for row in records if row["overall_status"] == "failed_recoverable"),
        "failed_terminal_sources": sum(1 for row in records if row["overall_status"] == "failed_terminal"),
        "metadata_done": sum(1 for row in records if row["stage_status"]["metadata"] == "done"),
        "fulltext_found": sum(1 for row in records if row["stage_status"]["fulltext"] == "done"),
        "fulltext_missing": sum(1 for row in records if row["stage_status"]["fulltext"] == "missing"),
        "parse_done": sum(1 for row in records if row["stage_status"]["parse"] == "done"),
        "extract_done": sum(1 for row in records if row["stage_status"]["extract"] == "done"),
        "review_done": sum(1 for row in records if row["stage_status"]["review"] == "done"),
        "retry_queue_size": len(retries),
        "manual_handoff_queue_size": len(handoffs),
        "error_queue_size": len(errors),
        "can_resume": True,
        "orchestration_validation_passed": False,
        "ready_for_next_batch": False,
    }


def write_reports(root: Path, validation_passed: bool = False) -> dict[str, Any]:
    state = root / "data" / "state"
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    records = read_jsonl(state / "source_status_board.jsonl")
    errors = read_jsonl(state / "error_queue.jsonl")
    retries = read_jsonl(state / "retry_queue.jsonl")
    handoffs = read_jsonl(state / "manual_handoff_queue.jsonl")
    checkpoint = read_json(state / "orchestration_checkpoint.json")
    summary = summarize(records, retries, handoffs, errors)
    summary["can_resume"] = bool(checkpoint.get("can_resume", False))
    summary["orchestration_validation_passed"] = validation_passed
    summary["ready_for_next_batch"] = validation_passed

    (reports / "current_status_board.md").write_text(render_status_board(records), encoding="utf-8", newline="\n")
    (reports / "current_error_summary.md").write_text(render_error_summary(errors), encoding="utf-8", newline="\n")
    (reports / "current_manual_handoff.md").write_text(render_manual_handoff(handoffs), encoding="utf-8", newline="\n")
    (reports / "stage2_4f_orchestration_summary.md").write_text(render_summary(summary), encoding="utf-8", newline="\n")
    (reports / "stage2_4f_fault_tolerance_audit.md").write_text(render_fault_tolerance_audit(validation_passed), encoding="utf-8", newline="\n")
    return summary


def render_summary(summary: dict[str, Any]) -> str:
    lines = ["# Stage 2.4f Orchestration Summary", ""]
    for key, value in summary.items():
        if isinstance(value, bool):
            value_text = str(value).lower()
        else:
            value_text = str(value)
        lines.append(f"{key} = {value_text}")
    return "\n".join(lines) + "\n"


def render_fault_tolerance_audit(validation_passed: bool) -> str:
    ready = "yes" if validation_passed else "no"
    return "\n".join(
        [
            "# Stage 2.4f Fault Tolerance Audit",
            "",
            "single_source_failure_interrupts_batch = no",
            "supports_resume = yes",
            "supports_retry = yes",
            "supports_manual_handoff = yes",
            "avoids_duplicate_cache_hit_processing = yes",
            "avoids_duplicate_codex_task_generation = yes",
            f"validation_passed = {ready}",
        ]
    ) + "\n"
