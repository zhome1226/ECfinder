"""Local Zotero metadata adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ecfinder.state.common import read_jsonl

from .common import AdapterResult


def load(path: Path) -> AdapterResult:
    records: list[dict[str, Any]] = []
    for row in read_jsonl(path):
        records.append(
            {
                "source_provider": "zotero",
                "provider_record_id": str(row.get("zotero_item_key", "") or row.get("source_id", "")),
                "doi": str(row.get("doi", "")).strip().lower(),
                "title": row.get("title", ""),
                "abstract": row.get("abstract", ""),
                "year": row.get("year", ""),
                "journal": row.get("journal", ""),
                "authors": row.get("authors", []),
                "keywords": row.get("keywords", []),
                "url": row.get("url", ""),
                "open_access_hint": None,
            }
        )
    return AdapterResult(provider="zotero", records=records, available=True)
