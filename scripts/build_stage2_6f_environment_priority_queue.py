"""Build Stage 2.6f environment-prioritized streaming queue."""

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
OUTPUT_QUEUE = BATCH / "stage2_6f_environment_priority_queue.jsonl"
SUMMARY_REPORT = REPORTS / "stage2_6f_environment_priority_queue_summary.md"

COMPLETED_STATUS = {"validated", "rejected", "auxiliary", "completed_no_records", "excluded"}
HARD_SKIP_STATUS = COMPLETED_STATUS | {"blocked_external"}


def lower_text(row: dict[str, Any]) -> str:
    return " ".join(
        [
            str(row.get("title", "")),
            str(row.get("abstract", "")),
            str(row.get("journal", "")),
            " ".join(str(item) for item in row.get("keywords", [])),
        ]
    ).lower()


def row_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("source_id", "")),
        str(row.get("zotero_item_key", "")),
        str(row.get("doi", "")).strip().lower(),
    )


def has_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def add_score(text: str, terms: list[str], value: int, label: str, reasons: list[str]) -> int:
    if has_any(text, terms):
        reasons.append(label)
        return value
    return 0


def environment_score(text: str, reasons: list[str]) -> int:
    score = 0
    score += add_score(
        text,
        ["afff-contaminated groundwater", "afff-contaminated aquifer", "afff-impacted groundwater", "afff impacted groundwater", "fire-training site", "fire training site"],
        80,
        "afff_contaminated_groundwater_or_fire_training_site",
        reasons,
    )
    score += add_score(text, ["groundwater", "aquifer", "natural attenuation", "plume"], 70, "groundwater_aquifer_natural_attenuation_plume", reasons)
    score += add_score(text, ["soil", "sediment", "wetland", "estuarine", "marine", "surface water"], 60, "soil_sediment_wetland_or_surface_water", reasons)
    score += add_score(text, ["environmental microcosm", "field-contaminated", "field contaminated", "environmental solids"], 50, "environmental_microcosm_or_field_material", reasons)
    score += add_score(text, ["biosolids-amended soil", "agricultural soil", "landfill-impacted soil", "landfill impacted soil"], 40, "biosolids_agricultural_or_landfill_soil", reasons)
    return score


def transformation_score(text: str, reasons: list[str]) -> int:
    score = 0
    score += add_score(text, ["transformation product", "degradation product", "metabolite", "metabolites", "pathway"], 80, "product_metabolite_pathway", reasons)
    score += add_score(text, ["precursor transformation", "biotransformation", "biotransform", "natural attenuation"], 70, "precursor_biotransformation_or_natural_attenuation", reasons)
    score += add_score(text, ["fluorotelomer transformation", "ftoh", "ftsa", "fluorotelomer"], 60, "fluorotelomer_ftoh_ftsa", reasons)
    score += add_score(text, ["fosa", "fose", "fosaa", "sulfonamide precursor", "sulfonamido precursor"], 50, "fosa_fose_sulfonamide_precursor", reasons)
    score += add_score(text, ["pap", "dipap", "phosphate ester precursor", "polyfluoroalkyl phosphate"], 50, "pap_dipap_phosphate_precursor", reasons)
    score += add_score(text, ["afff precursor", "precursor assay", "top assay", "total oxidizable precursor", "top-related precursor"], 40, "afff_or_top_precursor_evidence", reasons)
    return score


def negative_score(text: str, previous: dict[str, Any], reasons: list[str]) -> int:
    score = 0
    if previous.get("overall_status") in COMPLETED_STATUS:
        reasons.append("previous_completed_or_excluded")
        score -= 100
    if previous.get("screening_decision") == "exclude":
        reasons.append("previous_screening_exclude")
        score -= 100
    negative_groups = [
        (["pure culture only", "pure culture", "isolated strain", "cunninghamella", "human liver microsomes"], -90, "pure_culture_or_isolated_strain_only"),
        (["wwtp", "activated sludge", "wastewater treatment", "water resource recovery", "wastewater microbial consortia"], -90, "wwtp_activated_sludge_or_wastewater_treatment"),
        (["aop", "advanced oxidation", "electrochemical", "plasma", "photocatalysis", "photocatalytic", "ozonation", "uv-persulfate", "uv/persulfate", "uv/sulfite"], -90, "engineered_oxidation_treatment"),
        (["analytical method", "method development", "occurrence only", "occurrence", "toxicity", "human exposure", "review", "food web"], -80, "method_occurrence_toxicity_exposure_or_review"),
        (["adsorption", "removal"], -60, "adsorption_or_removal_only"),
    ]
    for terms, value, label in negative_groups:
        if has_any(text, terms):
            reasons.append(label)
            score += value
    return score


def load_previous() -> tuple[dict[str, dict[str, Any]], set[str], set[str], set[str], int, int]:
    by_any: dict[str, dict[str, Any]] = {}
    hard_ids: set[str] = set()
    hard_keys: set[str] = set()
    hard_dois: set[str] = set()
    completed_count = 0
    previous_exclude = 0
    for path in [
        STATE / "stage2_6c_streaming_source_status.jsonl",
        STATE / "stage2_6d_streaming_source_status.jsonl",
        STATE / "stage2_6e_streaming_source_status.jsonl",
    ]:
        for row in read_jsonl(path):
            source_id, zotero_key, doi = row_key(row)
            for key in [source_id, zotero_key, doi]:
                if key:
                    by_any[key] = row
            if row.get("overall_status") in HARD_SKIP_STATUS:
                completed_count += 1
                if row.get("overall_status") == "excluded":
                    previous_exclude += 1
                if source_id:
                    hard_ids.add(source_id)
                if zotero_key:
                    hard_keys.add(zotero_key)
                if doi:
                    hard_dois.add(doi)
    for path in [
        BATCH / "stage2_6c_streaming_screening_decisions.jsonl",
        BATCH / "stage2_6d_streaming_screening_decisions.jsonl",
        BATCH / "stage2_6e_streaming_screening_decisions.jsonl",
    ]:
        for row in read_jsonl(path):
            source_id = str(row.get("source_id", ""))
            if source_id and source_id not in by_any:
                by_any[source_id] = row
    for row in read_jsonl(STATE / "source_registry.jsonl"):
        source_id, zotero_key, doi = row_key(row)
        if row.get("status") in {"validated", "rejected", "auxiliary", "manual_review"}:
            completed_count += 1
            if source_id:
                hard_ids.add(source_id)
            if zotero_key:
                hard_keys.add(zotero_key)
            if doi:
                hard_dois.add(doi)
    return by_any, hard_ids, hard_keys, hard_dois, completed_count, previous_exclude


def previous_for(row: dict[str, Any], manifest: dict[str, Any] | None, previous_by_any: dict[str, dict[str, Any]]) -> dict[str, Any]:
    keys = [row.get("source_id", ""), row.get("zotero_item_key", ""), str(row.get("doi", "")).strip().lower()]
    if manifest:
        keys.extend([manifest.get("source_id", ""), manifest.get("zotero_item_key", ""), str(manifest.get("doi", "")).strip().lower()])
    for key in keys:
        if key and key in previous_by_any:
            return previous_by_any[key]
    return {}


def make_item(row: dict[str, Any], manifest: dict[str, Any] | None, previous: dict[str, Any]) -> dict[str, Any] | None:
    text = lower_text(row)
    reasons: list[str] = []
    env_score = environment_score(text, reasons)
    trans_score = transformation_score(text, reasons)
    attach_score = 70 if manifest else 0
    if manifest:
        reasons.append("has_pdf_or_html_attachment")
    prev_decision = previous.get("screening_decision")
    previous_decision_score = 0
    allow_manual_rescreen = False
    if prev_decision == "include_for_fulltext":
        previous_decision_score = 60
        reasons.append("previous_include_for_fulltext")
    elif prev_decision == "manual_screen" and env_score >= 60 and trans_score >= 50:
        previous_decision_score = 30
        allow_manual_rescreen = True
        reasons.append("manual_screen_strong_environment_transformation_rescreen")
    elif not previous:
        previous_decision_score = 20
        reasons.append("not_yet_screened")
    neg_score = negative_score(text, previous, reasons)
    priority = env_score + trans_score + attach_score + previous_decision_score + neg_score
    if env_score <= 0 or trans_score <= 0:
        return None
    if priority < 100:
        return None
    if prev_decision == "exclude" or previous.get("overall_status") in COMPLETED_STATUS:
        return None
    if prev_decision == "manual_screen" and not allow_manual_rescreen:
        return None
    source_id, zotero_key, doi = row_key(row)
    manifest_source_id = str((manifest or {}).get("source_id", ""))
    return {
        "source_id": source_id or manifest_source_id,
        "screening_source_id": source_id or manifest_source_id,
        "manifest_source_id": manifest_source_id,
        "zotero_item_key": zotero_key or (manifest or {}).get("zotero_item_key", ""),
        "doi": row.get("doi") or (manifest or {}).get("doi", ""),
        "title": row.get("title") or (manifest or {}).get("title", ""),
        "abstract": row.get("abstract", ""),
        "year": row.get("year", ""),
        "journal": row.get("journal", ""),
        "keywords": row.get("keywords", []),
        "has_attachment_metadata": bool(manifest),
        "has_pdf_or_html_attachment": bool(manifest),
        "attachment_count": 1 if manifest else 0,
        "pdf_or_html_attachment_count": 1 if manifest else 0,
        "previous_screening_decision": prev_decision,
        "previous_overall_status": previous.get("overall_status", ""),
        "environment_score": env_score,
        "transformation_score": trans_score,
        "attachment_score": attach_score,
        "previous_decision_score": previous_decision_score,
        "negative_score": neg_score,
        "priority_score": priority,
        "priority_reasons": reasons,
        "allow_manual_rescreen": allow_manual_rescreen,
        "status": "pending_streaming",
    }


def build_queue() -> list[dict[str, Any]]:
    metadata = read_jsonl(METADATA_QUEUE)
    manifest_rows = read_jsonl(FULLTEXT_MANIFEST)
    manifest_by_key = {str(row.get("zotero_item_key", "")): row for row in manifest_rows if row.get("zotero_item_key")}
    manifest_by_doi = {str(row.get("doi", "")).strip().lower(): row for row in manifest_rows if row.get("doi")}
    previous_by_any, hard_ids, hard_keys, hard_dois, completed_count, previous_exclude = load_previous()
    queue: list[dict[str, Any]] = []
    skipped_completed: set[str] = set()
    skipped_excluded: set[str] = set()
    for row in metadata:
        manifest = manifest_by_key.get(str(row.get("zotero_item_key", ""))) or manifest_by_doi.get(str(row.get("doi", "")).strip().lower())
        source_id, zotero_key, doi = row_key(row)
        manifest_source_id = str((manifest or {}).get("source_id", ""))
        previous = previous_for(row, manifest, previous_by_any)
        hard_skip = source_id in hard_ids or manifest_source_id in hard_ids or zotero_key in hard_keys or doi in hard_dois
        if hard_skip:
            key = source_id or manifest_source_id or zotero_key or doi
            if previous.get("overall_status") == "excluded" or previous.get("screening_decision") == "exclude":
                skipped_excluded.add(key)
            else:
                skipped_completed.add(key)
            continue
        item = make_item(row, manifest, previous)
        if item:
            queue.append(item)
    queue.sort(
        key=lambda item: (
            int(item.get("priority_score", 0)),
            bool(item.get("has_pdf_or_html_attachment")),
            item.get("previous_screening_decision") == "include_for_fulltext",
            int(item.get("environment_score", 0)),
            int(item.get("transformation_score", 0)),
        ),
        reverse=True,
    )
    write_jsonl(OUTPUT_QUEUE, queue)
    write_summary(metadata, manifest_rows, queue, completed_count, previous_exclude, len(skipped_completed), len(skipped_excluded))
    return queue


def write_summary(
    metadata: list[dict[str, Any]],
    manifest_rows: list[dict[str, Any]],
    queue: list[dict[str, Any]],
    completed_count: int,
    previous_exclude: int,
    skipped_completed: int,
    skipped_excluded: int,
) -> None:
    top_50 = queue[:50]
    lines = [
        "# Stage 2.6f Environment Priority Queue Summary",
        "",
        f"total_metadata_sources = {len(metadata)}",
        f"sources_with_pdf_or_html_attachment = {len(manifest_rows)}",
        f"previously_completed_sources_excluded = {skipped_completed or completed_count}",
        f"previous_exclude_sources_excluded = {skipped_excluded or previous_exclude}",
        f"priority_queue_size = {len(queue)}",
        f"environment_priority_sources = {sum(1 for row in queue if row.get('environment_score', 0) > 0 and row.get('transformation_score', 0) > 0)}",
        f"sources_with_pdf_or_html_attachment_in_queue = {sum(1 for row in queue if row.get('has_pdf_or_html_attachment'))}",
        f"previous_include_sources = {sum(1 for row in queue if row.get('previous_screening_decision') == 'include_for_fulltext')}",
        f"manual_rescreen_sources = {sum(1 for row in queue if row.get('allow_manual_rescreen') is True)}",
        "",
        "| rank | source_id | score | env | trans | attachment | previous | title | reasons |",
        "| ---: | --- | ---: | ---: | ---: | --- | --- | --- | --- |",
    ]
    for rank, row in enumerate(top_50, start=1):
        title = " ".join(str(row.get("title", "")).split()).replace("|", "/")
        if len(title) > 90:
            title = title[:87].rstrip() + "..."
        reasons = ",".join(str(item) for item in row.get("priority_reasons", [])[:7])
        lines.append(
            f"| {rank} | {row.get('source_id', '')} | {row.get('priority_score', 0)} | "
            f"{row.get('environment_score', 0)} | {row.get('transformation_score', 0)} | "
            f"{str(bool(row.get('has_pdf_or_html_attachment'))).lower()} | "
            f"{row.get('previous_screening_decision') or ''} | {title} | {reasons} |"
        )
    SUMMARY_REPORT.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    queue = build_queue()
    print(f"priority_queue_size={len(queue)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
