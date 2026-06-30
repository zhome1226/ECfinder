"""Ingest user-provided local full text for Stage 2.4b targets.

The script never downloads copyrighted content. It reads a manifest, checks for
locally supplied PDF/HTML/SI files, parses them when present, and writes run
artifacts under data/runs/stage2_4b_{source_id}/.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ecfinder.state.artifact_index import index_artifact
from ecfinder.state.common import (
    doi_hash,
    normalize_text,
    normalized_title_hash,
    read_json,
    read_jsonl,
    relative_path,
    sha256_file,
    sha256_text,
    utc_now,
    write_json,
    write_jsonl,
)
from ecfinder.state.source_registry import upsert_source


ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = ROOT / "data" / "runs"
STATE_DIR = ROOT / "data" / "state"
ARTIFACT_INDEX_PATH = STATE_DIR / "artifact_index.jsonl"
SOURCE_REGISTRY_PATH = STATE_DIR / "source_registry.jsonl"

RUN_JSONL_OUTPUTS = [
    "chunks.jsonl",
    "candidate_records.jsonl",
    "reviewed_records.jsonl",
    "validated_records.jsonl",
    "manual_review_records.jsonl",
    "rejected_records.jsonl",
]

ARTIFACT_FILES = {
    "metadata": "source_metadata.json",
    "screening": "screening.json",
    "download": "download_status.json",
    "chunks": "chunks.jsonl",
    "candidate_records": "candidate_records.jsonl",
    "reviewed_records": "reviewed_records.jsonl",
    "validated_records": "validated_records.jsonl",
    "manual_review": "manual_review_records.jsonl",
    "rejected_records": "rejected_records.jsonl",
}

SCHEMA_BY_ARTIFACT_TYPE = {
    "metadata": "schemas/source_metadata.schema.json",
    "screening": "schemas/screening_decision.schema.json",
    "download": "",
    "chunks": "schemas/chunk.schema.json",
    "candidate_records": "schemas/transformation_record.schema.json",
    "reviewed_records": "schemas/transformation_record.schema.json",
    "validated_records": "schemas/transformation_record.schema.json",
    "manual_review": "schemas/review_decision.schema.json",
    "rejected_records": "schemas/review_decision.schema.json",
}

RELEVANT_TERMS = [
    "pfas",
    "perfluoro",
    "polyfluoro",
    "fluorotelomer",
    "ftsa",
    "ftoh",
    "fosa",
    "fose",
    "fosaa",
    "pfos",
    "pfoa",
    "pap",
    "dipap",
    "sulfluramid",
    "afff",
    "biotransformation",
    "biodegradation",
    "transformation",
    "metabolite",
    "soil",
    "sediment",
    "wetland",
    "groundwater",
]


class TextBlockParser(HTMLParser):
    """Extract readable block text from locally supplied HTML."""

    BLOCK_TAGS = {"p", "li", "td", "th", "figcaption", "section", "div"}

    def __init__(self) -> None:
        super().__init__()
        self.depth = 0
        self.current_id = ""
        self.parts: list[str] = []
        self.blocks: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self.BLOCK_TAGS:
            if self.depth == 0:
                self.parts = []
                attr_map = {key.lower(): value or "" for key, value in attrs}
                self.current_id = attr_map.get("id", "") or attr_map.get("class", "")
            self.depth += 1

    def handle_data(self, data: str) -> None:
        if self.depth:
            self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() not in self.BLOCK_TAGS or not self.depth:
            return
        self.depth -= 1
        if self.depth == 0:
            text = normalize_text(" ".join(self.parts))
            if len(text) >= 60:
                self.blocks.append({"section": "html_block", "section_id": self.current_id, "text": text})
            self.current_id = ""
            self.parts = []


def resolve_local_path(path_text: str) -> Path | None:
    if not path_text:
        return None
    path = Path(path_text)
    if not path.is_absolute():
        path = ROOT / path
    return path


def stage2_4_run_dir(source_id: str) -> Path:
    return RUNS_DIR / source_id


def stage2_4b_run_dir(source_id: str) -> Path:
    return RUNS_DIR / f"stage2_4b_{source_id}"


def load_source_metadata(entry: dict[str, Any]) -> dict[str, Any]:
    source_id = str(entry.get("source_id", ""))
    cached = stage2_4_run_dir(source_id) / "source_metadata.json"
    if cached.exists():
        metadata = read_json(cached)
    else:
        metadata = {
            "source_id": source_id,
            "doi": entry.get("doi", ""),
            "title": entry.get("title", ""),
            "year": "",
            "journal": "",
            "authors": [],
            "metadata_retrieved": False,
            "provider": "stage2_4b_manifest",
        }
    metadata["source_id"] = source_id
    metadata["doi"] = metadata.get("doi") or entry.get("doi", "")
    metadata["title"] = metadata.get("title") or entry.get("title", "")
    return metadata


def load_screening(entry: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    cached = stage2_4_run_dir(str(entry.get("source_id", ""))) / "screening.json"
    if cached.exists():
        return read_json(cached)
    return {
        "source_id": entry.get("source_id", ""),
        "decision": "include_for_local_full_text_ingest",
        "reason": "High-priority Stage 2.4 manual full-text target.",
        "screened_at": utc_now(),
        "title": metadata.get("title", ""),
    }


def parse_html_blocks(path: Path) -> list[dict[str, str]]:
    parser = TextBlockParser()
    parser.feed(path.read_text(encoding="utf-8", errors="ignore"))
    return parser.blocks


def parse_text_blocks(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    blocks: list[dict[str, str]] = []
    for idx, raw_block in enumerate(text.replace("\r", "\n").split("\n\n"), start=1):
        block = normalize_text(raw_block)
        if len(block) >= 60:
            blocks.append({"section": "text_block", "section_id": f"block_{idx:03d}", "text": block})
    return blocks


def parse_pdf_blocks(path: Path) -> tuple[list[dict[str, str]], str]:
    try:
        from pypdf import PdfReader
    except ImportError:
        return [], "pypdf is not installed; PDF text extraction skipped."
    reader = PdfReader(str(path))
    blocks: list[dict[str, str]] = []
    for page_no, page in enumerate(reader.pages, start=1):
        text = normalize_text(page.extract_text() or "")
        if len(text) >= 60:
            blocks.append({"section": "pdf_page", "section_id": f"page_{page_no}", "text": text})
    return blocks, ""


def parse_local_file(entry: dict[str, Any], path: Path) -> tuple[list[dict[str, str]], str]:
    suffix = path.suffix.lower()
    file_type = str(entry.get("file_type", "")).lower()
    if file_type == "pdf" or suffix == ".pdf":
        return parse_pdf_blocks(path)
    if file_type == "html" or suffix in {".html", ".htm", ".xhtml"}:
        return parse_html_blocks(path), ""
    if suffix in {".txt", ".md", ".xml"}:
        return parse_text_blocks(path), ""
    if file_type == "si":
        if suffix == ".pdf":
            return parse_pdf_blocks(path)
        if suffix in {".html", ".htm", ".xhtml"}:
            return parse_html_blocks(path), ""
        return parse_text_blocks(path), ""
    return [], f"Unsupported local full-text file type: {file_type or suffix}"


def make_chunks(blocks: list[dict[str, str]], entry: dict[str, Any], metadata: dict[str, Any]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    source_id = str(entry.get("source_id", ""))
    doi = str(entry.get("doi", "") or metadata.get("doi", ""))
    title = str(entry.get("title", "") or metadata.get("title", ""))
    for idx, block in enumerate(blocks, start=1):
        text = normalize_text(block["text"])
        lower = text.lower()
        if not any(term in lower for term in RELEVANT_TERMS):
            continue
        chunk_id = f"stage2_4b_{source_id}_chunk_{idx:03d}"
        chunks.append(
            {
                "chunk_id": chunk_id,
                "source_id": source_id,
                "doi": doi,
                "title": title,
                "section": block.get("section", "local_fulltext_block"),
                "section_id": block.get("section_id", f"block_{idx:03d}"),
                "text": text,
                "word_count": len(text.split()),
                "char_count": len(text),
                "text_hash": sha256_text(text),
            }
        )
    return chunks


def empty_jsonl_outputs(run_dir: Path) -> None:
    for name in RUN_JSONL_OUTPUTS:
        write_jsonl(run_dir / name, [])


def write_run_summary(run_dir: Path, status: dict[str, Any]) -> None:
    lines = [
        "# Stage 2.4b Local Full-text Ingest Run",
        "",
        f"run_id = {status.get('run_id', '')}",
        f"source_id = {status.get('source_id', '')}",
        f"doi = {status.get('doi', '')}",
        f"title = {status.get('title', '')}",
        f"file_type = {status.get('file_type', '')}",
        f"local_path = {status.get('local_path', '')}",
        f"local_fulltext_found = {str(bool(status.get('local_fulltext_found'))).lower()}",
        f"download_status = {status.get('download_status', '')}",
        f"parsed_chunks = {status.get('parsed_chunks', 0)}",
        f"candidate_records = {status.get('candidate_records', 0)}",
        f"validated_records = {status.get('validated_records', 0)}",
        f"manual_review_records = {status.get('manual_review_records', 0)}",
        f"rejected_records = {status.get('rejected_records', 0)}",
        f"next_action = {status.get('next_action', '')}",
        f"failure_reason = {status.get('failure_reason', '')}",
        "",
        "Boundary note: Stage 2.4b does not merge records into the natural-environment main database.",
    ]
    (run_dir / "run_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def index_run_artifacts(source_id: str, run_dir: Path) -> dict[str, str]:
    refs: dict[str, str] = {}
    for artifact_type, filename in ARTIFACT_FILES.items():
        path = run_dir / filename
        if not path.exists():
            continue
        artifact = index_artifact(
            ROOT,
            ARTIFACT_INDEX_PATH,
            source_id,
            artifact_type,
            path,
            "LocalFullTextIngest",
            SCHEMA_BY_ARTIFACT_TYPE.get(artifact_type, ""),
        )
        refs[f"{artifact_type}_ref"] = artifact["path"]
    return refs


def update_source_registry(entry: dict[str, Any], metadata: dict[str, Any], refs: dict[str, str], status: str, fulltext_hash: str) -> None:
    source_id = str(entry.get("source_id", ""))
    title = str(metadata.get("title") or entry.get("title", ""))
    metadata_ref = refs.get("metadata_ref", "")
    chunks_ref = refs.get("chunks_ref", "")
    metadata_path = ROOT / metadata_ref if metadata_ref else None
    chunks_path = ROOT / chunks_ref if chunks_ref else None
    upsert_source(
        SOURCE_REGISTRY_PATH,
        {
            "authors": metadata.get("authors", []),
            "candidate_records_ref": refs.get("candidate_records_ref", ""),
            "chunks_ref": chunks_ref,
            "doi": entry.get("doi", metadata.get("doi", "")),
            "download_ref": refs.get("download_ref", ""),
            "hashes": {
                "chunks_hash": sha256_file(chunks_path) if chunks_path and chunks_path.exists() else "",
                "doi_hash": doi_hash(str(entry.get("doi", metadata.get("doi", "")))),
                "fulltext_hash": fulltext_hash,
                "metadata_hash": sha256_file(metadata_path) if metadata_path and metadata_path.exists() else "",
                "title_hash": normalized_title_hash(title),
            },
            "journal": metadata.get("journal", ""),
            "manual_review_ref": refs.get("manual_review_ref", ""),
            "metadata_ref": metadata_ref,
            "rejected_records_ref": refs.get("rejected_records_ref", ""),
            "reviewed_records_ref": refs.get("reviewed_records_ref", ""),
            "screening_ref": refs.get("screening_ref", ""),
            "source_id": source_id,
            "status": status,
            "title": title,
            "title_normalized": " ".join(title.lower().split()),
            "validated_records_ref": refs.get("validated_records_ref", ""),
            "year": metadata.get("year", ""),
        },
    )


def ingest_manifest_entry(entry: dict[str, Any]) -> dict[str, Any]:
    source_id = str(entry.get("source_id", ""))
    run_id = f"stage2_4b_{source_id}"
    run_dir = stage2_4b_run_dir(source_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    metadata = load_source_metadata(entry)
    screening = load_screening(entry, metadata)
    write_json(run_dir / "source_metadata.json", metadata)
    write_json(run_dir / "screening.json", screening)

    local_path_text = str(entry.get("local_path", ""))
    local_path = resolve_local_path(local_path_text)
    local_found = bool(local_path and local_path.exists() and local_path.is_file())
    fulltext_sha = sha256_file(local_path) if local_found and local_path else ""
    parse_warning = ""
    chunks: list[dict[str, Any]] = []

    if local_found and local_path is not None:
        blocks, parse_warning = parse_local_file(entry, local_path)
        chunks = make_chunks(blocks, entry, metadata)
        download_status = {
            "access_method": entry.get("access_method", ""),
            "checked_at": utc_now(),
            "doi": entry.get("doi", metadata.get("doi", "")),
            "file_type": entry.get("file_type", ""),
            "full_text_available": True,
            "full_text_downloaded": False,
            "full_text_path": local_path_text,
            "fulltext_sha256": fulltext_sha,
            "license_or_access_note": entry.get("license_or_access_note", ""),
            "local_fulltext_found": True,
            "reason": parse_warning or "User-provided local full text was parsed.",
            "source_id": source_id,
            "status": "ingested" if chunks else "ingested_no_relevant_chunks",
            "text_source_mode": f"local_{entry.get('file_type', 'fulltext')}",
        }
    else:
        download_status = {
            "access_method": entry.get("access_method", ""),
            "checked_at": utc_now(),
            "doi": entry.get("doi", metadata.get("doi", "")),
            "file_type": entry.get("file_type", ""),
            "full_text_available": False,
            "full_text_downloaded": False,
            "full_text_path": "",
            "fulltext_sha256": "",
            "license_or_access_note": entry.get("license_or_access_note", ""),
            "local_fulltext_found": False,
            "local_path_expected": local_path_text,
            "reason": "No local fulltext provided for this Stage 2.4b target.",
            "source_id": source_id,
            "status": "missing_local_fulltext",
            "text_source_mode": "metadata_only",
        }

    write_json(run_dir / "download_status.json", download_status)
    write_jsonl(run_dir / "chunks.jsonl", chunks)
    for name in RUN_JSONL_OUTPUTS[1:]:
        write_jsonl(run_dir / name, [])

    status_value = "parsed_needs_codex" if chunks else ("missing_local_fulltext" if not local_found else "ingested_no_relevant_chunks")
    next_action = "codex_extract_review" if chunks else "manual_full_text_check"
    failure_reason = "" if chunks else download_status["reason"]
    status = {
        "access_method": entry.get("access_method", ""),
        "candidate_records": 0,
        "doi": entry.get("doi", metadata.get("doi", "")),
        "download_status": download_status["status"],
        "failure_reason": failure_reason,
        "file_type": entry.get("file_type", ""),
        "fulltext_sha256": fulltext_sha,
        "local_fulltext_found": local_found,
        "local_path": local_path_text,
        "manual_review_records": 0,
        "next_action": next_action,
        "parsed_chunks": len(chunks),
        "rejected_records": 0,
        "reviewed_records": 0,
        "run_dir": relative_path(ROOT, run_dir),
        "run_id": run_id,
        "source_id": source_id,
        "status": status_value,
        "title": metadata.get("title", entry.get("title", "")),
        "updated_at": utc_now(),
        "validated_records": 0,
    }
    write_run_summary(run_dir, status)
    refs = index_run_artifacts(source_id, run_dir)
    status["artifact_refs"] = refs
    update_source_registry(entry, metadata, refs, "chunked" if chunks else "metadata_only", fulltext_sha)
    return status


def ingest_manifest(manifest_path: Path) -> list[dict[str, Any]]:
    records = read_jsonl(manifest_path)
    return [ingest_manifest_entry(record) for record in records]


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest Stage 2.4b local full-text manifest.")
    parser.add_argument(
        "--manifest",
        default="data/local_fulltext/stage2_4b/fulltext_manifest.jsonl",
        help="Manifest JSONL path.",
    )
    args = parser.parse_args()
    statuses = ingest_manifest(ROOT / args.manifest)
    print(json.dumps({"sources": len(statuses), "parsed_sources": sum(1 for item in statuses if item["parsed_chunks"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
