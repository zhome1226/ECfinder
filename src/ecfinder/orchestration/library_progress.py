"""Library progress accounting for production autonomous runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ecfinder.state.common import read_jsonl


TERMINAL_STATUSES = {"validated", "rejected", "auxiliary", "completed_no_records", "excluded"}
SCREENED_STATUSES = {"done", "cache_hit"}


def source_identity(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("source_id", "")),
        str(row.get("zotero_item_key", "")),
        str(row.get("doi", "")).strip().lower(),
    )


def unique_source_ids(rows: list[dict[str, Any]]) -> set[str]:
    return {source_id for source_id, _, _ in (source_identity(row) for row in rows) if source_id}


def load_status_rows(root: Path, paths: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        actual = path if path.is_absolute() else root / path
        rows.extend(read_jsonl(actual))
    return rows


def summarize_previous_progress(root: Path, status_paths: list[Path]) -> dict[str, int]:
    rows = load_status_rows(root, status_paths)
    screened = {
        source_id
        for row in rows
        for source_id, _, _ in [source_identity(row)]
        if source_id and row.get("screening_status") in SCREENED_STATUSES
    }
    terminal = {
        source_id
        for row in rows
        for source_id, _, _ in [source_identity(row)]
        if source_id and row.get("overall_status") in TERMINAL_STATUSES
    }
    manual = {
        source_id
        for row in rows
        for source_id, _, _ in [source_identity(row)]
        if source_id and row.get("overall_status") == "manual_screen"
    }
    blocked = {
        source_id
        for row in rows
        for source_id, _, _ in [source_identity(row)]
        if source_id and row.get("overall_status") == "blocked_external"
    }
    return {
        "previous_sources_screened": len(screened),
        "previously_processed_sources": len(screened | terminal | manual | blocked),
        "previous_terminal_sources": len(terminal),
        "previous_manual_sources": len(manual),
        "previous_blocked_sources": len(blocked),
    }
