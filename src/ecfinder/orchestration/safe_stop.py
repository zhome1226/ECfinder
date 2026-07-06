"""Safe-stop policy for the production autonomous daemon."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Any


@dataclass(frozen=True)
class SafeStopPolicy:
    root: Path
    started_at_monotonic: float
    max_wall_minutes: int | None = None
    max_records: int | None = None
    max_new_screen: int | None = None
    max_new_fulltext: int | None = None
    max_new_extract_sources: int | None = None
    safe_stop_on_token_budget: bool = False
    token_budget: int | None = None
    stop_file: Path | None = None

    def stop_file_path(self) -> Path:
        if self.stop_file:
            return self.stop_file if self.stop_file.is_absolute() else self.root / self.stop_file
        return self.root / "data" / "state" / "STOP_DAEMON"

    def elapsed_minutes(self) -> float:
        return (monotonic() - self.started_at_monotonic) / 60.0

    def estimate_tokens(self, stats: dict[str, Any]) -> int:
        screened = int(stats.get("screened_sources", 0) or 0)
        extracted = int(stats.get("sources_extracted", 0) or 0)
        reviewed = int(stats.get("reviewed_records", 0) or 0)
        return screened * 180 + extracted * 1400 + reviewed * 350

    def should_stop_before_next_source(self, stats: dict[str, Any]) -> tuple[bool, str]:
        if self.stop_file_path().exists():
            return True, "stop_file_detected"
        if self.max_wall_minutes is not None and self.elapsed_minutes() >= self.max_wall_minutes:
            return True, "max_wall_minutes_reached"
        if self.max_records is not None and int(stats.get("processed_sources", 0) or 0) >= self.max_records:
            return True, "max_records_reached"
        if self.max_new_screen is not None and int(stats.get("screened_sources", 0) or 0) >= self.max_new_screen:
            return True, "max_new_screen_reached"
        if self.max_new_fulltext is not None and int(stats.get("fulltext_found", 0) or 0) >= self.max_new_fulltext:
            return True, "max_new_fulltext_reached"
        if self.max_new_extract_sources is not None and int(stats.get("sources_extracted", 0) or 0) >= self.max_new_extract_sources:
            return True, "max_new_extract_sources_reached"
        if self.safe_stop_on_token_budget and self.token_budget is not None and self.estimate_tokens(stats) >= self.token_budget:
            return True, "token_budget_reached"
        return False, ""
