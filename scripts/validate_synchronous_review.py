"""Validate extraction -> review -> database write synchronous lineage."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ecfinder.state.common import read_jsonl


ROOT = Path(__file__).resolve().parents[1]
TRACE = ROOT / "data" / "batches" / "stage2_5_agent_execution_trace.jsonl"
REPORT = ROOT / "reports" / "stage2_6_synchronous_review_audit.md"


def main() -> int:
    trace = read_jsonl(TRACE)
    by_source: dict[str, list[str]] = {}
    for row in trace:
        by_source.setdefault(str(row.get("source_id", "")), []).append(str(row.get("task_type", "")))
    violations: list[str] = []
    for source_id, types in by_source.items():
        if "extract" in types:
            joined = " > ".join(types)
            if "extract > review > write_database" not in joined:
                violations.append(source_id)
    candidate = reviewed = validated = 0
    missing_review = 0
    for run_dir in (ROOT / "data" / "runs").glob("stage2_4j_zotero_stage2_4j_src_*"):
        candidates = read_jsonl(run_dir / "candidate_records.jsonl")
        reviews = read_jsonl(run_dir / "reviewed_records.jsonl")
        vals = read_jsonl(run_dir / "validated_records.jsonl")
        candidate += len(candidates)
        reviewed += len(reviews)
        validated += len(vals)
        reviewed_ids = {row.get("record_id") for row in reviews}
        for row in candidates:
            if row.get("record_id") not in reviewed_ids:
                missing_review += 1
        for row in vals:
            if not row.get("review", {}).get("review_status"):
                violations.append(f"validated_without_review:{row.get('record_id')}")
    ready = not violations and missing_review == 0
    lines = [
        "# Stage 2.6 Synchronous Review Audit",
        "",
        f"candidate_records = {candidate}",
        f"reviewed_records = {reviewed}",
        f"validated_records = {validated}",
        f"unreviewed_candidate_records = {missing_review}",
        f"lineage_violations = {len(violations)}",
        f"synchronous_review_ready = {str(ready).lower()}",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    if not ready:
        raise ValueError(f"synchronous review violations: {violations}")
    print(json.dumps({"synchronous_review_ready": ready, "candidate_records": candidate, "reviewed_records": reviewed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
