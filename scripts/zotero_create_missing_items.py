"""Create missing Stage 2.4g Zotero items when a lawful API is configured."""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any

from zotero_stage2_4i_common import (
    BATCH_DIR,
    REPORTS_DIR,
    TAG,
    capability_summary,
    manifest_targets,
    write_jsonl,
    write_key_value_report,
    zotero_snapshot,
)


STATUS_PATH = BATCH_DIR / "stage2_4i_zotero_item_creation_status.jsonl"
REPORT_PATH = REPORTS_DIR / "stage2_4i_zotero_item_creation_summary.md"


def web_api_base() -> str:
    group_id = os.environ.get("ZOTERO_GROUP_ID", "").strip()
    if group_id:
        return f"https://api.zotero.org/groups/{urllib.parse.quote(group_id)}/items"
    user_id = os.environ.get("ZOTERO_USER_ID", "").strip()
    if user_id:
        return f"https://api.zotero.org/users/{urllib.parse.quote(user_id)}/items"
    return ""


def create_item_via_web_api(target: dict[str, Any]) -> tuple[bool, str]:
    api_key = os.environ.get("ZOTERO_API_KEY", "").strip()
    base = web_api_base()
    if not api_key or not base:
        return False, "Zotero Web API credentials are not configured."
    payload = [
        {
            "itemType": "journalArticle",
            "title": target.get("title", ""),
            "DOI": target.get("doi", ""),
            "tags": [{"tag": TAG}, {"tag": str(target.get("source_id", ""))}],
            "extra": f"source_id = {target.get('source_id', '')}\nECfinder target = Stage 2.4g",
        }
    ]
    request = urllib.request.Request(
        base,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Zotero-API-Key": api_key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status in {200, 201}, response.read().decode("utf-8", errors="replace")[:500]
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def run_create_missing_items() -> dict[str, Any]:
    targets = manifest_targets()
    before = zotero_snapshot(targets)
    caps = capability_summary()
    rows: list[dict[str, Any]] = []
    for target, snap in zip(targets, before, strict=True):
        source_id = str(target.get("source_id", ""))
        if snap["zotero_item_count"] > 0:
            rows.append(
                {
                    "source_id": source_id,
                    "doi": target.get("doi", ""),
                    "title": target.get("title", ""),
                    "zotero_item_existed_before": True,
                    "create_attempted": False,
                    "create_success": False,
                    "zotero_item_key": ",".join(snap["zotero_item_keys"]),
                    "item_creation_requires_user_import": False,
                    "status": "existing_item",
                    "notes": "Exact DOI Zotero item already exists.",
                }
            )
            continue
        attempted = bool(caps["can_create_items"])
        success = False
        notes = "item_creation_requires_user_import"
        if attempted:
            success, notes = create_item_via_web_api(target)
        rows.append(
            {
                "source_id": source_id,
                "doi": target.get("doi", ""),
                "title": target.get("title", ""),
                "zotero_item_existed_before": False,
                "create_attempted": attempted,
                "create_success": success,
                "zotero_item_key": "",
                "item_creation_requires_user_import": not success,
                "status": "created" if success else "requires_user_import",
                "notes": notes,
            }
        )
    write_jsonl(STATUS_PATH, rows)
    after = zotero_snapshot(targets)
    summary = {
        "targets": len(targets),
        "zotero_items_existing_before": sum(1 for row in before if row["zotero_item_count"] > 0),
        "zotero_items_created": sum(1 for row in rows if row["create_success"]),
        "zotero_items_total_after": sum(1 for row in after if row["zotero_item_count"] > 0),
        "item_creation_requires_user_import": sum(1 for row in rows if row["item_creation_requires_user_import"]),
        "can_create_items": caps["can_create_items"],
    }
    write_key_value_report(
        REPORT_PATH,
        "Stage 2.4i Zotero Item Creation Summary",
        summary,
        [
            "Items are created only through Zotero Web API when credentials are configured.",
            "When credentials are absent, import `data/local_fulltext/zotero/stage2_4g_targets.ris` or `.bib` in Zotero.",
        ],
    )
    return summary


def main() -> int:
    print(json.dumps(run_create_missing_items(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
