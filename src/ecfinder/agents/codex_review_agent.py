"""Prepare evidence-grounded review packets for interactive Codex review."""

from __future__ import annotations

from pathlib import Path

from ecfinder.agents.codex_common import load_prompt, load_raw_chunks, load_sources, write_task_packets
from ecfinder.utils.logging import read_jsonl


def prepare_review_tasks(root: str | Path, input_file: str = "pfas_transformation_records_codex_raw.jsonl") -> list[dict]:
    repo_root = Path(root)
    prompt = load_prompt(repo_root, "review_transformation_records.md")
    sources = load_sources(repo_root)
    raw_chunks = load_raw_chunks(repo_root)
    records = list(read_jsonl(repo_root / "data" / "extracted" / input_file))
    packets = []
    for record in records:
        source = sources.get(str(record.get("source_id") or ""), {})
        chunk = raw_chunks.get(str(record.get("chunk_id") or ""), {})
        packets.append(
            {
                "task_type": "codex_review_record",
                "prompt": prompt,
                "source_metadata": {key: source.get(key) for key in ["source_id", "doi", "title", "year", "journal"]},
                "record": record,
                "chunk_text": chunk.get("text"),
                "expected_output": "review decision using Stage 1.5 status vocabulary",
                "status": "interactive_codex_required",
            }
        )
    write_task_packets(repo_root, "codex_review_tasks", packets)
    return packets
