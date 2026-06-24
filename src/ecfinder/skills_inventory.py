"""Inventory reusable local skills, tools, and prior modules for ECfinder."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class InventoryItem:
    category: str
    name: str
    location: str
    input: str
    output: str
    reusable: str
    ecfinder_call: str
    risks_or_limits: str


def _exists(path: str) -> bool:
    return Path(path).exists()


def build_inventory() -> list[InventoryItem]:
    codex_home = Path.home() / ".codex"
    runtime = Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies"
    docs = Path.home() / "Documents"

    items = [
        InventoryItem(
            "literature_search",
            "nature-academic-search",
            str(codex_home / "skills" / "nature-academic-search"),
            "Topic, Boolean query, DOI/PMID/arXiv IDs, optional source choices.",
            "Structured paper metadata, DOI/PMID/arXiv IDs, citations, deduplicated search results.",
            "yes",
            "Wrap source routing and dedup rules in src/ecfinder/search; prefer T1 CrossRef/PubMed/OpenAlex fallback.",
            "MCP search tools are not exposed in this session; standalone fallback should use public APIs and record failures.",
        ),
        InventoryItem(
            "metadata_lookup",
            "nature-academic-search format-converter and DOI tools",
            str(codex_home / "skills" / "nature-academic-search" / "scripts"),
            "DOI, PMID, arXiv ID, or title.",
            "RIS/BibTeX/NBIB-style metadata or formatted citation.",
            "partial",
            "Use DOI as primary key; fallback to normalized title plus first author.",
            "Scripts are external to this repo; use wrappers rather than modifying skill code.",
        ),
        InventoryItem(
            "pdf_download",
            "nature-reader DOI/arXiv source handling",
            str(codex_home / "skills" / "nature-reader"),
            "DOI, arXiv URL, publisher landing page, or known PDF URL.",
            "Resolved lawful PDF/HTML source and source map.",
            "partial",
            "Use as retrieval design reference; ECfinder downloader stores only local raw files and source hashes.",
            "Do not bypass paywalls; copyright PDFs must remain ignored by Git.",
        ),
        InventoryItem(
            "html_fulltext_fallback",
            "nature-reader html fragment",
            str(codex_home / "skills" / "nature-reader" / "static" / "fragments" / "source"),
            "Publisher/preprint HTML page.",
            "Section-aware extracted text with source anchors.",
            "partial",
            "Implement src/ecfinder/parse/html_parser.py with section and anchor preservation.",
            "Publisher HTML varies; JavaScript-heavy pages may need browser automation later.",
        ),
        InventoryItem(
            "pdf_parse",
            "pdf skill plus bundled pdfplumber/pypdf",
            str(Path.home() / ".codex" / "plugins" / "cache" / "openai-primary-runtime" / "pdf"),
            "Local PDF file path.",
            "Page text, page count, rendered-page QA assets when needed.",
            "yes",
            "Use pdfplumber first, pypdf as fallback; store page numbers and source hashes.",
            "Scanned PDFs need OCR; bundled runtime exposes pdfinfo/pdftoppm but no OCR was confirmed.",
        ),
        InventoryItem(
            "table_extraction",
            "pdfplumber and pandas",
            str(runtime / "python"),
            "PDF pages or HTML tables.",
            "Row-oriented table records with page/table labels.",
            "yes",
            "Use src/ecfinder/parse/table_parser.py; preserve table_id and page.",
            "Complex scientific tables may require manual review or model-assisted cleanup.",
        ),
        InventoryItem(
            "llm_screening",
            "prompt wrapper",
            "prompts/screen_title_abstract.md",
            "Title, abstract, metadata.",
            "include/exclude decision, reason, confidence.",
            "new_wrapper",
            "Implement deterministic prompt contract and JSONL output in download.semantic_screen.",
            "Requires an LLM runtime/API not configured in this repo; dry-run rules remain available.",
        ),
        InventoryItem(
            "llm_extraction",
            "prompt wrapper",
            "prompts/extract_transformation_records.md",
            "Weighted chunk with section/page/table/figure context.",
            "Raw PFAS transformation records in JSONL.",
            "new_wrapper",
            "Implement schema-first JSON parsing and provenance checks in extract.llm_extractor.",
            "LLM may hallucinate; ReviewAgent must reject unsupported fields.",
        ),
        InventoryItem(
            "record_review",
            "rule checks plus review prompt",
            "configs/review_rules.yaml; prompts/review_transformation_records.md",
            "Raw extracted record plus source chunk.",
            "Accepted/rejected record with reasons and re-extraction requests.",
            "new_wrapper",
            "Use review.rule_checks before optional LLM review.",
            "Acceptance depends on evidence quote and natural-environment condition clarity.",
        ),
        InventoryItem(
            "chemical_name_standardization",
            "local normalizer; optional external chemistry packages",
            "src/ecfinder/extract/record_normalizer.py",
            "Parent/product names, abbreviations, formulas, CAS if present.",
            "Canonical display names, aliases, confidence flags.",
            "new_wrapper",
            "Normalize common PFAS abbreviations locally; leave external IDs nullable.",
            "RDKit and ChEMBL clients were not installed in bundled Python; avoid hard dependency.",
        ),
        InventoryItem(
            "github_commit",
            "git CLI and GitHub connector",
            "git on PATH; mcp__codex_apps__github connector",
            "Local changes, branch, repository name.",
            "Commits, branches, pushes when remote exists.",
            "partial",
            "Use local git for branch/commit; use manual GitHub creation because gh/create-repo is unavailable.",
            "GitHub CLI is not installed and connector cannot create a new repo in this session.",
        ),
        InventoryItem(
            "prior_ecmonitor_ecoscan_pfas_modules",
            "Documents/EC_MONITOR and Codex archives",
            str(docs),
            "Existing project directories and archived task text.",
            "Reusable module candidates or negative finding.",
            "no_direct_module_found",
            "Do not copy archived text; record that EC_MONITOR currently contains only .git metadata.",
            "Search found PFAS-related archived prompts and spectra files, but no reusable ECMonitor/EcoScan code module in workspace.",
        ),
    ]

    return items


def write_inventory(report_path: Path, json_path: Path) -> None:
    items = build_inventory()
    json_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps([asdict(item) for item in items], indent=2) + "\n", encoding="utf-8")
    report_path.write_text(render_markdown(items), encoding="utf-8")


def render_markdown(items: Iterable[InventoryItem]) -> str:
    lines = [
        "# Skill Inventory",
        "",
        "Checked on 2026-06-24 in the local Codex desktop environment.",
        "",
        "## Environment Summary",
        "",
        "- Current workspace before ECfinder creation: empty Git repository at `C:/Users/Administrator/Documents/pfasfinder`.",
        "- New repository path: `C:/Users/Administrator/Documents/pfasfinder/ECfinder`.",
        "- Bundled runtime includes Python, Git, Node, `pdfinfo`, and `pdftoppm`.",
        "- Confirmed bundled Python packages: `lxml`, `pdfplumber`, `pypdf`, `pandas`, `openpyxl`.",
        "- Missing in bundled Python: `requests`, `beautifulsoup4`, `pyyaml`, `rdkit`, `chembl_webresource_client`.",
        "- `gh` is not installed and no `GITHUB_TOKEN` or `GH_TOKEN` is set.",
        "",
        "## Reuse Decisions",
        "",
        "| Category | Skill / Tool | Location | Input | Output | Reuse | ECfinder call | Risks / limits |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for item in items:
        lines.append(
            "| {category} | {name} | `{location}` | {input} | {output} | {reusable} | {ecfinder_call} | {risks_or_limits} |".format(
                **asdict(item)
            )
        )
    lines.extend(
        [
            "",
            "## Conclusion",
            "",
            "ECfinder should reuse the existing academic-search routing, deduplication, and PDF parsing guidance, but implement project-local wrappers so the old skills are not modified. No reusable ECMonitor, EcoScan, or PFAS transformation-product database code module was found in the active workspace; the closest historical material is archived prompt text and spectra data, which is not copied into this repository.",
            "",
        ]
    )
    return "\n".join(lines)


def tool_presence() -> dict[str, bool]:
    return {name: shutil.which(name) is not None for name in ["git", "gh", "python", "pdfinfo", "pdftoppm"]}
