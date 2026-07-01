"""Audit the Zotero collection scope for Stage 2.4j available-first ingest."""

from __future__ import annotations

import json
from typing import Any

from stage2_4j_common import AUDIT_JSONL, REPORTS_DIR, load_stage2_mappings, normalize_doi, screen_relevance, write_jsonl, write_summary
from zotero_stage2_4i_common import attachments_for_item, connect_zotero, item_field


TARGET_COLLECTION_HINT = "\u5316\u5b66\u7269"
SUMMARY_PATH = REPORTS_DIR / "stage2_4j_zotero_scope_audit_summary.md"


def item_collections(con, item_id: int) -> list[str]:
    rows = con.execute(
        """
        select c.collectionName
        from collectionItems ci
        join collections c on c.collectionID = ci.collectionID
        where ci.itemID = ?
        order by c.collectionName
        """,
        (item_id,),
    ).fetchall()
    return [str(row["collectionName"]) for row in rows]


def target_collection_id(con) -> int | None:
    row = con.execute(
        "select collectionID from collections where collectionName like ? order by collectionID limit 1",
        (f"%{TARGET_COLLECTION_HINT}%",),
    ).fetchone()
    return int(row["collectionID"]) if row else None


def field(con, item_id: int, *names: str) -> str:
    for name in names:
        value = item_field(con, item_id, name)
        if value:
            return value
    return ""


def audit_scope() -> list[dict[str, Any]]:
    queue_map, targets_map = load_stage2_mappings()
    records: list[dict[str, Any]] = []
    with connect_zotero() as con:
        collection_id = target_collection_id(con)
        if collection_id is not None:
            rows = con.execute(
                """
                select i.itemID, i.key, it.typeName
                from collectionItems ci
                join items i on i.itemID = ci.itemID
                join itemTypes it on it.itemTypeID = i.itemTypeID
                where ci.collectionID = ? and it.typeName not in ('attachment', 'note')
                order by i.itemID
                """,
                (collection_id,),
            ).fetchall()
        else:
            rows = con.execute(
                """
                select i.itemID, i.key, it.typeName
                from items i
                join itemTypes it on it.itemTypeID = i.itemTypeID
                where it.typeName not in ('attachment', 'note')
                order by i.itemID
                """
            ).fetchall()
        for row in rows:
            item_id = int(row["itemID"])
            title = field(con, item_id, "title")
            doi = field(con, item_id, "DOI", "doi")
            year = field(con, item_id, "date")
            journal = field(con, item_id, "publicationTitle", "journalAbbreviation")
            abstract = field(con, item_id, "abstractNote")
            attachments = attachments_for_item(con, item_id)
            existing = [attachment for attachment in attachments if attachment.get("exists")]
            supported_existing = [
                attachment for attachment in existing if attachment.get("supported") and str(attachment.get("path", "")).lower().rsplit(".", 1)[-1] in {"pdf", "html", "htm", "xhtml", "txt", "md", "xml"}
            ]
            doi_norm = normalize_doi(doi)
            relevance, reason = screen_relevance(title, abstract)
            collection_names = item_collections(con, item_id)
            records.append(
                {
                    "zotero_item_key": str(row["key"]),
                    "collection_or_library": ";".join(collection_names) if collection_names else "library",
                    "title": title,
                    "doi": doi,
                    "year": year[:4],
                    "journal": journal,
                    "item_type": str(row["typeName"]),
                    "has_attachment": bool(attachments),
                    "attachment_count": len(attachments),
                    "attachment_types": sorted({str(attachment.get("content_type", "")) for attachment in attachments if attachment.get("content_type")}),
                    "attachment_paths_existing": len(existing),
                    "pdf_or_html_attachment_count": len(supported_existing),
                    "matched_stage2_4_source_id": queue_map.get(doi_norm) or None,
                    "matched_stage2_4b_target": doi_norm in targets_map,
                    "possible_pfas_transformation_relevance": relevance,
                    "screening_reason": reason,
                }
            )
    return records


def write_reports(records: list[dict[str, Any]]) -> dict[str, Any]:
    summary = {
        "zotero_total_items": len(records),
        "items_with_doi": sum(1 for row in records if row.get("doi")),
        "items_without_doi": sum(1 for row in records if not row.get("doi")),
        "items_with_pdf_or_html_attachment": sum(1 for row in records if int(row.get("pdf_or_html_attachment_count", 0)) > 0),
        "items_with_existing_attachment_path": sum(1 for row in records if int(row.get("attachment_paths_existing", 0)) > 0),
        "items_matching_stage2_4_queue": sum(1 for row in records if row.get("matched_stage2_4_source_id")),
        "items_matching_stage2_4_30source_queue": sum(1 for row in records if row.get("matched_stage2_4_source_id")),
        "items_matching_stage2_4b_12_targets": sum(1 for row in records if row.get("matched_stage2_4b_target")),
        "items_possible_pfas_transformation_high": sum(1 for row in records if row.get("possible_pfas_transformation_relevance") == "high"),
        "items_possible_pfas_transformation_medium": sum(1 for row in records if row.get("possible_pfas_transformation_relevance") == "medium"),
        "items_possible_pfas_transformation_low": sum(1 for row in records if row.get("possible_pfas_transformation_relevance") == "low"),
        "items_selected_for_available_first_ingest": 0,
    }
    write_summary(
        SUMMARY_PATH,
        "Stage 2.4j Zotero Scope Audit Summary",
        summary,
        ["scope = Zotero collection whose name contains the Stage 2.4j chemical-database hint; attachments are counted but raw files are not committed."],
    )
    return summary


def main() -> int:
    records = audit_scope()
    write_jsonl(AUDIT_JSONL, records)
    summary = write_reports(records)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
