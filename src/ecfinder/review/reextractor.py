"""Create re-extraction tasks from failed review records."""

from __future__ import annotations

from pathlib import Path

from ecfinder.utils.logging import read_jsonl, write_jsonl


def build_reextract_tasks(root: str | Path) -> list[dict]:
    repo_root = Path(root)
    chunks = {chunk.get("chunk_id"): chunk for chunk in read_jsonl(repo_root / "data" / "interim" / "chunks.jsonl")}
    tasks = []
    for record in read_jsonl(repo_root / "data" / "reviewed" / "rejected_records.jsonl"):
        if record.get("reviewer_status") == "needs_reextract":
            chunk = chunks.get(record.get("chunk_id"), {})
            tasks.append(
                {
                    "source_id": record.get("source_id"),
                    "chunk_id": record.get("chunk_id"),
                    "failed_record_id": record.get("record_id"),
                    "review_reasons": record.get("review_reasons", []),
                    "chunk_text": chunk.get("text"),
                }
            )
    write_jsonl(repo_root / "data" / "interim" / "reextract_tasks.jsonl", tasks)
    return tasks
