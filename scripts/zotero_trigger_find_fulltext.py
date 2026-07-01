"""Attempt safe local triggers for Zotero Find Available PDF / Full Text."""

from __future__ import annotations

import json

from zotero_stage2_4i_common import BATCH_DIR, REPORTS_DIR, capability_summary, manifest_targets, write_jsonl, write_key_value_report, zotero_snapshot


STATUS_PATH = BATCH_DIR / "stage2_4i_find_fulltext_trigger_status.jsonl"
REPORT_PATH = REPORTS_DIR / "stage2_4i_find_fulltext_trigger_summary.md"
USER_ACTION = "Select ECfinder_stage2_4g items in Zotero and run Find Available PDF"


def run_trigger() -> dict[str, object]:
    targets = manifest_targets()
    snapshot = zotero_snapshot(targets)
    caps = capability_summary()
    rows: list[dict[str, object]] = []
    for target, snap in zip(targets, snapshot, strict=True):
        trigger_available = bool(caps["can_trigger_find_available_pdf"])
        rows.append(
            {
                "source_id": target.get("source_id", ""),
                "doi": target.get("doi", ""),
                "zotero_item_key": ",".join(snap["zotero_item_keys"]),
                "trigger_attempted": trigger_available,
                "trigger_method": caps["trigger_method"] if trigger_available else "not_available",
                "trigger_success": False,
                "requires_user_action": True,
                "user_action": USER_ACTION if snap["zotero_item_count"] else "Import/create Zotero item, then run Find Available PDF",
                "notes": "No supported programmable Zotero Find Available PDF endpoint was detected.",
            }
        )
    write_jsonl(STATUS_PATH, rows)
    summary = {
        "targets": len(rows),
        "can_trigger_find_available_pdf": bool(caps["can_trigger_find_available_pdf"]),
        "trigger_attempted": sum(1 for row in rows if row["trigger_attempted"]),
        "trigger_success_count": sum(1 for row in rows if row["trigger_success"]),
        "requires_user_action_count": sum(1 for row in rows if row["requires_user_action"]),
    }
    write_key_value_report(
        REPORT_PATH,
        "Stage 2.4i Find Full-text Trigger Summary",
        summary,
        [
            "No paywall, login, MFA, CAPTCHA, or cookie/session bypass is attempted.",
            f"Required user action: {USER_ACTION}.",
        ],
    )
    return summary


def main() -> int:
    print(json.dumps(run_trigger(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
