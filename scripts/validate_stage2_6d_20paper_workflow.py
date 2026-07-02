"""Validate the Stage 2.6d 20-paper integrated workflow."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ecfinder.state.common import read_json, read_jsonl


ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "data" / "batches"
STATE = ROOT / "data" / "state"
REPORT = ROOT / "reports" / "stage2_6d_20paper_workflow_summary.md"
PREFIX = "stage2_6d_20paper"

FORBIDDEN = [
    "activated sludge",
    "wastewater treatment",
    "wwtp",
    "advanced oxidation",
    "electrochemical",
    "plasma",
    "photocatalysis",
    "ozonation",
    "incineration",
]


def parse_report(path: Path) -> dict[str, str]:
    if not path.exists():
        raise ValueError(f"missing report: {path}")
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if " = " in line:
            key, value = line.split(" = ", 1)
            values[key] = value
    return values


def require_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise ValueError(f"missing JSONL: {path}")
    return read_jsonl(path)


def validate_no_raw_fulltext_tracked() -> None:
    result = subprocess.run(["git", "ls-files"], cwd=ROOT, text=True, capture_output=True, check=False)
    bad = [line for line in result.stdout.splitlines() if Path(line).suffix.lower() in {".pdf", ".html", ".htm", ".xhtml", ".sqlite"}]
    if bad:
        raise ValueError(f"raw fulltext tracked: {bad[:10]}")


def main() -> int:
    summary = parse_report(REPORT)
    queue = require_jsonl(BATCH / f"{PREFIX}_metadata_queue.jsonl")
    fetch_status = require_jsonl(BATCH / f"{PREFIX}_live_session_fetch_status.jsonl")
    decisions = require_jsonl(BATCH / f"{PREFIX}_screening_decisions.jsonl")
    candidates = require_jsonl(BATCH / f"{PREFIX}_candidate_records.jsonl")
    reviewed = require_jsonl(BATCH / f"{PREFIX}_reviewed_records.jsonl")
    validated = require_jsonl(BATCH / f"{PREFIX}_validated_records.jsonl")
    rejected = require_jsonl(BATCH / f"{PREFIX}_rejected_records.jsonl")
    auxiliary = require_jsonl(BATCH / f"{PREFIX}_auxiliary_records.jsonl")
    status = require_jsonl(STATE / f"{PREFIX}_source_status.jsonl")
    checkpoint = read_json(STATE / f"{PREFIX}_checkpoint.json")
    if len(queue) != 20:
        raise ValueError(f"expected 20 queue records, got {len(queue)}")
    if len(fetch_status) != 20:
        raise ValueError(f"expected 20 fetch status records, got {len(fetch_status)}")
    with (BATCH / f"{PREFIX}_sciencedirect_fetch_input.csv").open("r", encoding="utf-8", newline="") as handle:
        csv_rows = list(csv.DictReader(handle))
    if len(csv_rows) != 20:
        raise ValueError(f"expected 20 fetch CSV rows, got {len(csv_rows)}")
    if int(summary.get("sources_screened", 0)) != 20:
        raise ValueError("20-paper workflow did not screen 20 sources")
    if int(summary.get("fulltext_found", 0)) < 20:
        raise ValueError("20-paper workflow did not find local fulltext for all 20 selected sources")
    if int(summary.get("pending_tasks_remaining", -1)) != 0:
        raise ValueError("pending tasks remain")
    candidate_ids = {row.get("record_id") for row in candidates}
    reviewed_ids = {row.get("record_id") for row in reviewed}
    if candidate_ids - reviewed_ids:
        raise ValueError("unreviewed candidate records remain")
    database_records = len(validated) + len(rejected) + len(auxiliary)
    if database_records < len(reviewed):
        raise ValueError("reviewed records were not written to terminal database outputs")
    for row in validated:
        text = json.dumps(row, ensure_ascii=False).lower()
        if any(term in text for term in FORBIDDEN):
            raise ValueError(f"forbidden boundary violation in validated record: {row.get('record_id')}")
        if row.get("review", {}).get("natural_environment_valid") is not True:
            raise ValueError(f"validated record missing natural_environment_valid: {row.get('record_id')}")
    if checkpoint.get("can_resume") is not True:
        raise ValueError("checkpoint can_resume must be true")
    if len(status) != 20 or len(decisions) != 20:
        raise ValueError("status/decision counts do not match 20-paper queue")
    validate_no_raw_fulltext_tracked()
    output = {
        "targets": 20,
        "sources_screened": 20,
        "fulltext_found": int(summary.get("fulltext_found", 0)),
        "candidate_records": len(candidates),
        "reviewed_records": len(reviewed),
        "validated_records": len(validated),
        "workflow_success": summary.get("workflow_streaming_success") == "true",
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
