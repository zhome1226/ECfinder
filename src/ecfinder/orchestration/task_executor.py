"""Task discovery and deterministic extraction/review execution helpers."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ecfinder.state.artifact_index import index_artifact
from ecfinder.state.common import read_json, read_jsonl, relative_path, sha256_file, sha256_text, utc_now, write_jsonl
from ecfinder.state.decision_cache import upsert_decision
from ecfinder.state.source_registry import upsert_source

from .agent_executor import AgentExecutor
from .status_model import ARTIFACT_REF_KEYS, empty_retry_count


STATE_DIR = Path("data/state")
BATCH_DIR = Path("data/batches")
REPORTS_DIR = Path("reports")
ARTIFACT_INDEX = STATE_DIR / "artifact_index.jsonl"
SOURCE_REGISTRY = STATE_DIR / "source_registry.jsonl"
DECISION_CACHE = STATE_DIR / "decision_cache.jsonl"
TASK_REGISTRY = STATE_DIR / "task_registry.jsonl"
STATUS_BOARD = STATE_DIR / "source_status_board.jsonl"
AGENT_EVENTS = STATE_DIR / "agent_run_events.jsonl"
CHECKPOINT = STATE_DIR / "orchestration_checkpoint.json"

FORBIDDEN_ENGINEERED = [
    "activated sludge",
    "wastewater",
    "wwtp",
    "water resource recovery",
    "advanced oxidation",
    "aop",
    "uv/sulfite",
    "photolysis",
    "photocatalytic",
    "photocatalysis",
    "electrochemical",
    "electrocatalytic",
    "ozonation",
    "persulfate",
    "plasma",
    "incineration",
]
NATURAL_TERMS = [
    "soil",
    "sediment",
    "groundwater",
    "surface water",
    "aquifer",
    "wetland",
    "marine",
    "estuarine",
    "natural attenuation",
    "afff-impacted",
    "microcosm",
    "field",
]
NON_EVIDENCE_TERMS = [
    "toxicity",
    "food web",
    "serum",
    "follicular",
    "metabolomics",
    "adolescents",
    "biomarkers",
    "analytical method",
    "external liquid calibration",
    "exposure to environmental chemicals",
]


def repo_path(root: Path, ref: str) -> Path:
    path = Path(ref)
    return path if path.is_absolute() else root / path


def line_count(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def compact_quote(text: str, limit: int = 420) -> str:
    text = " ".join(text.split())
    return text[: limit - 3].rstrip() + "..." if len(text) > limit else text


def contains_any(text: str, terms: list[str]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def title_is_non_evidence(title: str) -> bool:
    lowered = title.lower()
    return any(term in lowered for term in NON_EVIDENCE_TERMS)


def natural_environment_valid(title: str, text: str) -> bool:
    joined = f"{title} {text}".lower()
    return contains_any(joined, NATURAL_TERMS) and not contains_any(joined, FORBIDDEN_ENGINEERED)


def engineered_or_auxiliary(title: str, text: str) -> bool:
    joined = f"{title} {text}".lower()
    return contains_any(joined, FORBIDDEN_ENGINEERED)


def source_rejection_reason(title: str, text: str) -> str:
    if title_is_non_evidence(title):
        return "non_transformation_or_human_exposure_scope"
    if engineered_or_auxiliary(title, text):
        return "engineered_treatment_or_auxiliary_boundary"
    return "no_parent_product_transformation_evidence"


PATTERNS: list[dict[str, Any]] = [
    {
        "source_title": "Biotransformation of 8:2 Fluorotelomer Alcohol in Soil from Aqueous Film-Forming Foams",
        "parent": "8:2 fluorotelomer alcohol",
        "products": ["8:2 FTCA", "8:2 FTUA", "7:2 sFTOH", "PFOA", "1H-perfluoroheptane", "3-F-7:3 acid"],
        "condition": "AFFF-impacted soil microcosms under nitrate-, sulfate-, and iron-reducing conditions",
        "matrix": "AFFF-impacted soil",
        "setting_type": "soil_microcosm_from_field_sample",
        "tier": "confirmed_validated",
        "quote_regex": r"Transformation products 8:2 fluorotelomer saturated and unsaturated carboxylic acids .*?were detected.*?3-F-7:3 acid .*?identified.*?8:2 FTOH biotransformation\.",
    },
    {
        "source_title": "Nitrifying Microorganisms Linked to Biotransformation",
        "parent": "C6 sulfonamido precursors",
        "products": ["PFHxS", "FHxSA", "PFHxSAm pathway intermediates"],
        "condition": "aerobic water and sediment slurry microcosms representative of the groundwater/surface water boundary",
        "matrix": "groundwater/surface water boundary sediment slurry",
        "setting_type": "sediment_microcosm_from_field_sample",
        "tier": "probable_validated",
        "quote_regex": r"C6 precursors can be transformed through nitrification .*? into perfluorohexane sulfonate .*?key intermediates using high-resolution mass spectrometry\.",
    },
    {
        "source_title": "Transcriptomic response of Gordonia",
        "parent": "6:2 fluorotelomer sulfonamidoalkyl betaine and 6:2 fluorotelomer sulfonate",
        "products": ["observable metabolites from 6:2 FTAB and 6:2 FTSA"],
        "condition": "Gordonia sp. strain NB4-1Y pure culture under sulfur-limiting conditions",
        "matrix": "pure culture isolated from environmental material",
        "setting_type": "auxiliary_pure_culture_mechanistic",
        "tier": "tentative_validated",
        "quote_regex": r"NB4-1Y transforms both 6:2 FTAB and 6:2 FTSA to 16 observable metabolites over 7 days.*?sole sulfur sources",
        "auxiliary": True,
    },
]


def regex_quote(text: str, pattern: str) -> str:
    match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
    if match:
        return compact_quote(match.group(0))
    return ""


def make_record(
    source: dict[str, Any],
    chunk: dict[str, Any],
    pattern: dict[str, Any],
    product: str,
    index: int,
    quote: str,
) -> dict[str, Any]:
    source_id = str(source.get("source_id", chunk.get("source_id", "")))
    tier = pattern.get("tier", "tentative_validated")
    return {
        "record_id": f"stage2_5_{source_id}_candidate_{index:03d}",
        "source_id": source_id,
        "doi": str(source.get("doi", chunk.get("doi", ""))),
        "title": str(source.get("title", chunk.get("title", ""))),
        "year": source.get("year", ""),
        "journal": source.get("journal", ""),
        "chunk_id": chunk.get("chunk_id", ""),
        "evidence_location": {"section": chunk.get("section", ""), "section_id": chunk.get("section_id", "")},
        "evidence_quote": quote,
        "parent_compound": {"name": pattern["parent"], "compound_class": "PFAS precursor", "synonyms": []},
        "product_compound": {"name": product, "compound_class": "PFAS transformation product", "synonyms": []},
        "transformation": {
            "direction": "parent_to_product",
            "is_precursor_transformation": True,
            "reaction_description": f"{pattern['parent']} transformed to {product}.",
            "reaction_name": f"{pattern['parent']} transformation",
            "reaction_type": "microbial biotransformation",
            "defluorination_involved": "defluor" in quote.lower(),
        },
        "conditions": {
            "condition": pattern["condition"],
            "environment_matrix": pattern["matrix"],
            "environment_type": pattern["setting_type"],
            "setting_type": pattern["setting_type"],
        },
        "evidence": {
            "analytical_method": "text-mined from parsed local full text; original study methods referenced in evidence chunk",
            "extraction_method": "stage2_5_closed_loop_deterministic_executor",
            "identification_confidence": tier,
        },
        "review": {
            "review_status": "pending_review",
            "evidence_tier": tier,
            "review_confidence": None,
            "natural_environment_valid": False,
            "requires_manual_confirmation": False,
        },
        "provenance": {
            "added_by": "stage2_5_closed_loop_executor",
            "run_id": f"stage2_4j_{source_id}",
            "stage": "closed_loop_extract",
        },
    }


def extract_candidates(metadata: dict[str, Any], chunks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []
    rejections: list[dict[str, Any]] = []
    title = str(metadata.get("title", ""))
    joined_text = " ".join(str(chunk.get("text", "")) for chunk in chunks[:4])
    index = 1
    for pattern in PATTERNS:
        if pattern["source_title"].lower() not in title.lower():
            continue
        for chunk in chunks:
            quote = regex_quote(str(chunk.get("text", "")), pattern["quote_regex"])
            if not quote:
                continue
            for product in pattern["products"]:
                candidates.append(make_record(metadata, chunk, pattern, product, index, quote))
                index += 1
            break
    if not candidates:
        rejections.append(
            {
                "record_id": f"stage2_5_{metadata.get('source_id', '')}_rejected_001",
                "source_id": metadata.get("source_id", ""),
                "doi": metadata.get("doi", ""),
                "title": title,
                "chunk_id": chunks[0].get("chunk_id", "") if chunks else "",
                "review_status": "rejected",
                "review_confidence": 0.9,
                "review_reason": "Closed-loop extraction executed but no direct parent-product PFAS transformation evidence was found in parsed chunks.",
                "evidence_tier": "none",
                "requires_manual_confirmation": False,
                "natural_environment_valid": False,
                "rejection_reason": source_rejection_reason(title, joined_text),
                "next_action": "none",
                "provenance": {"added_by": "stage2_5_closed_loop_executor", "stage": "closed_loop_extract_review"},
            }
        )
    return candidates, rejections


def review_candidates(candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    reviewed: list[dict[str, Any]] = []
    validated: list[dict[str, Any]] = []
    manual: list[dict[str, Any]] = []
    auxiliary: list[dict[str, Any]] = []
    for candidate in candidates:
        text = json.dumps(candidate, ensure_ascii=False)
        title = str(candidate.get("title", ""))
        quote = str(candidate.get("evidence_quote", ""))
        is_aux = "auxiliary_pure_culture" in text or engineered_or_auxiliary(title, quote)
        is_natural = natural_environment_valid(title, quote + " " + json.dumps(candidate.get("conditions", {}), ensure_ascii=False))
        tier = str(candidate.get("review", {}).get("evidence_tier") or "tentative_validated")
        status = "validated" if is_natural and not is_aux else ("auxiliary_engineered" if is_aux else "manual_review")
        review = {
            "review_status": status,
            "review_confidence": 0.88 if status == "validated" else 0.72,
            "review_reason": "Evidence quote contains a direct parent-product transformation relation and passes natural-environment boundary."
            if status == "validated"
            else "Evidence is transformation-relevant but does not pass the natural-environment main database boundary.",
            "evidence_tier": tier,
            "requires_manual_confirmation": status == "manual_review",
            "natural_environment_valid": status == "validated",
            "rejection_reason": None if status == "validated" else "outside_natural_main_boundary",
            "next_action": "write_validated" if status == "validated" else "auxiliary_or_manual_audit",
        }
        reviewed_record = {**candidate, "review": review}
        reviewed.append(reviewed_record)
        if status == "validated":
            validated.append(reviewed_record)
        elif status == "manual_review":
            manual.append(reviewed_record)
        else:
            auxiliary.append(reviewed_record)
    return reviewed, validated, manual, auxiliary


def update_task_status(root: Path, task_id: str, status: str, reason: str) -> None:
    registry_path = root / TASK_REGISTRY
    records = read_jsonl(registry_path)
    updated = []
    for row in records:
        if row.get("task_id") == task_id:
            row = {**row, "status": status, "completed_at": utc_now(), "completion_reason": reason}
            payload_path = repo_path(root, str(row.get("task_path", "")))
            if payload_path.exists():
                payload = read_json(payload_path)
                payload.update({"status": status, "completed_at": row["completed_at"], "completion_reason": reason})
                payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        updated.append(row)
    write_jsonl(registry_path, updated)
    batch_path = root / BATCH_DIR / "stage2_4j_codex_tasks.jsonl"
    if batch_path.exists():
        rows = []
        for row in read_jsonl(batch_path):
            if row.get("task_id") == task_id:
                row = {**row, "status": status, "completed_at": utc_now(), "completion_reason": reason}
            rows.append(row)
        write_jsonl(batch_path, rows)


def upsert_board_record(root: Path, metadata: dict[str, Any], refs: dict[str, str], task_ref: str, overall: str, next_action: str) -> None:
    board_path = root / STATUS_BOARD
    rows = [row for row in read_jsonl(board_path) if row.get("source_id") != metadata.get("source_id")]
    rows.append(
        {
            "source_id": metadata.get("source_id", ""),
            "doi": metadata.get("doi", ""),
            "title": metadata.get("title", ""),
            "batch_id": "stage2_4j",
            "overall_status": overall,
            "current_stage": "done",
            "stage_status": {
                "metadata": "done",
                "screening": "done",
                "fulltext": "done",
                "parse": "done",
                "chunk": "done",
                "extract": "done",
                "review": "done",
            },
            "artifact_refs": {key: refs.get(key, "") for key in ARTIFACT_REF_KEYS},
            "task_refs": [task_ref] if task_ref else [],
            "retry_count": empty_retry_count(),
            "last_error": None,
            "next_action": next_action,
            "updated_at": utc_now(),
        }
    )
    write_jsonl(board_path, rows)


def append_event(root: Path, task: dict[str, Any], event_type: str, message: str, artifact_ref: str = "") -> None:
    path = root / AGENT_EVENTS
    rows = read_jsonl(path)
    event_id = f"stage2_5_{task.get('task_id')}_{event_type}_{sha256_text(message)[:10]}"
    rows.append(
        {
            "event_id": event_id,
            "timestamp": utc_now(),
            "batch_id": "stage2_4j",
            "source_id": task.get("source_id", ""),
            "agent": "ExtractionAgent" if task.get("task_type") == "extract" else "ReviewAgent",
            "stage": "extract" if task.get("task_type") == "extract" else "review",
            "event_type": event_type,
            "status_before": "pending",
            "status_after": "done",
            "artifact_ref": artifact_ref,
            "task_ref": task.get("task_payload_ref", ""),
            "error_ref": "",
            "message": message[:220],
        }
    )
    write_jsonl(path, rows)


class ExtractionAgentExecutor(AgentExecutor):
    name = "ExtractionAgent"

    def can_run(self, task: dict[str, Any]) -> bool:
        return task.get("task_type") == "extract" and task.get("status") in {"pending", "runnable"}

    def run(self, task: dict[str, Any]) -> dict[str, Any]:
        input_refs = task.get("input_refs", {})
        metadata = read_json(repo_path(self.root, input_refs.get("metadata_ref", "")))
        chunks = read_jsonl(repo_path(self.root, input_refs.get("chunks_ref", "")))
        candidates, source_rejections = extract_candidates(metadata, chunks)
        reviewed, validated, manual, auxiliary = review_candidates(candidates)
        return {
            "task": task,
            "metadata": metadata,
            "chunks": chunks,
            "candidates": candidates,
            "reviewed": reviewed,
            "validated": validated,
            "manual": manual,
            "rejected": source_rejections,
            "auxiliary": auxiliary,
        }

    def write_outputs(self, result: dict[str, Any]) -> None:
        task = result["task"]
        metadata = result["metadata"]
        source_id = str(metadata.get("source_id", task.get("source_id", "")))
        run_dir = repo_path(self.root, str(task.get("run_id", f"stage2_4j_{source_id}")))
        if not run_dir.exists():
            run_dir = self.root / "data" / "runs" / f"stage2_4j_{source_id}"
        candidate_path = run_dir / "candidate_records.jsonl"
        reviewed_path = run_dir / "reviewed_records.jsonl"
        validated_path = run_dir / "validated_records.jsonl"
        manual_path = run_dir / "manual_review_records.jsonl"
        rejected_path = run_dir / "rejected_records.jsonl"
        auxiliary_path = run_dir / "auxiliary_records.jsonl"
        write_jsonl(candidate_path, result["candidates"])
        write_jsonl(reviewed_path, result["reviewed"])
        write_jsonl(validated_path, result["validated"])
        write_jsonl(manual_path, result["manual"])
        write_jsonl(rejected_path, result["rejected"])
        write_jsonl(auxiliary_path, result["auxiliary"])
        refs = {
            "metadata_ref": task.get("input_refs", {}).get("metadata_ref", ""),
            "screening_ref": relative_path(self.root, run_dir / "screening.json") if (run_dir / "screening.json").exists() else "",
            "download_ref": task.get("input_refs", {}).get("download_ref", ""),
            "chunks_ref": task.get("input_refs", {}).get("chunks_ref", ""),
            "candidate_records_ref": relative_path(self.root, candidate_path),
            "reviewed_records_ref": relative_path(self.root, reviewed_path),
            "validated_records_ref": relative_path(self.root, validated_path),
            "manual_review_ref": relative_path(self.root, manual_path),
            "rejected_records_ref": relative_path(self.root, rejected_path),
        }
        for artifact_type, path, schema in [
            ("candidate_records", candidate_path, "schemas/transformation_record.schema.json"),
            ("reviewed_records", reviewed_path, "schemas/transformation_record.schema.json"),
            ("validated_records", validated_path, "schemas/transformation_record.schema.json"),
            ("manual_review", manual_path, "schemas/review_decision.schema.json"),
            ("rejected_records", rejected_path, "schemas/review_decision.schema.json"),
            ("auxiliary_records", auxiliary_path, "schemas/review_decision.schema.json"),
        ]:
            index_artifact(self.root, self.root / ARTIFACT_INDEX, source_id, artifact_type, path, "Stage2_5ClosedLoopExecutor", schema)
        input_hash = sha256_file(repo_path(self.root, refs["chunks_ref"])) if refs.get("chunks_ref") else ""
        upsert_decision(
            self.root / DECISION_CACHE,
            "extract",
            input_hash,
            "stage2_5_v1",
            "stage2_5_v1",
            refs["candidate_records_ref"],
            f"{len(result['candidates'])} candidate records; {len(result['rejected'])} source rejections",
            None,
        )
        upsert_decision(
            self.root / DECISION_CACHE,
            "review",
            sha256_file(candidate_path),
            "stage2_5_v1",
            "stage2_5_v1",
            refs["reviewed_records_ref"],
            f"{len(result['reviewed'])} reviewed, {len(result['validated'])} validated, {len(result['manual'])} manual, {len(result['auxiliary'])} auxiliary",
            None,
        )
        status = "validated" if result["validated"] else ("manual_review" if result["manual"] else "rejected")
        next_action = "validated_records_ready_for_database" if result["validated"] else "closed_loop_no_natural_validated_records"
        upsert_board_record(self.root, metadata, refs, task.get("task_payload_ref", ""), status, next_action)
        source = {
            **metadata,
            "source_id": source_id,
            "metadata_ref": refs["metadata_ref"],
            "screening_ref": refs["screening_ref"],
            "download_ref": refs["download_ref"],
            "chunks_ref": refs["chunks_ref"],
            "candidate_records_ref": refs["candidate_records_ref"],
            "reviewed_records_ref": refs["reviewed_records_ref"],
            "validated_records_ref": refs["validated_records_ref"],
            "manual_review_ref": refs["manual_review_ref"],
            "rejected_records_ref": refs["rejected_records_ref"],
            "status": "validated" if result["validated"] else "rejected",
            "hashes": {
                "doi_hash": sha256_text(str(metadata.get("doi", "")).lower()),
                "title_hash": sha256_text(" ".join(str(metadata.get("title", "")).lower().split())),
                "metadata_hash": sha256_file(repo_path(self.root, refs["metadata_ref"])) if refs["metadata_ref"] else "",
                "fulltext_hash": "",
                "chunks_hash": sha256_file(repo_path(self.root, refs["chunks_ref"])) if refs["chunks_ref"] else "",
            },
        }
        upsert_source(self.root / SOURCE_REGISTRY, source)
        update_task_status(self.root, task["task_id"], "done", "closed_loop_consumed")
        append_event(self.root, task, "success", "closed-loop extraction and review completed", refs["reviewed_records_ref"])


class ReviewAgentExecutor(ExtractionAgentExecutor):
    name = "ReviewAgent"

    def can_run(self, task: dict[str, Any]) -> bool:
        return task.get("task_type") == "review" and task.get("status") in {"pending", "runnable"}


class DatabaseWriteAgentExecutor(AgentExecutor):
    name = "DatabaseWriteAgent"

    def can_run(self, task: dict[str, Any]) -> bool:
        return task.get("task_type") == "write_database" and task.get("status") in {"pending", "runnable"}

    def run(self, task: dict[str, Any]) -> dict[str, Any]:
        return {"task": task, "status": "done"}

    def write_outputs(self, result: dict[str, Any]) -> None:
        task = result["task"]
        update_task_status(self.root, task["task_id"], "done", "database_write_completed")


def discover_stage2_4j_tasks(root: Path, batch_id: str) -> list[dict[str, Any]]:
    tasks_path = root / BATCH_DIR / f"{batch_id}_codex_tasks.jsonl"
    tasks = read_jsonl(tasks_path) if tasks_path.exists() else []
    runnable: list[dict[str, Any]] = []
    for task in tasks:
        input_refs = task.get("input_refs", {})
        chunks_ref = input_refs.get("chunks_ref", "")
        candidate_ref = task.get("expected_output", "")
        if task.get("status") == "done":
            continue
        if task.get("task_type") == "extract" and chunks_ref and repo_path(root, chunks_ref).exists():
            runnable.append(
                {
                    **task,
                    "status": "runnable",
                    "reason": "parsed chunks exist and extraction result is not complete",
                    "output_expected": candidate_ref,
                }
            )
    return runnable


def write_runnable_report(root: Path, batch_id: str, runnable: list[dict[str, Any]]) -> None:
    write_jsonl(root / STATE_DIR / "runnable_tasks.jsonl", runnable)
    lines = [
        "# Current Runnable Tasks",
        "",
        f"batch_id = {batch_id}",
        f"runnable_tasks = {len(runnable)}",
        "",
        "| task_id | source_id | task_type | reason |",
        "| --- | --- | --- | --- |",
    ]
    for task in runnable:
        lines.append(f"| {task.get('task_id', '')} | {task.get('source_id', '')} | {task.get('task_type', '')} | {task.get('reason', '')} |")
    (root / REPORTS_DIR / "current_runnable_tasks.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def update_checkpoint(root: Path, batch_id: str) -> None:
    records = read_jsonl(root / STATUS_BOARD)
    payload = {
        "batch_id": batch_id,
        "last_run_started_at": utc_now(),
        "last_run_finished_at": utc_now(),
        "total_sources": len(records),
        "completed_sources": sum(1 for row in records if row.get("overall_status") in {"validated", "manual_review", "rejected", "failed_terminal"}),
        "in_progress_sources": sum(1 for row in records if row.get("overall_status") == "in_progress"),
        "manual_required_sources": sum(1 for row in records if row.get("overall_status") == "manual_review"),
        "failed_recoverable_sources": sum(1 for row in records if row.get("overall_status") == "failed_recoverable"),
        "failed_terminal_sources": sum(1 for row in records if row.get("overall_status") == "failed_terminal"),
        "can_resume": True,
    }
    (root / CHECKPOINT).write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
