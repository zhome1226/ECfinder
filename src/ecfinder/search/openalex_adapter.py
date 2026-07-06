"""OpenAlex metadata adapter."""

from __future__ import annotations

from typing import Any

from .common import AdapterResult, fetch_json, inverted_index_to_text, normalize_doi, query_url


def search(query: str, *, max_results: int) -> AdapterResult:
    url = query_url(
        "https://api.openalex.org/works",
        {
            "search": query,
            "per-page": min(max_results, 50),
            "filter": "type:article",
            "select": "id,doi,title,display_name,abstract_inverted_index,publication_year,primary_location,authorships,keywords,open_access",
        },
    )
    try:
        payload = fetch_json(url)
    except Exception as exc:  # pragma: no cover - network dependent
        return AdapterResult(provider="openalex", records=[], available=False, error=str(exc))
    records: list[dict[str, Any]] = []
    for item in payload.get("results", []):
        primary = item.get("primary_location") or {}
        source = primary.get("source") or {}
        authors = []
        for authorship in item.get("authorships", []) or []:
            author = authorship.get("author") or {}
            if author.get("display_name"):
                authors.append(author["display_name"])
        keywords = []
        for keyword in item.get("keywords", []) or []:
            if isinstance(keyword, dict) and keyword.get("display_name"):
                keywords.append(keyword["display_name"])
        open_access = item.get("open_access") or {}
        records.append(
            {
                "source_provider": "openalex",
                "provider_record_id": str(item.get("id", "")),
                "doi": normalize_doi(item.get("doi")),
                "title": str(item.get("title") or item.get("display_name") or ""),
                "abstract": inverted_index_to_text(item.get("abstract_inverted_index")),
                "year": str(item.get("publication_year") or ""),
                "journal": str(source.get("display_name", "")),
                "authors": authors,
                "keywords": keywords,
                "url": str(primary.get("landing_page_url") or item.get("id") or ""),
                "open_access_hint": {
                    "is_oa": bool(open_access.get("is_oa")),
                    "oa_url": open_access.get("oa_url") or primary.get("pdf_url") or "",
                    "pdf_url": primary.get("pdf_url") or "",
                },
            }
        )
    return AdapterResult(provider="openalex", records=[row for row in records if row.get("title")], available=True)
