"""LLM extraction wrapper and conservative local fallback."""

from __future__ import annotations

import json
import re
from pathlib import Path

from ecfinder.extract.record_normalizer import normalize_name
from ecfinder.extract.schema import assign_record_id, validate_record_shape
from ecfinder.utils.hashing import sha256_text
from ecfinder.utils.logging import read_jsonl, write_jsonl


def parse_llm_records(response_text: str) -> list[dict]:
    payload = json.loads(response_text)
    records = payload.get("records", []) if isinstance(payload, dict) else []
    normalized = []
    for record in records:
        record = dict(record)
        record["parent_normalized"] = normalize_name(record.get("parent_name"))
        record["product_normalized"] = normalize_name(record.get("product_name"))
        assign_record_id(record)
        record["schema_errors"] = validate_record_shape(record)
        record.setdefault("reviewer_status", "unreviewed")
        normalized.append(record)
    return normalized


PFAS_NAME_RE = re.compile(
    r"\b(?:\d+:\d+\s*FTOH|\d+:\d+\s*fluorotelomer alcohol|\d+:\d+\s*fluorotelomer sulfonate|"
    r"PFOA|PFOS|PFHxA|PFHxS|PFBA|PFBS|FOSA|FOSE|perfluoro[a-z -]+acid|perfluoro[a-z -]+sulfonate|"
    r"fluorotelomer[a-z0-9: -]*)\b",
    re.I,
)
PROCESS_RE = re.compile(r"\b(?:biodegradation|biotransformation|transformation|metabolite|pathway|product|yield)\b", re.I)
ENV_RE = re.compile(r"\b(?:soil|sediment|groundwater|surface water|wastewater|sludge|biosolid|environment|microcosm)\b", re.I)
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def extract_from_chunks_stub(root: str | Path) -> list[dict]:
    """Conservative local extraction when no LLM runtime is configured."""
    repo_root = Path(root)
    chunks = {chunk.get("chunk_id"): chunk for chunk in read_jsonl(repo_root / "data" / "interim" / "chunks.jsonl")}
    raw_chunks = list(read_jsonl(repo_root / "data" / "raw" / "chunks" / "chunk_text.jsonl"))
    records: list[dict] = []
    for chunk in raw_chunks:
        text = chunk.get("text") or ""
        if not PROCESS_RE.search(text) or not ENV_RE.search(text):
            continue
        names = []
        for match in PFAS_NAME_RE.finditer(text):
            name = " ".join(match.group(0).split())
            if name.lower() not in {item.lower() for item in names}:
                names.append(name)
        if len(names) < 2:
            continue
        sentence = _best_sentence(text)
        if not sentence:
            continue
        public_chunk = chunks.get(chunk.get("chunk_id"), {})
        record = {
            "source_id": chunk.get("source_id"),
            "chunk_id": chunk.get("chunk_id"),
            "parent_name": names[0],
            "parent_aliases": [],
            "product_name": names[1],
            "product_aliases": names[2:],
            "transformation_process": _classify_process(sentence),
            "pathway_description": None,
            "directionality": "ambiguous",
            "natural_environment_context": _environment_context(sentence) or "environmental context mentioned in chunk",
            "matrix": _matrix(sentence),
            "condition_type": "environmental_microcosm" if "microcosm" in sentence.lower() else "unclear",
            "evidence_quote": sentence[:500],
            "evidence_location": {
                "page": public_chunk.get("page") or chunk.get("page"),
                "section": public_chunk.get("section") or chunk.get("section") or "unknown",
                "table_id": None,
                "figure_id": None,
                "caption": None,
            },
            "confidence": 0.45,
            "extraction_method": "regex_fallback_needs_review",
            "chunk_text_hash": sha256_text(text),
        }
        record["parent_normalized"] = normalize_name(record.get("parent_name"))
        record["product_normalized"] = normalize_name(record.get("product_name"))
        assign_record_id(record)
        record["schema_errors"] = validate_record_shape(record)
        record["reviewer_status"] = "unreviewed"
        records.append(record)
    write_jsonl(repo_root / "data" / "extracted" / "pfas_transformation_records_raw.jsonl", records)
    return records


def _best_sentence(text: str) -> str | None:
    candidates = []
    for sentence in SENTENCE_RE.split(" ".join(text.split())):
        if PROCESS_RE.search(sentence) and PFAS_NAME_RE.search(sentence) and ENV_RE.search(sentence):
            candidates.append(sentence)
    if not candidates:
        for sentence in SENTENCE_RE.split(" ".join(text.split())):
            if PROCESS_RE.search(sentence) and PFAS_NAME_RE.search(sentence):
                candidates.append(sentence)
    if not candidates:
        return None
    return max(candidates, key=lambda value: len(PFAS_NAME_RE.findall(value))).strip()


def _classify_process(sentence: str) -> str:
    lower = sentence.lower()
    if "biotransformation" in lower:
        return "biotransformation"
    if "biodegradation" in lower:
        return "biodegradation"
    if "photo" in lower:
        return "phototransformation"
    return "unknown_environmental_transformation"


def _matrix(sentence: str) -> str | None:
    lower = sentence.lower()
    for term in ["soil", "sediment", "groundwater", "surface water", "wastewater", "sludge", "biosolids"]:
        if term in lower:
            return term
    return None


def _environment_context(sentence: str) -> str | None:
    for term in ["soil", "sediment", "groundwater", "surface water", "wastewater", "sludge", "biosolids", "microcosm"]:
        if term in sentence.lower():
            return term
    return None
