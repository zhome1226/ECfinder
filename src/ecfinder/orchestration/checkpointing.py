"""Checkpoint helpers for the production autonomous daemon."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ecfinder.state.common import utc_now, write_json


def write_daemon_checkpoint(
    root: Path,
    *,
    batch_id: str,
    last_processed_source_id: str,
    processed_sources: int,
    screened_sources: int,
    fulltext_found: int,
    sources_parsed: int,
    sources_extracted: int,
    database_records_written: int,
    blocked_external_sources: int,
    manual_screen_sources: int,
    completed_sources: int,
    pending_tasks_remaining: int,
    checkpoint_count: int,
    ended_because: str,
) -> None:
    write_json(
        root / "data" / "state" / "stage2_7_daemon_checkpoint.json",
        {
            "batch_id": batch_id,
            "blocked_external_sources": blocked_external_sources,
            "checkpoint_count": checkpoint_count,
            "completed_sources": completed_sources,
            "database_records_written": database_records_written,
            "ended_because": ended_because,
            "fulltext_found": fulltext_found,
            "last_processed_source_id": last_processed_source_id,
            "manual_screen_sources": manual_screen_sources,
            "pending_tasks_remaining": pending_tasks_remaining,
            "processed_sources": processed_sources,
            "screened_sources": screened_sources,
            "sources_extracted": sources_extracted,
            "sources_parsed": sources_parsed,
            "updated_at": utc_now(),
        },
    )


def checkpoint_due(processed_sources: int, checkpoint_every: int, checkpoint_count: int) -> bool:
    if checkpoint_every <= 0 or processed_sources <= 0:
        return False
    return processed_sources // checkpoint_every > checkpoint_count
