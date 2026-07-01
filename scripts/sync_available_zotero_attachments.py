"""Sync already available Zotero attachments for Stage 2.4j available-first ingest."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from stage2_4j_common import (
    AUDIT_JSONL,
    AVAILABLE_MANIFEST,
    LOCAL_ROOT,
    REPORTS_DIR,
    SYNC_STATUS,
    file_type_for_attachment,
    load_stage2_mappings,
    local_destination,
    normalize_doi,
    read_jsonl,
    sha256_file,
    write_jsonl,
    write_summary,
)
from zotero_stage2_4i_common import attachments_for_item, connect_zotero, item_field


SUMMARY_PATH = REPORTS_DIR / "stage2_4j_available_attachment_sync_summary.md"


def ensure_dirs() -> None:
    for child in ["pdf", "html", "si"]:
        path = LOCAL_ROOT / child
        path.mkdir(parents=True, exist_ok=True)
        keep = path / ".gitkeep"
        if not keep.exists():
            keep.write_text("\n", encoding="utf-8", newline="\n")


def stage2_4j_source_id(index: int) -> str:
    return f"zotero_stage2_4j_src_{index:03d}"


def classify_tier(audit_row: dict[str, Any]) -> tuple[str, str, str, str]:
    if audit_row.get("matched_stage2_4_source_id") or audit_row.get("matched_stage2_4b_target"):
        return "A", "doi_exact", "highest", "pending_ingest"
    relevance = audit_row.get("possible_pfas_transformation_relevance")
    if relevance == "high":
        return "B", "keyword_screen", "high", "pending_ingest"
    if relevance == "medium":
        return "C", "keyword_screen", "medium", "manual_screen"
    return "D", "keyword_screen", "low", "skip"


def zotero_items_by_key() -> dict[str, int]:
    with connect_zotero() as con:
        rows = con.execute("select itemID, key from items").fetchall()
        return {str(row["key"]): int(row["itemID"]) for row in rows}


def sync_available() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ensure_dirs()
    queue_map, target_map = load_stage2_mappings()
    audit_rows = read_jsonl(AUDIT_JSONL)
    key_to_id = zotero_items_by_key()
    status_rows: list[dict[str, Any]] = []
    manifest_rows: list[dict[str, Any]] = []
    zotero_index = 1
    with connect_zotero() as con:
        for audit in audit_rows:
            tier, method, priority, status = classify_tier(audit)
            item_key = str(audit.get("zotero_item_key", ""))
            item_id = key_to_id.get(item_key)
            attachments = attachments_for_item(con, item_id) if item_id is not None else []
            existing_supported = []
            for attachment in attachments:
                path = Path(str(attachment.get("path", "")))
                file_type = file_type_for_attachment(str(attachment.get("content_type", "")), path)
                if attachment.get("exists") and file_type:
                    existing_supported.append((attachment, file_type, path))
            copied = 0
            doi_norm = normalize_doi(str(audit.get("doi", "")))
            selected_source_id = audit.get("matched_stage2_4_source_id") or target_map.get(doi_norm, "")
            if tier in {"B", "C"}:
                selected_source_id = stage2_4j_source_id(zotero_index)
                zotero_index += 1
            if tier in {"A", "B", "C"} and existing_supported:
                attachment, file_type, source_path = existing_supported[0]
                suffix = source_path.suffix.lower()
                dest = local_destination(str(selected_source_id), file_type, suffix)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, dest)
                copied = 1
                manifest_status = status
                manifest_rows.append(
                    {
                        "source_id": selected_source_id,
                        "source_origin": "stage2_4_queue" if tier == "A" else "zotero_existing_library",
                        "zotero_item_key": item_key,
                        "doi": audit.get("doi", ""),
                        "title": audit.get("title", ""),
                        "file_type": file_type,
                        "local_path": str(dest.relative_to(LOCAL_ROOT.parents[2])).replace("\\", "/"),
                        "original_zotero_path": str(source_path),
                        "sha256": sha256_file(source_path),
                        "match_tier": tier,
                        "match_method": method,
                        "priority": priority,
                        "status": manifest_status,
                    }
                )
            status_rows.append(
                {
                    "zotero_item_key": item_key,
                    "doi": audit.get("doi", ""),
                    "title": audit.get("title", ""),
                    "matched_stage2_4_source_id": audit.get("matched_stage2_4_source_id"),
                    "match_tier": tier,
                    "priority": priority,
                    "available_attachment_count": len(existing_supported),
                    "copied_attachment_count": copied,
                    "status": "synced" if copied else ("manual_screen" if tier == "C" else "skipped_or_no_attachment"),
                }
            )
    return status_rows, manifest_rows


def update_audit_summary_selected(manifest_rows: list[dict[str, Any]]) -> None:
    summary_path = REPORTS_DIR / "stage2_4j_zotero_scope_audit_summary.md"
    lines = summary_path.read_text(encoding="utf-8").splitlines() if summary_path.exists() else []
    updated: list[str] = []
    replaced = False
    selected = sum(1 for row in manifest_rows if row.get("status") == "pending_ingest")
    for line in lines:
        if line.startswith("items_selected_for_available_first_ingest = "):
            updated.append(f"items_selected_for_available_first_ingest = {selected}")
            replaced = True
        else:
            updated.append(line)
    if not replaced:
        updated.append(f"items_selected_for_available_first_ingest = {selected}")
    summary_path.write_text("\n".join(updated) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    status_rows, manifest_rows = sync_available()
    write_jsonl(SYNC_STATUS, status_rows)
    write_jsonl(AVAILABLE_MANIFEST, manifest_rows)
    update_audit_summary_selected(manifest_rows)
    summary = {
        "zotero_items_scanned": len(status_rows),
        "available_fulltext_sources": len(manifest_rows),
        "tier_a_sources": sum(1 for row in manifest_rows if row.get("match_tier") == "A"),
        "tier_b_sources": sum(1 for row in manifest_rows if row.get("match_tier") == "B"),
        "tier_c_manual_screen_sources": sum(1 for row in manifest_rows if row.get("match_tier") == "C"),
        "pending_ingest_sources": sum(1 for row in manifest_rows if row.get("status") == "pending_ingest"),
        "manual_screen_sources": sum(1 for row in manifest_rows if row.get("status") == "manual_screen"),
        "raw_fulltext_committed": False,
    }
    write_summary(SUMMARY_PATH, "Stage 2.4j Available Attachment Sync Summary", summary)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
