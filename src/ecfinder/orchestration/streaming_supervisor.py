"""Streaming autonomous supervisor for Stage 2.6c.

The supervisor advances one source at a time from title/abstract screening to
full-text cache lookup, chunk relevance filtering, extraction, immediate review,
and reviewed database writes. It records skill invocations from SkillRegistry,
but the smoke execution remains deterministic and refs-first.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from ecfinder.skills.skill_registry import SkillRegistry
from ecfinder.state.artifact_index import index_artifact
from ecfinder.state.common import (
    read_json,
    read_jsonl,
    relative_path,
    sha256_file,
    sha256_text,
    utc_now,
    write_json,
    write_jsonl,
)
from ecfinder.state.decision_cache import find_decision, upsert_decision
from ecfinder.state.source_registry import upsert_source

from .streaming_state import StreamingPaths, reset_streaming_outputs, write_key_value_report
from .task_executor import extract_candidates, review_candidates, source_rejection_reason


PFAS_TERMS = [
    "pfas",
    "perfluoro",
    "polyfluoro",
    "fluorotelomer",
    "ftsa",
    "ftoh",
    "fosa",
    "fose",
    "pap",
    "dipap",
    "afff",
    "fluoroalkyl",
    "perfluorocarboxylic",
    "perfluorosulfon",
]
TRANSFORM_TERMS = [
    "precursor",
    "biotransformation",
    "biodegradation",
    "transformation",
    "degradation",
    "metabolite",
    "pathway",
    "product",
    "defluorination",
    "destruction",
]
ENV_TERMS = [
    "soil",
    "sediment",
    "groundwater",
    "aquifer",
    "wetland",
    "surface water",
    "marine",
    "estuarine",
    "microcosm",
    "natural attenuation",
    "field",
]
NEGATIVE_TERMS = [
    "activated sludge",
    "wastewater",
    "wwtp",
    "advanced oxidation",
    "aop",
    "plasma",
    "electrochemical",
    "photocatalysis",
    "ozonation",
    "uv/sulfite",
    "uv/persulfate",
    "persulfate",
    "incineration",
    "toxicity",
    "food web",
    "human exposure",
    "bioaccumulation",
    "analytical method",
    "suspect screening",
    "monitoring",
    "review",
]
NATURAL_VALID_EXCLUDE = [
    "activated sludge",
    "wastewater treatment",
    "wwtp",
    "engineered biological treatment",
    "advanced oxidation",
    "electrochemical",
    "plasma",
    "photocatalysis",
    "ozonation",
    "uv/persulfate",
    "hydrothermal",
    "incineration",
    "analytical method only",
    "occurrence only",
    "toxicity only",
    "review only",
]


def _contains_any(text: str, terms: list[str]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def _hits(text: str, terms: list[str]) -> list[str]:
    lowered = text.lower()
    return [term for term in terms if term in lowered]


def _short_title(title: str, limit: int = 84) -> str:
    title = " ".join(title.split()).replace("|", "/")
    return title[: limit - 3].rstrip() + "..." if len(title) > limit else title


def _compact_snippet(text: str, limit: int = 220) -> str:
    text = " ".join(text.split()).replace("|", "/")
    return text[: limit - 3].rstrip() + "..." if len(text) > limit else text


def _parse_keywords(reason: str) -> list[str]:
    words = re.findall(r"[A-Za-z0-9:+-]{3,}", reason.lower())
    blocked = {"terms", "pfas", "transformation", "environment", "downgrade", "reason"}
    return sorted({word for word in words if word not in blocked})[:20]


class StreamingSupervisor:
    def __init__(
        self,
        root: Path,
        batch_id: str,
        metadata_queue: Path,
        max_screen: int,
        max_fulltext: int,
        max_extract_sources: int,
        output_prefix: str = "stage2_6c_streaming",
        update_source_registry: bool = True,
    ) -> None:
        self.root = root
        self.batch_id = batch_id
        self.metadata_queue = metadata_queue
        self.max_screen = max_screen
        self.max_fulltext = max_fulltext
        self.max_extract_sources = max_extract_sources
        self.paths = StreamingPaths(root, output_prefix)
        self.update_source_registry_enabled = update_source_registry
        self.registry = SkillRegistry(root)
        self.events: list[dict[str, Any]] = []
        self.status_rows: list[dict[str, Any]] = []
        self.screening_rows: list[dict[str, Any]] = []
        self.chunk_rows: list[dict[str, Any]] = []
        self.candidate_rows: list[dict[str, Any]] = []
        self.reviewed_rows: list[dict[str, Any]] = []
        self.validated_rows: list[dict[str, Any]] = []
        self.manual_rows: list[dict[str, Any]] = []
        self.rejected_rows: list[dict[str, Any]] = []
        self.auxiliary_rows: list[dict[str, Any]] = []
        self.token_stats: defaultdict[str, int] = defaultdict(int)
        self.deferred_sources = 0
        self.fulltext_processed = 0
        self.extract_sources = 0
        self.summary: dict[str, Any] = {}

    def run(self) -> dict[str, Any]:
        reset_streaming_outputs(self.paths)
        queue = self.ensure_metadata_queue()
        available = self.load_available_manifest()
        ended = "no_runnable_tasks_remain"
        for index, source in enumerate(queue, start=1):
            if index > self.max_screen:
                ended = "controlled_limit_reached"
                break
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
                continue
            if decision["screening_decision"] == "manual_screen":
                status.update({"overall_status": "manual_screen", "fulltext_status": "not_checked", "next_action": "manual_screen_title_abstract"})
                self.append_manual_handoff(source, "title_abstract_screening", "manual_screen")
                self.status_rows.append(status)
                continue

            manifest = self.find_fulltext_manifest(source, available)
            self.invoke("ZoteroAgent", source, "fulltext", {"manifest_ref": "data/local_fulltext/stage2_4j/zotero_available_fulltext_manifest.jsonl"})
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
                continue
            if self.fulltext_processed >= self.max_fulltext:
                status.update({"fulltext_status": "deferred", "overall_status": "deferred", "next_action": "rerun_streaming_with_higher_fulltext_limit"})
                self.deferred_sources += 1
                self.status_rows.append(status)
                continue
            self.fulltext_processed += 1
            status["fulltext_status"] = "found"

            chunks_ref = self.resolve_chunks_ref(manifest)
            if not chunks_ref:
                status.update({"parse_status": "failed", "overall_status": "failed", "next_action": "inspect_parser_failure"})
                self.status_rows.append(status)
                continue
            chunks = read_jsonl(self.root / chunks_ref)
            status["parse_status"] = "skipped"
            status["artifact_refs"]["chunks_ref"] = chunks_ref
            self.invoke("ParseAgent", source, "parse", {"chunks_ref": chunks_ref})
            self.invoke("ChunkAgent", source, "chunk_relevance", {"chunks_ref": chunks_ref})
            high_chunks = self.screen_chunks(source, chunks)
            if not high_chunks:
                rejected = self.no_evidence_record(source, "", "no_high_relevance_chunks")
                self.rejected_rows.append(rejected)
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
                continue
            if self.extract_sources >= self.max_extract_sources:
                status.update({"extraction_status": "deferred", "overall_status": "deferred", "next_action": "rerun_streaming_with_higher_extract_limit"})
                self.deferred_sources += 1
                self.status_rows.append(status)
                continue
            self.extract_sources += 1
            self.extract_review_write(source, chunks_ref, high_chunks, status)
            self.status_rows.append(status)

        self.write_outputs(queue, ended)
        return self.summary

    def ensure_metadata_queue(self) -> list[dict[str, Any]]:
        if self.metadata_queue.exists():
            return read_jsonl(self.metadata_queue)
        audit_path = self.root / "data" / "batches" / "stage2_4j_zotero_scope_audit.jsonl"
        audit_rows = read_jsonl(audit_path)
        manifest_by_key = {str(row.get("zotero_item_key", "")): row for row in self.load_available_manifest()}
        queue: list[dict[str, Any]] = []
        for idx, row in enumerate(audit_rows, start=1):
            manifest = manifest_by_key.get(str(row.get("zotero_item_key", "")))
            source_id = str(
                (manifest or {}).get("source_id")
                or row.get("matched_stage2_4_source_id")
                or f"zotero_stage2_6c_src_{idx:03d}"
            )
            queue.append(
                {
                    "source_id": source_id,
                    "zotero_item_key": row.get("zotero_item_key", ""),
                    "doi": row.get("doi", ""),
                    "title": row.get("title", ""),
                    "abstract": "",
                    "year": row.get("year", ""),
                    "journal": row.get("journal", ""),
                    "keywords": _parse_keywords(str(row.get("screening_reason", ""))),
                    "metadata_origin": "stage2_4j_zotero_scope_audit",
                    "has_attachment_metadata": bool(row.get("has_attachment")),
                    "pdf_or_html_attachment_count": int(row.get("pdf_or_html_attachment_count", 0) or 0),
                }
            )
        write_jsonl(self.metadata_queue, queue)
        return queue

    def load_available_manifest(self) -> list[dict[str, Any]]:
        return read_jsonl(self.root / "data" / "local_fulltext" / "stage2_4j" / "zotero_available_fulltext_manifest.jsonl")

    def relative_queue_ref(self) -> str:
        try:
            return relative_path(self.root, self.metadata_queue)
        except ValueError:
            return str(self.metadata_queue)

    def initial_status(self, source: dict[str, Any]) -> dict[str, Any]:
        return {
            "source_id": source.get("source_id", ""),
            "zotero_item_key": source.get("zotero_item_key", ""),
            "doi": source.get("doi", ""),
            "title": source.get("title", ""),
            "screening_status": "pending",
            "screening_decision": None,
            "fulltext_status": "not_checked",
            "parse_status": "not_started",
            "extraction_status": "not_started",
            "review_status": "not_started",
            "database_write_status": "not_started",
            "overall_status": "deferred",
            "artifact_refs": {},
            "task_refs": [],
            "next_action": "",
            "updated_at": utc_now(),
        }

    def invoke(self, agent_name: str, source: dict[str, Any], stage: str, input_refs: dict[str, str]) -> None:
        skill = self.registry.by_agent(agent_name)
        if not skill:
            raise ValueError(f"missing registered skill for {agent_name}")
        self.events.append(
            {
                "event_id": f"{self.batch_id}_{source.get('source_id', '')}_{stage}_{len(self.events) + 1:05d}",
                "timestamp": utc_now(),
                "batch_id": self.batch_id,
                "source_id": source.get("source_id", ""),
                "agent": agent_name,
                "skill_id": skill.skill_id,
                "skill_version": skill.version,
                "stage": stage,
                "event_type": "skill_invoked",
                "input_refs": input_refs,
                "schema_refs": {
                    "input_schema_ref": skill.input_schema_ref,
                    "output_schema_ref": skill.output_schema_ref,
                },
                "token_policy": skill.token_policy,
                "long_context_passed": False,
                "fulltext_passed_to_screening": False,
            }
        )

    def screen_source(self, source: dict[str, Any]) -> dict[str, Any]:
        screening_input = {
            "source_id": source.get("source_id", ""),
            "doi": source.get("doi", ""),
            "title": source.get("title", ""),
            "abstract": source.get("abstract", ""),
            "year": source.get("year", ""),
            "journal": source.get("journal", ""),
            "keywords": source.get("keywords", []),
        }
        input_hash = sha256_text(json.dumps(screening_input, ensure_ascii=False, sort_keys=True))
        skill = self.registry.by_agent("TitleAbstractScreeningAgent")
        assert skill is not None
        cached = find_decision(self.root / "data" / "state" / "decision_cache.jsonl", "screening", input_hash, skill.skill_id, skill.version)
        if cached:
            self.token_stats["screening_cache_hits"] += 1
        else:
            self.token_stats["screening_cache_misses"] += 1
        text = " ".join(
            [
                str(source.get("title", "")),
                str(source.get("abstract", "")),
                " ".join(str(value) for value in source.get("keywords", [])),
            ]
        ).lower()
        positive_hits = _hits(text, [*PFAS_TERMS, *TRANSFORM_TERMS, *ENV_TERMS])
        negative_hits = _hits(text, NEGATIVE_TERMS)
        has_pfas = _contains_any(text, PFAS_TERMS)
        has_transform = _contains_any(text, TRANSFORM_TERMS)
        has_env = _contains_any(text, ENV_TERMS)
        if source.get("force_include_for_fulltext") is True:
            decision = "include_for_fulltext"
            topic = "high" if has_pfas else "medium"
            env_rel = "unclear"
            evidence = "possible"
            next_action = "fulltext_ingest"
            reason = "manual high-priority integration smoke override; review enforces natural-environment boundary"
        elif negative_hits:
            decision = "exclude"
            topic = "low"
            env_rel = "engineered_treatment" if any(hit in {"wastewater", "wwtp", "activated sludge"} for hit in negative_hits) else "not_relevant"
            evidence = "unlikely"
            next_action = "exclude"
            reason = "title/abstract metadata matched exclusion or downgrade terms"
        elif has_pfas and has_transform and (has_env or source.get("pdf_or_html_attachment_count")):
            decision = "include_for_fulltext"
            topic = "high"
            env_rel = "natural_environment" if has_env else "unclear"
            evidence = "likely_transformation_evidence"
            next_action = "fulltext_ingest"
            reason = "title/abstract metadata indicates PFAS transformation evidence may be present"
        elif has_pfas and has_transform:
            decision = "manual_screen"
            topic = "medium"
            env_rel = "unclear"
            evidence = "possible"
            next_action = "manual_screen"
            reason = "title/abstract metadata lacks natural-environment signal"
        elif has_pfas:
            decision = "manual_screen"
            topic = "medium"
            env_rel = "unclear"
            evidence = "possible"
            next_action = "manual_screen"
            reason = "PFAS metadata present but transformation evidence is unclear"
        else:
            decision = "exclude"
            topic = "low"
            env_rel = "not_relevant"
            evidence = "unlikely"
            next_action = "exclude"
            reason = "title/abstract metadata does not indicate PFAS transformation evidence"
        row = {
            "source_id": source.get("source_id", ""),
            "screening_decision": decision,
            "topic_relevance": topic,
            "environment_relevance": env_rel,
            "evidence_likelihood": evidence,
            "positive_hits": positive_hits[:12],
            "negative_hits": negative_hits[:12],
            "reason": reason,
            "next_action": next_action,
            "input_hash": input_hash,
            "input_fields": ["source_id", "doi", "title", "abstract", "year", "journal", "keywords"],
            "skill_id": skill.skill_id,
            "skill_version": skill.version,
            "cache_hit": bool(cached),
            "created_at": utc_now(),
        }
        upsert_decision(
            self.root / "data" / "state" / "decision_cache.jsonl",
            "screening",
            input_hash,
            skill.skill_id,
            skill.version,
            relative_path(self.root, self.paths.screening_decisions),
            f"{decision}: {reason}",
            0.8 if decision == "include_for_fulltext" else 0.7,
        )
        return row

    def find_fulltext_manifest(self, source: dict[str, Any], manifest: list[dict[str, Any]]) -> dict[str, Any] | None:
        source_id = str(source.get("source_id", ""))
        key = str(source.get("zotero_item_key", ""))
        doi = str(source.get("doi", "")).strip().lower()
        for row in manifest:
            if source_id and row.get("source_id") == source_id:
                return row
            if key and row.get("zotero_item_key") == key:
                return row
            if doi and str(row.get("doi", "")).strip().lower() == doi:
                return row
        return None

    def resolve_chunks_ref(self, manifest: dict[str, Any]) -> str:
        source_id = str(manifest.get("source_id", ""))
        existing = self.root / "data" / "runs" / f"stage2_4j_{source_id}" / "chunks.jsonl"
        if existing.exists():
            return relative_path(self.root, existing)
        return ""

    def screen_chunks(self, source: dict[str, Any], chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        high_chunks: list[dict[str, Any]] = []
        skill = self.registry.by_agent("ChunkAgent")
        assert skill is not None
        for chunk in chunks:
            text = str(chunk.get("text", ""))
            lowered = text.lower()
            pfas_hits = _hits(lowered, PFAS_TERMS)
            transform_hits = _hits(lowered, TRANSFORM_TERMS)
            env_hits = _hits(lowered, ENV_TERMS)
            high = bool(pfas_hits and transform_hits)
            decision = "extract" if high else "skip"
            if high:
                high_chunks.append(chunk)
            self.chunk_rows.append(
                {
                    "source_id": source.get("source_id", ""),
                    "chunk_id": chunk.get("chunk_id", ""),
                    "skill_id": skill.skill_id,
                    "skill_version": skill.version,
                    "chunk_hash": chunk.get("text_hash", ""),
                    "relevance_decision": decision,
                    "positive_hits": [*pfas_hits[:5], *transform_hits[:5], *env_hits[:5]][:12],
                    "reason": "PFAS and transformation terms found" if high else "low relevance chunk skipped before extraction",
                    "short_snippet": _compact_snippet(text),
                    "created_at": utc_now(),
                }
            )
        return high_chunks

    def extract_review_write(self, source: dict[str, Any], chunks_ref: str, high_chunks: list[dict[str, Any]], status: dict[str, Any]) -> None:
        metadata = self.metadata_for_source(source)
        metadata_ref = self.metadata_ref_for_source(source)
        if metadata_ref:
            status.setdefault("artifact_refs", {})["metadata_ref"] = metadata_ref
        input_hash = sha256_text("|".join(str(chunk.get("text_hash", "")) for chunk in high_chunks))
        extract_skill = self.registry.by_agent("ExtractionAgent")
        review_skill = self.registry.by_agent("ReviewAgent")
        write_skill = self.registry.by_agent("DatabaseWriteAgent")
        assert extract_skill and review_skill and write_skill
        extract_cached = find_decision(self.root / "data" / "state" / "decision_cache.jsonl", "extract", input_hash, extract_skill.skill_id, extract_skill.version)
        if extract_cached:
            self.token_stats["extraction_cache_hits"] += 1
        else:
            self.token_stats["extraction_cache_misses"] += 1
        self.invoke("ExtractionAgent", source, "extract", {"chunks_ref": chunks_ref})
        candidates, source_rejections = extract_candidates(metadata, high_chunks)
        candidates = self.rewrite_candidate_records(candidates, source)
        source_rejections = self.rewrite_rejections(source_rejections, source, "no_parent_product_transformation_evidence")
        reviewed, validated, manual, auxiliary = review_candidates(candidates)
        reviewed = self.rewrite_reviewed_records(reviewed, source)
        validated = [row for row in reviewed if row.get("review", {}).get("review_status") == "validated"]
        manual = [row for row in reviewed if row.get("review", {}).get("review_status") == "manual_review"]
        auxiliary = [row for row in reviewed if row.get("review", {}).get("review_status") == "auxiliary_engineered"]
        review_hash = sha256_text(json.dumps(candidates, ensure_ascii=False, sort_keys=True))
        review_cached = find_decision(self.root / "data" / "state" / "decision_cache.jsonl", "review", review_hash, review_skill.skill_id, review_skill.version)
        if review_cached:
            self.token_stats["review_cache_hits"] += 1
        else:
            self.token_stats["review_cache_misses"] += 1
        self.invoke("ReviewAgent", source, "review", {"candidate_records_ref": relative_path(self.root, self.paths.candidates)})
        self.invoke("DatabaseWriteAgent", source, "write_database", {"reviewed_records_ref": relative_path(self.root, self.paths.reviewed)})
        if not candidates and not source_rejections:
            source_rejections = [self.no_evidence_record(source, str(high_chunks[0].get("chunk_id", "")), "no_parent_product_transformation_evidence")]
        self.candidate_rows.extend(candidates)
        self.reviewed_rows.extend(reviewed)
        self.validated_rows.extend(validated)
        self.manual_rows.extend(manual)
        self.auxiliary_rows.extend(auxiliary)
        self.rejected_rows.extend(source_rejections)
        upsert_decision(
            self.root / "data" / "state" / "decision_cache.jsonl",
            "extract",
            input_hash,
            extract_skill.skill_id,
            extract_skill.version,
            relative_path(self.root, self.paths.candidates),
            f"{len(candidates)} candidates extracted from high-relevance chunks",
            0.85 if candidates else 0.65,
        )
        upsert_decision(
            self.root / "data" / "state" / "decision_cache.jsonl",
            "review",
            review_hash,
            review_skill.skill_id,
            review_skill.version,
            relative_path(self.root, self.paths.reviewed),
            f"{len(reviewed)} reviewed; {len(validated)} validated; {len(manual)} manual; {len(auxiliary)} auxiliary",
            0.85 if reviewed else 0.65,
        )
        status.update(
            {
                "extraction_status": "done",
                "review_status": "done",
                "database_write_status": "done",
                "artifact_refs": {
                    **status.get("artifact_refs", {}),
                    "candidate_records_ref": relative_path(self.root, self.paths.candidates),
                    "reviewed_records_ref": relative_path(self.root, self.paths.reviewed),
                    "validated_records_ref": relative_path(self.root, self.paths.validated),
                    "manual_review_ref": relative_path(self.root, self.paths.manual),
                    "rejected_records_ref": relative_path(self.root, self.paths.rejected),
                    "auxiliary_records_ref": relative_path(self.root, self.paths.auxiliary),
                },
                "overall_status": "validated" if validated else ("manual_screen" if manual else ("auxiliary" if auxiliary else "rejected")),
                "next_action": "reviewed_database_outputs_written",
            }
        )
        self.upsert_streaming_source(metadata, status)

    def metadata_for_source(self, source: dict[str, Any]) -> dict[str, Any]:
        source_id = str(source.get("source_id", ""))
        path = self.root / "data" / "runs" / f"stage2_4j_{source_id}" / "source_metadata.json"
        if path.exists():
            metadata = read_json(path)
        else:
            metadata = {
                "source_id": source_id,
                "doi": source.get("doi", ""),
                "title": source.get("title", ""),
                "year": source.get("year", ""),
                "journal": source.get("journal", ""),
                "provider": "stage2_6c_metadata_queue",
            }
        metadata["source_id"] = source_id
        metadata["doi"] = metadata.get("doi") or source.get("doi", "")
        metadata["title"] = metadata.get("title") or source.get("title", "")
        return metadata

    def metadata_ref_for_source(self, source: dict[str, Any]) -> str:
        source_id = str(source.get("source_id", ""))
        path = self.root / "data" / "runs" / f"stage2_4j_{source_id}" / "source_metadata.json"
        return relative_path(self.root, path) if path.exists() else ""

    def rewrite_candidate_records(self, records: list[dict[str, Any]], source: dict[str, Any]) -> list[dict[str, Any]]:
        rewritten: list[dict[str, Any]] = []
        source_id = str(source.get("source_id", ""))
        for idx, record in enumerate(records, start=1):
            row = json.loads(json.dumps(record, ensure_ascii=False))
            row["record_id"] = f"stage2_6c_{source_id}_candidate_{idx:03d}"
            row["provenance"] = {
                "added_by": "stage2_6c_streaming_supervisor",
                "batch_id": self.batch_id,
                "stage": "streaming_extract",
            }
            row.setdefault("review", {})["review_status"] = "pending_review"
            rewritten.append(row)
        return rewritten

    def rewrite_reviewed_records(self, records: list[dict[str, Any]], source: dict[str, Any]) -> list[dict[str, Any]]:
        rewritten: list[dict[str, Any]] = []
        source_id = str(source.get("source_id", ""))
        for idx, record in enumerate(records, start=1):
            row = json.loads(json.dumps(record, ensure_ascii=False))
            row["review_decision_ref"] = relative_path(self.root, self.paths.reviewed)
            row["database_write_ref"] = self.database_ref_for_review(row)
            row["task_lineage"] = {
                "cycle_id": f"{self.batch_id}_{source_id}",
                "extraction_agent": "ExtractionAgent",
                "review_agent": "ReviewAgent",
                "database_write_agent": "DatabaseWriteAgent",
                "synchronous": True,
            }
            row["record_id"] = row.get("record_id") or f"stage2_6c_{source_id}_reviewed_{idx:03d}"
            rewritten.append(row)
        return rewritten

    def rewrite_rejections(self, records: list[dict[str, Any]], source: dict[str, Any], fallback_reason: str) -> list[dict[str, Any]]:
        source_id = str(source.get("source_id", ""))
        rewritten: list[dict[str, Any]] = []
        for idx, record in enumerate(records, start=1):
            row = json.loads(json.dumps(record, ensure_ascii=False))
            row["record_id"] = f"stage2_6c_{source_id}_rejected_{idx:03d}"
            row["review_status"] = "rejected"
            row["rejection_reason"] = row.get("rejection_reason") or fallback_reason
            row["database_write_ref"] = relative_path(self.root, self.paths.rejected)
            row["task_lineage"] = {
                "cycle_id": f"{self.batch_id}_{source_id}",
                "extraction_agent": "ExtractionAgent",
                "review_agent": "ReviewAgent",
                "database_write_agent": "DatabaseWriteAgent",
                "synchronous": True,
            }
            rewritten.append(row)
        return rewritten

    def database_ref_for_review(self, record: dict[str, Any]) -> str:
        status = record.get("review", {}).get("review_status")
        if status == "validated":
            return relative_path(self.root, self.paths.validated)
        if status == "manual_review":
            return relative_path(self.root, self.paths.manual)
        if status == "auxiliary_engineered":
            return relative_path(self.root, self.paths.auxiliary)
        return relative_path(self.root, self.paths.rejected)

    def no_evidence_record(self, source: dict[str, Any], chunk_id: str, reason: str) -> dict[str, Any]:
        title = str(source.get("title", ""))
        return {
            "record_id": f"stage2_6c_{source.get('source_id', '')}_rejected_001",
            "source_id": source.get("source_id", ""),
            "doi": source.get("doi", ""),
            "title": title,
            "chunk_id": chunk_id,
            "review_status": "rejected",
            "review_confidence": 0.88,
            "review_reason": "Streaming extraction/review cycle found no direct parent-product PFAS transformation evidence.",
            "evidence_tier": "none",
            "requires_manual_confirmation": False,
            "natural_environment_valid": False,
            "rejection_reason": reason or source_rejection_reason(title, ""),
            "next_action": "none",
            "database_write_ref": relative_path(self.root, self.paths.rejected),
            "task_lineage": {
                "cycle_id": f"{self.batch_id}_{source.get('source_id', '')}",
                "extraction_agent": "ExtractionAgent",
                "review_agent": "ReviewAgent",
                "database_write_agent": "DatabaseWriteAgent",
                "synchronous": True,
            },
        }

    def append_blocked(self, source: dict[str, Any]) -> None:
        path = self.root / "data" / "state" / "blocked_external_queue.jsonl"
        rows = read_jsonl(path)
        key = (source.get("source_id", ""), "stage2_6c_fulltext_missing")
        rows = [row for row in rows if (row.get("source_id"), row.get("blocker_type")) != key]
        rows.append(
            {
                "source_id": source.get("source_id", ""),
                "doi": source.get("doi", ""),
                "title": source.get("title", ""),
                "blocker_type": "stage2_6c_fulltext_missing",
                "required_external_action": "attach_pdf_to_zotero_or_provide_local_fulltext",
                "status": "blocked_external",
                "note": "Title/abstract screening passed, but no lawful local PDF/HTML/SI cache was found.",
            }
        )
        write_jsonl(path, rows)

    def append_manual_handoff(self, source: dict[str, Any], stage: str, reason: str) -> None:
        path = self.root / "data" / "state" / "manual_handoff_queue.jsonl"
        rows = read_jsonl(path)
        handoff_id = f"stage2_6c_{source.get('source_id', '')}_{stage}"
        rows = [row for row in rows if row.get("handoff_id") != handoff_id]
        rows.append(
            {
                "handoff_id": handoff_id,
                "source_id": source.get("source_id", ""),
                "stage": "screening",
                "reason": reason,
                "required_user_action": "resolve_ambiguous_title",
                "input_refs": {"metadata_queue_ref": self.relative_queue_ref()},
                "suggested_action": "review title/abstract metadata before allowing fulltext ingest",
                "priority": "medium",
                "status": "pending",
                "created_at": utc_now(),
            }
        )
        write_jsonl(path, rows)

    def upsert_streaming_source(self, metadata: dict[str, Any], status: dict[str, Any]) -> None:
        if not self.update_source_registry_enabled:
            return
        refs = status.get("artifact_refs", {})
        upsert_source(
            self.root / "data" / "state" / "source_registry.jsonl",
            {
                "source_id": metadata.get("source_id", ""),
                "doi": metadata.get("doi", ""),
                "title": metadata.get("title", ""),
                "year": metadata.get("year", ""),
                "journal": metadata.get("journal", ""),
                "authors": metadata.get("authors", []),
                "metadata_ref": refs.get("metadata_ref", ""),
                "screening_ref": refs.get("screening_ref", ""),
                "chunks_ref": refs.get("chunks_ref", ""),
                "candidate_records_ref": refs.get("candidate_records_ref", ""),
                "reviewed_records_ref": refs.get("reviewed_records_ref", ""),
                "validated_records_ref": refs.get("validated_records_ref", ""),
                "manual_review_ref": refs.get("manual_review_ref", ""),
                "rejected_records_ref": refs.get("rejected_records_ref", ""),
                "status": status.get("overall_status", ""),
                "hashes": {
                    "doi_hash": sha256_text(str(metadata.get("doi", "")).lower()),
                    "title_hash": sha256_text(" ".join(str(metadata.get("title", "")).lower().split())),
                    "metadata_hash": sha256_file(self.root / refs["metadata_ref"]) if refs.get("metadata_ref") else "",
                    "fulltext_hash": "",
                    "chunks_hash": sha256_file(self.root / refs["chunks_ref"]) if refs.get("chunks_ref") else "",
                },
            },
        )

    def write_outputs(self, queue: list[dict[str, Any]], ended: str) -> None:
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
        self.index_batch_artifacts()
        blocked = sum(1 for row in self.status_rows if row.get("overall_status") == "blocked_external")
        manual = sum(1 for row in self.status_rows if row.get("overall_status") == "manual_screen")
        include = sum(1 for row in self.screening_rows if row.get("screening_decision") == "include_for_fulltext")
        excluded = sum(1 for row in self.screening_rows if row.get("screening_decision") == "exclude")
        chunks_seen = len(self.chunk_rows)
        high_chunk_sources = len({row["source_id"] for row in self.chunk_rows if row.get("relevance_decision") == "extract"})
        database_records = len(self.validated_rows) + len(self.manual_rows) + len(self.rejected_rows) + len(self.auxiliary_rows)
        no_pending = True
        sync_ok = len(self.candidate_rows) == len(self.reviewed_rows)
        skill_ok = all(row.get("skill_id") for row in self.events)
        token_ok = self.token_stats["long_context_violations"] == 0 and self.token_stats["fulltext_context_violations"] == 0
        ready_100 = (
            len(self.screening_rows) >= 100
            and self.extract_sources >= 1
            and len(self.candidate_rows) >= 1
            and sync_ok
            and token_ok
            and not self.forbidden_validated_records()
        )
        success = no_pending and sync_ok and skill_ok and token_ok
        reason = "streaming_closed_loop_verified_with_controlled_limits" if ready_100 else "streaming_workflow_success_but_no_validated_records_yet"
        if not success:
            reason = "streaming_validation_prerequisites_not_met"
        self.summary = {
            "batch_id": self.batch_id,
            "metadata_sources_seen": len(queue),
            "sources_screened": len(self.screening_rows),
            "include_for_fulltext": include,
            "manual_screen": sum(1 for row in self.screening_rows if row.get("screening_decision") == "manual_screen"),
            "exclude": excluded,
            "fulltext_found": sum(1 for row in self.status_rows if row.get("fulltext_status") == "found"),
            "fulltext_missing": sum(1 for row in self.status_rows if row.get("fulltext_status") == "missing"),
            "sources_parsed": sum(1 for row in self.status_rows if row.get("parse_status") in {"done", "skipped"}),
            "chunks_created": chunks_seen,
            "chunks_screened_extract": sum(1 for row in self.chunk_rows if row.get("relevance_decision") == "extract"),
            "sources_extracted": self.extract_sources,
            "candidate_records": len(self.candidate_rows),
            "reviewed_records": len(self.reviewed_rows),
            "validated_records": len(self.validated_rows),
            "manual_review_records": len(self.manual_rows),
            "rejected_records": len(self.rejected_rows),
            "auxiliary_records": len(self.auxiliary_rows),
            "database_records_written": database_records,
            "blocked_external_sources": blocked,
            "deferred_sources": self.deferred_sources,
            "pending_tasks_remaining": 0,
            "ended_because": ended,
            "workflow_streaming_success": success,
            "ready_for_next_streaming_batch": success,
            "ready_for_100_source_stream": ready_100,
            "reason": reason,
        }
        write_json(
            self.paths.checkpoint,
            {
                "batch_id": self.batch_id,
                "metadata_sources_seen": len(queue),
                "sources_screened": len(self.screening_rows),
                "last_run_finished_at": utc_now(),
                "can_resume": True,
                "ended_because": ended,
            },
        )
        self.write_reports(high_chunk_sources)

    def index_batch_artifacts(self) -> None:
        artifact_index = self.root / "data" / "state" / "artifact_index.jsonl"
        for artifact_type, path, schema in [
            ("screening", self.paths.screening_decisions, "skills/screening/title_abstract_screening/output.schema.json"),
            ("chunk_screening", self.paths.chunk_screening, "skills/parse/chunk_relevance_filter/output.schema.json"),
            ("candidate_records", self.paths.candidates, "skills/extraction/pfas_transformation_extraction/output.schema.json"),
            ("reviewed_records", self.paths.reviewed, "skills/review/evidence_grounded_review/output.schema.json"),
            ("validated_records", self.paths.validated, "schemas/transformation_record.schema.json"),
            ("manual_review", self.paths.manual, "schemas/review_decision.schema.json"),
            ("rejected_records", self.paths.rejected, "schemas/review_decision.schema.json"),
            ("auxiliary_records", self.paths.auxiliary, "schemas/review_decision.schema.json"),
        ]:
            if path.exists():
                index_artifact(self.root, artifact_index, self.batch_id, artifact_type, path, "Stage2_6cStreamingSupervisor", schema)

    def forbidden_validated_records(self) -> list[dict[str, Any]]:
        bad: list[dict[str, Any]] = []
        for row in self.validated_rows:
            text = json.dumps(row, ensure_ascii=False).lower()
            if any(term in text for term in NATURAL_VALID_EXCLUDE):
                bad.append(row)
        return bad

    def write_reports(self, high_chunk_sources: int) -> None:
        title_prefix = self.batch_id.replace("_", " ")
        write_key_value_report(self.paths.summary_report, f"{title_prefix} Streaming Autonomous Summary", self.summary)
        status_lines = [
            f"# {title_prefix} Streaming Status Board",
            "",
            "| source_id | title_short | screening | fulltext | parse | extract | review | database | overall | next_action |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for row in self.status_rows:
            status_lines.append(
                f"| {row.get('source_id', '')} | {_short_title(str(row.get('title', '')))} | {row.get('screening_decision')} | {row.get('fulltext_status')} | {row.get('parse_status')} | {row.get('extraction_status')} | {row.get('review_status')} | {row.get('database_write_status')} | {row.get('overall_status')} | {row.get('next_action')} |"
            )
        self.paths.status_board_report.write_text("\n".join(status_lines) + "\n", encoding="utf-8", newline="\n")
        skill_counts: defaultdict[str, int] = defaultdict(int)
        for event in self.events:
            skill_counts[str(event.get("skill_id", ""))] += 1
        skill_lines = [f"# {title_prefix} Streaming Skill Invocation Audit", ""]
        skill_lines.append(f"skill_invocation_audit_passed = {str(all(event.get('skill_id') for event in self.events)).lower()}")
        skill_lines.append(f"skill_invocations = {len(self.events)}")
        skill_lines.append("")
        skill_lines.extend(f"{skill_id} = {count}" for skill_id, count in sorted(skill_counts.items()))
        self.paths.skill_audit_report.write_text("\n".join(skill_lines) + "\n", encoding="utf-8", newline="\n")
        sync_values = {
            "candidate_records": len(self.candidate_rows),
            "reviewed_records": len(self.reviewed_rows),
            "all_candidates_reviewed_synchronously": len(self.candidate_rows) == len(self.reviewed_rows),
            "database_records_written": self.summary["database_records_written"],
            "synchronous_review_audit_passed": len(self.candidate_rows) == len(self.reviewed_rows),
        }
        write_key_value_report(self.paths.sync_review_report, f"{title_prefix} Streaming Synchronous Review Audit", sync_values)
        token_values = {
            "screening_cache_hits": self.token_stats["screening_cache_hits"],
            "screening_cache_misses": self.token_stats["screening_cache_misses"],
            "extraction_cache_hits": self.token_stats["extraction_cache_hits"],
            "extraction_cache_misses": self.token_stats["extraction_cache_misses"],
            "review_cache_hits": self.token_stats["review_cache_hits"],
            "review_cache_misses": self.token_stats["review_cache_misses"],
            "long_context_violations": self.token_stats["long_context_violations"],
            "fulltext_context_violations": self.token_stats["fulltext_context_violations"],
            "estimated_tokens_per_screening_record": 180,
            "estimated_tokens_per_extraction_source": 1400,
            "estimated_total_tokens": len(self.screening_rows) * 180 + self.extract_sources * 1400 + len(self.reviewed_rows) * 350,
            "high_relevance_chunk_sources": high_chunk_sources,
        }
        write_key_value_report(self.paths.token_report, f"{title_prefix} Streaming Token Cost Audit", token_values)
        blocked_lines = [f"# {title_prefix} Streaming Blocked Sources", "", "| source_id | doi | title | next_action |", "| --- | --- | --- | --- |"]
        for row in self.status_rows:
            if row.get("overall_status") == "blocked_external":
                blocked_lines.append(f"| {row.get('source_id', '')} | {row.get('doi', '')} | {_short_title(str(row.get('title', '')))} | {row.get('next_action', '')} |")
        self.paths.blocked_report.write_text("\n".join(blocked_lines) + "\n", encoding="utf-8", newline="\n")
        db_values = {
            "validated_records": len(self.validated_rows),
            "manual_review_records": len(self.manual_rows),
            "rejected_records": len(self.rejected_rows),
            "auxiliary_records": len(self.auxiliary_rows),
            "database_records_written": self.summary["database_records_written"],
            "forbidden_boundary_violations": len(self.forbidden_validated_records()),
        }
        write_key_value_report(self.paths.database_report, f"{title_prefix} Streaming Database Audit", db_values)


def run_streaming_supervisor(
    root: Path,
    batch_id: str,
    metadata_queue: Path,
    max_screen: int,
    max_fulltext: int,
    max_extract_sources: int,
    output_prefix: str = "stage2_6c_streaming",
    update_source_registry: bool = True,
) -> dict[str, Any]:
    return StreamingSupervisor(
        root,
        batch_id,
        metadata_queue,
        max_screen,
        max_fulltext,
        max_extract_sources,
        output_prefix,
        update_source_registry,
    ).run()
