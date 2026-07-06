"""Small loop helpers shared by production daemon validation and reports."""

from __future__ import annotations

from typing import Any


def database_record_count(rows: dict[str, list[dict[str, Any]]]) -> int:
    return len(rows.get("validated", [])) + len(rows.get("manual", [])) + len(rows.get("rejected", [])) + len(rows.get("auxiliary", []))


def terminal_source_count(status_rows: list[dict[str, Any]]) -> int:
    terminal = {"validated", "rejected", "auxiliary", "completed_no_records"}
    return sum(1 for row in status_rows if row.get("overall_status") in terminal)


def has_unreviewed_candidates(candidates: list[dict[str, Any]], reviewed: list[dict[str, Any]]) -> bool:
    candidate_ids = {str(row.get("record_id", "")) for row in candidates}
    reviewed_ids = {str(row.get("record_id", "")) for row in reviewed}
    return bool(candidate_ids - reviewed_ids)
