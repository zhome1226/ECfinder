"""Shared helpers for Stage 2.4j available-first Zotero ingest."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from zotero_stage2_4i_common import ROOT, normalize_doi, read_jsonl, sha256_file, write_jsonl


BATCH_DIR = ROOT / "data" / "batches"
REPORTS_DIR = ROOT / "reports"
LOCAL_ROOT = ROOT / "data" / "local_fulltext" / "stage2_4j"
AVAILABLE_MANIFEST = LOCAL_ROOT / "zotero_available_fulltext_manifest.jsonl"
AUDIT_JSONL = BATCH_DIR / "stage2_4j_zotero_scope_audit.jsonl"
SYNC_STATUS = BATCH_DIR / "stage2_4j_available_attachment_sync_status.jsonl"

QUEUE_30 = ROOT / "data" / "batches" / "stage2_4_30source_queue.jsonl"
TARGETS_12 = ROOT / "data" / "local_fulltext" / "stage2_4b" / "fulltext_manifest.jsonl"

PFAS_TERMS = [
    "pfas",
    "perfluoro",
    "polyfluoro",
    "fluorotelomer",
    "ftsa",
    "ftoh",
    "fosa",
    "fose",
    "fosaa",
    "pap",
    "dipap",
    "afff",
    "fluorinated",
    "perfluorinated",
    "polyfluorinated",
    "fluoroalkyl",
    "sulfonamide",
    "sulfonamido",
    "perfluorooctane",
    "perfluorooctanesulfonate",
    "perfluorooctanoate",
    "pfos",
    "pfoa",
    "pfhxa",
    "pfhxs",
    "pfna",
    "pfda",
    "genx",
    "ad ona",
    "sulfluramid",
]
TRANSFORMATION_TERMS = [
    "precursor",
    "biotransformation",
    "biodegradation",
    "transformation product",
    "transformation",
    "degradation product",
    "degradation",
    "metabolite",
]
ENV_TERMS = [
    "soil",
    "sediment",
    "groundwater",
    "aquifer",
    "wetland",
    "microcosm",
    "natural attenuation",
    "surface water",
    "marine",
    "estuarine",
]
DOWNGRADE_TERMS = [
    "activated sludge",
    "wastewater treatment",
    "wwtp",
    "aop",
    "plasma",
    "electrochemical",
    "photocatalysis",
    "ozonation",
    "incineration",
    "toxicity",
    "monitoring",
    "analytical method",
    "review",
]

SUPPORTED_CONTENT_TYPES = {
    "application/pdf": ("pdf", ".pdf"),
    "text/html": ("html", ".html"),
    "application/xhtml+xml": ("html", ".html"),
}
SUPPORTED_SUFFIXES = {
    ".pdf": "pdf",
    ".html": "html",
    ".htm": "html",
    ".xhtml": "html",
    ".txt": "si",
    ".md": "si",
    ".xml": "si",
}


def load_stage2_mappings() -> tuple[dict[str, str], dict[str, str]]:
    queue_rows = read_jsonl(QUEUE_30)
    target_rows = read_jsonl(TARGETS_12)
    queue = {normalize_doi(str(row.get("doi", ""))): str(row.get("source_id", "")) for row in queue_rows if row.get("doi")}
    targets = {normalize_doi(str(row.get("doi", ""))): str(row.get("source_id", "")) for row in target_rows if row.get("doi")}
    return queue, targets


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def screen_relevance(title: str, extra_text: str = "") -> tuple[str, str]:
    text = f"{title} {extra_text}".lower()
    pfas_hits = [term for term in PFAS_TERMS if term in text]
    transform_hits = [term for term in TRANSFORMATION_TERMS if term in text]
    env_hits = [term for term in ENV_TERMS if term in text]
    downgrade_hits = [term for term in DOWNGRADE_TERMS if term in text]
    if pfas_hits and transform_hits and env_hits and not downgrade_hits:
        return "high", f"PFAS terms={pfas_hits[:4]}; transformation terms={transform_hits[:4]}; environment terms={env_hits[:4]}"
    if pfas_hits and transform_hits and not downgrade_hits:
        return "high", f"PFAS transformation terms={pfas_hits[:4]}; transformation terms={transform_hits[:4]}"
    if pfas_hits:
        return "medium" if not downgrade_hits else "low", f"PFAS terms={pfas_hits[:4]}; downgrade terms={downgrade_hits[:4]}"
    if env_hits and ("fluoro" in text or "precursor" in text):
        return "medium", f"environment terms={env_hits[:4]}"
    return "low", "No PFAS transformation keyword signal."


def file_type_for_attachment(content_type: str, path: Path) -> str:
    lowered = content_type.lower()
    if lowered in SUPPORTED_CONTENT_TYPES:
        return SUPPORTED_CONTENT_TYPES[lowered][0]
    return SUPPORTED_SUFFIXES.get(path.suffix.lower(), "")


def local_destination(source_id: str, file_type: str, suffix: str) -> Path:
    if file_type == "pdf":
        return LOCAL_ROOT / "pdf" / f"{source_id}{suffix or '.pdf'}"
    if file_type == "html":
        return LOCAL_ROOT / "html" / f"{source_id}{suffix or '.html'}"
    return LOCAL_ROOT / "si" / f"{source_id}{suffix or '.txt'}"


def write_summary(path: Path, title: str, values: dict[str, Any], extra: list[str] | None = None) -> None:
    lines = [f"# {title}", ""]
    for key, value in values.items():
        rendered = str(value).lower() if isinstance(value, bool) else str(value)
        lines.append(f"{key} = {rendered}")
    if extra:
        lines.extend(["", *extra])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def parse_summary(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        if " = " in line:
            key, value = line.split(" = ", 1)
            if key.replace("_", "").isalnum():
                values[key] = value
    return values
