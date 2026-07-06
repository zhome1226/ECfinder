"""Semantic Scholar metadata adapter."""

from __future__ import annotations

from .common import AdapterResult, fetch_json, normalize_doi, query_url


def search(query: str, *, max_results: int) -> AdapterResult:
    url = query_url(
        "https://api.semanticscholar.org/graph/v1/paper/search",
        {
            "query": query,
            "limit": min(max_results, 50),
            "fields": "paperId,title,abstract,year,journal,authors,externalIds,openAccessPdf,url",
        },
    )
    try:
        payload = fetch_json(url)
    except Exception as exc:  # pragma: no cover - network dependent
        return AdapterResult(provider="semantic_scholar", records=[], available=False, error=str(exc))
    records = []
    for item in payload.get("data", []) or []:
        external = item.get("externalIds") or {}
        journal = item.get("journal") or {}
        open_pdf = item.get("openAccessPdf") or {}
        records.append(
            {
                "source_provider": "semantic_scholar",
                "provider_record_id": str(item.get("paperId", "")),
                "doi": normalize_doi(external.get("DOI")),
                "title": str(item.get("title", "")),
                "abstract": str(item.get("abstract", "") or ""),
                "year": str(item.get("year", "") or ""),
                "journal": str(journal.get("name", "") if isinstance(journal, dict) else ""),
                "authors": [str(author.get("name", "")) for author in item.get("authors", []) if author.get("name")],
                "keywords": [],
                "url": str(item.get("url", "")),
                "open_access_hint": {"pdf_url": open_pdf.get("url", ""), "status": open_pdf.get("status", "")},
            }
        )
    return AdapterResult(provider="semantic_scholar", records=[row for row in records if row.get("title")], available=True)
