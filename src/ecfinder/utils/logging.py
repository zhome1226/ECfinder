"""JSONL and agent-run logging helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_jsonl(path: str | Path) -> Iterator[dict]:
    file_path = Path(path)
    if not file_path.exists():
        return iter(())

    def _iter() -> Iterator[dict]:
        with file_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    yield json.loads(line)

    return _iter()


def write_jsonl(path: str | Path, records: Iterable[dict], append: bool = False) -> int:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    mode = "a" if append else "w"
    with file_path.open(mode, encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    return count


def append_jsonl(path: str | Path, record: dict) -> None:
    write_jsonl(path, [record], append=True)


def log_agent_run(root: str | Path, agent: str, event: str, payload: dict | None = None) -> Path:
    repo_root = Path(root)
    log_dir = repo_root / "logs" / "agent_runs"
    log_dir.mkdir(parents=True, exist_ok=True)
    date = datetime.now(timezone.utc).strftime("%Y%m%d")
    log_path = log_dir / f"{date}_{agent}.jsonl"
    append_jsonl(
        log_path,
        {
            "agent": agent,
            "event": event,
            "payload": payload or {},
            "timestamp": utc_now(),
        },
    )
    return log_path
