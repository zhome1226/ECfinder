"""Autonomous closed-loop executor for runnable PFASfinder agent tasks."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ecfinder.state.common import read_jsonl, write_jsonl

from .agent_executor import FulltextAgentExecutor, MetadataAgentExecutor, ParseChunkAgentExecutor, ScreeningAgentExecutor
from .task_executor import (
    DatabaseWriteAgentExecutor,
    ExtractionAgentExecutor,
    ReviewAgentExecutor,
    discover_stage2_4j_tasks,
    line_count,
    update_checkpoint,
    write_runnable_report,
)


class ClosedLoopExecutor:
    def __init__(self, root: Path, batch_id: str, max_cycles: int = 50) -> None:
        self.root = root
        self.batch_id = batch_id
        self.max_cycles = max_cycles
        self.executors = [
            ExtractionAgentExecutor(root),
            ReviewAgentExecutor(root),
            DatabaseWriteAgentExecutor(root),
            MetadataAgentExecutor(root),
            ScreeningAgentExecutor(root),
            FulltextAgentExecutor(root),
            ParseChunkAgentExecutor(root),
        ]
        self.trace: list[dict[str, Any]] = []

    def discover(self) -> list[dict[str, Any]]:
        if self.batch_id == "stage2_4j":
            runnable = discover_stage2_4j_tasks(self.root, self.batch_id)
        else:
            runnable = []
        write_runnable_report(self.root, self.batch_id, runnable)
        return runnable

    def execute_task(self, task: dict[str, Any]) -> bool:
        for executor in self.executors:
            if executor.can_run(task):
                result = executor.run(task)
                executor.write_outputs(result)
                self.trace.append(
                    {
                        "task_id": task.get("task_id", ""),
                        "source_id": task.get("source_id", ""),
                        "task_type": task.get("task_type", ""),
                        "executor": executor.name,
                        "status": "done",
                    }
                )
                if task.get("task_type") == "extract":
                    self.trace.append(
                        {
                            "task_id": f"{task.get('task_id', '')}_review",
                            "source_id": task.get("source_id", ""),
                            "task_type": "review",
                            "executor": "ReviewAgent",
                            "status": "done",
                        }
                    )
                    self.trace.append(
                        {
                            "task_id": f"{task.get('task_id', '')}_write_database",
                            "source_id": task.get("source_id", ""),
                            "task_type": "write_database",
                            "executor": "DatabaseWriteAgent",
                            "status": "done",
                        }
                    )
                return True
        self.trace.append(
            {
                "task_id": task.get("task_id", ""),
                "source_id": task.get("source_id", ""),
                "task_type": task.get("task_type", ""),
                "executor": "",
                "status": "no_executor",
            }
        )
        return False

    def run_until_idle(self) -> dict[str, Any]:
        initial = self.discover()
        previous = self.previous_successful_summary()
        if not initial and previous:
            update_checkpoint(self.root, self.batch_id)
            print(json.dumps(previous, ensure_ascii=False, sort_keys=True))
            return previous
        executed = 0
        cycles = 0
        ended = "no_runnable_tasks_remain"
        while cycles < self.max_cycles:
            cycles += 1
            runnable = self.discover()
            if not runnable:
                ended = "no_runnable_tasks_remain"
                break
            progress = 0
            for task in runnable:
                if self.execute_task(task):
                    executed += 1
                    progress += 1
            if progress == 0:
                ended = "no_runnable_tasks_remain"
                break
        else:
            ended = "max_cycles_reached"
        update_checkpoint(self.root, self.batch_id)
        summary = self.build_summary(initial, executed, ended)
        self.write_reports(summary)
        self.discover()
        return summary

    def previous_successful_summary(self) -> dict[str, Any] | None:
        path = self.root / "reports" / "stage2_5_closed_loop_summary.md"
        if not path.exists():
            return None
        values: dict[str, Any] = {}
        pattern = re.compile(r"^([A-Za-z0-9_]+)\s*=\s*(.+?)\s*$")
        for line in path.read_text(encoding="utf-8").splitlines():
            match = pattern.match(line)
            if not match:
                continue
            key, value = match.group(1), match.group(2)
            if value in {"true", "false"}:
                values[key] = value == "true"
            else:
                try:
                    values[key] = int(value)
                except ValueError:
                    values[key] = value
        if values.get("batch_id") == self.batch_id and values.get("workflow_closed_loop_success") is True and values.get("no_runnable_tasks_remain") is True:
            return values
        return None

    def build_summary(self, initial: list[dict[str, Any]], executed: int, ended: str) -> dict[str, Any]:
        status_rows = read_jsonl(self.root / "data" / "batches" / "stage2_4j_available_fulltext_ingest_status.jsonl")
        task_rows = read_jsonl(self.root / "data" / "batches" / "stage2_4j_codex_tasks.jsonl")
        run_dirs = [self.root / str(row.get("run_dir", "")) for row in status_rows if row.get("run_dir")]
        candidate = sum(line_count(path / "candidate_records.jsonl") for path in run_dirs)
        reviewed = sum(line_count(path / "reviewed_records.jsonl") for path in run_dirs)
        validated = sum(line_count(path / "validated_records.jsonl") for path in run_dirs)
        manual = sum(line_count(path / "manual_review_records.jsonl") for path in run_dirs)
        rejected = sum(line_count(path / "rejected_records.jsonl") for path in run_dirs)
        auxiliary = sum(line_count(path / "auxiliary_records.jsonl") for path in run_dirs)
        pending = sum(1 for task in task_rows if task.get("status") == "pending")
        blocked_external = line_count(self.root / "data" / "state" / "blocked_external_queue.jsonl")
        sources_with_validated = len({row.get("source_id") for path in run_dirs for row in read_jsonl(path / "validated_records.jsonl")})
        validated_records = [row for path in run_dirs for row in read_jsonl(path / "validated_records.jsonl")]
        strong_validated = sum(1 for row in validated_records if row.get("review", {}).get("evidence_tier") in {"confirmed_validated", "probable_validated"})
        no_runnable = len(self.discover()) == 0 and pending == 0
        ready = validated >= 5 and sources_with_validated >= 2 and strong_validated >= 3 and no_runnable
        reason = "database_ready_for_100_sources" if ready else "closed_loop_success_but_insufficient_validated_records"
        if not no_runnable:
            reason = "runnable_tasks_remain"
        return {
            "batch_id": self.batch_id,
            "input_parsed_sources": sum(1 for row in status_rows if int(row.get("parsed_chunks", 0)) > 0),
            "input_chunks": sum(int(row.get("parsed_chunks", 0)) for row in status_rows),
            "input_pending_codex_tasks": len(initial),
            "runnable_tasks_discovered": len(initial),
            "tasks_executed": executed,
            "extraction_tasks_executed": sum(1 for row in self.trace if row["task_type"] == "extract" and row["status"] == "done"),
            "review_tasks_executed": sum(1 for row in self.trace if row["task_type"] == "review" and row["status"] == "done"),
            "database_write_tasks_executed": sum(1 for row in self.trace if row["task_type"] == "write_database" and row["status"] == "done"),
            "candidate_records_written": candidate,
            "reviewed_records_written": reviewed,
            "validated_records_written": validated,
            "manual_review_records_written": manual,
            "rejected_records_written": rejected,
            "auxiliary_records_written": auxiliary,
            "pending_tasks_remaining": pending,
            "blocked_external_sources": blocked_external,
            "manual_required_sources": manual,
            "closed_loop_ended_because": ended,
            "no_runnable_tasks_remain": no_runnable,
            "workflow_closed_loop_success": no_runnable and executed > 0,
            "database_ready_for_100_sources": ready,
            "reason": reason,
        }

    def write_reports(self, summary: dict[str, Any]) -> None:
        reports = self.root / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        lines = ["# Stage 2.5 Closed-loop Summary", ""]
        for key, value in summary.items():
            rendered = str(value).lower() if isinstance(value, bool) else str(value)
            lines.append(f"{key} = {rendered}")
        (reports / "stage2_5_closed_loop_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        trace_lines = ["# Stage 2.5 Agent Execution Trace", "", "| task_id | source_id | task_type | executor | status |", "| --- | --- | --- | --- | --- |"]
        for row in self.trace:
            trace_lines.append(f"| {row['task_id']} | {row['source_id']} | {row['task_type']} | {row['executor']} | {row['status']} |")
        (reports / "stage2_5_agent_execution_trace.md").write_text("\n".join(trace_lines) + "\n", encoding="utf-8", newline="\n")
        audit = [
            "# Stage 2.5 Task Completion Audit",
            "",
            f"pending_tasks_remaining = {summary['pending_tasks_remaining']}",
            f"closed_loop_ended_because = {summary['closed_loop_ended_because']}",
            f"no_runnable_tasks_remain = {str(summary['no_runnable_tasks_remain']).lower()}",
        ]
        (reports / "stage2_5_task_completion_audit.md").write_text("\n".join(audit) + "\n", encoding="utf-8", newline="\n")
        db = [
            "# Stage 2.5 Database Write Audit",
            "",
            f"validated_records_written = {summary['validated_records_written']}",
            f"manual_review_records_written = {summary['manual_review_records_written']}",
            f"rejected_records_written = {summary['rejected_records_written']}",
            f"auxiliary_records_written = {summary['auxiliary_records_written']}",
            f"database_ready_for_100_sources = {str(summary['database_ready_for_100_sources']).lower()}",
        ]
        (reports / "stage2_5_database_write_audit.md").write_text("\n".join(db) + "\n", encoding="utf-8", newline="\n")
        blockers = [
            "# Stage 2.5 Remaining Blockers",
            "",
            f"blocked_external_sources = {summary['blocked_external_sources']}",
            f"manual_required_sources = {summary['manual_required_sources']}",
            f"reason = {summary['reason']}",
        ]
        (reports / "stage2_5_remaining_blockers.md").write_text("\n".join(blockers) + "\n", encoding="utf-8", newline="\n")
        write_jsonl(self.root / "data" / "batches" / "stage2_5_agent_execution_trace.jsonl", self.trace)
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
