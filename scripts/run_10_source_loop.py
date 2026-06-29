"""Run the Stage 2.3 minimal 10-source PFAS evidence loop."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BATCH_DIR = ROOT / "data" / "batches"
RUNS_DIR = ROOT / "data" / "runs"
REPORTS_DIR = ROOT / "reports"
QUEUE_PATH = BATCH_DIR / "stage2_3_10source_queue.jsonl"
STATUS_PATH = BATCH_DIR / "stage2_3_10source_status.jsonl"
EVENTS_PATH = BATCH_DIR / "stage2_3_10source_events.jsonl"
CODEX_TASKS_PATH = BATCH_DIR / "stage2_3_codex_tasks.jsonl"
SUMMARY_PATH = REPORTS_DIR / "stage2_3_10source_loop_summary.md"
PERFORMANCE_PATH = REPORTS_DIR / "stage2_3_10source_query_performance.md"
ONE_SOURCE_SCRIPT = ROOT / "scripts" / "run_one_source_loop.py"

JSONL_OUTPUTS = [
    "chunks.jsonl",
    "candidate_records.jsonl",
    "reviewed_records.jsonl",
    "validated_records.jsonl",
    "manual_review_records.jsonl",
    "rejected_records.jsonl",
]

FORBIDDEN_TERMS = ["activated sludge", "wastewater treatment", "wwtp", "engineered treatment"]


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
    for path in [STATUS_PATH, EVENTS_PATH, CODEX_TASKS_PATH]:
        path.write_text("", encoding="utf-8")


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

    counts = summarize_run_files(run_dir)
    status = classify_status(result.returncode, run_dir, counts)
    failure_reason = ""
    if status == "failed":
        failure_reason = (result.stderr or result.stdout or "single-source loop failed").strip()
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
        "return_code": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
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
        "updated_at": utc_now(),
    }
    append_jsonl(STATUS_PATH, record)
    collect_codex_tasks(source, run_id, run_dir)
    event(source_id, "success" if status != "failed" else "failure", f"Finished with {status}", record)
    return record


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


def collect_codex_tasks(source: dict[str, Any], run_id: str, run_dir: Path) -> None:
    download_status = read_json(run_dir / "download_status.json")
    if download_status.get("text_source_mode") == "metadata_only":
        append_jsonl(
            CODEX_TASKS_PATH,
            {
                "task_id": f"stage2_3_{source['source_id']}_manual_full_text",
                "source_id": source["source_id"],
                "run_id": run_id,
                "task_type": "manual_full_text_check",
                "input_files": [str((run_dir / "download_status.json").relative_to(ROOT))],
                "prompt_file": "",
                "expected_output": str((run_dir / "chunks.jsonl").relative_to(ROOT)),
                "reason": download_status.get("reason", "No full text available for automatic extraction."),
                "status": "pending",
            },
        )
        return

    local_tasks = read_jsonl(run_dir / "codex_tasks.jsonl")
    if local_tasks:
        for task in local_tasks:
            append_jsonl(
                CODEX_TASKS_PATH,
                {
                    "task_id": f"stage2_3_{task.get('task_id', source['source_id'])}",
                    "source_id": source["source_id"],
                    "run_id": run_id,
                    "task_type": "extract" if task.get("task_type") == "codex_extract_and_review" else task.get("task_type", ""),
                    "input_files": [task.get("input_ref", "")],
                    "prompt_file": "prompts/extract_transformation_records.md",
                    "expected_output": task.get("output_expected", ""),
                    "reason": task.get("reason", ""),
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
                "stdout": "",
                "stderr": repr(exc),
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
