"""Weighted chunking for extraction."""

from __future__ import annotations

from pathlib import Path

from ecfinder.utils.hashing import sha256_text, stable_id
from ecfinder.utils.logging import read_jsonl, write_jsonl


WEIGHT_TERMS = {
    "pfas": 2.0,
    "perfluoro": 2.0,
    "fluorotelomer": 2.0,
    "transformation": 2.0,
    "degradation": 1.5,
    "biotransformation": 2.0,
    "product": 1.5,
    "precursor": 1.5,
    "pathway": 1.5,
    "soil": 1.0,
    "sediment": 1.0,
    "groundwater": 1.0,
    "wastewater": 1.0,
    "table": 1.0,
    "figure": 1.0,
}


def chunk_section(section: dict, max_words: int = 450, overlap: int = 60) -> list[dict]:
    words = (section.get("text") or "").split()
    if not words:
        return []
    chunks = []
    step = max(1, max_words - overlap)
    for start in range(0, len(words), step):
        window = words[start : start + max_words]
        if not window:
            continue
        text = " ".join(window)
        chunk_id = stable_id("chunk", section.get("source_id"), section.get("section_id"), start, text[:100])
        chunks.append(
            {
                "source_id": section.get("source_id"),
                "section_id": section.get("section_id"),
                "chunk_id": chunk_id,
                "section": section.get("section"),
                "page": section.get("page"),
                "text": text,
                "word_start": start,
                "word_count": len(window),
                "weight": score_chunk(text),
            }
        )
        if start + max_words >= len(words):
            break
    return chunks


def score_chunk(text: str) -> float:
    lower = text.lower()
    return round(sum(weight for term, weight in WEIGHT_TERMS.items() if term in lower), 3)


def chunk_parsed_sections(root: str | Path) -> list[dict]:
    repo_root = Path(root)
    raw_sections = repo_root / "data" / "raw" / "text" / "parsed_sections_text.jsonl"
    section_path = raw_sections if raw_sections.exists() else repo_root / "data" / "interim" / "parsed_sections.jsonl"
    chunks = []
    for section in read_jsonl(section_path):
        chunks.extend(chunk_section(section))
    chunks.sort(key=lambda item: item["weight"], reverse=True)
    public_chunks = []
    raw_chunk_text = []
    for chunk in chunks:
        text = chunk.pop("text", "")
        raw_chunk_text.append({**chunk, "text": text})
        public_chunks.append({**chunk, "text_hash": sha256_text(text), "char_count": len(text)})
    write_jsonl(repo_root / "data" / "raw" / "chunks" / "chunk_text.jsonl", raw_chunk_text)
    write_jsonl(repo_root / "data" / "interim" / "chunks.jsonl", public_chunks)
    return public_chunks
