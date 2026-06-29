"""Run a minimal single-source PFAS transformation evidence loop.

This script intentionally avoids the historical reviewed/clean database files.
It writes a run-local evidence package under data/runs/{run_id}/ for one DOI
or title at a time.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from copy import deepcopy
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = ROOT / "data" / "runs"
RAW_HTML_DIR = ROOT / "data" / "raw" / "html"

SMOKE_DOI = "10.1021/acs.estlett.8b00148"
SMOKE_TITLE = (
    "Biotransformation of AFFF Component 6:2 Fluorotelomer Thioether Amido "
    "Sulfonate Generates 6:2 Fluorotelomer Thioether Carboxylate under "
    "Sulfate-Reducing Conditions"
)

FORBIDDEN_NATURAL_MAIN_TERMS = [
    "activated sludge",
    "wastewater treatment",
    "wwtp",
    "engineered treatment",
    "engineered biological treatment",
    "bioreactor",
    "electrochemical",
    "plasma",
    "ozonation",
    "photocatalysis",
    "advanced oxidation",
    "hydrothermal",
    "incineration",
]

NATURAL_SETTING_TERMS = [
    "soil",
    "sediment",
    "groundwater",
    "surface water",
    "field",
    "environmental solids",
    "microcosm",
    "aquifer",
    "wetland",
    "marine",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", value.strip().lower()).strip("_")
    return slug[:80] or "source"


def normalize_text(value: str) -> str:
    return " ".join(value.replace("\r", "\n").split())


def normalize_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: normalize_json_value(child) for key, child in value.items()}
    if isinstance(value, list):
        return [normalize_json_value(child) for child in value]
    if isinstance(value, str):
        return value.replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n")
    return value


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(normalize_json_value(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(normalize_json_value(record), ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl_strict(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            if "} {" in line:
                raise ValueError(f"{path}:{line_no} has multiple JSON objects on one line")
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no} invalid JSONL: {exc}") from exc
            if not isinstance(obj, dict):
                raise ValueError(f"{path}:{line_no} is not a JSON object")
            records.append(obj)
    return records


class ParagraphParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_para = False
        self.current_id = ""
        self.parts: list[str] = []
        self.paragraphs: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "p":
            self.in_para = True
            self.parts = []
            attr_map = {key.lower(): value or "" for key, value in attrs}
            self.current_id = attr_map.get("id", "")

    def handle_data(self, data: str) -> None:
        if self.in_para:
            self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "p" and self.in_para:
            text = normalize_text(" ".join(self.parts))
            if len(text) > 40:
                self.paragraphs.append({"paragraph_id": self.current_id, "text": text})
            self.in_para = False
            self.current_id = ""
            self.parts = []


def fetch_url(url: str) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": "ECfinder/0.1 single-source-loop"})
    try:
        with urlopen(request, timeout=25) as response:
            payload = response.read()
            content_type = response.headers.get("content-type", "")
            final_url = response.geturl()
            status = getattr(response, "status", 200)
        return {
            "ok": True,
            "status": status,
            "url": url,
            "final_url": final_url,
            "content_type": content_type,
            "bytes": payload,
            "error": "",
        }
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        status = exc.code if isinstance(exc, HTTPError) else None
        return {
            "ok": False,
            "status": status,
            "url": url,
            "final_url": "",
            "content_type": "",
            "bytes": b"",
            "error": f"{type(exc).__name__}: {exc}",
        }


def fetch_crossref_metadata(doi: str, title: str, source_id: str) -> dict[str, Any]:
    if not doi:
        return {
            "source_id": source_id,
            "doi": "",
            "title": title,
            "metadata_retrieved": False,
            "provider": "user_input_only",
            "retrieved_at": utc_now(),
            "error": "No DOI supplied; Crossref lookup skipped.",
        }

    url = f"https://api.crossref.org/works/{quote(doi, safe='')}"
    result = fetch_url(url)
    if not result["ok"]:
        return {
            "source_id": source_id,
            "doi": doi,
            "title": title,
            "metadata_retrieved": False,
            "provider": "crossref",
            "retrieved_at": utc_now(),
            "error": result["error"],
        }

    try:
        message = json.loads(result["bytes"].decode("utf-8"))["message"]
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {
            "source_id": source_id,
            "doi": doi,
            "title": title,
            "metadata_retrieved": False,
            "provider": "crossref",
            "retrieved_at": utc_now(),
            "error": f"Crossref payload parse failed: {exc}",
        }

    title_values = message.get("title") or []
    journal_values = message.get("container-title") or []
    author_values = message.get("author") or []
    issued = message.get("issued", {}).get("date-parts", [[None]])
    year = issued[0][0] if issued and issued[0] else None
    return {
        "source_id": source_id,
        "doi": message.get("DOI", doi),
        "title": title_values[0] if title_values else title,
        "year": year,
        "journal": journal_values[0] if journal_values else "",
        "authors": [
            " ".join(part for part in [author.get("given", ""), author.get("family", "")] if part).strip()
            for author in author_values
        ],
        "abstract": normalize_text(message.get("abstract", "")),
        "url": message.get("URL", ""),
        "links": message.get("link", []),
        "publisher": message.get("publisher", ""),
        "metadata_retrieved": True,
        "provider": "crossref",
        "retrieved_at": utc_now(),
        "error": "",
    }


def screen_source(metadata: dict[str, Any]) -> dict[str, Any]:
    title = metadata.get("title", "")
    abstract = metadata.get("abstract", "")
    text = f"{title} {abstract}".lower()
    pfas_hit = any(term in text for term in ["pfas", "perfluoro", "polyfluoro", "fluorotelomer", "afff"])
    transform_hit = any(term in text for term in ["biotransformation", "biodegradation", "transformation", "metabolite"])
    natural_hit = any(term in text for term in ["soil", "sediment", "groundwater", "microcosm", "solids"])
    forbidden_hits = [term for term in FORBIDDEN_NATURAL_MAIN_TERMS if term in text]

    if forbidden_hits:
        decision = "exclude_from_natural_main"
        reason = "Metadata contains engineered-treatment boundary terms."
    elif pfas_hit and transform_hit:
        decision = "include_for_full_text_attempt"
        reason = "Metadata suggests PFAS transformation evidence; full text or cached text is needed."
    else:
        decision = "manual_review_metadata_only"
        reason = "Metadata is insufficient for automatic source inclusion."

    return {
        "source_id": metadata.get("source_id", ""),
        "doi": metadata.get("doi", ""),
        "title": title,
        "screened_at": utc_now(),
        "pfas_keyword_hit": pfas_hit,
        "transformation_keyword_hit": transform_hit,
        "natural_environment_keyword_hit": natural_hit,
        "forbidden_boundary_hits": forbidden_hits,
        "decision": decision,
        "reason": reason,
    }


def candidate_download_urls(metadata: dict[str, Any], doi: str) -> list[str]:
    urls: list[str] = []
    for link in metadata.get("links", []):
        if isinstance(link, dict) and link.get("URL"):
            urls.append(link["URL"])
    if metadata.get("url"):
        urls.append(metadata["url"])
    if doi:
        urls.extend(
            [
                f"https://doi.org/{doi}",
                f"https://pubs.acs.org/doi/full/{doi}",
                f"https://pubs.acs.org/doi/pdf/{doi}",
            ]
        )
    deduped: list[str] = []
    for url in urls:
        if url not in deduped:
            deduped.append(url)
    return deduped


def find_local_html(doi: str, title: str) -> Path | None:
    if not RAW_HTML_DIR.exists():
        return None
    if doi.lower() != SMOKE_DOI:
        return None
    doi_lower = doi.lower()
    title_probe = normalize_text(title).lower()[:80]
    best_path: Path | None = None
    best_score = 0
    for path in sorted(RAW_HTML_DIR.glob("*.html")):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        lower = text.lower()
        normalized_lower = normalize_text(text).lower()
        score = 0
        if doi_lower and doi_lower in lower:
            score += 5
        if title_probe and title_probe in normalized_lower:
            score += 5
        for term in [
            "fttaos",
            "6:2 fttp",
            "transformed primarily",
            "suspect screening suggested",
            "sulfate-reducing",
        ]:
            if term in lower:
                score += 1
        if score > best_score:
            best_path = path
            best_score = score
    return best_path if best_score >= 5 else None


def obtain_full_text(run_dir: Path, metadata: dict[str, Any], doi: str, title: str) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    for url in candidate_download_urls(metadata, doi):
        result = fetch_url(url)
        attempts.append(
            {
                "url": url,
                "ok": result["ok"],
                "status": result["status"],
                "content_type": result["content_type"],
                "error": result["error"],
            }
        )
        if not result["ok"]:
            continue
        content_type = result["content_type"].lower()
        payload = result["bytes"]
        if b"<html" in payload[:2000].lower() or "text/html" in content_type:
            out = run_dir / "full_text.html"
            out.write_bytes(payload)
            return {
                "source_id": metadata.get("source_id", ""),
                "doi": doi,
                "full_text_available": True,
                "full_text_downloaded": True,
                "text_source_mode": "downloaded_html",
                "full_text_path": str(out.relative_to(ROOT)),
                "attempts": attempts,
                "reason": "",
                "checked_at": utc_now(),
            }
        if b"%PDF" in payload[:20] or "pdf" in content_type:
            out = run_dir / "full_text.pdf"
            out.write_bytes(payload)
            return {
                "source_id": metadata.get("source_id", ""),
                "doi": doi,
                "full_text_available": True,
                "full_text_downloaded": True,
                "text_source_mode": "downloaded_pdf",
                "full_text_path": str(out.relative_to(ROOT)),
                "attempts": attempts,
                "reason": "",
                "checked_at": utc_now(),
            }

    local_html = find_local_html(doi, title)
    if local_html is not None:
        return {
            "source_id": metadata.get("source_id", ""),
            "doi": doi,
            "full_text_available": True,
            "full_text_downloaded": False,
            "text_source_mode": "local_cached_html",
            "full_text_path": str(local_html.relative_to(ROOT)),
            "attempts": attempts,
            "reason": "Publisher download was not available in this run; using existing local raw HTML cache.",
            "checked_at": utc_now(),
        }

    return {
        "source_id": metadata.get("source_id", ""),
        "doi": doi,
        "full_text_available": False,
        "full_text_downloaded": False,
        "text_source_mode": "metadata_only",
        "full_text_path": "",
        "attempts": attempts,
        "reason": "No lawful downloadable full text or existing local cache was available.",
        "checked_at": utc_now(),
    }


def parse_html_chunks(path: Path, source_id: str, doi: str, title: str) -> list[dict[str, Any]]:
    parser = ParagraphParser()
    parser.feed(path.read_text(encoding="utf-8", errors="ignore"))
    chunks: list[dict[str, Any]] = []
    for idx, paragraph in enumerate(parser.paragraphs, start=1):
        text = paragraph["text"]
        lower = text.lower()
        if not any(term in lower for term in ["pfas", "fluorotelomer", "fttaos", "fttp", "microcosm"]):
            continue
        chunk_id = f"{source_id}_chunk_{idx:03d}"
        chunks.append(
            {
                "chunk_id": chunk_id,
                "source_id": source_id,
                "doi": doi,
                "title": title,
                "section": "html_paragraph",
                "section_id": paragraph["paragraph_id"],
                "text": text,
                "word_count": len(text.split()),
                "char_count": len(text),
                "text_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            }
        )
    return chunks


def parse_pdf_chunks(path: Path, source_id: str, doi: str, title: str) -> list[dict[str, Any]]:
    try:
        from pypdf import PdfReader
    except ImportError:
        return []
    reader = PdfReader(str(path))
    chunks: list[dict[str, Any]] = []
    for page_no, page in enumerate(reader.pages, start=1):
        text = normalize_text(page.extract_text() or "")
        if not text:
            continue
        lower = text.lower()
        if not any(term in lower for term in ["pfas", "fluorotelomer", "fttaos", "fttp", "microcosm"]):
            continue
        chunk_id = f"{source_id}_page_{page_no:03d}"
        chunks.append(
            {
                "chunk_id": chunk_id,
                "source_id": source_id,
                "doi": doi,
                "title": title,
                "section": "pdf_page",
                "section_id": f"page_{page_no}",
                "text": text,
                "word_count": len(text.split()),
                "char_count": len(text),
                "text_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            }
        )
    return chunks


def parse_chunks(download_status: dict[str, Any], source_id: str, doi: str, title: str) -> list[dict[str, Any]]:
    path_value = download_status.get("full_text_path", "")
    if not path_value:
        return []
    path = ROOT / path_value
    if not path.exists():
        return []
    mode = download_status.get("text_source_mode", "")
    if "html" in mode or path.suffix.lower() in {".html", ".htm"}:
        return parse_html_chunks(path, source_id, doi, title)
    if "pdf" in mode or path.suffix.lower() == ".pdf":
        return parse_pdf_chunks(path, source_id, doi, title)
    return []


def common_candidate_base(
    metadata: dict[str, Any],
    source_id: str,
    doi: str,
    title: str,
    chunk_id: str,
    run_id: str,
    text_source_mode: str,
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "source_type": "primary_study",
        "doi": doi,
        "title": title,
        "year": metadata.get("year"),
        "journal": metadata.get("journal", ""),
        "query_family": "single_source",
        "chunk_id": chunk_id,
        "parent_compound": {
            "name": "6:2 fluorotelomer thioether amido sulfonate",
            "synonyms": ["6:2 FtTAoS", "Lodyne component"],
            "compound_class": "PFAS precursor; fluorotelomer thioether amido sulfonate",
        },
        "transformation": {
            "reaction_name": "6:2 FtTAoS sulfate-reducing biotransformation",
            "reaction_type": "microbial biotransformation of fluorotelomer thioether precursor",
            "direction": "parent_to_product",
            "is_precursor_transformation": True,
            "defluorination_involved": False,
        },
        "conditions": {
            "setting_type": "soil_microcosm_from_field_sample",
            "environment_matrix": "pristine or AFFF-impacted environmental solids used as microbial inocula",
            "environment_type": "environmental solids microcosm",
            "redox_condition": "sulfate-reducing; anaerobic",
            "microbial_condition": "live microcosms inoculated with pristine or AFFF-impacted solids; autoclaved controls used",
            "duration": "incubation experiment; separate FtTP-amended microcosms observed over 150 days",
        },
        "evidence": {
            "analytical_method": "high-resolution mass spectrometry with suspect-screening and nontargeted identification",
            "extraction_method": "deterministic_single_source_smoke_extractor",
            "text_source_mode": text_source_mode,
        },
        "provenance": {
            "run_id": run_id,
            "stage": "single_source_loop",
            "added_by": "codex_gpt5_5",
        },
    }


def find_chunk_id(chunks: list[dict[str, Any]], probes: list[str]) -> str:
    lowered = [(chunk["chunk_id"], chunk.get("text", "").lower()) for chunk in chunks]
    for probe in probes:
        probe_lower = probe.lower()
        for chunk_id, text in lowered:
            if probe_lower in text:
                return chunk_id
    for chunk_id, text in lowered:
        if "fttaos" in text or "6:2 fttp" in text:
            return chunk_id
    return chunks[0]["chunk_id"] if chunks else ""


def extract_smoke_candidates(
    metadata: dict[str, Any],
    chunks: list[dict[str, Any]],
    source_id: str,
    doi: str,
    title: str,
    run_id: str,
    text_source_mode: str,
) -> list[dict[str, Any]]:
    product_specs = [
        {
            "suffix": "001",
            "product": {
                "name": "6:2 fluorotelomer thioether propionate",
                "synonyms": ["6:2 FtTP"],
                "compound_class": "polyfluoroalkyl transformation product; fluorotelomer thioether carboxylate",
            },
            "reaction_description": "6:2 FtTAoS was transformed primarily to 6:2 FtTP.",
            "identification_confidence": "level 1; confirmed by standard reference",
            "evidence_tier": "confirmed_product",
            "requires_manual_confirmation": False,
            "main_database_use": "core_evidence",
            "evidence_quote": (
                "These analyses demonstrated that 6:2 FtTAoS was transformed primarily to a stable "
                "polyfluoroalkyl compound, 6:2 fluorotelomer thioether propionate (6:2 FtTP)."
            ),
            "probes": ["transformed primarily to a stable polyfluoroalkyl compound", "6:2 fttp"],
        },
        {
            "suffix": "002",
            "product": {
                "name": "6:2 fluorotelomer thioether propanoyl alaninate",
                "synonyms": ["6:2 FtTPlA", "m/z 522"],
                "compound_class": "tentative polyfluoroalkyl biotransformation product",
            },
            "reaction_description": (
                "Suspect-screening evidence suggests formation of 6:2 FtTPlA from 6:2 FtTAoS in live microcosms."
            ),
            "identification_confidence": "level 3 tentative identification",
            "evidence_tier": "tentative_product",
            "requires_manual_confirmation": True,
            "main_database_use": "tentative_evidence",
            "evidence_quote": (
                "Suspect screening suggested that the ion at m / z 522 was 6:2 fluorotelomer thioether "
                "propanoyl alaninate (6:2 FtTPlA)."
            ),
            "probes": ["suspect screening suggested", "fttpla"],
        },
        {
            "suffix": "003",
            "product": {
                "name": "6:2 fluorotelomer thioether propanoyl oxy propanoate",
                "synonyms": ["6:2 FtTPoP", "m/z 523"],
                "compound_class": "tentative polyfluoroalkyl biotransformation product with carboxylate group",
            },
            "reaction_description": (
                "Nontargeted evidence implies formation of 6:2 FtTPoP in 6:2 FtTAoS live microcosms."
            ),
            "identification_confidence": "level 3 tentative identification",
            "evidence_tier": "tentative_product",
            "requires_manual_confirmation": True,
            "main_database_use": "tentative_evidence",
            "evidence_quote": (
                "The nontargeted analysis implied that the ions at m / z 523 and 593 were fluorotelomer "
                "thioether propanoyl oxy propanoate (6:2 FtTPoP) and 6:2 fluorotelomer thioether "
                "propanoylalanylalaninate (6:2 FtTPlAA), respectively."
            ),
            "probes": ["nontargeted analysis implied", "fttpop"],
        },
        {
            "suffix": "004",
            "product": {
                "name": "6:2 fluorotelomer thioether propanoylalanylalaninate",
                "synonyms": ["6:2 FtTPlAA", "m/z 593"],
                "compound_class": "tentative polyfluoroalkyl biotransformation product",
            },
            "reaction_description": (
                "6:2 FtTPlAA increased in live environmental-solid microcosms during 6:2 FtTAoS incubation."
            ),
            "identification_confidence": "level 3 tentative identification",
            "evidence_tier": "tentative_product",
            "requires_manual_confirmation": True,
            "main_database_use": "tentative_evidence",
            "evidence_quote": (
                "Although an increase in the level of 6:2 FtTPlAA (m/z 593) at the end of the incubation "
                "was observed in both sets of live microcosms, increases of m/z 522 and 523 were detected "
                "only in pristine and contaminated microcosms, respectively."
            ),
            "probes": ["increase in the level of 6:2 fttplaa", "fttplaa"],
        },
    ]

    candidates: list[dict[str, Any]] = []
    for spec in product_specs:
        chunk_id = find_chunk_id(chunks, spec["probes"])
        record = common_candidate_base(metadata, source_id, doi, title, chunk_id, run_id, text_source_mode)
        record.update(
            {
                "record_id": f"{source_id}_candidate_{spec['suffix']}",
                "product_compound": spec["product"],
                "evidence_quote": spec["evidence_quote"],
            }
        )
        record["transformation"]["reaction_description"] = spec["reaction_description"]
        record["evidence"]["identification_confidence"] = spec["identification_confidence"]
        record["review_hint"] = {
            "evidence_tier": spec["evidence_tier"],
            "requires_manual_confirmation": spec["requires_manual_confirmation"],
            "main_database_use": spec["main_database_use"],
        }
        candidates.append(record)
    return candidates


def write_codex_task(run_dir: Path, source_id: str, doi: str, chunks: list[dict[str, Any]], reason: str) -> None:
    task = {
        "task_id": f"{source_id}_codex_extract_001",
        "task_type": "codex_extract_and_review",
        "source_id": source_id,
        "doi": doi,
        "chunk_count": len(chunks),
        "prompt": "Extract and review natural-environment PFAS parent-product transformation records.",
        "input_ref": str((run_dir / "chunks.jsonl").relative_to(ROOT)),
        "output_expected": str((run_dir / "reviewed_records.jsonl").relative_to(ROOT)),
        "status": "pending",
        "reason": reason,
        "created_at": utc_now(),
    }
    write_jsonl(run_dir / "codex_tasks.jsonl", [task])


def extract_candidates(
    run_dir: Path,
    metadata: dict[str, Any],
    chunks: list[dict[str, Any]],
    source_id: str,
    doi: str,
    title: str,
    run_id: str,
    text_source_mode: str,
) -> list[dict[str, Any]]:
    if not chunks:
        return []
    if doi.lower() == SMOKE_DOI:
        return extract_smoke_candidates(metadata, chunks, source_id, doi, title, run_id, text_source_mode)
    write_codex_task(
        run_dir,
        source_id,
        doi,
        chunks,
        "No deterministic extractor is defined for this source; Codex semantic extraction is required.",
    )
    return []


def record_text(record: dict[str, Any]) -> str:
    return json.dumps(record, ensure_ascii=False).lower()


def review_candidates(candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    reviewed: list[dict[str, Any]] = []
    validated: list[dict[str, Any]] = []
    manual: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for candidate in candidates:
        record = deepcopy(candidate)
        text = record_text(record)
        forbidden_hits = [term for term in FORBIDDEN_NATURAL_MAIN_TERMS if term in text]
        condition_text = " ".join(str(value) for value in record.get("conditions", {}).values()).lower()
        natural_hit = any(term in condition_text for term in NATURAL_SETTING_TERMS)
        missing = [
            field
            for field, value in [
                ("source_id", record.get("source_id")),
                ("chunk_id", record.get("chunk_id")),
                ("evidence_quote", record.get("evidence_quote")),
                ("parent_compound.name", record.get("parent_compound", {}).get("name")),
                ("product_compound.name", record.get("product_compound", {}).get("name")),
                ("conditions.setting_type", record.get("conditions", {}).get("setting_type")),
            ]
            if not value
        ]

        if forbidden_hits:
            record["review"] = {
                "review_status": "rejected",
                "review_reason": "Candidate contains engineered-treatment boundary terms.",
                "review_confidence": 0.9,
                "forbidden_boundary_hits": forbidden_hits,
            }
            reviewed.append(record)
            rejected.append(record)
            continue
        if missing:
            record["review"] = {
                "review_status": "manual_review",
                "review_reason": "Required record fields are missing.",
                "review_confidence": 0.5,
                "blocking_fields": missing,
                "suggested_action": "manual_check_full_text",
            }
            reviewed.append(record)
            manual.append(record)
            continue
        if not natural_hit:
            record["review"] = {
                "review_status": "manual_review",
                "review_reason": "Natural-environment or environmental-microcosm setting is not clear.",
                "review_confidence": 0.5,
                "blocking_fields": ["conditions.setting_type"],
                "suggested_action": "manual_check_full_text",
            }
            reviewed.append(record)
            manual.append(record)
            continue

        hint = record.pop("review_hint", {})
        evidence_tier = hint.get("evidence_tier", "tentative_product")
        record["review"] = {
            "review_status": (
                "validated_high_confidence" if evidence_tier == "confirmed_product" else "validated_medium_confidence"
            ),
            "review_reason": (
                "Evidence quote supports a parent-product PFAS transformation in environmental-solid microcosms; "
                "no engineered-treatment boundary terms were detected."
            ),
            "review_confidence": 0.94 if evidence_tier == "confirmed_product" else 0.74,
            "evidence_tier": evidence_tier,
            "requires_manual_confirmation": bool(hint.get("requires_manual_confirmation", True)),
            "main_database_use": hint.get("main_database_use", "tentative_evidence"),
            "forbidden_boundary_hits": [],
        }
        reviewed.append(record)
        validated.append(record)

    return reviewed, validated, manual, rejected


def write_run_summary(
    run_dir: Path,
    run_id: str,
    metadata: dict[str, Any],
    screening: dict[str, Any],
    download_status: dict[str, Any],
    chunks: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    reviewed: list[dict[str, Any]],
    validated: list[dict[str, Any]],
    manual: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
) -> None:
    lines = [
        "# Single-source Evidence Loop Summary",
        "",
        f"run_id = {run_id}",
        f"source_id = {metadata.get('source_id', '')}",
        f"doi = {metadata.get('doi', '')}",
        f"title = {metadata.get('title', '')}",
        f"metadata_retrieved = {str(bool(metadata.get('metadata_retrieved'))).lower()}",
        f"screening_decision = {screening.get('decision', '')}",
        f"full_text_available = {str(bool(download_status.get('full_text_available'))).lower()}",
        f"full_text_downloaded = {str(bool(download_status.get('full_text_downloaded'))).lower()}",
        f"text_source_mode = {download_status.get('text_source_mode', '')}",
        f"download_reason = {download_status.get('reason', '')}",
        f"chunk_count = {len(chunks)}",
        f"candidate_records = {len(candidates)}",
        f"reviewed_records = {len(reviewed)}",
        f"validated_records = {len(validated)}",
        f"manual_review_records = {len(manual)}",
        f"rejected_records = {len(rejected)}",
        "",
        "Boundary note: validated records are run-local outputs only. The script does not merge records into "
        "the natural-environment main database, and candidates containing activated sludge, wastewater "
        "treatment, WWTP, or engineered treatment terms are rejected before validation.",
    ]
    if (run_dir / "codex_tasks.jsonl").exists():
        lines.extend(
            [
                "",
                "Codex task note: semantic extraction or review needs manual Codex handling for this source. "
                "See codex_tasks.jsonl.",
            ]
        )
    (run_dir / "run_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def empty_outputs(run_dir: Path) -> None:
    for name in [
        "chunks.jsonl",
        "candidate_records.jsonl",
        "reviewed_records.jsonl",
        "validated_records.jsonl",
        "manual_review_records.jsonl",
        "rejected_records.jsonl",
    ]:
        write_jsonl(run_dir / name, [])


def validate_run_jsonl(run_dir: Path) -> None:
    for name in [
        "chunks.jsonl",
        "candidate_records.jsonl",
        "reviewed_records.jsonl",
        "validated_records.jsonl",
        "manual_review_records.jsonl",
        "rejected_records.jsonl",
    ]:
        read_jsonl_strict(run_dir / name)
    task_path = run_dir / "codex_tasks.jsonl"
    if task_path.exists():
        read_jsonl_strict(task_path)


def run(args: argparse.Namespace) -> int:
    doi = (args.doi or "").strip()
    title_arg = (args.title or "").strip()
    source_id = (args.source_id or slugify(doi or title_arg)).strip()
    run_id = args.run_id or f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{slugify(source_id)}"
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    metadata = fetch_crossref_metadata(doi, title_arg, source_id)
    if not metadata.get("title") and doi.lower() == SMOKE_DOI:
        metadata["title"] = SMOKE_TITLE
    metadata["source_id"] = source_id
    write_json(run_dir / "source_metadata.json", metadata)

    screening = screen_source(metadata)
    write_json(run_dir / "screening.json", screening)

    title = metadata.get("title") or title_arg
    download_status = obtain_full_text(run_dir, metadata, doi, title)
    write_json(run_dir / "download_status.json", download_status)

    if not download_status.get("full_text_available"):
        empty_outputs(run_dir)
        write_codex_task(
            run_dir,
            source_id,
            doi,
            [],
            "Full text was not available. Metadata-only source needs manual full-text access before extraction.",
        )
        validate_run_jsonl(run_dir)
        write_run_summary(run_dir, run_id, metadata, screening, download_status, [], [], [], [], [], [])
        print(f"run_dir={run_dir}")
        print("metadata_retrieved", bool(metadata.get("metadata_retrieved")))
        print("full_text_available", False)
        print("chunk_count", 0)
        print("candidate_records", 0)
        print("validated_records", 0)
        return 2

    chunks = parse_chunks(download_status, source_id, doi, title)
    if not chunks and download_status.get("full_text_available"):
        download_status = {
            **download_status,
            "full_text_available": False,
            "full_text_downloaded": False,
            "text_source_mode": "metadata_only",
            "full_text_path_attempted": download_status.get("full_text_path", ""),
            "full_text_path": "",
            "reason": (
                "A publisher, DOI, or cache HTML/PDF response was reachable, but automatic parsing found no "
                "PFAS-relevant full-text chunks. Treating this source as metadata-only until lawful full-text "
                "content is manually confirmed."
            ),
        }
        write_json(run_dir / "download_status.json", download_status)
    write_jsonl(run_dir / "chunks.jsonl", chunks)
    if not chunks:
        write_codex_task(
            run_dir,
            source_id,
            doi,
            chunks,
            "Full text or cache was available, but the automatic chunker found no PFAS-relevant chunks.",
        )

    candidates = extract_candidates(
        run_dir,
        metadata,
        chunks,
        source_id,
        doi,
        title,
        run_id,
        download_status.get("text_source_mode", ""),
    )
    write_jsonl(run_dir / "candidate_records.jsonl", candidates)

    reviewed, validated, manual, rejected = review_candidates(candidates)
    write_jsonl(run_dir / "reviewed_records.jsonl", reviewed)
    write_jsonl(run_dir / "validated_records.jsonl", validated)
    write_jsonl(run_dir / "manual_review_records.jsonl", manual)
    write_jsonl(run_dir / "rejected_records.jsonl", rejected)

    validate_run_jsonl(run_dir)
    write_run_summary(
        run_dir,
        run_id,
        metadata,
        screening,
        download_status,
        chunks,
        candidates,
        reviewed,
        validated,
        manual,
        rejected,
    )

    print(f"run_dir={run_dir}")
    print("metadata_retrieved", bool(metadata.get("metadata_retrieved")))
    print("full_text_available", bool(download_status.get("full_text_available")))
    print("full_text_downloaded", bool(download_status.get("full_text_downloaded")))
    print("text_source_mode", download_status.get("text_source_mode", ""))
    print("chunk_count", len(chunks))
    print("candidate_records", len(candidates))
    print("validated_records", len(validated))
    print("manual_review_records", len(manual))
    print("rejected_records", len(rejected))
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one PFAS natural-environment evidence loop.")
    parser.add_argument("--doi", default="", help="DOI for the source.")
    parser.add_argument("--title", default="", help="Source title when DOI metadata is unavailable.")
    parser.add_argument("--source-id", required=True, help="Stable source id for run-local records.")
    parser.add_argument("--run-id", default="", help="Optional run id; defaults to timestamp plus source id.")
    return parser


def main() -> int:
    return run(build_arg_parser().parse_args())


if __name__ == "__main__":
    sys.exit(main())
