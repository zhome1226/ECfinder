"""Validate the title/abstract-first screening gate contract."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ecfinder.state.common import read_jsonl


ROOT = Path(__file__).resolve().parents[1]
DRY_RUN = ROOT / "data" / "state" / "stage2_6_autonomous_workflow_dry_run.jsonl"
REPORT = ROOT / "reports" / "stage2_6_title_abstract_screening_gate_audit.md"


def main() -> int:
    rows = read_jsonl(DRY_RUN)
    if not rows:
        raise ValueError("missing dry-run title/abstract screening rows")
    allowed_decisions = {"include_for_fulltext", "exclude", "manual_screen"}
    violations: list[str] = []
    for row in rows:
        if row.get("screening_decision") not in allowed_decisions:
            violations.append(f"bad_decision:{row.get('source_id')}")
        text = json.dumps(row, ensure_ascii=False).lower()
        if "full_text" in text or "chunk_text" in text or "\"text\"" in text:
            violations.append(f"long_context_in_screening:{row.get('source_id')}")
    include = sum(1 for row in rows if row.get("screening_decision") == "include_for_fulltext")
    exclude = sum(1 for row in rows if row.get("screening_decision") == "exclude")
    manual = sum(1 for row in rows if row.get("screening_decision") == "manual_screen")
    ready = not violations and include >= 1 and exclude >= 1
    lines = [
        "# Stage 2.6 Title/Abstract Screening Gate Audit",
        "",
        f"screened_sources = {len(rows)}",
        f"include_for_fulltext = {include}",
        f"exclude = {exclude}",
        f"manual_screen = {manual}",
        f"violations = {len(violations)}",
        f"title_abstract_gate_ready = {str(ready).lower()}",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    if not ready:
        raise ValueError(f"title/abstract gate violations: {violations}")
    print(json.dumps({"title_abstract_gate_ready": ready, "screened_sources": len(rows)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
