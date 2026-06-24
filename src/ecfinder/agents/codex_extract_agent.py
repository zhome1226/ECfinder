"""Prepare chunk extraction packets for interactive Codex semantic extraction."""

from __future__ import annotations

from pathlib import Path

from ecfinder.agents.codex_common import load_prompt, load_public_chunks, load_raw_chunks, load_sources, write_task_packets
from ecfinder.utils.logging import read_jsonl


def prepare_extract_tasks(
    root: str | Path,
    top_chunks: int = 30,
    include_reextract_chunks: bool = False,
) -> list[dict]:
    repo_root = Path(root)
    prompt = load_prompt(repo_root, "extract_transformation_records.md")
    sources = load_sources(repo_root)
    public_chunks = load_public_chunks(repo_root)
    raw_chunks = load_raw_chunks(repo_root)

    selected_ids: list[str] = []
    for chunk in sorted(public_chunks.values(), key=lambda item: item.get("weight") or 0, reverse=True):
        if _eligible_section(chunk):
            selected_ids.append(chunk["chunk_id"])
        if len(selected_ids) >= top_chunks:
            break

    if include_reextract_chunks:
        for record in read_jsonl(repo_root / "data" / "reviewed" / "rejected_records.jsonl"):
            chunk_id = record.get("chunk_id")
            if chunk_id and chunk_id not in selected_ids:
                selected_ids.append(chunk_id)

    packets = []
    for chunk_id in selected_ids:
        public = public_chunks.get(chunk_id, {})
        raw = raw_chunks.get(chunk_id, {})
        source = sources.get(public.get("source_id") or raw.get("source_id"), {})
        packets.append(
            {
                "task_type": "codex_extract_chunk",
                "prompt": prompt,
                "source_metadata": _source_metadata(source),
                "chunk_index": {key: public.get(key) for key in ["source_id", "chunk_id", "section", "page", "weight", "text_hash"]},
                "chunk_text": raw.get("text"),
                "expected_output": "records array matching extraction schema",
                "status": "interactive_codex_required",
            }
        )
    write_task_packets(repo_root, "codex_extract_tasks", packets)
    return packets


def _eligible_section(chunk: dict) -> bool:
    section = str(chunk.get("section") or "").lower()
    if "reference" in section or section.startswith("page_") and (chunk.get("page") or 0) >= 10:
        return False
    return True


def _source_metadata(source: dict) -> dict:
    return {key: source.get(key) for key in ["source_id", "doi", "title", "year", "journal", "url", "landing_page_url"]}

