"""SearchAgent implementation with public-API fallbacks."""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Iterable

from ecfinder.search.query_builder import QuerySpec, dedup_key, load_queries, source_id_for
from ecfinder.utils.logging import log_agent_run, utc_now, write_jsonl


USER_AGENT = "ECfinder/0.1 (mailto optional via OPENALEX_MAILTO/CROSSREF_MAILTO)"


def _get_json(url: str, timeout: int = 25) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec - user-controlled only through encoded query
        return json.loads(response.read().decode("utf-8"))


def _openalex_abstract(index: dict | None) -> str | None:
    if not index:
        return None
    words: list[tuple[int, str]] = []
    for word, positions in index.items():
        for position in positions:
            words.append((int(position), word))
    return " ".join(word for _, word in sorted(words)) or None


def search_openalex(query: str, limit: int = 25) -> list[dict]:
    params = {"search": query, "per-page": str(limit)}
    mailto = os.getenv("OPENALEX_MAILTO")
    if mailto:
        params["mailto"] = mailto
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
    data = _get_json(url)
    records = []
    for rank, item in enumerate(data.get("results", []), start=1):
        authors = [
            authorship.get("author", {}).get("display_name", "")
            for authorship in item.get("authorships", [])
            if authorship.get("author")
        ]
        doi = item.get("doi")
        if doi:
            doi = doi.replace("https://doi.org/", "")
        records.append(
            {
                "provider": "openalex",
                "rank": rank,
                "title": item.get("title"),
                "doi": doi,
                "year": item.get("publication_year"),
                "journal": (item.get("primary_location") or {}).get("source", {}).get("display_name"),
                "url": item.get("id"),
                "landing_page_url": (item.get("primary_location") or {}).get("landing_page_url"),
                "pdf_url": (item.get("primary_location") or {}).get("pdf_url"),
                "is_open_access": (item.get("open_access") or {}).get("is_oa"),
                "authors": authors,
                "abstract": _openalex_abstract(item.get("abstract_inverted_index")),
                "cited_by_count": item.get("cited_by_count"),
            }
        )
    return records


def search_crossref(query: str, limit: int = 25) -> list[dict]:
    params = {"query.bibliographic": query, "rows": str(limit)}
    mailto = os.getenv("CROSSREF_MAILTO")
    if mailto:
        params["mailto"] = mailto
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode(params)
    data = _get_json(url)
    records = []
    for rank, item in enumerate(data.get("message", {}).get("items", []), start=1):
        title = (item.get("title") or [None])[0]
        authors = []
        for author in item.get("author", []):
            name = " ".join(part for part in [author.get("given"), author.get("family")] if part)
            if name:
                authors.append(name)
        date_parts = item.get("published-print", item.get("published-online", {})).get("date-parts", [[None]])
        year = date_parts[0][0] if date_parts and date_parts[0] else None
        links = item.get("link") or []
        pdf_url = next((link.get("URL") for link in links if "pdf" in (link.get("content-type") or "")), None)
        records.append(
            {
                "provider": "crossref",
                "rank": rank,
                "title": title,
                "doi": item.get("DOI"),
                "year": year,
                "journal": (item.get("container-title") or [None])[0],
                "url": item.get("URL"),
                "landing_page_url": item.get("URL"),
                "pdf_url": pdf_url,
                "authors": authors,
                "abstract": item.get("abstract"),
                "cited_by_count": item.get("is-referenced-by-count"),
            }
        )
    return records


def run_search(
    root: str | Path,
    query_config: str | Path | None = None,
    limit: int = 25,
    sources: Iterable[str] = ("crossref", "openalex"),
) -> list[dict]:
    repo_root = Path(root)
    queries = load_queries(query_config or repo_root / "configs" / "search_queries.yaml")
    seen: set[str] = set()
    output: list[dict] = []
    performance: list[dict] = []
    run_id = f"search_{utc_now()}"

    for query in queries:
        for source in sources:
            started = utc_now()
            try:
                raw = search_crossref(query.boolean, limit) if source == "crossref" else search_openalex(query.boolean, limit)
                failed = False
                error = None
            except Exception as exc:
                raw = []
                failed = True
                error = f"{type(exc).__name__}: {exc}"
            accepted = 0
            for record in raw:
                record.update({"query_id": query.query_id, "query_priority": query.priority, "retrieved_at": started})
                record["source_id"] = source_id_for(record)
                key = dedup_key(record)
                if key in seen:
                    continue
                seen.add(key)
                output.append(record)
                accepted += 1
            performance.append(
                {
                    "run_id": run_id,
                    "query_id": query.query_id,
                    "source": source,
                    "retrieved_at": started,
                    "result_count": len(raw),
                    "accepted_count": accepted,
                    "failed": failed,
                    "notes": error,
                }
            )

    write_jsonl(repo_root / "data" / "interim" / "search_results.jsonl", output)
    write_jsonl(repo_root / "data" / "interim" / "query_performance.jsonl", performance)
    _write_performance_report(repo_root / "reports" / "query_performance.md", performance)
    log_agent_run(repo_root, "SearchAgent", "search_complete", {"records": len(output), "run_id": run_id})
    return output


def _write_performance_report(path: Path, rows: list[dict]) -> None:
    lines = [
        "# Query Performance",
        "",
        "| run_id | query_id | source | retrieved_at | result_count | accepted_count | failed | notes |",
        "|---|---|---|---|---:|---:|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {run_id} | {query_id} | {source} | {retrieved_at} | {result_count} | {accepted_count} | {failed} | {notes} |".format(
                **{k: "" if v is None else v for k, v in row.items()}
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
