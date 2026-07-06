"""Metadata-only lawful fulltext resolution for external sources."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ecfinder.state.common import read_jsonl, utc_now, write_jsonl


def resolve_external_fulltext(root: Path, source: dict[str, Any], manifest_rows: list[dict[str, Any]]) -> dict[str, Any]:
    doi = str(source.get("doi", "")).strip().lower()
    source_id = str(source.get("source_id", ""))
    for row in manifest_rows:
        if source_id and row.get("source_id") == source_id:
            return resolution_row(source, "found_local", True, "zotero_or_local_manifest", "")
        if doi and str(row.get("doi", "")).strip().lower() == doi:
            return resolution_row(source, "found_local", True, "zotero_or_local_manifest", "")
    hint = source.get("open_access_hint")
    if isinstance(hint, dict) and (hint.get("is_oa") is True or hint.get("oa_url") or hint.get("pdf_url")):
        return resolution_row(source, "metadata_only", False, "open_access_hint_metadata_only", "open access hint not downloaded in controlled pilot")
    return resolution_row(source, "blocked_external", False, "metadata_refs_only", "no lawful local PDF/HTML cache")


def resolution_row(source: dict[str, Any], status: str, available: bool, method: str, reason: str) -> dict[str, Any]:
    return {
        "access_method": method,
        "blocked_reason": reason,
        "checked_at": utc_now(),
        "doi": source.get("doi", ""),
        "fulltext_available": available,
        "lawful_access_checked": True,
        "paywall_bypass_used": False,
        "raw_fulltext_committed": False,
        "resolution_status": status,
        "source_id": source.get("source_id", ""),
        "source_origin": source.get("source_origin", ""),
        "source_provider": source.get("source_provider", ""),
        "title": source.get("title", ""),
    }


def append_resolution(root: Path, row: dict[str, Any]) -> None:
    path = root / "data" / "state" / "stage2_8_external_fulltext_resolution.jsonl"
    rows = read_jsonl(path)
    key = str(row.get("source_id", ""))
    rows = [existing for existing in rows if str(existing.get("source_id", "")) != key]
    rows.append(row)
    write_jsonl(path, rows)
