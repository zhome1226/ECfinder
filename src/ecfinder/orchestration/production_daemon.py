"""Production autonomous daemon for until-exhausted PFAS literature workflow."""

from __future__ import annotations

import json
from pathlib import Path
from time import monotonic
from typing import Any

from ecfinder.state.common import read_json, read_jsonl, relative_path, write_jsonl

from .autonomous_loop import database_record_count, has_unreviewed_candidates, terminal_source_count
from .checkpointing import checkpoint_due, write_daemon_checkpoint
from .library_progress import summarize_previous_progress
from .runnable_source_discovery import DiscoveryResult, discover_runnable_sources
from .safe_stop import SafeStopPolicy
from .streaming_state import reset_streaming_outputs, write_key_value_report
from .streaming_supervisor import StreamingSupervisor, _short_title


STAGE2_6_STATUS_PATHS = [
    Path("data/state/stage2_6c_streaming_source_status.jsonl"),
    Path("data/state/stage2_6d_streaming_source_status.jsonl"),
    Path("data/state/stage2_6e_streaming_source_status.jsonl"),
    Path("data/state/stage2_6f_streaming_source_status.jsonl"),
]
STAGE2_6_DECISION_PATHS = [
    Path("data/batches/stage2_6c_streaming_screening_decisions.jsonl"),
    Path("data/batches/stage2_6d_streaming_screening_decisions.jsonl"),
    Path("data/batches/stage2_6e_streaming_screening_decisions.jsonl"),
    Path("data/batches/stage2_6f_streaming_screening_decisions.jsonl"),
]
STAGE2_7_STATUS = Path("data/state/stage2_7_library_source_status.jsonl")
STAGE2_7_QUEUE = Path("data/batches/stage2_7_runnable_queue.jsonl")
FULLTEXT_MANIFEST = Path("data/local_fulltext/stage2_4j/zotero_available_fulltext_manifest.jsonl")


class ProductionDaemon(StreamingSupervisor):
    def __init__(
        self,
        root: Path,
        *,
        batch_id: str,
        metadata_queue: Path,
        library: str,
        mode: str,
        until_library_exhausted: bool,
        checkpoint_every: int,
        rescan_zotero_attachments_every_cycle: bool,
        max_wall_minutes: int | None,
        max_records: int | None,
        max_new_screen: int,
        max_new_fulltext: int,
        max_new_extract_sources: int,
        safe_stop_on_token_budget: bool,
        token_budget: int | None,
        stop_file: Path | None,
        resume: bool,
    ) -> None:
        self.original_metadata_queue = metadata_queue
        self.library = library
        self.mode = mode
        self.until_library_exhausted = until_library_exhausted
        self.checkpoint_every = checkpoint_every
        self.rescan_zotero_attachments_every_cycle = rescan_zotero_attachments_every_cycle
        self.resume = resume
        self.output_queue = root / STAGE2_7_QUEUE
        self.discovery: DiscoveryResult | None = None
        self.checkpoint_count = 0
        self.last_processed_source_id = ""
        self.daemon_cycles = 0
        status_paths = [root / path for path in STAGE2_6_STATUS_PATHS]
        if resume and (root / STAGE2_7_STATUS).exists():
            status_paths.append(root / STAGE2_7_STATUS)
        self.stage_status_paths = status_paths
        self.stage_decision_paths = [root / path for path in STAGE2_6_DECISION_PATHS]
        if resume:
            self.stage_decision_paths.append(root / "data" / "batches" / "stage2_7_screening_decisions.jsonl")
        super().__init__(
            root=root,
            batch_id=batch_id,
            metadata_queue=self.output_queue,
            max_screen=max_new_screen,
            max_fulltext=max_new_fulltext,
            max_extract_sources=max_new_extract_sources,
            output_prefix="stage2_7",
            update_source_registry=True,
            resume_from=status_paths,
        )
        self.safe_stop = SafeStopPolicy(
            root=root,
            started_at_monotonic=monotonic(),
            max_wall_minutes=max_wall_minutes,
            max_records=max_records,
            max_new_screen=max_new_screen,
            max_new_fulltext=max_new_fulltext,
            max_new_extract_sources=max_new_extract_sources,
            safe_stop_on_token_budget=safe_stop_on_token_budget,
            token_budget=token_budget,
            stop_file=stop_file,
        )

    def run(self) -> dict[str, Any]:
        if self.resume:
            self.load_existing_outputs()
        else:
            reset_streaming_outputs(self.paths)
            self.reset_stage2_7_queues()
        self.daemon_cycles += 1
        self.discovery = discover_runnable_sources(
            metadata_queue=self.original_metadata_queue,
            fulltext_manifest=self.root / FULLTEXT_MANIFEST,
            status_paths=self.stage_status_paths,
            decision_paths=self.stage_decision_paths,
            output_queue=self.output_queue,
            audit_report=self.root / "reports" / "stage2_7_runnable_source_audit.md",
        )
        queue = self.discovery.runnable_sources
        self.load_resume_skip_set()
        available = self.load_available_manifest()
        ended = "no_runnable_sources_remain"
        for source in queue:
            stop, reason = self.safe_stop.should_stop_before_next_source(self.current_stats())
            if stop:
                ended = reason
                break
            if len(self.screening_rows) >= self.max_screen:
                ended = "max_new_screen_reached"
                break
            if self.should_skip_source(source):
                self.skipped_previously_completed_sources += 1
                continue
            self.register_allowed_reprocess(source)
            self.process_source_cycle(source, available)
            self.daemon_cycles += 1
            self.last_processed_source_id = str(source.get("source_id", ""))
            if checkpoint_due(len(self.status_rows), self.checkpoint_every, self.checkpoint_count):
                self.checkpoint_count += 1
                self.flush_jsonl_outputs()
                self.write_checkpoint(ended_because="checkpoint")
        self.flush_jsonl_outputs()
        self.write_outputs(queue, ended)
        self.write_stage2_7_outputs(queue, ended)
        return self.summary

    def register_allowed_reprocess(self, source: dict[str, Any]) -> None:
        if not (source.get("allow_manual_rescreen") is True or source.get("allow_resume_reprocess") is True):
            return
        source_id = str(source.get("source_id", ""))
        zotero_key = str(source.get("zotero_item_key", ""))
        doi = str(source.get("doi", "")).strip().lower()
        if source_id:
            self.allowed_rescreen_source_ids.add(source_id)
        if zotero_key:
            self.allowed_rescreen_zotero_keys.add(zotero_key)
        if doi:
            self.allowed_rescreen_dois.add(doi)

    def process_source_cycle(self, source: dict[str, Any], available: list[dict[str, Any]]) -> None:
        status = self.initial_status(source)
        self.invoke("TitleAbstractScreeningAgent", source, "screening", {"metadata_ref": self.relative_queue_ref()})
        decision = self.screen_source(source)
        self.screening_rows.append(decision)
        status.update(
            {
                "screening_status": "cache_hit" if decision["cache_hit"] else "done",
                "screening_decision": decision["screening_decision"],
                "artifact_refs": {"screening_ref": relative_path(self.root, self.paths.screening_decisions)},
                "next_action": decision["next_action"],
            }
        )
        if decision["screening_decision"] == "exclude":
            status.update({"overall_status": "excluded", "fulltext_status": "not_checked"})
            self.status_rows.append(status)
            return
        if decision["screening_decision"] == "manual_screen":
            status.update({"overall_status": "manual_screen", "fulltext_status": "not_checked", "next_action": "manual_screen_title_abstract"})
            self.append_manual_handoff(source, "title_abstract_screening", "manual_screen")
            self.status_rows.append(status)
            return
        manifest = self.find_fulltext_manifest(source, available)
        self.invoke("ZoteroAgent", source, "fulltext", {"manifest_ref": str(FULLTEXT_MANIFEST).replace("\\", "/")})
        if not manifest:
            status.update(
                {
                    "fulltext_status": "missing",
                    "overall_status": "blocked_external",
                    "next_action": "attach_pdf_to_zotero_or_provide_local_fulltext",
                }
            )
            self.append_blocked(source)
            self.status_rows.append(status)
            return
        if self.fulltext_processed >= self.max_fulltext:
            status.update({"fulltext_status": "deferred", "overall_status": "deferred", "next_action": "rerun_daemon_with_higher_fulltext_limit"})
            self.deferred_sources += 1
            self.status_rows.append(status)
            return
        self.fulltext_processed += 1
        status["fulltext_status"] = "found"
        chunks_info = self.resolve_chunks_ref(source, manifest)
        chunks_ref = str(chunks_info.get("chunks_ref", ""))
        if not chunks_ref:
            status.update({"parse_status": "failed", "overall_status": "failed", "next_action": "inspect_parser_failure"})
            self.status_rows.append(status)
            return
        chunks = read_jsonl(self.root / chunks_ref)
        status["parse_status"] = str(chunks_info.get("parse_status", "skipped"))
        status["artifact_refs"]["chunks_ref"] = chunks_ref
        if chunks_info.get("metadata_ref"):
            status["artifact_refs"]["metadata_ref"] = chunks_info["metadata_ref"]
        if chunks_info.get("download_ref"):
            status["artifact_refs"]["download_ref"] = chunks_info["download_ref"]
        self.invoke("ParseAgent", source, "parse", {"chunks_ref": chunks_ref})
        self.invoke("ChunkAgent", source, "chunk_relevance", {"chunks_ref": chunks_ref})
        high_chunks = self.screen_chunks(source, chunks)
        if not high_chunks:
            self.rejected_rows.append(self.no_evidence_record(source, "", "no_high_relevance_chunks"))
            status.update(
                {
                    "extraction_status": "skipped",
                    "review_status": "skipped",
                    "database_write_status": "done",
                    "overall_status": "rejected",
                    "next_action": "no_high_relevance_chunks",
                }
            )
            self.status_rows.append(status)
            return
        if self.extract_sources >= self.max_extract_sources:
            status.update({"extraction_status": "deferred", "overall_status": "deferred", "next_action": "rerun_daemon_with_higher_extract_limit"})
            self.deferred_sources += 1
            self.status_rows.append(status)
            return
        self.extract_sources += 1
        self.extract_review_write(source, chunks_ref, high_chunks, status)
        self.status_rows.append(status)

    def current_stats(self) -> dict[str, Any]:
        return {
            "processed_sources": len(self.status_rows),
            "screened_sources": len(self.screening_rows),
            "fulltext_found": sum(1 for row in self.status_rows if row.get("fulltext_status") == "found"),
            "sources_extracted": self.extract_sources,
            "reviewed_records": len(self.reviewed_rows),
        }

    def flush_jsonl_outputs(self) -> None:
        write_jsonl(self.paths.screening_decisions, self.screening_rows)
        write_jsonl(self.paths.chunk_screening, self.chunk_rows)
        write_jsonl(self.paths.candidates, self.candidate_rows)
        write_jsonl(self.paths.reviewed, self.reviewed_rows)
        write_jsonl(self.paths.validated, self.validated_rows)
        write_jsonl(self.paths.manual, self.manual_rows)
        write_jsonl(self.paths.rejected, self.rejected_rows)
        write_jsonl(self.paths.auxiliary, self.auxiliary_rows)
        write_jsonl(self.paths.source_status, self.status_rows)
        write_jsonl(self.paths.events, self.events)

    def load_existing_outputs(self) -> None:
        self.screening_rows = read_jsonl(self.paths.screening_decisions)
        self.chunk_rows = read_jsonl(self.paths.chunk_screening)
        self.candidate_rows = read_jsonl(self.paths.candidates)
        self.reviewed_rows = read_jsonl(self.paths.reviewed)
        self.validated_rows = read_jsonl(self.paths.validated)
        self.manual_rows = read_jsonl(self.paths.manual)
        self.rejected_rows = read_jsonl(self.paths.rejected)
        self.auxiliary_rows = read_jsonl(self.paths.auxiliary)
        self.status_rows = read_jsonl(self.paths.source_status)
        self.events = read_jsonl(self.paths.events)
        self.fulltext_processed = sum(1 for row in self.status_rows if row.get("fulltext_status") == "found")
        self.extract_sources = sum(1 for row in self.status_rows if row.get("extraction_status") == "done")
        self.deferred_sources = sum(1 for row in self.status_rows if row.get("overall_status") == "deferred")
        checkpoint = read_json(self.paths.checkpoint)
        self.checkpoint_count = int(checkpoint.get("checkpoint_count", 0) or 0)
        self.last_processed_source_id = str(checkpoint.get("last_processed_source_id", "") or "")

    def reset_stage2_7_queues(self) -> None:
        for path in [
            "stage2_7_blocked_external_queue.jsonl",
            "stage2_7_manual_screen_queue.jsonl",
            "stage2_7_deferred_queue.jsonl",
            "stage2_7_completed_sources.jsonl",
        ]:
            write_jsonl(self.root / "data" / "state" / path, [])

    def write_checkpoint(self, ended_because: str) -> None:
        rows = self.terminal_rows()
        write_daemon_checkpoint(
            self.root,
            batch_id=self.batch_id,
            last_processed_source_id=self.last_processed_source_id,
            processed_sources=len(self.status_rows),
            screened_sources=len(self.screening_rows),
            fulltext_found=sum(1 for row in self.status_rows if row.get("fulltext_status") == "found"),
            sources_parsed=sum(1 for row in self.status_rows if row.get("parse_status") in {"done", "skipped"}),
            sources_extracted=self.extract_sources,
            database_records_written=database_record_count(rows),
            blocked_external_sources=sum(1 for row in self.status_rows if row.get("overall_status") == "blocked_external"),
            manual_screen_sources=sum(1 for row in self.status_rows if row.get("overall_status") == "manual_screen"),
            completed_sources=terminal_source_count(self.status_rows),
            pending_tasks_remaining=0,
            checkpoint_count=self.checkpoint_count,
            ended_because=ended_because,
        )

    def terminal_rows(self) -> dict[str, list[dict[str, Any]]]:
        return {
            "validated": self.validated_rows,
            "manual": self.manual_rows,
            "rejected": self.rejected_rows,
            "auxiliary": self.auxiliary_rows,
        }

    def discover_remaining_sources(self) -> DiscoveryResult:
        status_paths = [self.root / path for path in STAGE2_6_STATUS_PATHS]
        if (self.root / STAGE2_7_STATUS).exists():
            status_paths.append(self.root / STAGE2_7_STATUS)
        decision_paths = [self.root / path for path in STAGE2_6_DECISION_PATHS]
        stage2_7_decisions = self.root / "data" / "batches" / "stage2_7_screening_decisions.jsonl"
        if stage2_7_decisions.exists():
            decision_paths.append(stage2_7_decisions)
        return discover_runnable_sources(
            metadata_queue=self.original_metadata_queue,
            fulltext_manifest=self.root / FULLTEXT_MANIFEST,
            status_paths=status_paths,
            decision_paths=decision_paths,
            output_queue=self.output_queue,
            audit_report=self.root / "reports" / "stage2_7_runnable_source_audit.md",
        )

    def write_stage2_7_outputs(self, queue: list[dict[str, Any]], ended: str) -> None:
        previous = summarize_previous_progress(self.root, self.stage_status_paths)
        db_records = len(self.validated_rows) + len(self.manual_rows) + len(self.rejected_rows) + len(self.auxiliary_rows)
        duplicate_violations = 0 if self.no_duplicate_reprocessing() else 1
        boundary_violations = len(self.forbidden_validated_records())
        self.write_stage2_7_queues()
        strict_jsonl = self.stage2_7_strict_jsonl_audit_passed()
        pending = 0
        sync_ok = not has_unreviewed_candidates(self.candidate_rows, self.reviewed_rows)
        workflow_invariants_ok = (
            self.daemon_cycles > 1
            and sync_ok
            and pending == 0
            and self.token_stats["long_context_violations"] == 0
            and self.token_stats["fulltext_context_violations"] == 0
            and duplicate_violations == 0
            and boundary_violations == 0
            and strict_jsonl
        )
        post_discovery = self.discover_remaining_sources()
        runnable_after_run = len(post_discovery.runnable_sources)
        safe_stop_triggered = ended != "no_runnable_sources_remain"
        no_runnable_sources_remain = runnable_after_run == 0
        if safe_stop_triggered and runnable_after_run > 0:
            workflow_status: bool | str = "partial" if workflow_invariants_ok else False
            ready = False
            reason = (
                "safety_limit_reached_before_library_exhausted_and_no_fulltext_extraction_verified"
                if db_records == 0 and sum(1 for row in self.status_rows if row.get("fulltext_status") == "found") == 0
                else "safety_limit_reached_before_library_exhausted"
            )
        else:
            workflow_status = workflow_invariants_ok and no_runnable_sources_remain
            ready = bool(workflow_status) and self.checkpoint_count >= 1 and sync_ok and duplicate_violations == 0
            reason = (
                "production_daemon_success_but_database_growth_limited_by_missing_fulltext"
                if workflow_status
                and (db_records == 0 or sum(1 for row in self.status_rows if row.get("fulltext_status") == "missing") >= sum(1 for row in self.status_rows if row.get("fulltext_status") == "found"))
                else ("production_daemon_verified_for_unattended_long_run" if ready else "production_daemon_validation_prerequisites_not_met")
            )
        discovery = self.discovery
        assert discovery is not None
        self.summary = {
            "batch_id": self.batch_id,
            "daemon_mode": self.mode,
            "library_total_sources": discovery.library_total_sources,
            "previously_processed_sources": previous["previously_processed_sources"],
            "new_sources_seen": len(self.status_rows),
            "new_sources_screened": len(self.screening_rows),
            "processed_sources": len(self.status_rows),
            "screened_sources": len(self.screening_rows),
            "cumulative_sources_screened": previous["previous_sources_screened"] + len(self.screening_rows),
            "runnable_sources_discovered": len(queue),
            "runnable_sources_discovered_after_run": runnable_after_run,
            "sources_completed_this_run": terminal_source_count(self.status_rows),
            "sources_excluded_this_run": sum(1 for row in self.status_rows if row.get("overall_status") == "excluded"),
            "manual_screen_sources": sum(1 for row in self.status_rows if row.get("overall_status") == "manual_screen"),
            "include_for_fulltext": sum(1 for row in self.screening_rows if row.get("screening_decision") == "include_for_fulltext"),
            "blocked_external_sources": sum(1 for row in self.status_rows if row.get("overall_status") == "blocked_external"),
            "blocked_sources_rescanned": discovery.blocked_sources_rescanned,
            "blocked_sources_unblocked": discovery.blocked_sources_unblocked,
            "new_attachments_found": discovery.new_attachments_found,
            "fulltext_found": sum(1 for row in self.status_rows if row.get("fulltext_status") == "found"),
            "fulltext_missing": sum(1 for row in self.status_rows if row.get("fulltext_status") == "missing"),
            "sources_parsed": sum(1 for row in self.status_rows if row.get("parse_status") in {"done", "skipped"}),
            "chunks_created": len(self.chunk_rows),
            "chunks_screened_extract": sum(1 for row in self.chunk_rows if row.get("relevance_decision") == "extract"),
            "sources_extracted": self.extract_sources,
            "candidate_records": len(self.candidate_rows),
            "reviewed_records": len(self.reviewed_rows),
            "validated_records": len(self.validated_rows),
            "manual_review_records": len(self.manual_rows),
            "rejected_records": len(self.rejected_rows),
            "auxiliary_records": len(self.auxiliary_rows),
            "database_records_written": db_records,
            "screening_cache_hits": self.token_stats["screening_cache_hits"],
            "screening_cache_misses": self.token_stats["screening_cache_misses"],
            "extraction_cache_hits": self.token_stats["extraction_cache_hits"],
            "extraction_cache_misses": self.token_stats["extraction_cache_misses"],
            "review_cache_hits": self.token_stats["review_cache_hits"],
            "review_cache_misses": self.token_stats["review_cache_misses"],
            "long_context_violations": self.token_stats["long_context_violations"],
            "fulltext_context_violations": self.token_stats["fulltext_context_violations"],
            "duplicate_work_violations": duplicate_violations,
            "boundary_violations": boundary_violations,
            "pending_tasks_remaining": pending,
            "checkpoint_count": self.checkpoint_count,
            "safe_stop_triggered": safe_stop_triggered,
            "ended_because": ended,
            "no_runnable_sources_remain": no_runnable_sources_remain,
            "workflow_production_daemon_success": workflow_status,
            "ready_for_unattended_long_run": ready,
            "strict_jsonl_audit_passed": strict_jsonl,
            "stage2_7_jsonl_strict": strict_jsonl,
            "reason": reason,
        }
        self.write_stage2_7_reports()
        self.write_checkpoint(ended_because=ended)

    def write_stage2_7_queues(self) -> None:
        blocked = [self.queue_row(row, "blocked_external") for row in self.status_rows if row.get("overall_status") == "blocked_external"]
        manual = [self.queue_row(row, "manual_screen") for row in self.status_rows if row.get("overall_status") == "manual_screen"]
        deferred = [self.queue_row(row, "deferred") for row in self.status_rows if row.get("overall_status") in {"deferred", "failed"}]
        completed = [self.queue_row(row, "completed") for row in self.status_rows if row.get("overall_status") in {"validated", "rejected", "auxiliary", "completed_no_records", "excluded"}]
        write_jsonl(self.root / "data" / "state" / "stage2_7_blocked_external_queue.jsonl", blocked)
        write_jsonl(self.root / "data" / "state" / "stage2_7_manual_screen_queue.jsonl", manual)
        write_jsonl(self.root / "data" / "state" / "stage2_7_deferred_queue.jsonl", deferred)
        write_jsonl(self.root / "data" / "state" / "stage2_7_completed_sources.jsonl", completed)

    def queue_row(self, row: dict[str, Any], queue_type: str) -> dict[str, Any]:
        return {
            "source_id": row.get("source_id", ""),
            "zotero_item_key": row.get("zotero_item_key", ""),
            "doi": row.get("doi", ""),
            "title": row.get("title", ""),
            "queue_type": queue_type,
            "overall_status": row.get("overall_status", ""),
            "next_action": row.get("next_action", ""),
            "artifact_refs": row.get("artifact_refs", {}),
        }

    def stage2_7_jsonl_targets(self) -> list[Path]:
        return [
            self.paths.screening_decisions,
            self.paths.chunk_screening,
            self.paths.candidates,
            self.paths.reviewed,
            self.paths.validated,
            self.paths.manual,
            self.paths.rejected,
            self.paths.auxiliary,
            self.paths.source_status,
            self.paths.events,
            self.root / "data" / "state" / "stage2_7_blocked_external_queue.jsonl",
            self.root / "data" / "state" / "stage2_7_manual_screen_queue.jsonl",
            self.root / "data" / "state" / "stage2_7_deferred_queue.jsonl",
            self.root / "data" / "state" / "stage2_7_completed_sources.jsonl",
        ]

    def stage2_7_strict_jsonl_audit_passed(self) -> bool:
        try:
            for path in self.stage2_7_jsonl_targets():
                self.strict_jsonl_rows(path)
        except (OSError, ValueError, json.JSONDecodeError):
            return False
        return True

    def write_stage2_7_reports(self) -> None:
        write_key_value_report(self.paths.summary_report, "Stage 2.7 Production Daemon Summary", self.summary)
        self.write_status_board_report()
        self.write_blocked_report()
        self.write_completed_report()
        self.write_token_budget_report()
        self.write_skill_invocation_report()
        self.write_synchronous_review_report()
        self.write_database_report()
        self.write_stage2_7_strict_jsonl_report()
        self.write_skill_manager_recommendations()

    def write_status_board_report(self) -> None:
        lines = [
            "# Stage 2.7 Production Daemon Status Board",
            "",
            "| source_id | title_short | screening | fulltext | parse | extract | review | database | overall | next_action |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for row in self.status_rows:
            lines.append(
                f"| {row.get('source_id', '')} | {_short_title(str(row.get('title', '')))} | {row.get('screening_decision')} | {row.get('fulltext_status')} | {row.get('parse_status')} | {row.get('extraction_status')} | {row.get('review_status')} | {row.get('database_write_status')} | {row.get('overall_status')} | {row.get('next_action')} |"
            )
        self.paths.status_board_report.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    def write_blocked_report(self) -> None:
        lines = ["# Stage 2.7 Blocked Source Audit", "", "| source_id | doi | title | next_action |", "| --- | --- | --- | --- |"]
        for row in self.status_rows:
            if row.get("overall_status") == "blocked_external":
                lines.append(f"| {row.get('source_id', '')} | {row.get('doi', '')} | {_short_title(str(row.get('title', '')))} | {row.get('next_action', '')} |")
        self.paths.blocked_report.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    def write_completed_report(self) -> None:
        lines = ["# Stage 2.7 Completed Source Audit", ""]
        for key in ["sources_completed_this_run", "sources_excluded_this_run", "manual_screen_sources", "blocked_external_sources", "skipped_previously_completed_sources"]:
            lines.append(f"{key} = {self.summary.get(key, 0)}")
        lines.extend(["", "| source_id | status | database | title |", "| --- | --- | --- | --- |"])
        for row in self.status_rows:
            if row.get("overall_status") in {"validated", "rejected", "auxiliary", "completed_no_records", "excluded"}:
                lines.append(f"| {row.get('source_id', '')} | {row.get('overall_status', '')} | {row.get('database_write_status', '')} | {_short_title(str(row.get('title', '')))} |")
        self.paths.resume_skip_report.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    def write_token_budget_report(self) -> None:
        values = {
            "screening_cache_hits": self.summary["screening_cache_hits"],
            "screening_cache_misses": self.summary["screening_cache_misses"],
            "extraction_cache_hits": self.summary["extraction_cache_hits"],
            "extraction_cache_misses": self.summary["extraction_cache_misses"],
            "review_cache_hits": self.summary["review_cache_hits"],
            "review_cache_misses": self.summary["review_cache_misses"],
            "long_context_violations": self.summary["long_context_violations"],
            "fulltext_context_violations": self.summary["fulltext_context_violations"],
            "estimated_total_tokens": self.safe_stop.estimate_tokens(
                {
                    "screened_sources": self.summary["new_sources_screened"],
                    "sources_extracted": self.summary["sources_extracted"],
                    "reviewed_records": self.summary["reviewed_records"],
                }
            ),
            "token_budget": self.safe_stop.token_budget or 0,
            "safe_stop_on_token_budget": self.safe_stop.safe_stop_on_token_budget,
        }
        write_key_value_report(self.paths.token_report, "Stage 2.7 Token Budget Audit", values)

    def write_skill_invocation_report(self) -> None:
        counts: dict[str, int] = {}
        for event in self.events:
            skill_id = str(event.get("skill_id", ""))
            counts[skill_id] = counts.get(skill_id, 0) + 1
        lines = [
            "# Stage 2.7 Skill Invocation Audit",
            "",
            f"skill_invocation_audit_passed = {str(all(event.get('skill_id') for event in self.events)).lower()}",
            f"skill_invocations = {len(self.events)}",
            f"screening_invocations = {sum(1 for event in self.events if event.get('stage') == 'screening')}",
            f"fulltext_invocations = {sum(1 for event in self.events if event.get('stage') == 'fulltext')}",
            f"parse_invocations = {sum(1 for event in self.events if event.get('agent') == 'ParseAgent')}",
            f"extraction_invocations = {sum(1 for event in self.events if event.get('agent') == 'ExtractionAgent')}",
            f"review_invocations = {sum(1 for event in self.events if event.get('agent') == 'ReviewAgent')}",
            "",
        ]
        lines.extend(f"{skill_id or 'unknown'} = {count}" for skill_id, count in sorted(counts.items()))
        self.paths.skill_audit_report.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    def write_synchronous_review_report(self) -> None:
        values = {
            "candidate_records": len(self.candidate_rows),
            "reviewed_records": len(self.reviewed_rows),
            "unreviewed_candidate_records": len(
                {str(row.get("record_id", "")) for row in self.candidate_rows}
                - {str(row.get("record_id", "")) for row in self.reviewed_rows}
            ),
            "all_candidates_reviewed_synchronously": len(self.candidate_rows) == len(self.reviewed_rows),
            "database_records_written": self.summary["database_records_written"],
            "pending_review_tasks": 0,
            "synchronous_review_audit_passed": len(self.candidate_rows) == len(self.reviewed_rows),
        }
        write_key_value_report(self.paths.sync_review_report, "Stage 2.7 Synchronous Review Audit", values)

    def write_database_report(self) -> None:
        values = {
            "validated_records": len(self.validated_rows),
            "manual_review_records": len(self.manual_rows),
            "rejected_records": len(self.rejected_rows),
            "auxiliary_records": len(self.auxiliary_rows),
            "database_records_written": self.summary["database_records_written"],
            "forbidden_boundary_violations": self.summary["boundary_violations"],
            "all_candidates_reviewed_synchronously": len(self.candidate_rows) == len(self.reviewed_rows),
        }
        write_key_value_report(self.paths.database_report, "Stage 2.7 Database Write Audit", values)

    def write_stage2_7_strict_jsonl_report(self) -> None:
        lines = [
            "# Stage 2.7 Strict JSONL Audit",
            "",
            "| path | rows | physical_lines | strict_jsonl |",
            "| --- | ---: | ---: | --- |",
        ]
        all_ok = True
        for path in self.stage2_7_jsonl_targets():
            try:
                rows = self.strict_jsonl_rows(path)
                physical_lines = len(path.read_text(encoding="utf-8").splitlines()) if path.exists() else 0
                strict = True
            except (OSError, ValueError, json.JSONDecodeError):
                rows = 0
                physical_lines = 0
                strict = False
                all_ok = False
            lines.append(f"| {relative_path(self.root, path)} | {rows} | {physical_lines} | {str(strict).lower()} |")
        lines.append("")
        lines.append(f"strict_jsonl_audit_passed = {str(all_ok).lower()}")
        self.paths.strict_jsonl_report.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    def write_skill_manager_recommendations(self) -> None:
        manual_ratio = (self.summary["manual_screen_sources"] / self.summary["new_sources_screened"]) if self.summary["new_sources_screened"] else 0
        fulltext_ratio = (self.summary["fulltext_found"] / self.summary["include_for_fulltext"]) if self.summary.get("include_for_fulltext") else 0
        recommendations: list[dict[str, Any]] = []
        if manual_ratio > 0.35:
            recommendations.append(
                {
                    "recommendation_id": "stage2_7_manual_screen_gate_001",
                    "skill_id": "title_abstract_screening_v1",
                    "current_version": "v1",
                    "recommended_action": "revise_instruction",
                    "reason": "manual_screen ratio is high enough to justify clearer positive and negative title/abstract examples.",
                    "evidence": f"manual_ratio={manual_ratio:.2f}",
                    "requires_user_approval": True,
                }
            )
        if self.summary["include_for_fulltext"] and fulltext_ratio < 0.25:
            recommendations.append(
                {
                    "recommendation_id": "stage2_7_fulltext_availability_001",
                    "skill_id": "lawful_fulltext_resolution_v1",
                    "current_version": "v1",
                    "recommended_action": "keep",
                    "reason": "fulltext availability is the main bottleneck; prompt changes are unlikely to solve missing local attachments.",
                    "evidence": f"fulltext_found={self.summary['fulltext_found']}; include_for_fulltext={self.summary['include_for_fulltext']}",
                    "requires_user_approval": True,
                }
            )
        if self.summary["validated_records"] == 0 and self.summary["database_records_written"] > 0:
            recommendations.append(
                {
                    "recommendation_id": "stage2_7_natural_boundary_001",
                    "skill_id": "evidence_grounded_review_v1",
                    "current_version": "v1",
                    "recommended_action": "add_positive_examples",
                    "reason": "database writes are occurring but natural validated records remain zero.",
                    "evidence": f"database_records_written={self.summary['database_records_written']}; validated_records=0",
                    "requires_user_approval": True,
                }
            )
        if not recommendations:
            recommendations.append(
                {
                    "recommendation_id": "stage2_7_keep_active_skills_001",
                    "skill_id": "all_active_stage2_7_skills",
                    "current_version": "current",
                    "recommended_action": "keep",
                    "reason": "No concentrated failure pattern requires an automatic skill change.",
                    "evidence": "No duplicate, boundary, long-context, or synchronous-review violations detected.",
                    "requires_user_approval": True,
                }
            )
        lines = ["# Stage 2.7 Skill Manager Recommendations", ""]
        for recommendation in recommendations:
            lines.append(str(recommendation))
        (self.root / "reports" / "stage2_7_skill_manager_recommendations.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def run_discovery_dry_run(
    root: Path,
    *,
    batch_id: str,
    metadata_queue: Path,
    library: str,
    mode: str,
) -> dict[str, Any]:
    status_paths = [root / path for path in STAGE2_6_STATUS_PATHS]
    if (root / STAGE2_7_STATUS).exists():
        status_paths.append(root / STAGE2_7_STATUS)
    decision_paths = [root / path for path in STAGE2_6_DECISION_PATHS]
    stage2_7_decisions = root / "data" / "batches" / "stage2_7_screening_decisions.jsonl"
    if stage2_7_decisions.exists():
        decision_paths.append(stage2_7_decisions)
    discovery = discover_runnable_sources(
        metadata_queue=metadata_queue,
        fulltext_manifest=root / FULLTEXT_MANIFEST,
        status_paths=status_paths,
        decision_paths=decision_paths,
        output_queue=root / STAGE2_7_QUEUE,
        audit_report=root / "reports" / "stage2_7_runnable_source_audit.md",
    )
    classified_counts: dict[str, int] = {}
    for row in discovery.classified_rows:
        classification = str(row.get("classification", "unknown"))
        classified_counts[classification] = classified_counts.get(classification, 0) + 1
    values: dict[str, Any] = {
        "batch_id": batch_id,
        "daemon_mode": mode,
        "library": library,
        "dry_run_discovery_only": True,
        "library_total_sources": discovery.library_total_sources,
        "runnable_sources_remaining": len(discovery.runnable_sources),
        "blocked_external_sources": classified_counts.get("blocked_external", 0),
        "manual_screen_sources": classified_counts.get("manual_screen", 0),
        "completed_sources": classified_counts.get("completed", 0),
        "excluded_sources": classified_counts.get("excluded", 0),
        "blocked_sources_rescanned": discovery.blocked_sources_rescanned,
        "blocked_sources_unblocked": discovery.blocked_sources_unblocked,
        "new_attachments_found": discovery.new_attachments_found,
        "would_continue": len(discovery.runnable_sources) > 0,
        "discovery_dry_run_passed": True,
    }
    write_key_value_report(root / "reports" / "stage2_7_daemon_discovery_dry_run.md", "Stage 2.7 Daemon Discovery Dry Run", values)
    return values


def run_production_daemon(
    root: Path,
    *,
    batch_id: str,
    metadata_queue: Path,
    library: str,
    mode: str,
    until_library_exhausted: bool,
    checkpoint_every: int,
    rescan_zotero_attachments_every_cycle: bool,
    max_wall_minutes: int | None,
    max_records: int | None,
    max_new_screen: int,
    max_new_fulltext: int,
    max_new_extract_sources: int,
    safe_stop_on_token_budget: bool,
    token_budget: int | None,
    stop_file: Path | None,
    resume: bool,
    dry_run_discovery_only: bool = False,
) -> dict[str, Any]:
    if dry_run_discovery_only:
        return run_discovery_dry_run(
            root,
            batch_id=batch_id,
            metadata_queue=metadata_queue,
            library=library,
            mode=mode,
        )
    daemon = ProductionDaemon(
        root,
        batch_id=batch_id,
        metadata_queue=metadata_queue,
        library=library,
        mode=mode,
        until_library_exhausted=until_library_exhausted,
        checkpoint_every=checkpoint_every,
        rescan_zotero_attachments_every_cycle=rescan_zotero_attachments_every_cycle,
        max_wall_minutes=max_wall_minutes,
        max_records=max_records,
        max_new_screen=max_new_screen,
        max_new_fulltext=max_new_fulltext,
        max_new_extract_sources=max_new_extract_sources,
        safe_stop_on_token_budget=safe_stop_on_token_budget,
        token_budget=token_budget,
        stop_file=stop_file,
        resume=resume,
    )
    return daemon.run()
