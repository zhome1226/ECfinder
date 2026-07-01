"""Run the Stage 2.4i Zotero automatic full-text retrieval cycle."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from check_zotero_control_capabilities import REPORT_PATH as CAPABILITY_REPORT
from check_zotero_control_capabilities import main as check_capabilities_main
from zotero_create_missing_items import run_create_missing_items
from zotero_poll_attachments import run_poll
from zotero_stage2_4i_common import (
    BATCH_DIR,
    MANIFEST_PATH,
    REPORTS_DIR,
    STATE_DIR,
    TAG,
    capability_summary,
    parse_report_counts,
    read_jsonl,
    write_jsonl,
    write_key_value_report,
    zotero_snapshot,
)
from zotero_trigger_find_fulltext import run_trigger


ROOT = Path(__file__).resolve().parents[1]
BLOCKED_QUEUE = STATE_DIR / "blocked_external_queue.jsonl"
SUMMARY_REPORT = REPORTS_DIR / "stage2_4i_zotero_auto_fulltext_summary.md"
REMAINING_BLOCKERS_REPORT = REPORTS_DIR / "stage2_4i_remaining_blockers.md"


def run_python_script(script: str) -> None:
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / script)], cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"{script} failed: {result.stderr.strip() or result.stdout.strip()}")


def sync_and_ingest() -> dict[str, str]:
    run_python_script("sync_zotero_stage2_4b_attachments.py")
    run_python_script("run_stage2_4b_fulltext_ingest.py")
    return parse_report_counts(REPORTS_DIR / "stage2_4b_fulltext_ingest_summary.md")


def build_blockers(targets: list[dict[str, Any]], caps: dict[str, Any], poll_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    poll_by_source = {row.get("source_id"): row for row in poll_rows}
    snapshot_by_source = {row.get("source_id"): row for row in zotero_snapshot(targets)}
    blockers: list[dict[str, Any]] = []
    for target in targets:
        source_id = str(target.get("source_id", ""))
        poll = poll_by_source.get(source_id, {})
        snap = snapshot_by_source.get(source_id, {})
        if poll.get("attachment_found"):
            continue
        if not snap.get("zotero_item_count"):
            blocker_type = "zotero_item_missing"
            action = "import_to_zotero"
        elif not caps.get("can_trigger_find_available_pdf"):
            blocker_type = "zotero_find_fulltext_trigger_unavailable"
            action = "run_find_available_pdf"
        else:
            blocker_type = "zotero_find_fulltext_no_result"
            action = "attach_pdf_to_zotero"
        blockers.append(
            {
                "source_id": source_id,
                "doi": target.get("doi", ""),
                "title": target.get("title", ""),
                "blocker_type": blocker_type,
                "required_external_action": action,
                "status": "blocked_external",
                "note": "Use Zotero UI or manual mapping; no unlawful download or access bypass is attempted.",
            }
        )
    return blockers


def write_blocker_report(blockers: list[dict[str, Any]]) -> None:
    lines = [
        "# Stage 2.4i Remaining External Blockers",
        "",
        f"blocked_external_sources = {len(blockers)}",
        "",
        "| source_id | doi | blocker_type | required_external_action |",
        "| --- | --- | --- | --- |",
    ]
    for row in blockers:
        lines.append(f"| {row['source_id']} | {row['doi']} | {row['blocker_type']} | {row['required_external_action']} |")
    REMAINING_BLOCKERS_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def run_cycle(targets_path: Path, tag: str, timeout_minutes: float) -> dict[str, Any]:
    targets = read_jsonl(targets_path)
    before = zotero_snapshot(targets)
    check_capabilities_main()
    caps = capability_summary()
    creation = run_create_missing_items()
    trigger = run_trigger()
    poll_timeout = timeout_minutes if caps.get("can_trigger_find_available_pdf") or int(trigger.get("trigger_success_count", 0)) > 0 else 0
    poll = run_poll(tag, poll_timeout, 30)
    poll_rows = read_jsonl(BATCH_DIR / "stage2_4i_zotero_attachment_poll_status.jsonl")
    ingest_counts = sync_and_ingest()
    sync_counts = parse_report_counts(REPORTS_DIR / "stage2_4b_zotero_attachment_diagnosis.md")
    blockers = build_blockers(targets, caps, poll_rows)
    write_jsonl(BLOCKED_QUEUE, blockers)
    write_blocker_report(blockers)
    attachments_synced = int(sync_counts.get("attachments_synced", 0))
    parsed_sources = int(ingest_counts.get("parsed_sources", 0))
    if attachments_synced >= 5 and parsed_sources >= 5:
        can_scale = True
        reason = ""
    elif attachments_synced == 0 and not caps.get("can_trigger_find_available_pdf"):
        can_scale = False
        reason = "zotero_programmatic_fulltext_trigger_unavailable_waiting_for_user_action"
    elif int(trigger.get("trigger_success_count", 0)) > 0 and int(poll.get("attachments_found_after_polling", 0)) == 0:
        can_scale = False
        reason = "zotero_find_available_pdf_returned_no_attachments"
    else:
        can_scale = False
        reason = str(ingest_counts.get("reason", "zotero_fulltext_cycle_incomplete"))
    summary = {
        "targets": len(targets),
        "zotero_items_existing_before": sum(1 for row in before if row["zotero_item_count"] > 0),
        "zotero_items_created": int(creation.get("zotero_items_created", 0)),
        "zotero_items_total_after": int(creation.get("zotero_items_total_after", 0)),
        "can_trigger_find_available_pdf": bool(caps.get("can_trigger_find_available_pdf")),
        "trigger_attempted": int(trigger.get("trigger_attempted", 0)),
        "trigger_success_count": int(trigger.get("trigger_success_count", 0)),
        "requires_user_action_count": int(trigger.get("requires_user_action_count", 0)),
        "attachments_found_after_polling": int(poll.get("attachments_found_after_polling", 0)),
        "attachments_synced": attachments_synced,
        "local_fulltext_found": int(ingest_counts.get("local_fulltext_found", 0)),
        "parsed_sources": parsed_sources,
        "total_chunks": int(ingest_counts.get("total_chunks", 0)),
        "candidate_records": int(ingest_counts.get("candidate_records", 0)),
        "validated_records": int(ingest_counts.get("validated_records", 0)),
        "manual_review_records": int(ingest_counts.get("manual_review_records", 0)),
        "codex_tasks_created": int(ingest_counts.get("codex_tasks_created", 0)),
        "blocked_external_sources": len(blockers),
        "phase": "waiting_for_user_to_run_zotero_find_available_pdf" if not caps.get("can_trigger_find_available_pdf") else str(poll.get("phase", "")),
        "can_scale_to_100_sources": can_scale,
        "reason": reason,
    }
    write_key_value_report(
        SUMMARY_REPORT,
        "Stage 2.4i Zotero Auto Full-text Summary",
        summary,
        [f"capability_report = {CAPABILITY_REPORT.relative_to(ROOT).as_posix()}"],
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets", default=str(MANIFEST_PATH))
    parser.add_argument("--tag", default=TAG)
    parser.add_argument("--timeout-minutes", type=float, default=10)
    args = parser.parse_args()
    summary = run_cycle(Path(args.targets), args.tag, args.timeout_minutes)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
