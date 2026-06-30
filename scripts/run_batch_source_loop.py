"""Run a cache-aware PFAS source batch loop from a JSONL queue."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ecfinder.state.artifact_index import index_artifact
from ecfinder.state.common import (
    doi_hash,
    normalized_title_hash,
    read_json,
    read_jsonl,
    relative_path,
    sha256_file,
    write_json,
    write_jsonl,
    append_jsonl,
    utc_now,
)
from ecfinder.state.decision_cache import find_decision, upsert_decision
from ecfinder.state.source_registry import upsert_source
from ecfinder.state.task_payloads import create_task_payload


ROOT = Path(__file__).resolve().parents[1]
BATCH_DIR = ROOT / "data" / "batches"
RUNS_DIR = ROOT / "data" / "runs"
REPORTS_DIR = ROOT / "reports"
STATE_DIR = ROOT / "data" / "state"
TASKS_DIR = ROOT / "data" / "tasks"
SOURCE_REGISTRY_PATH = STATE_DIR / "source_registry.jsonl"
ARTIFACT_INDEX_PATH = STATE_DIR / "artifact_index.jsonl"
DECISION_CACHE_PATH = STATE_DIR / "decision_cache.jsonl"
TASK_REGISTRY_PATH = STATE_DIR / "task_registry.jsonl"
CACHE_STATS_PATH = STATE_DIR / "cache_stats.json"
ONE_SOURCE_SCRIPT = ROOT / "scripts" / "run_one_source_loop.py"
PROMPT_VERSION = "stage2_4_v1"
SCHEMA_VERSION = "stage2_4_v1"

RUN_JSONL_OUTPUTS = [
    "chunks.jsonl",
    "candidate_records.jsonl",
    "reviewed_records.jsonl",
    "validated_records.jsonl",
    "manual_review_records.jsonl",
    "rejected_records.jsonl",
]
RUN_REQUIRED_FILES = [
    "source_metadata.json",
    "screening.json",
    "download_status.json",
    *RUN_JSONL_OUTPUTS,
    "run_summary.md",
]
FORBIDDEN_TERMS = [
    "activated sludge",
    "wastewater treatment",
    "wwtp",
    "engineered treatment",
    "aop",
    "electrochemical",
    "plasma",
    "photocatalysis",
    "ozonation",
    "uv_persulfate",
    "hydrothermal",
    "incineration",
]
LONG_TEXT_KEYS = {
    "stdout",
    "stderr",
    "abstract",
    "text",
    "full_text",
    "chunk_text",
    "evidence_text",
    "evidence_quote",
}

SCHEMA_BY_ARTIFACT_TYPE = {
    "metadata": "schemas/source_metadata.schema.json",
    "screening": "schemas/screening_decision.schema.json",
    "download": "",
    "chunks": "schemas/chunk.schema.json",
    "candidate_records": "schemas/transformation_record.schema.json",
    "reviewed_records": "schemas/transformation_record.schema.json",
    "validated_records": "schemas/transformation_record.schema.json",
    "manual_review": "schemas/review_decision.schema.json",
    "rejected_records": "schemas/review_decision.schema.json",
}

ARTIFACT_FILES = {
    "metadata": "source_metadata.json",
    "screening": "screening.json",
    "download": "download_status.json",
    "chunks": "chunks.jsonl",
    "candidate_records": "candidate_records.jsonl",
    "reviewed_records": "reviewed_records.jsonl",
    "validated_records": "validated_records.jsonl",
    "manual_review": "manual_review_records.jsonl",
    "rejected_records": "rejected_records.jsonl",
}

TOKENS_SAVED_WEIGHTS = {
    "metadata_cache_hits": 800,
    "screening_cache_hits": 1000,
    "parse_cache_hits": 3000,
    "extraction_cache_hits": 2500,
    "review_cache_hits": 1500,
}


def batch_paths(batch_id: str) -> dict[str, Path]:
    return {
        "status": BATCH_DIR / f"{batch_id}_30source_status.jsonl",
        "events": BATCH_DIR / f"{batch_id}_30source_events.jsonl",
        "codex_tasks": BATCH_DIR / f"{batch_id}_codex_tasks.jsonl",
        "validated": BATCH_DIR / f"{batch_id}_validated_records.jsonl",
        "manual": BATCH_DIR / f"{batch_id}_manual_review_records.jsonl",
        "rejected": BATCH_DIR / f"{batch_id}_rejected_records.jsonl",
        "summary": REPORTS_DIR / f"{batch_id}_30source_loop_summary.md",
        "query_performance": REPORTS_DIR / f"{batch_id}_query_performance.md",
        "validated_audit": REPORTS_DIR / f"{batch_id}_validated_records_audit.md",
        "manual_targets": REPORTS_DIR / f"{batch_id}_manual_full_text_targets.md",
        "scale_readiness": REPORTS_DIR / f"{batch_id}_scale_readiness.md",
        "cache_performance": REPORTS_DIR / f"{batch_id}_cache_performance.md",
    }


def load_cache_stats() -> dict[str, int]:
    stats = read_json(CACHE_STATS_PATH)
    return {key: int(value) for key, value in stats.items()}


def save_cache_stats(stats: dict[str, int]) -> None:
    write_json(CACHE_STATS_PATH, stats)


def bump_cache_stat(key: str, amount: int = 1) -> None:
    stats = load_cache_stats()
    stats[key] = stats.get(key, 0) + amount
    save_cache_stats(stats)


def reset_cache_stats() -> None:
    write_json(
        CACHE_STATS_PATH,
        {
            "download_cache_hits": 0,
            "download_cache_misses": 0,
            "extraction_cache_hits": 0,
            "extraction_cache_misses": 0,
            "metadata_cache_hits": 0,
            "metadata_cache_misses": 0,
            "parse_cache_hits": 0,
            "parse_cache_misses": 0,
            "review_cache_hits": 0,
            "review_cache_misses": 0,
            "screening_cache_hits": 0,
            "screening_cache_misses": 0,
            "tasks_created": 0,
            "tokens_saved_estimate": 0,
        },
    )


def event(paths: dict[str, Path], source_id: str, event_type: str, message: str, counts: dict[str, Any] | None = None) -> None:
    append_jsonl(
        paths["events"],
        {
            "counts": counts or {},
            "event_type": event_type,
            "message": message,
            "source_id": source_id,
            "timestamp": utc_now(),
        },
    )


def initialize_outputs(paths: dict[str, Path]) -> None:
    for directory in [BATCH_DIR, REPORTS_DIR, STATE_DIR, TASKS_DIR]:
        directory.mkdir(parents=True, exist_ok=True)
    for key in ["status", "events", "codex_tasks", "validated", "manual", "rejected"]:
        paths[key].write_text("", encoding="utf-8", newline="\n")
    for path in [SOURCE_REGISTRY_PATH, ARTIFACT_INDEX_PATH, DECISION_CACHE_PATH, TASK_REGISTRY_PATH]:
        if not path.exists():
            path.write_text("", encoding="utf-8", newline="\n")
    reset_cache_stats()


def summarize_run_files(run_dir: Path) -> dict[str, Any]:
    counts: dict[str, Any] = {
        "download_status": read_json(run_dir / "download_status.json"),
        "metadata": read_json(run_dir / "source_metadata.json"),
        "screening": read_json(run_dir / "screening.json"),
    }
    for output in RUN_JSONL_OUTPUTS:
        counts[output.removesuffix(".jsonl")] = len(read_jsonl(run_dir / output))
    return counts


def index_run_artifacts(source_id: str, run_dir: Path) -> dict[str, str]:
    refs: dict[str, str] = {}
    for artifact_type, filename in ARTIFACT_FILES.items():
        path = run_dir / filename
        if not path.exists():
            continue
        artifact = index_artifact(
            ROOT,
            ARTIFACT_INDEX_PATH,
            source_id,
            artifact_type,
            path,
            "BatchRunner",
            SCHEMA_BY_ARTIFACT_TYPE.get(artifact_type, ""),
        )
        refs[f"{artifact_type}_ref"] = artifact["path"]
    return refs


def stage2_3_cache_run_dir(source: dict[str, Any], batch_id: str) -> Path | None:
    if batch_id != "stage2_4":
        return None
    source_id = str(source.get("source_id", ""))
    if not source_id.startswith("stage2_4_src_"):
        return None
    try:
        number = int(source_id.rsplit("_", 1)[1])
    except ValueError:
        return None
    if 1 <= number <= 10:
        candidate = RUNS_DIR / f"stage2_3_src_{number:03d}"
        if (candidate / "run_summary.md").exists():
            return candidate
    return None


def replace_string_values(value: Any, old: str, new: str) -> Any:
    if isinstance(value, dict):
        return {key: replace_string_values(child, old, new) for key, child in value.items()}
    if isinstance(value, list):
        return [replace_string_values(child, old, new) for child in value]
    if isinstance(value, str):
        return value.replace(old, new)
    return value


def mirror_cached_run(cached_dir: Path, target_dir: Path, target_source_id: str) -> None:
    old_source_id = cached_dir.name
    target_dir.mkdir(parents=True, exist_ok=True)
    for name in RUN_REQUIRED_FILES:
        source_path = cached_dir / name
        target_path = target_dir / name
        if not source_path.exists():
            continue
        if name.endswith(".json"):
            payload = replace_string_values(read_json(source_path), old_source_id, target_source_id)
            write_json(target_path, payload)
        elif name.endswith(".jsonl"):
            payload = [replace_string_values(record, old_source_id, target_source_id) for record in read_jsonl(source_path)]
            write_jsonl(target_path, payload)
        else:
            text = source_path.read_text(encoding="utf-8").replace(old_source_id, target_source_id)
            target_path.write_text(text, encoding="utf-8", newline="\n")
    optional_task_path = cached_dir / "codex_tasks.jsonl"
    if optional_task_path.exists():
        payload = [replace_string_values(record, old_source_id, target_source_id) for record in read_jsonl(optional_task_path)]
        write_jsonl(target_dir / "codex_tasks.jsonl", payload)


def run_dir_for_source(source: dict[str, Any], batch_id: str) -> tuple[Path, bool]:
    direct = RUNS_DIR / str(source["source_id"])
    if (direct / "run_summary.md").exists():
        return direct, True
    cached_stage2_3 = stage2_3_cache_run_dir(source, batch_id)
    if cached_stage2_3 is not None:
        mirror_cached_run(cached_stage2_3, direct, str(source["source_id"]))
        return direct, True
    return direct, False


def run_single_source(source: dict[str, Any], run_dir: Path) -> tuple[int, str]:
    command = [
        sys.executable,
        str(ONE_SOURCE_SCRIPT),
        "--doi",
        source.get("doi", ""),
        "--title",
        source.get("title", ""),
        "--source-id",
        source["source_id"],
        "--run-id",
        source["source_id"],
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    message = (result.stderr or result.stdout or "").strip()
    return result.returncode, message


def update_cache_decisions(run_dir: Path, counts: dict[str, Any], used_cached_run: bool) -> None:
    if used_cached_run and counts.get("metadata"):
        bump_cache_stat("metadata_cache_hits")
    else:
        bump_cache_stat("metadata_cache_misses")
    if used_cached_run and counts.get("screening"):
        bump_cache_stat("screening_cache_hits")
    else:
        bump_cache_stat("screening_cache_misses")
    if used_cached_run and counts.get("download_status"):
        bump_cache_stat("download_cache_hits")
    else:
        bump_cache_stat("download_cache_misses")
    if used_cached_run and int(counts.get("chunks", 0)) > 0:
        bump_cache_stat("parse_cache_hits")
    else:
        bump_cache_stat("parse_cache_misses")

    chunks_path = run_dir / "chunks.jsonl"
    candidates_path = run_dir / "candidate_records.jsonl"
    reviewed_path = run_dir / "reviewed_records.jsonl"
    if chunks_path.exists():
        input_hash = sha256_file(chunks_path)
        if find_decision(DECISION_CACHE_PATH, "extract", input_hash, PROMPT_VERSION, SCHEMA_VERSION):
            bump_cache_stat("extraction_cache_hits")
        else:
            bump_cache_stat("extraction_cache_misses")
            upsert_decision(
                DECISION_CACHE_PATH,
                "extract",
                input_hash,
                PROMPT_VERSION,
                SCHEMA_VERSION,
                relative_path(ROOT, candidates_path),
                f"{counts['candidate_records']} candidate records",
                None,
            )
    if candidates_path.exists():
        input_hash = sha256_file(candidates_path)
        if find_decision(DECISION_CACHE_PATH, "review", input_hash, PROMPT_VERSION, SCHEMA_VERSION):
            bump_cache_stat("review_cache_hits")
        else:
            bump_cache_stat("review_cache_misses")
            upsert_decision(
                DECISION_CACHE_PATH,
                "review",
                input_hash,
                PROMPT_VERSION,
                SCHEMA_VERSION,
                relative_path(ROOT, reviewed_path),
                f"{counts['reviewed_records']} reviewed records",
                None,
            )


def update_tokens_saved_estimate() -> None:
    stats = load_cache_stats()
    estimate = sum(int(stats.get(key, 0)) * weight for key, weight in TOKENS_SAVED_WEIGHTS.items())
    stats["tokens_saved_estimate"] = estimate
    save_cache_stats(stats)


def classify_status(return_code: int, run_dir: Path, counts: dict[str, Any]) -> str:
    if not run_dir.exists() or not (run_dir / "run_summary.md").exists():
        return "failed"
    if return_code not in {0, 2}:
        return "failed"
    if counts["download_status"].get("text_source_mode") == "metadata_only":
        return "metadata_only"
    if int(counts.get("validated_records", 0)) > 0:
        return "validated"
    if int(counts.get("manual_review_records", 0)) > 0 or (run_dir / "codex_tasks.jsonl").exists():
        return "manual_review"
    return "completed_no_records"


def next_action(status: str, counts: dict[str, Any]) -> str:
    if status == "validated":
        return "use run-local validated records for audit; do not merge automatically"
    if status == "metadata_only":
        return "manual_full_text_check"
    if status == "manual_review":
        return "codex_extract_or_review"
    if status == "completed_no_records":
        return "no automatic record found; inspect if source remains high priority"
    return "inspect_failure"


def update_source_registry(source: dict[str, Any], counts: dict[str, Any], artifact_refs: dict[str, str], status: str) -> None:
    metadata = counts["metadata"]
    title = metadata.get("title") or source.get("title") or source.get("expected_topic", "")
    metadata_ref = artifact_refs.get("metadata_ref", "")
    chunks_ref = artifact_refs.get("chunks_ref", "")
    metadata_path = ROOT / metadata_ref if metadata_ref else None
    chunks_path = ROOT / chunks_ref if chunks_ref else None
    upsert_source(
        SOURCE_REGISTRY_PATH,
        {
            "authors": metadata.get("authors", []),
            "candidate_records_ref": artifact_refs.get("candidate_records_ref", ""),
            "chunks_ref": chunks_ref,
            "conditions_ref": "",
            "doi": source.get("doi", ""),
            "download_ref": artifact_refs.get("download_ref", ""),
            "hashes": {
                "chunks_hash": sha256_file(chunks_path) if chunks_path and chunks_path.exists() else "",
                "doi_hash": doi_hash(source.get("doi", "")),
                "fulltext_hash": "",
                "metadata_hash": sha256_file(metadata_path) if metadata_path and metadata_path.exists() else "",
                "title_hash": normalized_title_hash(title),
            },
            "journal": metadata.get("journal", ""),
            "manual_review_ref": artifact_refs.get("manual_review_ref", ""),
            "metadata_ref": metadata_ref,
            "rejected_records_ref": artifact_refs.get("rejected_records_ref", ""),
            "reviewed_records_ref": artifact_refs.get("reviewed_records_ref", ""),
            "screening_ref": artifact_refs.get("screening_ref", ""),
            "source_id": source["source_id"],
            "status": status,
            "title": title,
            "title_normalized": " ".join(str(title).lower().split()),
            "validated_records_ref": artifact_refs.get("validated_records_ref", ""),
            "year": metadata.get("year", ""),
        },
    )


def task_already_exists(task_id: str) -> bool:
    return any(record.get("task_id") == task_id for record in read_jsonl(TASK_REGISTRY_PATH))


def create_batch_task(
    paths: dict[str, Path],
    source: dict[str, Any],
    run_dir: Path,
    artifact_refs: dict[str, str],
    task_type: str,
    reason: str,
    output_expected: str,
) -> None:
    task_id = f"stage2_4_{source['source_id']}_{task_type}"
    input_refs = {
        "download_ref": artifact_refs.get("download_ref", ""),
        "metadata_ref": artifact_refs.get("metadata_ref", ""),
    }
    if task_type in {"extract", "review"}:
        input_refs["chunk_ref"] = artifact_refs.get("chunks_ref", "")
        input_refs["record_ref"] = artifact_refs.get("candidate_records_ref", "")
    payload = create_task_payload(
        ROOT,
        TASKS_DIR,
        TASK_REGISTRY_PATH,
        task_id,
        task_type,
        "ReviewAgent" if task_type == "review" else "ExtractionAgent",
        source["source_id"],
        input_refs,
        output_expected,
        reason,
    )
    bump_cache_stat("tasks_created")
    append_jsonl(
        paths["codex_tasks"],
        {
            "expected_output": payload["output_expected"],
            "input_refs": input_refs,
            "prompt_refs": payload["prompt_refs"],
            "reason": payload["reason"],
            "run_id": source["source_id"],
            "schema_ref": payload["schema_ref"],
            "source_id": source["source_id"],
            "status": "pending",
            "task_id": task_id,
            "task_payload_ref": relative_path(ROOT, TASKS_DIR / f"{task_id}.json"),
            "task_type": task_type,
        },
    )


def collect_tasks(paths: dict[str, Path], source: dict[str, Any], run_dir: Path, artifact_refs: dict[str, str]) -> None:
    download_status = read_json(run_dir / "download_status.json")
    if download_status.get("text_source_mode") == "metadata_only":
        create_batch_task(
            paths,
            source,
            run_dir,
            artifact_refs,
            "manual_full_text_check",
            download_status.get("reason", "No full text available for automatic extraction."),
            artifact_refs.get("chunks_ref", relative_path(ROOT, run_dir / "chunks.jsonl")),
        )
        return
    for task in read_jsonl(run_dir / "codex_tasks.jsonl"):
        task_type = "extract" if task.get("task_type") == "codex_extract_and_review" else str(task.get("task_type", "extract"))
        create_batch_task(
            paths,
            source,
            run_dir,
            artifact_refs,
            task_type,
            task.get("reason", "Codex semantic handoff required."),
            task.get("output_expected", artifact_refs.get("reviewed_records_ref", "")),
        )


def write_batch_record_exports(paths: dict[str, Path], records: list[dict[str, Any]]) -> None:
    validated: list[dict[str, Any]] = []
    manual: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for status in records:
        run_dir = ROOT / str(status["run_dir"])
        validated.extend(read_jsonl(run_dir / "validated_records.jsonl"))
        manual.extend(read_jsonl(run_dir / "manual_review_records.jsonl"))
        rejected.extend(read_jsonl(run_dir / "rejected_records.jsonl"))
    write_jsonl(paths["validated"], validated)
    write_jsonl(paths["manual"], manual)
    write_jsonl(paths["rejected"], rejected)


def run_source(paths: dict[str, Path], source: dict[str, Any], batch_id: str) -> dict[str, Any]:
    source_id = source["source_id"]
    event(paths, source_id, "start", f"Starting {source.get('doi') or source.get('title')}")
    run_dir, used_cached_run = run_dir_for_source(source, batch_id)
    return_code = 0
    failure_message = ""
    if used_cached_run:
        event(paths, source_id, "warning", "Using cached run artifacts; single-source loop was not re-run.")
    else:
        return_code, failure_message = run_single_source(source, run_dir)
    counts = summarize_run_files(run_dir) if run_dir.exists() else {
        "candidate_records": 0,
        "chunks": 0,
        "download_status": {},
        "manual_review_records": 0,
        "metadata": {},
        "rejected_records": 0,
        "reviewed_records": 0,
        "screening": {},
        "validated_records": 0,
    }
    artifact_refs = index_run_artifacts(source_id, run_dir) if run_dir.exists() else {}
    update_cache_decisions(run_dir, counts, used_cached_run)
    status = classify_status(return_code, run_dir, counts)
    failure_reason = ""
    if status == "failed":
        failure_reason = failure_message or "single-source loop failed"
    elif counts["download_status"].get("text_source_mode") == "metadata_only":
        failure_reason = counts["download_status"].get("reason", "")
    record = {
        "artifact_refs": artifact_refs,
        "candidate_records": counts["candidate_records"],
        "counts": {
            "candidate_records": counts["candidate_records"],
            "manual_review_records": counts["manual_review_records"],
            "parsed_chunks": counts["chunks"],
            "rejected_records": counts["rejected_records"],
            "reviewed_records": counts["reviewed_records"],
            "validated_records": counts["validated_records"],
        },
        "doi": source.get("doi", ""),
        "download_status": counts["download_status"].get("text_source_mode", "missing"),
        "expected_topic": source.get("expected_topic", ""),
        "failure_reason": failure_reason,
        "full_text_available": bool(counts["download_status"].get("full_text_available")),
        "full_text_downloaded": bool(counts["download_status"].get("full_text_downloaded")),
        "manual_review_records": counts["manual_review_records"],
        "metadata_status": "success" if counts["metadata"].get("metadata_retrieved") else "failed",
        "next_action": next_action(status, counts),
        "parsed_chunks": counts["chunks"],
        "priority": source.get("priority", ""),
        "query_family": source.get("query_family", ""),
        "rejected_records": counts["rejected_records"],
        "return_code": return_code,
        "reviewed_records": counts["reviewed_records"],
        "run_dir": relative_path(ROOT, run_dir),
        "run_id": source_id,
        "screen_decision": counts["screening"].get("decision", ""),
        "source_id": source_id,
        "status": status,
        "title": source.get("title", ""),
        "updated_at": utc_now(),
        "validated_records": counts["validated_records"],
    }
    for forbidden_key in LONG_TEXT_KEYS:
        record.pop(forbidden_key, None)
    append_jsonl(paths["status"], record)
    collect_tasks(paths, source, run_dir, artifact_refs)
    update_source_registry(source, counts, artifact_refs, status)
    event(paths, source_id, "success" if status != "failed" else "failure", f"Finished with {status}", record)
    return record


def validate_boundary(records: list[dict[str, Any]]) -> None:
    for status in records:
        run_dir = ROOT / str(status["run_dir"])
        for record in read_jsonl(run_dir / "validated_records.jsonl"):
            text = json.dumps(record, ensure_ascii=False).lower()
            hits = [term for term in FORBIDDEN_TERMS if term in text]
            if hits:
                raise ValueError(f"{run_dir}/validated_records.jsonl contains forbidden terms: {hits}")


def task_has_contract(task: dict[str, Any]) -> bool:
    refs = task.get("input_refs", {})
    return bool(refs) and bool(task.get("expected_output")) and bool(task.get("reason"))


def aggregate_status(records: list[dict[str, Any]], paths: dict[str, Path]) -> dict[str, Any]:
    update_tokens_saved_estimate()
    cache_stats = load_cache_stats()
    tasks = read_jsonl(paths["codex_tasks"])
    total_sources = len(records)
    metadata_success = sum(1 for record in records if record.get("metadata_status") == "success")
    metadata_only = sum(1 for record in records if record.get("download_status") == "metadata_only")
    can_scale = (
        total_sources == 30
        and metadata_success >= 24
        and all(record.get("status") not in {"", "unknown", None} for record in records)
        and all((ROOT / str(record.get("run_dir", "")) / "run_summary.md").exists() for record in records)
        and all(record.get("failure_reason") for record in records if record.get("status") == "failed")
        and all(task_has_contract(task) for task in tasks)
    )
    can_scale_value: str | bool = can_scale
    if can_scale and metadata_only >= 20:
        can_scale_value = "true_for_workflow_only"
    return {
        "total_sources": total_sources,
        "metadata_success": metadata_success,
        "screen_download": sum(1 for record in records if record.get("screen_decision") == "include_for_full_text_attempt"),
        "download_success": sum(1 for record in records if record.get("full_text_downloaded") is True),
        "html_or_cache_used": sum(
            1 for record in records if record.get("download_status") in {"downloaded_html", "downloaded_pdf", "local_cached_html"}
        ),
        "metadata_only": metadata_only,
        "parsed_sources": sum(1 for record in records if int(record.get("parsed_chunks", 0)) > 0),
        "total_chunks": sum(int(record.get("parsed_chunks", 0)) for record in records),
        "candidate_records": sum(int(record.get("candidate_records", 0)) for record in records),
        "validated_records": sum(int(record.get("validated_records", 0)) for record in records),
        "manual_review_records": sum(int(record.get("manual_review_records", 0)) for record in records),
        "rejected_records": sum(int(record.get("rejected_records", 0)) for record in records),
        "failed_sources": sum(1 for record in records if record.get("status") == "failed"),
        "codex_tasks_created": len(tasks),
        "new_validated_records_beyond_stage2_3": max(0, sum(int(record.get("validated_records", 0)) for record in records) - 4),
        "metadata_cache_hits": cache_stats.get("metadata_cache_hits", 0),
        "metadata_cache_misses": cache_stats.get("metadata_cache_misses", 0),
        "screening_cache_hits": cache_stats.get("screening_cache_hits", 0),
        "screening_cache_misses": cache_stats.get("screening_cache_misses", 0),
        "download_cache_hits": cache_stats.get("download_cache_hits", 0),
        "download_cache_misses": cache_stats.get("download_cache_misses", 0),
        "parse_cache_hits": cache_stats.get("parse_cache_hits", 0),
        "parse_cache_misses": cache_stats.get("parse_cache_misses", 0),
        "extraction_cache_hits": cache_stats.get("extraction_cache_hits", 0),
        "extraction_cache_misses": cache_stats.get("extraction_cache_misses", 0),
        "review_cache_hits": cache_stats.get("review_cache_hits", 0),
        "review_cache_misses": cache_stats.get("review_cache_misses", 0),
        "tasks_created": cache_stats.get("tasks_created", 0),
        "tokens_saved_estimate": cache_stats.get("tokens_saved_estimate", 0),
        "can_scale_to_100_sources": can_scale_value,
        "database_coverage_still_insufficient": metadata_only >= 20,
    }


def markdown_cell(value: Any) -> str:
    return str(value).replace("\n", " ").replace("|", "\\|")


def write_reports(records: list[dict[str, Any]], paths: dict[str, Path]) -> dict[str, Any]:
    summary = aggregate_status(records, paths)
    lines = ["# Stage 2.4 30-source Loop Summary", ""]
    for key, value in summary.items():
        rendered = str(value).lower() if isinstance(value, bool) else str(value)
        lines.append(f"{key} = {rendered}")
    lines.extend(
        [
            "",
            "cache_hit_summary = see reports/stage2_4_cache_performance.md",
            "tokens_saved_estimate_note = rough estimate from cache hits, not actual token billing.",
            "coverage_note = metadata-only sources still require lawful full-text access before evidence extraction.",
        ]
    )
    paths["summary"].write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    write_query_performance(records, paths)
    write_validated_audit(records, paths)
    write_manual_targets(records, paths)
    write_scale_readiness(summary, paths)
    write_cache_performance(summary, paths)
    return summary


def write_query_performance(records: list[dict[str, Any]], paths: dict[str, Path]) -> None:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(str(record.get("query_family", "")), []).append(record)
    lines = [
        "# Stage 2.4 Query Performance",
        "",
        "| query_family | sources | metadata_success | download_success | parsed_sources | candidate_records | validated_records | manual_review_records | main_failure_reason | next_action |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for family, items in sorted(grouped.items()):
        failure_reasons = [item.get("failure_reason", "") for item in items if item.get("failure_reason")]
        next_actions = sorted({str(item.get("next_action", "")) for item in items if item.get("next_action")})
        lines.append(
            "| {family} | {sources} | {metadata_success} | {download_success} | {parsed_sources} | "
            "{candidate_records} | {validated_records} | {manual_review_records} | {main_failure_reason} | {next_action} |".format(
                family=markdown_cell(family),
                sources=len(items),
                metadata_success=sum(1 for item in items if item.get("metadata_status") == "success"),
                download_success=sum(1 for item in items if item.get("full_text_downloaded") is True),
                parsed_sources=sum(1 for item in items if int(item.get("parsed_chunks", 0)) > 0),
                candidate_records=sum(int(item.get("candidate_records", 0)) for item in items),
                validated_records=sum(int(item.get("validated_records", 0)) for item in items),
                manual_review_records=sum(int(item.get("manual_review_records", 0)) for item in items),
                main_failure_reason=markdown_cell(failure_reasons[0] if failure_reasons else ""),
                next_action=markdown_cell(", ".join(next_actions)),
            )
        )
    paths["query_performance"].write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def write_validated_audit(records: list[dict[str, Any]], paths: dict[str, Path]) -> None:
    lines = ["# Stage 2.4 Validated Records Audit", ""]
    total = 0
    for status in records:
        run_dir = ROOT / str(status["run_dir"])
        for record in read_jsonl(run_dir / "validated_records.jsonl"):
            total += 1
            lines.extend(
                [
                    f"## {record.get('record_id', '')}",
                    "",
                    f"source_id = {record.get('source_id', '')}",
                    f"doi = {record.get('doi', '')}",
                    f"parent = {record.get('parent_compound', {}).get('name', '')}",
                    f"product = {record.get('product_compound', {}).get('name', '')}",
                    f"evidence_tier = {record.get('review', {}).get('evidence_tier', '')}",
                    f"setting_type = {record.get('conditions', {}).get('setting_type', '')}",
                    f"requires_manual_confirmation = {str(record.get('review', {}).get('requires_manual_confirmation', '')).lower()}",
                    "accepted_reason = run-local validated record passed natural-environment boundary filter.",
                    "limitations = evidence remains run-local and is not merged into main database by this batch.",
                    "",
                ]
            )
    if total == 0:
        lines.append("No validated records were produced by this batch.")
    paths["validated_audit"].write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def write_manual_targets(records: list[dict[str, Any]], paths: dict[str, Path]) -> None:
    lines = [
        "# Stage 2.4 Manual Full-text Targets",
        "",
        "| priority | source_id | doi | title | reason | next_action |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for record in sorted(records, key=lambda item: str(item.get("priority", ""))):
        if record.get("next_action") != "manual_full_text_check":
            continue
        lines.append(
            "| {priority} | {source_id} | {doi} | {title} | {reason} | {next_action} |".format(
                priority=markdown_cell(record.get("priority", "")),
                source_id=markdown_cell(record.get("source_id", "")),
                doi=markdown_cell(record.get("doi", "")),
                title=markdown_cell(record.get("title", "")),
                reason=markdown_cell(record.get("failure_reason", "")),
                next_action=markdown_cell(record.get("next_action", "")),
            )
        )
    paths["manual_targets"].write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def write_scale_readiness(summary: dict[str, Any], paths: dict[str, Path]) -> None:
    lines = ["# Stage 2.4 Scale Readiness", ""]
    for key in [
        "total_sources",
        "metadata_success",
        "failed_sources",
        "codex_tasks_created",
        "can_scale_to_100_sources",
        "database_coverage_still_insufficient",
    ]:
        lines.append(f"{key} = {summary.get(key)}")
    lines.append("")
    lines.append("Criteria: 30 sources, at least 24 metadata successes, valid JSONL, no unknown statuses, valid task refs, and natural-environment boundary compliance.")
    paths["scale_readiness"].write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def write_cache_performance(summary: dict[str, Any], paths: dict[str, Path]) -> None:
    task_paths = [ROOT / record["task_path"] for record in read_jsonl(TASK_REGISTRY_PATH) if record.get("task_path", "").startswith("data/tasks/")]
    sizes = [path.stat().st_size for path in task_paths if path.exists()]
    average_size = int(sum(sizes) / len(sizes)) if sizes else 0
    lines = ["# Stage 2.4 Cache Performance", ""]
    for key in [
        "metadata_cache_hits",
        "metadata_cache_misses",
        "screening_cache_hits",
        "screening_cache_misses",
        "download_cache_hits",
        "download_cache_misses",
        "parse_cache_hits",
        "parse_cache_misses",
        "extraction_cache_hits",
        "extraction_cache_misses",
        "review_cache_hits",
        "review_cache_misses",
        "tasks_created",
        "tokens_saved_estimate",
    ]:
        lines.append(f"{key} = {summary.get(key)}")
    lines.extend(
        [
            f"task_registry_records = {len(read_jsonl(TASK_REGISTRY_PATH))}",
            f"average_task_payload_size = {average_size}",
            "long_text_removed_from_status = true",
            "",
            "tokens_saved_estimate is a rough estimate from configured cache-hit weights, not actual token billing.",
        ]
    )
    paths["cache_performance"].write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def run_batch(queue_path: Path, batch_id: str, max_sources: int) -> dict[str, Any]:
    paths = batch_paths(batch_id)
    queue = read_jsonl(queue_path)
    if max_sources:
        queue = queue[:max_sources]
    initialize_outputs(paths)
    records: list[dict[str, Any]] = []
    for source in queue:
        if source.get("status") != "pending":
            continue
        try:
            records.append(run_source(paths, source, batch_id))
        except Exception as exc:
            source_id = source.get("source_id", "unknown")
            run_dir = RUNS_DIR / source_id
            failure = {
                "artifact_refs": {},
                "candidate_records": 0,
                "counts": {
                    "candidate_records": 0,
                    "manual_review_records": 0,
                    "parsed_chunks": 0,
                    "rejected_records": 0,
                    "reviewed_records": 0,
                    "validated_records": 0,
                },
                "doi": source.get("doi", ""),
                "download_status": "missing",
                "expected_topic": source.get("expected_topic", ""),
                "failure_reason": repr(exc),
                "full_text_available": False,
                "full_text_downloaded": False,
                "manual_review_records": 0,
                "metadata_status": "failed",
                "next_action": "inspect_failure",
                "parsed_chunks": 0,
                "priority": source.get("priority", ""),
                "query_family": source.get("query_family", ""),
                "rejected_records": 0,
                "return_code": 1,
                "reviewed_records": 0,
                "run_dir": relative_path(ROOT, run_dir),
                "run_id": source_id,
                "screen_decision": "",
                "source_id": source_id,
                "status": "failed",
                "title": source.get("title", ""),
                "updated_at": utc_now(),
                "validated_records": 0,
            }
            append_jsonl(paths["status"], failure)
            event(paths, source_id, "failure", repr(exc), failure)
            records.append(failure)
    validate_boundary(records)
    write_batch_record_exports(paths, records)
    summary = write_reports(records, paths)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a cache-aware PFAS batch source loop.")
    parser.add_argument("--queue", required=True, help="Queue JSONL path.")
    parser.add_argument("--batch-id", required=True, help="Batch id prefix, e.g. stage2_4.")
    parser.add_argument("--max-sources", type=int, default=0, help="Maximum sources to process.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    run_batch(ROOT / args.queue, args.batch_id, args.max_sources)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
