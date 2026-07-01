"""Validate Stage 2.5 closed-loop executor outputs."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ecfinder.state.common import read_jsonl


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "reports" / "stage2_5_closed_loop_summary.md"
RUNNABLE = ROOT / "data" / "state" / "runnable_tasks.jsonl"
STATUS = ROOT / "data" / "batches" / "stage2_4j_available_fulltext_ingest_status.jsonl"
TASKS = ROOT / "data" / "batches" / "stage2_4j_codex_tasks.jsonl"
FORBIDDEN = ["activated sludge", "wastewater treatment", "wwtp", "aop", "plasma", "photocatalysis", "ozonation", "incineration"]


def parse_summary(path: Path) -> dict[str, str]:
    if not path.exists():
        raise ValueError(f"missing summary: {path}")
    values: dict[str, str] = {}
    pattern = re.compile(r"^([A-Za-z0-9_]+)\s*=\s*(.+?)\s*$")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            values[match.group(1)] = match.group(2)
    return values


def as_int(values: dict[str, str], key: str) -> int:
    return int(values.get(key, "0"))


def require(path: Path) -> None:
    if not path.exists():
        raise ValueError(f"missing required path: {path}")


def validate_raw_fulltext_not_committed() -> None:
    result = subprocess.run(
        ["git", "ls-files", "data/local_fulltext/stage2_4j/pdf", "data/local_fulltext/stage2_4j/html", "data/local_fulltext/stage2_4j/si"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(result.stderr.strip())
    bad = [line for line in result.stdout.splitlines() if line.strip() and not line.replace("\\", "/").endswith("/.gitkeep")]
    if bad:
        raise ValueError(f"raw fulltext tracked by Git: {bad}")


def validate_records() -> dict[str, int]:
    candidate = reviewed = validated = manual = rejected = auxiliary = 0
    for row in read_jsonl(STATUS):
        run_dir = ROOT / str(row.get("run_dir", ""))
        if not run_dir.exists():
            raise ValueError(f"missing run dir: {run_dir}")
        files = {
            "candidate": run_dir / "candidate_records.jsonl",
            "reviewed": run_dir / "reviewed_records.jsonl",
            "validated": run_dir / "validated_records.jsonl",
            "manual": run_dir / "manual_review_records.jsonl",
            "rejected": run_dir / "rejected_records.jsonl",
            "auxiliary": run_dir / "auxiliary_records.jsonl",
        }
        for path in files.values():
            require(path)
        candidates = read_jsonl(files["candidate"])
        for record in candidates:
            if not record.get("source_id") or not record.get("chunk_id"):
                raise ValueError(f"candidate missing source_id/chunk_id: {record}")
            if not (record.get("parent_compound") and record.get("product_compound")):
                raise ValueError(f"candidate missing parent/product: {record.get('record_id')}")
        for record in read_jsonl(files["validated"]):
            review = record.get("review", {})
            if review.get("natural_environment_valid") is not True:
                raise ValueError(f"validated record not natural_environment_valid: {record.get('record_id')}")
            if review.get("evidence_tier") not in {"confirmed_validated", "probable_validated", "tentative_validated"}:
                raise ValueError(f"validated record bad evidence tier: {record.get('record_id')}")
            text = json.dumps(record, ensure_ascii=False).lower()
            hits = [term for term in FORBIDDEN if term in text]
            if hits:
                raise ValueError(f"forbidden boundary in validated record: {hits}")
        candidate += len(candidates)
        reviewed += len(read_jsonl(files["reviewed"]))
        validated += len(read_jsonl(files["validated"]))
        manual += len(read_jsonl(files["manual"]))
        rejected += len(read_jsonl(files["rejected"]))
        auxiliary += len(read_jsonl(files["auxiliary"]))
    return {
        "candidate_records_written": candidate,
        "reviewed_records_written": reviewed,
        "validated_records_written": validated,
        "manual_review_records_written": manual,
        "rejected_records_written": rejected,
        "auxiliary_records_written": auxiliary,
    }


def main() -> int:
    summary = parse_summary(SUMMARY)
    if as_int(summary, "input_pending_codex_tasks") > 0 and as_int(summary, "tasks_executed") <= 0:
        raise ValueError("pending input tasks existed but no tasks were executed")
    if as_int(summary, "input_parsed_sources") > 0 and as_int(summary, "input_chunks") > 0 and as_int(summary, "extraction_tasks_executed") <= 0:
        raise ValueError("parsed chunks existed but no extraction task executed")
    if as_int(summary, "pending_tasks_remaining") != 0:
        raise ValueError("pending tasks remain after closed-loop")
    if summary.get("workflow_closed_loop_success") != "true":
        raise ValueError("workflow_closed_loop_success must be true")
    runnable = read_jsonl(RUNNABLE)
    if runnable:
        raise ValueError(f"runnable tasks remain: {len(runnable)}")
    task_rows = read_jsonl(TASKS)
    if any(row.get("status") == "pending" for row in task_rows):
        raise ValueError("stage2_4j task still pending")
    counts = validate_records()
    for key, value in counts.items():
        if as_int(summary, key) != value:
            raise ValueError(f"summary mismatch for {key}: expected {value}, got {summary.get(key)}")
    for report in [
        "stage2_5_agent_execution_trace.md",
        "stage2_5_task_completion_audit.md",
        "stage2_5_database_write_audit.md",
        "stage2_5_remaining_blockers.md",
        "current_runnable_tasks.md",
    ]:
        require(ROOT / "reports" / report)
    for state_file in ["task_registry.jsonl", "source_status_board.jsonl", "artifact_index.jsonl", "decision_cache.jsonl"]:
        read_jsonl(ROOT / "data" / "state" / state_file)
    validate_raw_fulltext_not_committed()
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
