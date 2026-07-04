"""State paths and report helpers for Stage 2.6c streaming workflow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ecfinder.state.common import write_json, write_jsonl


@dataclass(frozen=True)
class StreamingPaths:
    root: Path
    prefix: str = "stage2_6c_streaming"

    @property
    def batches(self) -> Path:
        return self.root / "data" / "batches"

    @property
    def state(self) -> Path:
        return self.root / "data" / "state"

    @property
    def reports(self) -> Path:
        return self.root / "reports"

    @property
    def source_status(self) -> Path:
        return self.state / f"{self.prefix}_source_status.jsonl"

    @property
    def events(self) -> Path:
        return self.state / f"{self.prefix}_events.jsonl"

    @property
    def checkpoint(self) -> Path:
        return self.state / f"{self.prefix}_checkpoint.json"

    @property
    def screening_decisions(self) -> Path:
        return self.batches / f"{self.prefix}_screening_decisions.jsonl"

    @property
    def chunk_screening(self) -> Path:
        return self.batches / f"{self.prefix}_chunk_screening.jsonl"

    @property
    def candidates(self) -> Path:
        return self.batches / f"{self.prefix}_candidate_records.jsonl"

    @property
    def reviewed(self) -> Path:
        return self.batches / f"{self.prefix}_reviewed_records.jsonl"

    @property
    def validated(self) -> Path:
        return self.batches / f"{self.prefix}_validated_records.jsonl"

    @property
    def manual(self) -> Path:
        return self.batches / f"{self.prefix}_manual_review_records.jsonl"

    @property
    def rejected(self) -> Path:
        return self.batches / f"{self.prefix}_rejected_records.jsonl"

    @property
    def auxiliary(self) -> Path:
        return self.batches / f"{self.prefix}_auxiliary_records.jsonl"

    @property
    def summary_report(self) -> Path:
        return self.reports / f"{self.prefix}_autonomous_summary.md"

    @property
    def status_board_report(self) -> Path:
        return self.reports / f"{self.prefix}_status_board.md"

    @property
    def skill_audit_report(self) -> Path:
        return self.reports / f"{self.prefix}_skill_invocation_audit.md"

    @property
    def sync_review_report(self) -> Path:
        return self.reports / f"{self.prefix}_synchronous_review_audit.md"

    @property
    def token_report(self) -> Path:
        return self.reports / f"{self.prefix}_token_cost_audit.md"

    @property
    def blocked_report(self) -> Path:
        return self.reports / f"{self.prefix}_blocked_sources.md"

    @property
    def database_report(self) -> Path:
        return self.reports / f"{self.prefix}_database_audit.md"

    @property
    def resume_skip_report(self) -> Path:
        return self.reports / f"{self.prefix}_resume_skip_audit.md"

    @property
    def strict_jsonl_report(self) -> Path:
        return self.reports / f"{self.prefix}_strict_jsonl_audit.md"


def write_key_value_report(path: Path, title: str, values: dict[str, Any], extra_lines: list[str] | None = None) -> None:
    lines = [f"# {title}", ""]
    for key, value in values.items():
        rendered = str(value).lower() if isinstance(value, bool) else str(value)
        lines.append(f"{key} = {rendered}")
    if extra_lines:
        lines.extend(["", *extra_lines])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def reset_streaming_outputs(paths: StreamingPaths) -> None:
    for path in [
        paths.source_status,
        paths.events,
        paths.screening_decisions,
        paths.chunk_screening,
        paths.candidates,
        paths.reviewed,
        paths.validated,
        paths.manual,
        paths.rejected,
        paths.auxiliary,
    ]:
        write_jsonl(path, [])
    write_json(paths.checkpoint, {})
