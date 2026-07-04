"""Build Stage 2.6e attachment-prioritized streaming queue."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ecfinder.state.common import read_jsonl, write_jsonl


ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "data" / "batches"
STATE = ROOT / "data" / "state"
REPORTS = ROOT / "reports"

METADATA_QUEUE = BATCH / "stage2_6b_zotero_metadata_screening_queue.jsonl"
FULLTEXT_MANIFEST = ROOT / "data" / "local_fulltext" / "stage2_4j" / "zotero_available_fulltext_manifest.jsonl"
OUTPUT_QUEUE = BATCH / "stage2_6e_attachment_priority_queue.jsonl"
SUMMARY_REPORT = REPORTS / "stage2_6e_attachment_priority_queue_summary.md"

TRANSFORM_TERMS = [
    "transformation",
    "transform",
    "biotransformation",
    "biotransform",
    "biotransformed",
    "biodegradation",
    "degradation",
    "metabolite",
    "metabolites",
    "pathway",
    "product",
]
PRECURSOR_TERMS = [
    "precursor",
    "ftoh",
    "ftsa",
    "fosa",
    "fose",
    "fosaa",
    "pap",
    "dipap",
    "afff",
    "fluorotelomer",
]
ENV_TERMS = [
    "soil",
    "sediment",
    "groundwater",
    "aquifer",
    "wetland",
    "microcosm",
    "surface water",
    "marine",
    "estuarine",
]
NEGATIVE_TERMS = [
    "analytical method",
    "method development",
    "occurrence",
    "monitoring",
    "review",
    "toxicity",
    "food web",
    "human exposure",
    "wastewater",
    "activated sludge",
    "wwtp",
    "advanced oxidation",
    "photocatalytic",
    "photocatalysis",
    "electrochemical",
    "ozonation",
    "uv/sulfite",
    "uv/persulfate",
    "incineration",
]
TERMINAL_STATUS = {
    "validated",
    "rejected",
    "auxiliary",
    "completed_no_records",
    "excluded",
    "blocked_external",
    "manual_screen",
}


def lower_text(row: dict[str, Any]) -> str:
    return " ".join(
        [
            str(row.get("title", "")),
            str(row.get("abstract", "")),
            str(row.get("journal", "")),
            " ".join(str(item) for item in row.get("keywords", [])),
        ]
    ).lower()


def contains_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def hits(text: str, terms: list[str]) -> list[str]:
    return [term for term in terms if term in text]


def row_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("source_id", "")),
        str(row.get("zotero_item_key", "")),
        str(row.get("doi", "")).strip().lower(),
    )


def load_previous() -> tuple[dict[str, dict[str, Any]], set[str], set[str], set[str], int, int]:
    by_any: dict[str, dict[str, Any]] = {}
    terminal_ids: set[str] = set()
    terminal_keys: set[str] = set()
    terminal_dois: set[str] = set()
    completed_excluded = 0
    previous_exclude = 0
    for path in [
        STATE / "stage2_6c_streaming_source_status.jsonl",
        STATE / "stage2_6d_streaming_source_status.jsonl",
    ]:
        for row in read_jsonl(path):
            source_id, zotero_key, doi = row_key(row)
            for key in [source_id, zotero_key, doi]:
                if key:
                    by_any[key] = row
            if row.get("overall_status") in TERMINAL_STATUS:
                completed_excluded += 1
                if row.get("overall_status") == "excluded":
                    previous_exclude += 1
                if source_id:
                    terminal_ids.add(source_id)
                if zotero_key:
                    terminal_keys.add(zotero_key)
                if doi:
                    terminal_dois.add(doi)
    for row in read_jsonl(STATE / "source_registry.jsonl"):
        source_id, zotero_key, doi = row_key(row)
        status = str(row.get("status", ""))
        if status in {"validated", "rejected", "auxiliary", "manual_review"}:
            completed_excluded += 1
            if source_id:
                terminal_ids.add(source_id)
            if zotero_key:
                terminal_keys.add(zotero_key)
            if doi:
                terminal_dois.add(doi)
    return by_any, terminal_ids, terminal_keys, terminal_dois, completed_excluded, previous_exclude


def previous_for(row: dict[str, Any], manifest: dict[str, Any], previous_by_any: dict[str, dict[str, Any]]) -> dict[str, Any]:
    for key in [
        row.get("source_id", ""),
        row.get("zotero_item_key", ""),
        str(row.get("doi", "")).strip().lower(),
        manifest.get("source_id", ""),
        manifest.get("zotero_item_key", ""),
        str(manifest.get("doi", "")).strip().lower(),
    ]:
        if key and key in previous_by_any:
            return previous_by_any[key]
    return {}


def score_item(row: dict[str, Any], manifest: dict[str, Any], previous: dict[str, Any]) -> tuple[int, list[str]]:
    text = lower_text(row)
    score = 0
    reasons: list[str] = []
    if manifest:
        score += 100
        reasons.append("has_pdf_or_html_attachment")
    if previous.get("screening_decision") == "include_for_fulltext":
        score += 80
        reasons.append("previous_include_for_fulltext")
    if contains_any(text, TRANSFORM_TERMS):
        score += 50
        reasons.append("transformation_degradation_metabolite_pathway_term")
    if contains_any(text, PRECURSOR_TERMS):
        score += 40
        reasons.append("precursor_fluorotelomer_afff_term")
    if contains_any(text, ENV_TERMS):
        score += 30
        reasons.append("natural_environment_matrix_term")
    if not previous:
        score += 20
        reasons.append("not_yet_screened")
    if previous.get("screening_decision") == "exclude":
        score -= 100
        reasons.append("previous_exclude")
    if previous.get("overall_status") in {"validated", "rejected", "auxiliary", "completed_no_records"}:
        score -= 80
        reasons.append("previous_completed")
    negative_hits = hits(text, NEGATIVE_TERMS)
    if negative_hits:
        score -= 70
        reasons.append("negative_scope_terms:" + ",".join(negative_hits[:6]))
    return score, reasons


def build_queue() -> list[dict[str, Any]]:
    metadata = read_jsonl(METADATA_QUEUE)
    manifest_rows = read_jsonl(FULLTEXT_MANIFEST)
    manifest_by_key = {str(row.get("zotero_item_key", "")): row for row in manifest_rows if row.get("zotero_item_key")}
    manifest_by_doi = {str(row.get("doi", "")).strip().lower(): row for row in manifest_rows if row.get("doi")}
    previous_by_any, terminal_ids, terminal_keys, terminal_dois, completed_excluded, previous_exclude = load_previous()
    queue: list[dict[str, Any]] = []
    excluded_completed_seen: set[str] = set()
    excluded_previous_seen: set[str] = set()
    for row in metadata:
        manifest = manifest_by_key.get(str(row.get("zotero_item_key", ""))) or manifest_by_doi.get(str(row.get("doi", "")).strip().lower())
        if not manifest:
            continue
        source_id, zotero_key, doi = row_key(row)
        manifest_source_id = str(manifest.get("source_id", ""))
        previous = previous_for(row, manifest, previous_by_any)
        is_terminal = (
            source_id in terminal_ids
            or manifest_source_id in terminal_ids
            or zotero_key in terminal_keys
            or doi in terminal_dois
            or previous.get("overall_status") in TERMINAL_STATUS
        )
        if is_terminal:
            if previous.get("overall_status") == "excluded":
                excluded_previous_seen.add(source_id or manifest_source_id or zotero_key or doi)
            else:
                excluded_completed_seen.add(source_id or manifest_source_id or zotero_key or doi)
            continue
        score, reasons = score_item(row, manifest, previous)
        item = {
            "source_id": source_id or manifest_source_id,
            "screening_source_id": source_id or manifest_source_id,
            "manifest_source_id": manifest_source_id,
            "zotero_item_key": zotero_key or manifest.get("zotero_item_key", ""),
            "doi": row.get("doi") or manifest.get("doi", ""),
            "title": row.get("title") or manifest.get("title", ""),
            "abstract": row.get("abstract", ""),
            "year": row.get("year", ""),
            "journal": row.get("journal", ""),
            "keywords": row.get("keywords", []),
            "has_attachment_metadata": True,
            "has_pdf_or_html_attachment": True,
            "attachment_count": int(row.get("pdf_or_html_attachment_count", 0) or 1),
            "pdf_or_html_attachment_count": int(row.get("pdf_or_html_attachment_count", 0) or 1),
            "previous_screening_decision": previous.get("screening_decision"),
            "previous_overall_status": previous.get("overall_status", ""),
            "priority_score": score,
            "priority_reasons": reasons,
            "status": "pending_streaming",
        }
        queue.append(item)
    queue.sort(
        key=lambda item: (
            int(item.get("priority_score", 0)),
            bool(item.get("has_pdf_or_html_attachment")),
            item.get("previous_screening_decision") == "include_for_fulltext",
            item.get("previous_overall_status") not in TERMINAL_STATUS,
        ),
        reverse=True,
    )
    write_jsonl(OUTPUT_QUEUE, queue)
    write_summary(metadata, manifest_rows, queue, completed_excluded, previous_exclude, len(excluded_completed_seen), len(excluded_previous_seen))
    return queue


def write_summary(
    metadata: list[dict[str, Any]],
    manifest_rows: list[dict[str, Any]],
    queue: list[dict[str, Any]],
    completed_excluded: int,
    previous_exclude: int,
    unique_completed_excluded: int,
    unique_previous_exclude: int,
) -> None:
    top_50 = queue[:50]
    top_50_previous_include = [row for row in top_50 if row.get("previous_screening_decision") == "include_for_fulltext"]
    top_50_unscreened = [row for row in top_50 if row.get("previous_screening_decision") is None]
    lines = [
        "# Stage 2.6e Attachment Priority Queue Summary",
        "",
        f"total_metadata_sources = {len(metadata)}",
        f"sources_with_pdf_or_html_attachment = {len(manifest_rows)}",
        f"previously_completed_sources_excluded = {unique_completed_excluded or completed_excluded}",
        f"previous_exclude_sources_excluded = {unique_previous_exclude or previous_exclude}",
        f"priority_queue_size = {len(queue)}",
        f"top_50_with_attachment = {sum(1 for row in top_50 if row.get('has_pdf_or_html_attachment'))}",
        f"top_50_previous_include = {len(top_50_previous_include)}",
        f"top_50_unscreened_high_relevance = {len(top_50_unscreened)}",
        "",
        "| rank | source_id | score | previous_decision | title | reasons |",
        "| ---: | --- | ---: | --- | --- | --- |",
    ]
    for rank, row in enumerate(top_50, start=1):
        title = " ".join(str(row.get("title", "")).split()).replace("|", "/")
        if len(title) > 96:
            title = title[:93].rstrip() + "..."
        reasons = ",".join(str(item) for item in row.get("priority_reasons", [])[:6])
        lines.append(
            f"| {rank} | {row.get('source_id', '')} | {row.get('priority_score', 0)} | {row.get('previous_screening_decision') or ''} | {title} | {reasons} |"
        )
    SUMMARY_REPORT.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    queue = build_queue()
    print(f"priority_queue_size={len(queue)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
