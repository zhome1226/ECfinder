"""Validate Stage 2.4i Zotero automatic full-text cycle outputs."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from zotero_stage2_4i_common import (
    BATCH_DIR,
    MANIFEST_PATH,
    REPORTS_DIR,
    ROOT,
    STATE_DIR,
    parse_report_counts,
    read_jsonl,
)


CAPABILITY_REPORT = REPORTS_DIR / "stage2_4i_zotero_control_capabilities.md"
CREATION_STATUS = BATCH_DIR / "stage2_4i_zotero_item_creation_status.jsonl"
TRIGGER_STATUS = BATCH_DIR / "stage2_4i_find_fulltext_trigger_status.jsonl"
POLL_STATUS = BATCH_DIR / "stage2_4i_zotero_attachment_poll_status.jsonl"
SUMMARY_REPORT = REPORTS_DIR / "stage2_4i_zotero_auto_fulltext_summary.md"
BLOCKERS_REPORT = REPORTS_DIR / "stage2_4i_remaining_blockers.md"
BLOCKED_QUEUE = STATE_DIR / "blocked_external_queue.jsonl"
ZOTERO_DIAGNOSIS = BATCH_DIR / "stage2_4b_zotero_attachment_status.jsonl"


def require_file(path: Path) -> None:
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        raise ValueError(f"missing or empty file: {path}")


def read_jsonl_strict(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise ValueError(f"missing JSONL file: {path}")
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            if "} {" in line:
                raise ValueError(f"{path}:{line_no} contains multiple JSON objects")
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_no} is not a JSON object")
            rows.append(value)
    return rows


def validate_raw_fulltext_not_committed() -> None:
    result = subprocess.run(
        [
            "git",
            "ls-files",
            "data/local_fulltext/stage2_4b/pdf",
            "data/local_fulltext/stage2_4b/html",
            "data/local_fulltext/stage2_4b/si",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(result.stderr.strip())
    tracked = [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]
    bad = [path for path in tracked if not path.endswith("/.gitkeep")]
    if bad:
        raise ValueError(f"raw fulltext files are tracked by Git: {bad}")


def validate_manifest_for_synced_attachments(zotero_rows: list[dict[str, Any]]) -> None:
    manifest = {row.get("source_id"): row for row in read_jsonl_strict(MANIFEST_PATH)}
    for row in zotero_rows:
        if int(row.get("accepted_attachment_count", 0)) <= 0:
            continue
        source_id = row.get("source_id")
        target = manifest.get(source_id)
        if not target:
            raise ValueError(f"synced attachment source missing from manifest: {source_id}")
        if not target.get("local_path") or not target.get("sha256"):
            raise ValueError(f"synced attachment missing manifest local_path/sha256: {source_id}")
        path = ROOT / str(target["local_path"])
        if not path.exists():
            raise ValueError(f"synced attachment local_path missing: {target['local_path']}")


def validate_blockers(blockers: list[dict[str, Any]], poll_rows: list[dict[str, Any]]) -> None:
    missing_sources = {row.get("source_id") for row in poll_rows if not row.get("attachment_found")}
    blocker_sources = {row.get("source_id") for row in blockers}
    if not missing_sources.issubset(blocker_sources):
        raise ValueError(f"blocked_external_queue missing sources: {sorted(missing_sources - blocker_sources)}")
    allowed_types = {
        "zotero_item_missing",
        "zotero_attachment_missing",
        "zotero_find_fulltext_trigger_unavailable",
        "zotero_find_fulltext_no_result",
        "manual_mapping_required",
    }
    allowed_actions = {
        "import_to_zotero",
        "run_find_available_pdf",
        "attach_pdf_to_zotero",
        "fill_manual_mapping",
        "rerun_zotero_poll",
    }
    for row in blockers:
        if row.get("blocker_type") not in allowed_types:
            raise ValueError(f"invalid blocker_type: {row}")
        if row.get("required_external_action") not in allowed_actions:
            raise ValueError(f"invalid required_external_action: {row}")


def validate_summary_counts() -> dict[str, Any]:
    counts = parse_report_counts(SUMMARY_REPORT)
    creation = read_jsonl_strict(CREATION_STATUS)
    trigger = read_jsonl_strict(TRIGGER_STATUS)
    poll = read_jsonl_strict(POLL_STATUS)
    blockers = read_jsonl_strict(BLOCKED_QUEUE)
    zotero_rows = read_jsonl_strict(ZOTERO_DIAGNOSIS)
    expected = {
        "targets": len(creation),
        "zotero_items_created": sum(1 for row in creation if row.get("create_success")),
        "trigger_attempted": sum(1 for row in trigger if row.get("trigger_attempted")),
        "trigger_success_count": sum(1 for row in trigger if row.get("trigger_success")),
        "requires_user_action_count": sum(1 for row in trigger if row.get("requires_user_action")),
        "attachments_found_after_polling": sum(1 for row in poll if row.get("attachment_found")),
        "attachments_synced": sum(1 for row in zotero_rows if int(row.get("accepted_attachment_count", 0)) > 0),
        "blocked_external_sources": len(blockers),
    }
    for key, value in expected.items():
        if counts.get(key) != str(value):
            raise ValueError(f"summary mismatch for {key}: expected {value}, got {counts.get(key)}")
    can_trigger = counts.get("can_trigger_find_available_pdf") == "true"
    if not can_trigger and expected["trigger_success_count"] != 0:
        raise ValueError("trigger_success_count must be 0 when can_trigger_find_available_pdf=false")
    validate_manifest_for_synced_attachments(zotero_rows)
    validate_blockers(blockers, poll)
    return {**expected, "can_trigger_find_available_pdf": can_trigger, "reason": counts.get("reason", "")}


def run_external_validator(script: str) -> None:
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / script)], cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise ValueError(f"{script} failed: {result.stderr.strip() or result.stdout.strip()}")


def main() -> int:
    for path in [
        CAPABILITY_REPORT,
        CREATION_STATUS,
        TRIGGER_STATUS,
        POLL_STATUS,
        SUMMARY_REPORT,
        BLOCKERS_REPORT,
        BLOCKED_QUEUE,
    ]:
        require_file(path)
    validate_raw_fulltext_not_committed()
    summary = validate_summary_counts()
    run_external_validator("validate_state_cache_layer.py")
    run_external_validator("validate_supervisor_workflow.py")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
