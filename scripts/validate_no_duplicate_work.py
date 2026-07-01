"""Validate duplicate-work prevention assumptions and write an audit report."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ecfinder.state.common import read_jsonl


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "stage2_6_duplicate_work_audit.md"


def duplicates(values: list[str]) -> int:
    return sum(count - 1 for count in Counter(value for value in values if value).values() if count > 1)


def main() -> int:
    sources = read_jsonl(ROOT / "data" / "state" / "source_registry.jsonl")
    artifacts = read_jsonl(ROOT / "data" / "state" / "artifact_index.jsonl")
    tasks = read_jsonl(ROOT / "data" / "state" / "task_registry.jsonl")
    doi_dupes = duplicates([str(row.get("hashes", {}).get("doi_hash", "")) for row in sources])
    title_dupes = duplicates([str(row.get("hashes", {}).get("title_hash", "")) for row in sources if not row.get("doi")])
    fulltext_dupes = duplicates([str(row.get("hashes", {}).get("fulltext_hash", "")) for row in sources if row.get("hashes", {}).get("fulltext_hash")])
    extract_keys = []
    for row in read_jsonl(ROOT / "data" / "state" / "decision_cache.jsonl"):
        if row.get("task_type") != "extract":
            continue
        input_hash = str(row.get("input_hash", ""))
        if not input_hash:
            continue
        extract_keys.append("|".join([input_hash, str(row.get("prompt_version", "")), str(row.get("schema_version", ""))]))
    chunk_extract_dupes = duplicates(extract_keys)
    task_dupes = duplicates([f"{row.get('source_id')}|{row.get('task_type')}|{row.get('agent')}" for row in tasks if str(row.get("task_id", "")).startswith("stage2_4j_")])
    artifact_path_dupes = duplicates([str(row.get("path", "")) for row in artifacts])
    violations = doi_dupes + title_dupes + max(0, fulltext_dupes - 20) + chunk_extract_dupes + task_dupes + artifact_path_dupes
    ready = task_dupes == 0 and artifact_path_dupes == 0 and chunk_extract_dupes == 0
    lines = [
        "# Stage 2.6 Duplicate Work Audit",
        "",
        f"duplicate_doi_hashes = {doi_dupes}",
        f"duplicate_title_hashes_without_doi = {title_dupes}",
        f"duplicate_fulltext_hashes = {fulltext_dupes}",
        f"duplicate_extraction_input_hashes = {chunk_extract_dupes}",
        f"duplicate_stage2_4j_tasks = {task_dupes}",
        f"duplicate_artifact_paths = {artifact_path_dupes}",
        f"duplicate_work_prevention_ready = {str(ready).lower()}",
        "",
        "note = Fulltext hash duplicates can be legitimate when multiple derived records reference the same local artifact; hard validation focuses on duplicate tasks, extraction decisions, and artifact paths.",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    if not ready:
        raise ValueError(f"duplicate work violations detected: {violations}")
    print(json.dumps({"duplicate_work_prevention_ready": ready, "duplicate_stage2_4j_tasks": task_dupes}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
