"""Runnable source discovery for the production autonomous daemon."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ecfinder.state.common import read_jsonl, write_jsonl


COMPLETED = {"validated", "rejected", "auxiliary", "completed_no_records", "excluded"}
MANUAL = {"manual_screen", "manual_review", "ambiguous_environment_boundary"}
BLOCKED = {"blocked_external"}

ENVIRONMENT_TERMS = [
    "soil",
    "sediment",
    "groundwater",
    "aquifer",
    "wetland",
    "surface water",
    "marine",
    "estuarine",
    "field-contaminated",
    "afff-contaminated",
    "fire-training site",
    "fire training site",
    "natural attenuation",
    "environmental microcosm",
    "environmental solids",
]
TRANSFORMATION_TERMS = [
    "transformation",
    "biotransformation",
    "degradation product",
    "transformation product",
    "metabolite",
    "pathway",
    "precursor",
    "ftoh",
    "ftsa",
    "fosa",
    "fose",
    "pap",
    "dipap",
    "fluorotelomer",
    "afff precursor",
]
PFAS_TERMS = ["pfas", "perfluoro", "polyfluoro", "fluorotelomer", "ftoh", "ftsa", "fosa", "fose", "pap", "dipap", "afff"]
NEGATIVE_TERMS = [
    "wwtp",
    "activated sludge",
    "wastewater treatment",
    "advanced oxidation",
    "electrochemical",
    "plasma",
    "photocatalysis",
    "ozonation",
    "uv/persulfate",
    "incineration",
    "analytical method",
    "occurrence only",
    "toxicity",
    "human exposure",
    "review",
    "pure culture",
]


@dataclass
class DiscoveryResult:
    library_total_sources: int
    runnable_sources: list[dict[str, Any]]
    classified_rows: list[dict[str, Any]]
    blocked_sources_rescanned: int
    blocked_sources_unblocked: int
    new_attachments_found: int
    completed_sources: int
    manual_sources: int
    blocked_sources: int


def identity(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("source_id", "")),
        str(row.get("zotero_item_key", "")),
        str(row.get("doi", "")).strip().lower(),
    )


def text_for(row: dict[str, Any]) -> str:
    return " ".join(
        [
            str(row.get("title", "")),
            str(row.get("abstract", "")),
            str(row.get("journal", "")),
            " ".join(str(item) for item in row.get("keywords", [])),
        ]
    ).lower()


def hits(text: str, terms: list[str]) -> list[str]:
    return [term for term in terms if term in text]


def previous_lookup(status_paths: list[Path], decision_paths: list[Path]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for path in status_paths:
        for row in read_jsonl(path):
            for key in identity(row):
                if key:
                    lookup[key] = row
    for path in decision_paths:
        for row in read_jsonl(path):
            source_id = str(row.get("source_id", ""))
            if source_id and source_id not in lookup:
                lookup[source_id] = row
    return lookup


def manifest_lookup(manifest_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for row in manifest_rows:
        for key in identity(row):
            if key:
                lookup[key] = row
    return lookup


def find_match(row: dict[str, Any], lookup: dict[str, dict[str, Any]]) -> dict[str, Any]:
    for key in identity(row):
        if key and key in lookup:
            return lookup[key]
    return {}


def score_source(row: dict[str, Any], previous: dict[str, Any], manifest: dict[str, Any]) -> tuple[int, list[str], int, int, int]:
    text = text_for(row)
    env_hits = hits(text, ENVIRONMENT_TERMS)
    transform_hits = hits(text, TRANSFORMATION_TERMS)
    pfas_hits = hits(text, PFAS_TERMS)
    negative_hits = hits(text, NEGATIVE_TERMS)
    env_score = 80 if any("afff" in hit or "fire" in hit for hit in env_hits) else (60 if env_hits else 0)
    transform_score = 80 if any("product" in hit or "metabolite" in hit or "pathway" in hit for hit in transform_hits) else (60 if transform_hits else 0)
    attachment_score = 70 if manifest else 0
    previous_score = 0
    reasons: list[str] = []
    if previous.get("screening_decision") == "include_for_fulltext":
        previous_score += 60
        reasons.append("previous_include_for_fulltext")
    if not previous:
        previous_score += 20
        reasons.append("not_yet_screened")
    if manifest:
        reasons.append("has_pdf_or_html_attachment")
    if env_hits:
        reasons.append("natural_environment_terms:" + ",".join(env_hits[:5]))
    if transform_hits:
        reasons.append("transformation_terms:" + ",".join(transform_hits[:5]))
    if pfas_hits:
        reasons.append("pfas_terms:" + ",".join(pfas_hits[:5]))
    negative_score = -70 if negative_hits else 0
    if negative_hits:
        reasons.append("negative_terms:" + ",".join(negative_hits[:5]))
    return env_score + transform_score + attachment_score + previous_score + negative_score, reasons, env_score, transform_score, negative_score


def classify_source(row: dict[str, Any], previous: dict[str, Any], manifest: dict[str, Any]) -> str:
    overall = str(previous.get("overall_status", previous.get("status", "")))
    decision = str(previous.get("screening_decision", ""))
    if overall in COMPLETED or decision == "exclude":
        return "excluded" if overall == "excluded" or decision == "exclude" else "completed"
    if overall in MANUAL or decision == "manual_screen":
        return "manual_screen"
    if overall in BLOCKED or (decision == "include_for_fulltext" and not manifest):
        return "runnable_fulltext" if manifest else "blocked_external"
    if decision == "include_for_fulltext":
        return "runnable_fulltext" if manifest else "blocked_external"
    return "runnable_screening"


def make_runnable_item(row: dict[str, Any], previous: dict[str, Any], manifest: dict[str, Any], classification: str) -> dict[str, Any]:
    source_id, zotero_key, doi = identity(row)
    manifest_source_id = str(manifest.get("source_id", ""))
    priority, reasons, env_score, transform_score, negative_score = score_source(row, previous, manifest)
    if classification == "runnable_fulltext" and previous.get("overall_status") == "blocked_external" and manifest:
        priority += 600
        reasons.append("blocked_external_now_has_attachment")
    elif classification == "runnable_fulltext" and manifest:
        priority += 500
        reasons.append("include_for_fulltext_with_attachment")
    elif env_score and transform_score and manifest:
        priority += 400
        reasons.append("environment_transformation_with_attachment")
    elif env_score and transform_score:
        priority += 300
        reasons.append("environment_transformation_without_attachment")
    elif hits(text_for(row), PFAS_TERMS + TRANSFORMATION_TERMS):
        priority += 200
        reasons.append("unscreened_high_title_abstract_relevance")
    else:
        priority += 100
        reasons.append("lower_relevance_unscreened_metadata")
    return {
        "source_id": source_id or manifest_source_id,
        "screening_source_id": source_id or manifest_source_id,
        "zotero_item_key": zotero_key or manifest.get("zotero_item_key", ""),
        "doi": row.get("doi") or manifest.get("doi", ""),
        "title": row.get("title") or manifest.get("title", ""),
        "abstract": row.get("abstract", ""),
        "year": row.get("year", ""),
        "journal": row.get("journal", ""),
        "keywords": row.get("keywords", []),
        "has_pdf_or_html_attachment": bool(manifest),
        "attachment_count": 1 if manifest else 0,
        "pdf_or_html_attachment_count": 1 if manifest else 0,
        "previous_screening_decision": previous.get("screening_decision"),
        "previous_overall_status": previous.get("overall_status", ""),
        "runnable_classification": classification,
        "environment_score": env_score,
        "transformation_score": transform_score,
        "negative_score": negative_score,
        "priority_score": priority,
        "priority_reasons": reasons,
        "allow_resume_reprocess": classification == "runnable_fulltext" and bool(previous),
        "status": "pending_streaming",
    }


def discover_runnable_sources(
    *,
    metadata_queue: Path,
    fulltext_manifest: Path,
    status_paths: list[Path],
    decision_paths: list[Path],
    output_queue: Path,
    audit_report: Path,
) -> DiscoveryResult:
    metadata = read_jsonl(metadata_queue)
    manifest_rows = read_jsonl(fulltext_manifest)
    manifest_by_any = manifest_lookup(manifest_rows)
    previous_by_any = previous_lookup(status_paths, decision_paths)
    runnable: list[dict[str, Any]] = []
    classified: list[dict[str, Any]] = []
    blocked_rescanned = 0
    blocked_unblocked = 0
    completed = 0
    manual = 0
    blocked = 0
    for row in metadata:
        previous = find_match(row, previous_by_any)
        manifest = find_match(row, manifest_by_any)
        classification = classify_source(row, previous, manifest)
        if previous.get("overall_status") == "blocked_external":
            blocked_rescanned += 1
            if manifest:
                blocked_unblocked += 1
        if classification == "completed" or classification == "excluded":
            completed += 1
        elif classification == "manual_screen":
            manual += 1
        elif classification == "blocked_external":
            blocked += 1
        classified.append(
            {
                "source_id": row.get("source_id", ""),
                "zotero_item_key": row.get("zotero_item_key", ""),
                "doi": row.get("doi", ""),
                "classification": classification,
                "has_pdf_or_html_attachment": bool(manifest),
                "previous_overall_status": previous.get("overall_status", ""),
                "previous_screening_decision": previous.get("screening_decision"),
            }
        )
        if classification.startswith("runnable"):
            runnable.append(make_runnable_item(row, previous, manifest, classification))
    runnable.sort(
        key=lambda item: (
            int(item.get("priority_score", 0)),
            bool(item.get("has_pdf_or_html_attachment")),
            item.get("previous_screening_decision") == "include_for_fulltext",
            int(item.get("environment_score", 0)),
            int(item.get("transformation_score", 0)),
        ),
        reverse=True,
    )
    write_jsonl(output_queue, runnable)
    write_audit_report(audit_report, metadata, manifest_rows, runnable, classified, blocked_rescanned, blocked_unblocked)
    return DiscoveryResult(
        library_total_sources=len(metadata),
        runnable_sources=runnable,
        classified_rows=classified,
        blocked_sources_rescanned=blocked_rescanned,
        blocked_sources_unblocked=blocked_unblocked,
        new_attachments_found=blocked_unblocked,
        completed_sources=completed,
        manual_sources=manual,
        blocked_sources=blocked,
    )


def write_audit_report(
    path: Path,
    metadata: list[dict[str, Any]],
    manifest_rows: list[dict[str, Any]],
    runnable: list[dict[str, Any]],
    classified: list[dict[str, Any]],
    blocked_rescanned: int,
    blocked_unblocked: int,
) -> None:
    counts: dict[str, int] = {}
    for row in classified:
        key = str(row.get("classification", "unknown"))
        counts[key] = counts.get(key, 0) + 1
    lines = [
        "# Stage 2.7 Runnable Source Audit",
        "",
        f"library_total_sources = {len(metadata)}",
        f"sources_with_pdf_or_html_attachment = {len(manifest_rows)}",
        f"runnable_sources_discovered = {len(runnable)}",
        f"blocked_sources_rescanned = {blocked_rescanned}",
        f"blocked_sources_unblocked = {blocked_unblocked}",
        f"new_attachments_found = {blocked_unblocked}",
    ]
    for key in sorted(counts):
        lines.append(f"classified_{key} = {counts[key]}")
    lines.extend(["", "| rank | source_id | class | score | attachment | previous | title | reasons |", "| ---: | --- | --- | ---: | --- | --- | --- | --- |"])
    for rank, row in enumerate(runnable[:75], start=1):
        title = " ".join(str(row.get("title", "")).split()).replace("|", "/")
        if len(title) > 90:
            title = title[:87].rstrip() + "..."
        reasons = ",".join(str(item) for item in row.get("priority_reasons", [])[:6]).replace("|", "/")
        lines.append(
            f"| {rank} | {row.get('source_id', '')} | {row.get('runnable_classification', '')} | "
            f"{row.get('priority_score', 0)} | {str(bool(row.get('has_pdf_or_html_attachment'))).lower()} | "
            f"{row.get('previous_overall_status', '')} | {title} | {reasons} |"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
