"""Shared helpers for Codex semantic agent task packets."""

from __future__ import annotations

from pathlib import Path

from ecfinder.utils.logging import read_jsonl, utc_now, write_jsonl


CODEX_MODE_NOTE = (
    "Codex mode uses the current interactive Codex/GPT model. "
    "This CLI does not call an external API and does not require OPENAI_API_KEY."
)


def load_prompt(root: str | Path, prompt_name: str) -> str:
    return (Path(root) / "prompts" / prompt_name).read_text(encoding="utf-8")


def load_sources(root: str | Path) -> dict[str, dict]:
    return {
        str(row.get("source_id")): row
        for row in read_jsonl(Path(root) / "data" / "interim" / "search_results.jsonl")
        if row.get("source_id")
    }


def load_public_chunks(root: str | Path) -> dict[str, dict]:
    return {
        str(row.get("chunk_id")): row
        for row in read_jsonl(Path(root) / "data" / "interim" / "chunks.jsonl")
        if row.get("chunk_id")
    }


def load_raw_chunks(root: str | Path) -> dict[str, dict]:
    return {
        str(row.get("chunk_id")): row
        for row in read_jsonl(Path(root) / "data" / "raw" / "chunks" / "chunk_text.jsonl")
        if row.get("chunk_id")
    }


def write_task_packets(root: str | Path, name: str, packets: list[dict]) -> Path:
    path = Path(root) / "data" / "interim" / f"{name}.jsonl"
    for packet in packets:
        packet.setdefault("created_at", utc_now())
        packet.setdefault("codex_mode_note", CODEX_MODE_NOTE)
    write_jsonl(path, packets)
    return path
