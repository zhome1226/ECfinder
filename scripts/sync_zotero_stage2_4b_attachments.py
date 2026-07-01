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
import csv
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
ZOTERO_WORKFLOW_ROOT = ROOT / "data" / "local_fulltext" / "zotero"
MANIFEST_PATH = LOCAL_ROOT / "fulltext_manifest.jsonl"
REPORT_PATH = ROOT / "reports" / "stage2_4b_zotero_attachment_diagnosis.md"
COMPLETION_REPORT_PATH = ROOT / "reports" / "stage2_4g_zotero_attachment_completion_targets.md"
USER_STEPS_PATH = ROOT / "reports" / "stage2_4g_user_zotero_steps.md"
STATUS_PATH = ROOT / "data" / "batches" / "stage2_4b_zotero_attachment_status.jsonl"
COMPLETION_CSV_PATH = ZOTERO_WORKFLOW_ROOT / "stage2_4g_zotero_completion_targets.csv"
COMPLETION_JSONL_PATH = ZOTERO_WORKFLOW_ROOT / "stage2_4g_zotero_completion_targets.jsonl"
TARGETS_RIS_PATH = ZOTERO_WORKFLOW_ROOT / "stage2_4g_targets.ris"
TARGETS_BIB_PATH = ZOTERO_WORKFLOW_ROOT / "stage2_4g_targets.bib"
MAPPING_TEMPLATE_PATH = ZOTERO_WORKFLOW_ROOT / "zotero_mapping_template.jsonl"

SUPPORTED_CONTENT_TYPES = {
    "application/pdf": ("pdf", ".pdf"),
    "text/html": ("html", ".html"),
    "application/xhtml+xml": ("html", ".html"),
}
SUPPORTED_EXTENSIONS = {
    "pdf": {".pdf"},
    "html": {".html", ".htm", ".xhtml"},
    "si": {".pdf", ".html", ".htm", ".xhtml", ".txt", ".md", ".xml"},
}
RECOMMENDED_ACTION_BY_DIAGNOSIS = {
    "zotero_attachment_synced": "ready_for_ingest",
    "manual_mapping_synced": "ready_for_ingest",
    "zotero_item_missing": "import_target_to_zotero",
    "zotero_item_without_attachment": "run_find_available_pdf_or_manual_attach",
    "zotero_attachment_file_missing": "sync_zotero_or_relink_attachment",
    "zotero_attachment_unsupported_type": "attach_pdf_or_html",
}
REQUIRED_ACTION_BY_DIAGNOSIS = {
    "zotero_attachment_synced": "ready_for_ingest",
    "manual_mapping_synced": "ready_for_ingest",
    "zotero_item_missing": "create_zotero_item",
    "zotero_item_without_attachment": "run_find_available_pdf",
    "zotero_attachment_file_missing": "sync_zotero_storage_or_relink_attachment",
    "zotero_attachment_unsupported_type": "manual_attach_pdf",
}
DIAGNOSES = set(RECOMMENDED_ACTION_BY_DIAGNOSIS)


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


def file_type_from_path(path: Path, preferred: str = "") -> tuple[str, str]:
    suffix = path.suffix.lower()
    if preferred in SUPPORTED_EXTENSIONS and suffix in SUPPORTED_EXTENSIONS[preferred]:
        return preferred, suffix
    if suffix == ".pdf":
        return "pdf", ".pdf"
    if suffix in {".html", ".htm", ".xhtml"}:
        return "html", ".html"
    if preferred == "si" and suffix in SUPPORTED_EXTENSIONS["si"]:
        return "si", suffix
    return "", suffix


def copy_supported_file(source_id: str, source_path: Path, file_type: str, dry_run: bool) -> dict[str, Any] | None:
    resolved_type, suffix = file_type_from_path(source_path, file_type)
    if not resolved_type or not source_path.exists() or not source_path.is_file():
        return None
    dest = destination_for(source_id, resolved_type, suffix)
    if not dry_run:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, dest)
    return {
        "file_type": resolved_type,
        "local_path": str(dest.relative_to(ROOT)).replace("\\", "/"),
        "sha256": sha256_file(source_path),
        "bytes": source_path.stat().st_size,
    }


def copy_attachment(source_id: str, attachment: dict[str, Any], dry_run: bool) -> dict[str, Any] | None:
    content_type = str(attachment.get("content_type", "")).lower()
    file_type, suffix = SUPPORTED_CONTENT_TYPES.get(content_type, ("", ""))
    source_path = Path(str(attachment.get("resolved_path", "")))
    if not file_type:
        file_type, suffix = file_type_from_path(source_path)
    if not file_type or not attachment.get("exists") or not source_path.exists():
        return None
    copied = copy_supported_file(source_id, source_path, file_type, dry_run)
    if copied:
        copied["match_method"] = "exact_doi_zotero_attachment"
    return copied


def resolve_user_path(path_text: str) -> Path:
    path = Path(path_text).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path


def ensure_mapping_template(manifest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if MAPPING_TEMPLATE_PATH.exists():
        return read_jsonl(MAPPING_TEMPLATE_PATH)
    rows = [
        {
            "source_id": row.get("source_id", ""),
            "doi": row.get("doi", ""),
            "title": row.get("title", ""),
            "attachment_path": "",
            "attachment_type": "pdf",
            "mapping_method": "manual_user_confirmed",
            "note": "",
        }
        for row in manifest
    ]
    write_jsonl(MAPPING_TEMPLATE_PATH, rows)
    return rows


def manual_mapping_by_source(manifest: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    manifest_by_source = {str(row.get("source_id", "")): row for row in manifest}
    rows = ensure_mapping_template(manifest)
    accepted: dict[str, dict[str, Any]] = {}
    for row in rows:
        source_id = str(row.get("source_id", ""))
        path_text = str(row.get("attachment_path", "")).strip()
        if not source_id or not path_text:
            continue
        manifest_row = manifest_by_source.get(source_id)
        if not manifest_row:
            continue
        if normalize_doi(str(row.get("doi", ""))) != normalize_doi(str(manifest_row.get("doi", ""))):
            continue
        attachment_type = str(row.get("attachment_type", "")).lower()
        if attachment_type not in SUPPORTED_EXTENSIONS:
            continue
        path = resolve_user_path(path_text)
        file_type, _ = file_type_from_path(path, attachment_type)
        if not file_type or not path.exists() or not path.is_file():
            continue
        accepted[source_id] = {
            **row,
            "resolved_path": str(path),
            "file_type": file_type,
        }
    return accepted


def apply_manual_mapping(source_id: str, mapping: dict[str, Any], dry_run: bool) -> dict[str, Any] | None:
    source_path = Path(str(mapping.get("resolved_path", "")))
    copied = copy_supported_file(source_id, source_path, str(mapping.get("file_type", "")), dry_run)
    if copied:
        copied["match_method"] = "manual_user_confirmed"
    return copied


def recommendation(diagnosis: str) -> str:
    return RECOMMENDED_ACTION_BY_DIAGNOSIS.get(diagnosis, "manual_review")


def completion_action(diagnosis: str) -> str:
    return REQUIRED_ACTION_BY_DIAGNOSIS.get(diagnosis, "manual_attach_pdf")


def diagnose_manifest(dry_run: bool) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    manifest = read_jsonl(MANIFEST_PATH)
    mappings = manual_mapping_by_source(manifest)
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
                "attachment_content_types": [],
                "attachment_paths": [],
                "copied_local_path": "",
                "sha256": "",
                "match_method": "",
                "diagnosis": "",
                "missing_reason": "",
                "recommended_user_action": "",
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
            row["attachment_content_types"] = sorted({str(attachment.get("content_type", "")) for attachment in all_attachments if attachment.get("content_type")})
            row["attachment_paths"] = [str(attachment.get("resolved_path", "")) for attachment in all_attachments]
            manual_mapping = mappings.get(source_id)
            if manual_mapping:
                accepted = apply_manual_mapping(source_id, manual_mapping, dry_run=dry_run)
            for attachment in all_attachments:
                if accepted:
                    break
                accepted = copy_attachment(source_id, attachment, dry_run=dry_run)
                if accepted:
                    break
            if accepted:
                row["accepted_attachment_count"] = 1
                row["copied_local_path"] = accepted["local_path"]
                row["sha256"] = accepted["sha256"]
                row["match_method"] = accepted.get("match_method", "exact_doi_zotero_attachment")
                row["diagnosis"] = "manual_mapping_synced" if row["match_method"] == "manual_user_confirmed" else "zotero_attachment_synced"
                row["recommended_user_action"] = recommendation(row["diagnosis"])
                updated_manifest.append(
                    {
                        **entry,
                        "access_method": row["match_method"],
                        "file_type": accepted["file_type"],
                        "local_path": accepted["local_path"],
                        "license_or_access_note": "Exact DOI Zotero attachment or user-confirmed local mapping copied into ignored local cache for local ingest only; raw file is not committed.",
                        "match_method": row["match_method"],
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
                row["missing_reason"] = row["diagnosis"]
                row["recommended_user_action"] = recommendation(row["diagnosis"])
                updated_manifest.append(
                    {
                        **entry,
                        "file_type": None,
                        "local_path": "",
                        "match_method": "",
                        "rescue_attempted": True,
                        "rescue_failure_reason": row["diagnosis"],
                        "sha256": "",
                        "status": "missing_fulltext",
                    }
                )
            status_rows.append(row)
    return status_rows, updated_manifest


def completion_targets(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for row in rows:
        targets.append(
            {
                "source_id": row.get("source_id", ""),
                "doi": row.get("doi", ""),
                "title": row.get("title", ""),
                "zotero_item_found": bool(row.get("zotero_item_count", 0)),
                "zotero_item_key": ",".join(row.get("zotero_item_keys", [])),
                "attachment_found": bool(row.get("zotero_attachments_existing", 0)),
                "required_action": completion_action(str(row.get("diagnosis", ""))),
                "priority": "high",
            }
        )
    return targets


def write_completion_files(rows: list[dict[str, Any]]) -> None:
    targets = completion_targets(rows)
    ZOTERO_WORKFLOW_ROOT.mkdir(parents=True, exist_ok=True)
    write_jsonl(COMPLETION_JSONL_PATH, targets)
    with COMPLETION_CSV_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "source_id",
                "doi",
                "title",
                "zotero_item_found",
                "zotero_item_key",
                "attachment_found",
                "required_action",
                "priority",
            ],
        )
        writer.writeheader()
        writer.writerows(targets)
    write_ris_targets(rows)
    write_bib_targets(rows)
    write_completion_report(targets)
    write_user_steps()


def write_ris_targets(rows: list[dict[str, Any]]) -> None:
    lines: list[str] = []
    for row in rows:
        lines.extend(
            [
                "TY  - JOUR",
                f"TI  - {row.get('title', '')}",
                f"DO  - {row.get('doi', '')}",
                f"N1  - source_id: {row.get('source_id', '')}",
                "KW  - ECfinder_stage2_4g",
                f"KW  - {row.get('source_id', '')}",
                "ER  -",
                "",
            ]
        )
    TARGETS_RIS_PATH.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def bib_escape(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def write_bib_targets(rows: list[dict[str, Any]]) -> None:
    entries: list[str] = []
    for row in rows:
        key = str(row.get("source_id", "")).replace("-", "_")
        entries.append(
            "\n".join(
                [
                    f"@article{{{key},",
                    f"  title = {{{bib_escape(row.get('title', ''))}}},",
                    f"  doi = {{{bib_escape(row.get('doi', ''))}}},",
                    "  keywords = {ECfinder_stage2_4g},",
                    f"  note = {{{bib_escape('source_id: ' + str(row.get('source_id', '')))}}}",
                    "}",
                ]
            )
        )
    TARGETS_BIB_PATH.write_text("\n\n".join(entries) + "\n", encoding="utf-8", newline="\n")


def write_completion_report(targets: list[dict[str, Any]]) -> None:
    lines = [
        "# Stage 2.4g Zotero Attachment Completion Targets",
        "",
        f"manifest_sources = {len(targets)}",
        f"zotero_items_found = {sum(1 for row in targets if row['zotero_item_found'])}",
        f"zotero_items_missing = {sum(1 for row in targets if not row['zotero_item_found'])}",
        f"attachments_found = {sum(1 for row in targets if row['attachment_found'])}",
        "",
        "| source_id | doi | zotero_item_found | zotero_item_key | attachment_found | required_action | priority |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in targets:
        lines.append(
            "| {source_id} | {doi} | {zotero_item_found} | {zotero_item_key} | {attachment_found} | {required_action} | {priority} |".format(
                **row
            )
        )
    COMPLETION_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    COMPLETION_REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def write_user_steps() -> None:
    lines = [
        "# Stage 2.4g User Zotero Steps",
        "",
        "1. In Zotero, import `data/local_fulltext/zotero/stage2_4g_targets.ris` or `data/local_fulltext/zotero/stage2_4g_targets.bib`.",
        "2. Create or use a collection named `ECfinder Stage 2.4g Fulltext Targets`.",
        "3. Move the imported or already existing target items into that collection.",
        "4. Select the collection items.",
        "5. Right-click and run `Find Available PDF` / `Find Full Text`.",
        "6. Wait until Zotero finishes all download attempts.",
        "7. Confirm whether each item has a PDF or HTML attachment under the exact DOI item.",
        "8. Return to this repository and run `python scripts/sync_zotero_stage2_4b_attachments.py`.",
        "",
        "If Zotero cannot automatically download a PDF, use campus/library access to download the file lawfully, then drag it onto the matching Zotero item as an attachment.",
        "",
        "Manual fallback: fill `data/local_fulltext/zotero/zotero_mapping_template.jsonl` with a local attachment path only after confirming the DOI/source_id mapping. The sync script will copy that file into the ignored local full-text cache and will not commit the original attachment.",
    ]
    USER_STEPS_PATH.parent.mkdir(parents=True, exist_ok=True)
    USER_STEPS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def write_report(rows: list[dict[str, Any]]) -> None:
    counts = {
        "manifest_sources": len(rows),
        "zotero_items_found": sum(1 for row in rows if row["zotero_item_count"] > 0),
        "zotero_items_missing": sum(1 for row in rows if row["zotero_item_count"] == 0),
        "zotero_items_without_attachment": sum(1 for row in rows if row["diagnosis"] == "zotero_item_without_attachment"),
        "zotero_attachments_existing": sum(int(row["zotero_attachments_existing"]) for row in rows),
        "attachments_synced": sum(1 for row in rows if row["diagnosis"] in {"zotero_attachment_synced", "manual_mapping_synced"}),
    }
    lines = ["# Stage 2.4b Zotero Attachment Diagnosis", ""]
    for key, value in counts.items():
        lines.append(f"{key} = {value}")
    lines.extend(
        [
            "",
            "| source_id | doi | zotero_items | attachments | synced | diagnosis | recommended_user_action |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in rows:
        lines.append(
            "| {source_id} | {doi} | {items} | {attachments} | {synced} | {diagnosis} | {recommended} |".format(
                source_id=row["source_id"],
                doi=row["doi"],
                items=",".join(row["zotero_item_keys"]),
                attachments=row["zotero_attachment_count"],
                synced=row["accepted_attachment_count"],
                diagnosis=row["diagnosis"],
                recommended=row["recommended_user_action"],
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
    write_completion_files(rows)
    if not args.dry_run:
        write_jsonl(MANIFEST_PATH, updated_manifest)
    summary = {
        "manifest_sources": len(rows),
        "zotero_items_found": sum(1 for row in rows if row["zotero_item_count"] > 0),
        "zotero_items_missing": sum(1 for row in rows if row["zotero_item_count"] == 0),
        "zotero_items_without_attachment": sum(1 for row in rows if row["diagnosis"] == "zotero_item_without_attachment"),
        "attachments_synced": sum(1 for row in rows if row["diagnosis"] in {"zotero_attachment_synced", "manual_mapping_synced"}),
        "dry_run": args.dry_run,
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
