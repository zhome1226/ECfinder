"""Discover Zotero attachments for Stage 2.4b targets and update the local manifest.

The script is intentionally conservative:
- it opens Zotero's SQLite database read-only;
- it only accepts exact DOI matches from the Stage 2.4b manifest;
- it copies only attached PDF/HTML files for those exact Zotero items into the
  ignored local_fulltext cache;
- it never uses title-similar or neighboring Zotero items as substitutes.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ecfinder.state.common import read_jsonl, sha256_file, write_jsonl


ROOT = Path(__file__).resolve().parents[1]
LOCAL_ROOT = ROOT / "data" / "local_fulltext" / "stage2_4b"
MANIFEST_PATH = LOCAL_ROOT / "fulltext_manifest.jsonl"
REPORT_PATH = ROOT / "reports" / "stage2_4b_zotero_attachment_diagnosis.md"
STATUS_PATH = ROOT / "data" / "batches" / "stage2_4b_zotero_attachment_status.jsonl"

SUPPORTED_CONTENT_TYPES = {
    "application/pdf": ("pdf", ".pdf"),
    "text/html": ("html", ".html"),
    "application/xhtml+xml": ("html", ".html"),
}


def normalize_doi(value: str) -> str:
    return value.strip().lower().removeprefix("https://doi.org/").removeprefix("doi:")


def zotero_db_path() -> Path:
    return Path.home() / "Zotero" / "zotero.sqlite"


def connect_zotero(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise FileNotFoundError(f"Zotero database not found: {path}")
    uri = f"file:{path.as_posix()}?mode=ro&immutable=1"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    return con


def item_field(con: sqlite3.Connection, item_id: int, field_name: str) -> str:
    row = con.execute(
        """
        select v.value
        from itemData d
        join fields f on f.fieldID = d.fieldID
        join itemDataValues v on v.valueID = d.valueID
        where d.itemID = ? and f.fieldName = ?
        """,
        (item_id, field_name),
    ).fetchone()
    return str(row["value"]) if row else ""


def find_items_by_doi(con: sqlite3.Connection, doi: str) -> list[sqlite3.Row]:
    return list(
        con.execute(
            """
            select i.itemID, i.key
            from items i
            join itemData d on d.itemID = i.itemID
            join fields f on f.fieldID = d.fieldID
            join itemDataValues v on v.valueID = d.valueID
            where lower(f.fieldName) = 'doi' and lower(v.value) = lower(?)
            order by i.itemID
            """,
            (doi,),
        )
    )


def resolve_attachment_path(zotero_root: Path, attachment_key: str, path_text: str) -> Path:
    if path_text.startswith("storage:"):
        return zotero_root / "storage" / attachment_key / path_text.split(":", 1)[1]
    path = Path(path_text)
    if path.is_absolute():
        return path
    return zotero_root / path


def attachments_for_item(con: sqlite3.Connection, zotero_root: Path, item_id: int) -> list[dict[str, Any]]:
    rows = con.execute(
        """
        select child.itemID, child.key, ia.contentType, ia.path
        from itemAttachments ia
        join items child on child.itemID = ia.itemID
        where ia.parentItemID = ?
        order by child.itemID
        """,
        (item_id,),
    ).fetchall()
    attachments: list[dict[str, Any]] = []
    for row in rows:
        local_path = resolve_attachment_path(zotero_root, str(row["key"]), str(row["path"] or ""))
        attachments.append(
            {
                "attachment_item_id": int(row["itemID"]),
                "attachment_key": str(row["key"]),
                "content_type": str(row["contentType"] or ""),
                "zotero_path": str(row["path"] or ""),
                "resolved_path": str(local_path),
                "exists": local_path.exists() and local_path.is_file(),
                "bytes": local_path.stat().st_size if local_path.exists() and local_path.is_file() else 0,
            }
        )
    return attachments


def destination_for(source_id: str, file_type: str, suffix: str) -> Path:
    if file_type == "pdf":
        return LOCAL_ROOT / "pdf" / f"{source_id}{suffix}"
    if file_type == "html":
        return LOCAL_ROOT / "html" / f"{source_id}{suffix}"
    return LOCAL_ROOT / "si" / f"{source_id}_si_01{suffix}"


def copy_attachment(source_id: str, attachment: dict[str, Any], dry_run: bool) -> dict[str, Any] | None:
    content_type = str(attachment.get("content_type", "")).lower()
    file_type, suffix = SUPPORTED_CONTENT_TYPES.get(content_type, ("", ""))
    if not file_type:
        source_suffix = Path(str(attachment.get("resolved_path", ""))).suffix.lower()
        if source_suffix == ".pdf":
            file_type, suffix = "pdf", ".pdf"
        elif source_suffix in {".html", ".htm", ".xhtml"}:
            file_type, suffix = "html", ".html"
    if not file_type or not attachment.get("exists"):
        return None
    source_path = Path(str(attachment["resolved_path"]))
    dest = destination_for(source_id, file_type, suffix)
    if not dry_run:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, dest)
    return {
        "file_type": file_type,
        "local_path": str(dest.relative_to(ROOT)).replace("\\", "/"),
        "sha256": sha256_file(source_path),
        "bytes": source_path.stat().st_size,
    }


def diagnose_manifest(dry_run: bool) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    manifest = read_jsonl(MANIFEST_PATH)
    zotero_root = Path.home() / "Zotero"
    with connect_zotero(zotero_db_path()) as con:
        status_rows: list[dict[str, Any]] = []
        updated_manifest: list[dict[str, Any]] = []
        for entry in manifest:
            source_id = str(entry.get("source_id", ""))
            doi = normalize_doi(str(entry.get("doi", "")))
            matches = find_items_by_doi(con, doi) if doi else []
            row: dict[str, Any] = {
                "source_id": source_id,
                "doi": entry.get("doi", ""),
                "title": entry.get("title", ""),
                "zotero_item_count": len(matches),
                "zotero_item_keys": [str(item["key"]) for item in matches],
                "zotero_attachment_count": 0,
                "zotero_attachments_existing": 0,
                "accepted_attachment_count": 0,
                "copied_local_path": "",
                "sha256": "",
                "diagnosis": "",
            }
            accepted: dict[str, Any] | None = None
            all_attachments: list[dict[str, Any]] = []
            for item in matches:
                item_title = item_field(con, int(item["itemID"]), "title")
                attachments = attachments_for_item(con, zotero_root, int(item["itemID"]))
                all_attachments.extend(attachments)
                row.setdefault("zotero_titles", []).append(item_title)
            row["zotero_attachment_count"] = len(all_attachments)
            row["zotero_attachments_existing"] = sum(1 for attachment in all_attachments if attachment.get("exists"))
            for attachment in all_attachments:
                accepted = copy_attachment(source_id, attachment, dry_run=dry_run)
                if accepted:
                    break
            if accepted:
                row["accepted_attachment_count"] = 1
                row["copied_local_path"] = accepted["local_path"]
                row["sha256"] = accepted["sha256"]
                row["diagnosis"] = "zotero_attachment_synced"
                updated_manifest.append(
                    {
                        **entry,
                        "access_method": "zotero_attachment",
                        "file_type": accepted["file_type"],
                        "local_path": accepted["local_path"],
                        "license_or_access_note": "Exact DOI Zotero attachment copied into ignored local cache for local ingest only; raw file is not committed.",
                        "sha256": accepted["sha256"],
                        "status": "pending_ingest",
                        "zotero_item_keys": row["zotero_item_keys"],
                    }
                )
            else:
                if not matches:
                    row["diagnosis"] = "zotero_item_missing"
                elif not all_attachments:
                    row["diagnosis"] = "zotero_item_without_attachment"
                elif not any(attachment.get("exists") for attachment in all_attachments):
                    row["diagnosis"] = "zotero_attachment_file_missing"
                else:
                    row["diagnosis"] = "zotero_attachment_unsupported_type"
                updated_manifest.append(
                    {
                        **entry,
                        "rescue_attempted": True,
                        "rescue_failure_reason": row["diagnosis"],
                        "status": "missing_fulltext",
                    }
                )
            status_rows.append(row)
    return status_rows, updated_manifest


def write_report(rows: list[dict[str, Any]]) -> None:
    counts = {
        "manifest_sources": len(rows),
        "zotero_items_found": sum(1 for row in rows if row["zotero_item_count"] > 0),
        "zotero_items_missing": sum(1 for row in rows if row["zotero_item_count"] == 0),
        "zotero_items_without_attachment": sum(1 for row in rows if row["diagnosis"] == "zotero_item_without_attachment"),
        "zotero_attachments_existing": sum(int(row["zotero_attachments_existing"]) for row in rows),
        "attachments_synced": sum(1 for row in rows if row["diagnosis"] == "zotero_attachment_synced"),
    }
    lines = ["# Stage 2.4b Zotero Attachment Diagnosis", ""]
    for key, value in counts.items():
        lines.append(f"{key} = {value}")
    lines.extend(
        [
            "",
            "| source_id | doi | zotero_items | attachments | synced | diagnosis |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in rows:
        lines.append(
            "| {source_id} | {doi} | {items} | {attachments} | {synced} | {diagnosis} |".format(
                source_id=row["source_id"],
                doi=row["doi"],
                items=",".join(row["zotero_item_keys"]),
                attachments=row["zotero_attachment_count"],
                synced=row["accepted_attachment_count"],
                diagnosis=row["diagnosis"],
            )
        )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Diagnose without copying files or updating manifest.")
    args = parser.parse_args()
    rows, updated_manifest = diagnose_manifest(dry_run=args.dry_run)
    write_jsonl(STATUS_PATH, rows)
    write_report(rows)
    if not args.dry_run:
        write_jsonl(MANIFEST_PATH, updated_manifest)
    summary = {
        "manifest_sources": len(rows),
        "zotero_items_found": sum(1 for row in rows if row["zotero_item_count"] > 0),
        "zotero_items_missing": sum(1 for row in rows if row["zotero_item_count"] == 0),
        "zotero_items_without_attachment": sum(1 for row in rows if row["diagnosis"] == "zotero_item_without_attachment"),
        "attachments_synced": sum(1 for row in rows if row["diagnosis"] == "zotero_attachment_synced"),
        "dry_run": args.dry_run,
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
