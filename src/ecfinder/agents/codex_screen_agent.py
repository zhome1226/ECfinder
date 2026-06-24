"""Prepare title/abstract screening packets for interactive Codex review."""

from __future__ import annotations

from pathlib import Path

from ecfinder.agents.codex_common import load_prompt, write_task_packets
from ecfinder.utils.logging import read_jsonl


def prepare_screen_tasks(root: str | Path, limit: int | None = None) -> list[dict]:
    repo_root = Path(root)
    prompt = load_prompt(repo_root, "screen_title_abstract.md")
    sources = list(read_jsonl(repo_root / "data" / "interim" / "search_results.jsonl"))
    packets = []
    for source in sources[:limit]:
        packets.append(
            {
                "task_type": "codex_screen_title_abstract",
                "prompt": prompt,
                "source_id": source.get("source_id"),
                "input": {
                    "title": source.get("title"),
                    "abstract": source.get("abstract"),
                    "doi": source.get("doi"),
                    "journal": source.get("journal"),
                    "year": source.get("year"),
                },
                "expected_output": "screened_sources JSON object",
                "status": "interactive_codex_required",
            }
        )
    write_task_packets(repo_root, "codex_screen_tasks", packets)
    return packets

