"""CrossRef metadata adapter."""

from __future__ import annotations

from typing import Any

from .common import AdapterResult, fetch_json, first_text, normalize_doi, query_url, strip_markup, year_from_date_parts


def search(query: str, *, max_results: int) -> AdapterResult:
    url = query_url(
        "https://api.crossref.org/works",
        {
            "query.bibliographic": query,
            "rows": min(max_results, 50),
            "select": "DOI,title,abstract,published-print,published-online,container-title,author,URL,link",
        },
    )
    try:
        payload = fetch_json(url)
    except Exception as exc:  # pragma: no cover - network dependent
        return AdapterResult(provider="crossref", records=[], available=False, error=str(exc))
    records: list[dict[str, Any]] = []
    for item in payload.get("message", {}).get("items", []):
        authors = []
        for author in item.get("author", []) or []:
            name = " ".join(str(author.get(part, "")).strip() for part in ["given", "family"]).strip()
            if name:
                authors.append(name)
        links = item.get("link", []) or []
        open_hint = None
        if links:
            open_hint = {"links": [{"url": link.get("URL", ""), "content_type": link.get("content-type", "")} for link in links[:3]]}
        records.append(
            {
                "source_provider": "crossref",
                "provider_record_id": normalize_doi(item.get("DOI")),
                "doi": normalize_doi(item.get("DOI")),
                "title": first_text(item.get("title")),
                "abstract": strip_markup(item.get("abstract", "")),
                "year": year_from_date_parts(item.get("published-print")) or year_from_date_parts(item.get("published-online")),
                "journal": first_text(item.get("container-title")),
                "authors": authors,
                "keywords": [],
                "url": str(item.get("URL", "")),
                "open_access_hint": open_hint,
            }
        )
    return AdapterResult(provider="crossref", records=[row for row in records if row.get("title")], available=True)
