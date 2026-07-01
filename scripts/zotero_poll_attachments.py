"""Poll Zotero SQLite for Stage 2.4g target attachments."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from zotero_stage2_4i_common import BATCH_DIR, REPORTS_DIR, TAG, manifest_targets, sha256_file, write_jsonl, write_key_value_report, zotero_snapshot


STATUS_PATH = BATCH_DIR / "stage2_4i_zotero_attachment_poll_status.jsonl"
REPORT_PATH = REPORTS_DIR / "stage2_4i_zotero_attachment_poll_summary.md"


def attachment_digest(path_text: str) -> str:
    path = Path(path_text)
    if path.exists() and path.is_file():
        return sha256_file(path)
    return ""


def collect_rows(tag: str) -> list[dict[str, object]]:
    targets = manifest_targets()
    snapshot = zotero_snapshot(targets)
    rows: list[dict[str, object]] = []
    for target, snap in zip(targets, snapshot, strict=True):
        found = [att for att in snap["attachments"] if att.get("exists") and att.get("supported")]
        first = found[0] if found else {}
        rows.append(
            {
                "source_id": target.get("source_id", ""),
                "doi": target.get("doi", ""),
                "title": target.get("title", ""),
                "tag": tag,
                "zotero_item_keys": snap["zotero_item_keys"],
                "zotero_item_count": snap["zotero_item_count"],
                "attachment_found": bool(found),
                "attachment_count": len(found),
                "attachment_path": first.get("path", ""),
                "attachment_content_type": first.get("content_type", ""),
                "attachment_sha256": attachment_digest(str(first.get("path", ""))) if first else "",
                "status": "attachment_found" if found else "blocked_external",
            }
        )
    return rows


def run_poll(tag: str, timeout_minutes: float, interval_seconds: float) -> dict[str, object]:
    deadline = time.time() + max(0, timeout_minutes) * 60
    rows = collect_rows(tag)
    while time.time() < deadline and not any(row["attachment_found"] for row in rows):
        time.sleep(max(1, interval_seconds))
        rows = collect_rows(tag)
    write_jsonl(STATUS_PATH, rows)
    summary = {
        "targets": len(rows),
        "attachments_found_after_polling": sum(1 for row in rows if row["attachment_found"]),
        "blocked_external_sources": sum(1 for row in rows if not row["attachment_found"]),
        "timeout_minutes": timeout_minutes,
        "interval_seconds": interval_seconds,
        "phase": "attachments_detected" if any(row["attachment_found"] for row in rows) else "blocked_external",
    }
    write_key_value_report(REPORT_PATH, "Stage 2.4i Zotero Attachment Poll Summary", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default=TAG)
    parser.add_argument("--timeout-minutes", type=float, default=10)
    parser.add_argument("--interval-seconds", type=float, default=30)
    args = parser.parse_args()
    print(json.dumps(run_poll(args.tag, args.timeout_minutes, args.interval_seconds), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
