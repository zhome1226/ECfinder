"""Run the Stage 2.3 minimal 10-source PFAS evidence loop."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ecfinder.state.artifact_index import index_artifact
from ecfinder.state.common import (
    doi_hash,
    normalized_title_hash,
    read_json as read_state_json,
    relative_path,
    sha256_file,
    write_json,
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
QUEUE_PATH = BATCH_DIR / "stage2_3_10source_queue.jsonl"
STATUS_PATH = BATCH_DIR / "stage2_3_10source_status.jsonl"
EVENTS_PATH = BATCH_DIR / "stage2_3_10source_events.jsonl"
CODEX_TASKS_PATH = BATCH_DIR / "stage2_3_codex_tasks.jsonl"
SUMMARY_PATH = REPORTS_DIR / "stage2_3_10source_loop_summary.md"
PERFORMANCE_PATH = REPORTS_DIR / "stage2_3_10source_query_performance.md"
ONE_SOURCE_SCRIPT = ROOT / "scripts" / "run_one_source_loop.py"
PROMPT_VERSION = "stage2_4_pre_v1"
SCHEMA_VERSION = "stage2_4_pre_v1"

JSONL_OUTPUTS = [
    "chunks.jsonl",
    "candidate_records.jsonl",
    "reviewed_records.jsonl",
    "validated_records.jsonl",
    "manual_review_records.jsonl",
    "rejected_records.jsonl",
]

FORBIDDEN_TERMS = ["activated sludge", "wastewater treatment", "wwtp", "engineered treatment"]

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


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: normalize_value(child) for key, child in value.items()}
    if isinstance(value, list):
        return [normalize_value(child) for child in value]
    if isinstance(value, str):
        return value.replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n")
    return value


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(normalize_value(record), ensure_ascii=False, sort_keys=True) + "\n")


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(normalize_value(record), ensure_ascii=False, sort_keys=True) + "\n")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            if "} {" in line:
                raise ValueError(f"{path}:{line_no} contains multiple JSON objects")
            obj = json.loads(line)
            if not isinstance(obj, dict):
                raise ValueError(f"{path}:{line_no} is not a JSON object")
            records.append(obj)
    return records


def load_queue() -> list[dict[str, Any]]:
    return read_jsonl(QUEUE_PATH)


def reset_batch_outputs() -> None:
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    for path in [STATUS_PATH, EVENTS_PATH, CODEX_TASKS_PATH]:
        path.write_text("", encoding="utf-8")
    for path in [SOURCE_REGISTRY_PATH, ARTIFACT_INDEX_PATH, DECISION_CACHE_PATH, TASK_REGISTRY_PATH]:
        if not path.exists():
            path.write_text("", encoding="utf-8")
    write_json(
        CACHE_STATS_PATH,
        {
            "metadata_cache_hits": 0,
            "metadata_cache_misses": 0,
            "screening_cache_hits": 0,
            "screening_cache_misses": 0,
            "parse_cache_hits": 0,
            "parse_cache_misses": 0,
            "extraction_cache_hits": 0,
            "extraction_cache_misses": 0,
            "review_cache_hits": 0,
            "review_cache_misses": 0,
            "tasks_created": 0,
            "tokens_saved_estimate": 0,
        },
    )


def load_cache_stats() -> dict[str, int]:
    stats = read_state_json(CACHE_STATS_PATH)
    return {key: int(value) for key, value in stats.items()}


def save_cache_stats(stats: dict[str, int]) -> None:
    write_json(CACHE_STATS_PATH, stats)


def bump_cache_stat(key: str, amount: int = 1) -> None:
    stats = load_cache_stats()
    stats[key] = stats.get(key, 0) + amount
    save_cache_stats(stats)


def event(source_id: str, event_type: str, message: str, counts: dict[str, Any] | None = None) -> None:
    append_jsonl(
        EVENTS_PATH,
        {
            "timestamp": utc_now(),
            "source_id": source_id,
            "event_type": event_type,
            "message": message,
            "counts": counts or {},
        },
    )


def run_source(source: dict[str, Any]) -> dict[str, Any]:
    source_id = source["source_id"]
    run_id = source_id
    run_dir = RUNS_DIR / run_id
    event(source_id, "start", f"Starting {source.get('doi', '')}")
    preexisting = summarize_run_files(run_dir) if run_dir.exists() else None
    if preexisting and (run_dir / "run_summary.md").exists():
        return_code = 0
        event(source_id, "warning", "Using cached run artifacts; single-source loop was not re-run.")
    else:
        command = [
            sys.executable,
            str(ONE_SOURCE_SCRIPT),
            "--doi",
            source["doi"],
            "--source-id",
            source_id,
            "--run-id",
            run_id,
        ]
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
        return_code = result.returncode

    counts = summarize_run_files(run_dir)
    artifact_refs = index_run_artifacts(source_id, run_dir)
    update_cache_decisions(source_id, run_dir, counts, preexisting)
    status = classify_status(return_code, run_dir, counts)
    failure_reason = ""
    if status == "failed":
        failure_reason = "single-source loop failed"
        if "result" in locals():
            failure_reason = (result.stderr or result.stdout or failure_reason).strip()
    elif counts["download_status"].get("text_source_mode") == "metadata_only":
        failure_reason = counts["download_status"].get("reason", "")

    record = {
        "source_id": source_id,
        "doi": source["doi"],
        "priority": source.get("priority", ""),
        "query_family": source.get("query_family", ""),
        "expected_topic": source.get("expected_topic", ""),
        "run_id": run_id,
        "run_dir": str(run_dir.relative_to(ROOT)),
        "status": status,
        "return_code": return_code,
        "metadata_status": "success" if counts["metadata"].get("metadata_retrieved") else "failed",
        "screen_decision": counts["screening"].get("decision", ""),
        "download_status": counts["download_status"].get("text_source_mode", "missing"),
        "full_text_downloaded": bool(counts["download_status"].get("full_text_downloaded")),
        "full_text_available": bool(counts["download_status"].get("full_text_available")),
        "parsed_chunks": counts["chunks"],
        "candidate_records": counts["candidate_records"],
        "reviewed_records": counts["reviewed_records"],
        "validated_records": counts["validated_records"],
        "manual_review_records": counts["manual_review_records"],
        "rejected_records": counts["rejected_records"],
        "failure_reason": failure_reason,
        "next_action": next_action(status, counts),
        "artifact_refs": artifact_refs,
        "counts": {
            "parsed_chunks": counts["chunks"],
            "candidate_records": counts["candidate_records"],
            "reviewed_records": counts["reviewed_records"],
            "validated_records": counts["validated_records"],
            "manual_review_records": counts["manual_review_records"],
            "rejected_records": counts["rejected_records"],
        },
        "updated_at": utc_now(),
    }
    append_jsonl(STATUS_PATH, record)
    collect_codex_tasks(source, run_id, run_dir, artifact_refs)
    update_source_registry(source, counts, artifact_refs, status)
    event(source_id, "success" if status != "failed" else "failure", f"Finished with {status}", record)
    return record


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


def update_cache_decisions(
    source_id: str,
    run_dir: Path,
    counts: dict[str, Any],
    preexisting: dict[str, Any] | None,
) -> None:
    metadata_path = run_dir / "source_metadata.json"
    screening_path = run_dir / "screening.json"
    chunks_path = run_dir / "chunks.jsonl"
    candidates_path = run_dir / "candidate_records.jsonl"
    reviewed_path = run_dir / "reviewed_records.jsonl"

    if preexisting and preexisting.get("metadata"):
        bump_cache_stat("metadata_cache_hits")
        bump_cache_stat("tokens_saved_estimate", 250)
    else:
        bump_cache_stat("metadata_cache_misses")
    if preexisting and preexisting.get("screening"):
        bump_cache_stat("screening_cache_hits")
        bump_cache_stat("tokens_saved_estimate", 150)
    else:
        bump_cache_stat("screening_cache_misses")
    if preexisting and preexisting.get("chunks", 0) > 0:
        bump_cache_stat("parse_cache_hits")
        bump_cache_stat("tokens_saved_estimate", max(1, preexisting.get("chunks", 0)) * 300)
    else:
        bump_cache_stat("parse_cache_misses")

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


def update_source_registry(
    source: dict[str, Any],
    counts: dict[str, Any],
    artifact_refs: dict[str, str],
    status: str,
) -> None:
    metadata = counts["metadata"]
    title = metadata.get("title") or source.get("expected_topic", "")
    chunks_ref = artifact_refs.get("chunks_ref", "")
    metadata_path = ROOT / artifact_refs["metadata_ref"] if artifact_refs.get("metadata_ref") else None
    chunks_path = ROOT / chunks_ref if chunks_ref else None
    registry_record = {
        "source_id": source["source_id"],
        "doi": source.get("doi", ""),
        "title": title,
        "title_normalized": " ".join(str(title).lower().split()),
        "year": metadata.get("year", ""),
        "journal": metadata.get("journal", ""),
        "authors": metadata.get("authors", []),
        "metadata_ref": artifact_refs.get("metadata_ref", ""),
        "screening_ref": artifact_refs.get("screening_ref", ""),
        "download_ref": artifact_refs.get("download_ref", ""),
        "chunks_ref": chunks_ref,
        "candidate_records_ref": artifact_refs.get("candidate_records_ref", ""),
        "reviewed_records_ref": artifact_refs.get("reviewed_records_ref", ""),
        "validated_records_ref": artifact_refs.get("validated_records_ref", ""),
        "manual_review_ref": artifact_refs.get("manual_review_ref", ""),
        "rejected_records_ref": artifact_refs.get("rejected_records_ref", ""),
        "status": status,
        "hashes": {
            "doi_hash": doi_hash(source.get("doi", "")),
            "title_hash": normalized_title_hash(title),
            "metadata_hash": sha256_file(metadata_path) if metadata_path and metadata_path.exists() else "",
            "fulltext_hash": "",
            "chunks_hash": sha256_file(chunks_path) if chunks_path and chunks_path.exists() else "",
        },
    }
    upsert_source(SOURCE_REGISTRY_PATH, registry_record)


def classify_status(return_code: int, run_dir: Path, counts: dict[str, Any]) -> str:
    if not run_dir.exists() or not (run_dir / "run_summary.md").exists():
        return "failed"
    if return_code not in {0, 2}:
        return "failed"
    if counts["download_status"].get("text_source_mode") == "metadata_only":
        return "metadata_only"
    if counts["validated_records"] > 0:
        return "validated"
    if counts["manual_review_records"] > 0 or (run_dir / "codex_tasks.jsonl").exists():
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


def summarize_run_files(run_dir: Path) -> dict[str, Any]:
    metadata = read_json(run_dir / "source_metadata.json")
    screening = read_json(run_dir / "screening.json")
    download_status = read_json(run_dir / "download_status.json")
    counts: dict[str, Any] = {
        "metadata": metadata,
        "screening": screening,
        "download_status": download_status,
    }
    for output in JSONL_OUTPUTS:
        counts[output.removesuffix(".jsonl")] = len(read_jsonl(run_dir / output))
    return counts


def collect_codex_tasks(source: dict[str, Any], run_id: str, run_dir: Path, artifact_refs: dict[str, str]) -> None:
    download_status = read_json(run_dir / "download_status.json")
    if download_status.get("text_source_mode") == "metadata_only":
        task_id = f"stage2_4_pre_{source['source_id']}_manual_full_text"
        task_payload = create_task_payload(
            ROOT,
            TASKS_DIR,
            TASK_REGISTRY_PATH,
            task_id,
            "manual_full_text_check",
            "DownloadAgent",
            source["source_id"],
            {
                "metadata_ref": artifact_refs.get("metadata_ref", ""),
                "download_ref": artifact_refs.get("download_ref", ""),
            },
            artifact_refs.get("chunks_ref", str((run_dir / "chunks.jsonl").relative_to(ROOT)).replace("\\", "/")),
            download_status.get("reason", "No full text available for automatic extraction."),
        )
        bump_cache_stat("tasks_created")
        append_jsonl(
            CODEX_TASKS_PATH,
            {
                "task_id": task_payload["task_id"],
                "source_id": source["source_id"],
                "run_id": run_id,
                "task_type": "manual_full_text_check",
                "input_files": [artifact_refs.get("download_ref", "")],
                "prompt_file": "",
                "expected_output": task_payload["output_expected"],
                "reason": task_payload["reason"],
                "task_payload_ref": relative_path(ROOT, TASKS_DIR / f"{task_id}.json"),
                "status": "pending",
            },
        )
        return

    local_tasks = read_jsonl(run_dir / "codex_tasks.jsonl")
    if local_tasks:
        for task in local_tasks:
            task_id = f"stage2_4_pre_{task.get('task_id', source['source_id'])}"
            task_payload = create_task_payload(
                ROOT,
                TASKS_DIR,
                TASK_REGISTRY_PATH,
                task_id,
                "extract",
                "ExtractionAgent",
                source["source_id"],
                {
                    "metadata_ref": artifact_refs.get("metadata_ref", ""),
                    "chunk_ref": artifact_refs.get("chunks_ref", ""),
                },
                task.get("output_expected", ""),
                task.get("reason", ""),
            )
            bump_cache_stat("tasks_created")
            append_jsonl(
                CODEX_TASKS_PATH,
                {
                    "task_id": task_payload["task_id"],
                    "source_id": source["source_id"],
                    "run_id": run_id,
                    "task_type": "extract" if task.get("task_type") == "codex_extract_and_review" else task.get("task_type", ""),
                    "input_files": [artifact_refs.get("chunks_ref", task.get("input_ref", ""))],
                    "prompt_file": "prompts/system/pfas_transformation_extraction.md",
                    "expected_output": task_payload["output_expected"],
                    "reason": task_payload["reason"],
                    "task_payload_ref": relative_path(ROOT, TASKS_DIR / f"{task_id}.json"),
                    "status": "pending",
                },
        )
        return


def aggregate_status(records: list[dict[str, Any]]) -> dict[str, int | bool]:
    total_chunks = sum(int(record["parsed_chunks"]) for record in records)
    candidate_records = sum(int(record["candidate_records"]) for record in records)
    validated_records = sum(int(record["validated_records"]) for record in records)
    manual_review_records = sum(int(record["manual_review_records"]) for record in records)
    rejected_records = sum(int(record["rejected_records"]) for record in records)
    codex_tasks_created = len(read_jsonl(CODEX_TASKS_PATH))
    cache_stats = load_cache_stats()
    metadata_success = sum(1 for record in records if record["metadata_status"] == "success")
    download_success = sum(1 for record in records if record["full_text_downloaded"])
    html_or_cache_used = sum(
        1 for record in records if record["download_status"] in {"downloaded_html", "downloaded_pdf", "local_cached_html"}
    )
    metadata_only = sum(1 for record in records if record["download_status"] == "metadata_only")
    failed_sources = sum(1 for record in records if record["status"] == "failed")
    parsed_sources = sum(1 for record in records if int(record["parsed_chunks"]) > 0)
    can_scale = (
        len(records) == 10
        and metadata_success >= 8
        and all(record["status"] not in {"", "unknown"} for record in records)
        and all((ROOT / record["run_dir"] / "run_summary.md").exists() for record in records)
        and all(record["failure_reason"] for record in records if record["status"] == "failed")
        and all(task_has_contract(task) for task in read_jsonl(CODEX_TASKS_PATH))
    )
    return {
        "total_sources": len(records),
        "metadata_success": metadata_success,
        "screen_download": sum(1 for record in records if record["screen_decision"] == "include_for_full_text_attempt"),
        "download_success": download_success,
        "html_or_cache_used": html_or_cache_used,
        "metadata_only": metadata_only,
        "parsed_sources": parsed_sources,
        "total_chunks": total_chunks,
        "candidate_records": candidate_records,
        "validated_records": validated_records,
        "manual_review_records": manual_review_records,
        "rejected_records": rejected_records,
        "failed_sources": failed_sources,
        "codex_tasks_created": codex_tasks_created,
        "can_scale_to_30_sources": can_scale,
        "metadata_cache_hits": cache_stats.get("metadata_cache_hits", 0),
        "metadata_cache_misses": cache_stats.get("metadata_cache_misses", 0),
        "screening_cache_hits": cache_stats.get("screening_cache_hits", 0),
        "screening_cache_misses": cache_stats.get("screening_cache_misses", 0),
        "parse_cache_hits": cache_stats.get("parse_cache_hits", 0),
        "parse_cache_misses": cache_stats.get("parse_cache_misses", 0),
        "extraction_cache_hits": cache_stats.get("extraction_cache_hits", 0),
        "extraction_cache_misses": cache_stats.get("extraction_cache_misses", 0),
        "review_cache_hits": cache_stats.get("review_cache_hits", 0),
        "review_cache_misses": cache_stats.get("review_cache_misses", 0),
        "tasks_created": cache_stats.get("tasks_created", 0),
        "tokens_saved_estimate": cache_stats.get("tokens_saved_estimate", 0),
    }


def task_has_contract(task: dict[str, Any]) -> bool:
    return bool(task.get("input_files")) and bool(task.get("expected_output")) and bool(task.get("reason"))


def write_reports(records: list[dict[str, Any]]) -> dict[str, int | bool]:
    summary = aggregate_status(records)
    lines = ["# Stage 2.3 10-source Loop Summary", ""]
    for key, value in summary.items():
        rendered = str(value).lower() if isinstance(value, bool) else str(value)
        lines.append(f"{key} = {rendered}")
    lines.append("")
    lines.append("Counts are generated from data/runs and data/batches JSONL files written by the 10-source loop.")
    SUMMARY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    perf_lines = [
        "# Stage 2.3 10-source Query Performance",
        "",
        "| source_id | doi | query_family | metadata_status | screen_decision | download_status | parsed_chunks | candidate_records | validated_records | manual_review_records | rejected_records | failure_reason | next_action |",
        "| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for record in records:
        perf_lines.append(
            "| {source_id} | {doi} | {query_family} | {metadata_status} | {screen_decision} | {download_status} | "
            "{parsed_chunks} | {candidate_records} | {validated_records} | {manual_review_records} | "
            "{rejected_records} | {failure_reason} | {next_action} |".format(
                **{key: markdown_cell(value) for key, value in record.items()}
            )
        )
    PERFORMANCE_PATH.write_text("\n".join(perf_lines) + "\n", encoding="utf-8")
    return summary


def markdown_cell(value: Any) -> str:
    text = str(value).replace("\n", " ").replace("|", "\\|")
    return text


def validate_no_forbidden_validated(records: list[dict[str, Any]]) -> None:
    for record in records:
        run_dir = ROOT / record["run_dir"]
        for validated in read_jsonl(run_dir / "validated_records.jsonl"):
            text = json.dumps(validated, ensure_ascii=False).lower()
            hits = [term for term in FORBIDDEN_TERMS if term in text]
            if hits:
                raise ValueError(f"{run_dir}/validated_records.jsonl contains forbidden terms: {hits}")


def main() -> int:
    queue = load_queue()
    if len(queue) != 10:
        raise SystemExit(f"Expected 10 sources in queue, found {len(queue)}")
    reset_batch_outputs()
    records: list[dict[str, Any]] = []
    for source in queue:
        if source.get("status") != "pending":
            continue
        try:
            records.append(run_source(source))
        except Exception as exc:  # keep the batch moving even if a source crashes
            source_id = source.get("source_id", "unknown")
            run_id = source_id
            failure = {
                "source_id": source_id,
                "doi": source.get("doi", ""),
                "priority": source.get("priority", ""),
                "query_family": source.get("query_family", ""),
                "expected_topic": source.get("expected_topic", ""),
                "run_id": run_id,
                "run_dir": str((RUNS_DIR / run_id).relative_to(ROOT)),
                "status": "failed",
                "return_code": 1,
                "metadata_status": "failed",
                "screen_decision": "",
                "download_status": "missing",
                "full_text_downloaded": False,
                "full_text_available": False,
                "parsed_chunks": 0,
                "candidate_records": 0,
                "reviewed_records": 0,
                "validated_records": 0,
                "manual_review_records": 0,
                "rejected_records": 0,
                "failure_reason": repr(exc),
                "next_action": "inspect_failure",
                "artifact_refs": {},
                "counts": {
                    "parsed_chunks": 0,
                    "candidate_records": 0,
                    "reviewed_records": 0,
                    "validated_records": 0,
                    "manual_review_records": 0,
                    "rejected_records": 0,
                },
                "updated_at": utc_now(),
            }
            append_jsonl(STATUS_PATH, failure)
            event(source_id, "failure", repr(exc), failure)
            records.append(failure)
    validate_no_forbidden_validated(records)
    summary = write_reports(records)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
