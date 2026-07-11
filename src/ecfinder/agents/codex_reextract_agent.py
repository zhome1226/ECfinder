"""Prepare re-extraction packets for records that need another Codex pass."""

from __future__ import annotations

from pathlib import Path

from ecfinder.agents.codex_common import load_prompt, load_raw_chunks, load_sources, write_task_packets
from ecfinder.utils.logging import read_jsonl


def prepare_reextract_tasks(root: str | Path, max_attempts: int = 2) -> list[dict]:
    repo_root = Path(root)
    prompt = load_prompt(repo_root, "reextract_from_failed_chunk.md")
    sources = load_sources(repo_root)
    raw_chunks = load_raw_chunks(repo_root)
    packets = []
    for record in read_jsonl(repo_root / "data" / "reviewed" / "rejected_records.jsonl"):
        if record.get("reviewer_status") not in {"needs_reextract", "needs_manual_review"}:
            continue
        attempts = int(record.get("reextract_attempts") or 0)
        if attempts >= max_attempts:
            continue
        chunk = raw_chunks.get(str(record.get("chunk_id") or ""), {})
        source = sources.get(str(record.get("source_id") or ""), {})
        packets.append(
            {
                "task_type": "codex_reextract_chunk",
                "prompt": prompt,
                "source_metadata": {key: source.get(key) for key in ["source_id", "doi", "title", "year", "journal"]},
                "failed_record": record,
                "chunk_text": chunk.get("text"),
                "attempt": attempts + 1,
                "max_attempts": max_attempts,
                "expected_output": "records array or empty records array",
                "status": "interactive_codex_required",
            }
        )
    write_task_packets(repo_root, "codex_reextract_tasks", packets)
    return packets
