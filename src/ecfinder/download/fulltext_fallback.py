"""Resolve candidate full-text URLs without bypassing access controls."""

from __future__ import annotations


def choose_fulltext_candidate(source: dict) -> dict:
    pdf_url = source.get("pdf_url")
    landing = source.get("landing_page_url") or source.get("url")
    if pdf_url:
        return {"source_id": source.get("source_id"), "kind": "pdf", "url": pdf_url, "reason": "provider_pdf_url"}
    if source.get("is_open_access") and landing:
        return {"source_id": source.get("source_id"), "kind": "html", "url": landing, "reason": "open_access_landing_page"}
    if landing:
        return {"source_id": source.get("source_id"), "kind": "landing", "url": landing, "reason": "metadata_landing_page_only"}
    return {"source_id": source.get("source_id"), "kind": "none", "url": None, "reason": "no_fulltext_candidate"}
