"""Executable runner for ``external_metadata_discovery_v1``.

The runner is the public skill boundary called by ECMonitor. Provider-specific
query compilation, HTTP execution, error classification, and metadata mapping
live here so callers do not import ECfinder provider internals.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, cast

USER_AGENT = "ECfinder-external-metadata-discovery-v1/1.1"
RUNNER_ID = "ecfinder.skills.external_metadata_discovery.runner"
JSON_HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}
XML_HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/xml,text/xml,*/*"}


@dataclass(frozen=True)
class ProviderRequest:
    provider: str
    url: str
    sanitized_url: str
    query: str
    params: dict[str, Any]
    sanitized_params: dict[str, Any]
    headers: dict[str, str] = field(default_factory=dict)
    sanitized_headers: dict[str, str] = field(default_factory=dict)
    chunks: list[dict[str, Any]] = field(default_factory=list)

    def executable_request(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "provider": self.provider,
            "query": self.query,
            "url": self.sanitized_url,
            "params": self.sanitized_params,
            "headers": self.sanitized_headers,
            "runner": RUNNER_ID,
        }
        if self.chunks:
            payload["chunks"] = self.chunks
        return payload


@dataclass(frozen=True)
class HttpResponse:
    status: int | None
    headers: dict[str, str]
    text: str
    payload: Any = None
    error: str = ""
    url: str = ""


@dataclass(frozen=True)
class ProviderResult:
    provider: str
    records: list[dict[str, Any]]
    status: str
    error: str = ""
    diagnostics: dict[str, Any] = field(default_factory=dict)
    excluded_counts: dict[str, int] = field(default_factory=dict)

    @property
    def available(self) -> bool:
        return self.status in {"success", "no-results", "partial"}


class ProviderImplementation(Protocol):
    name: str

    def compile_request(self, context: dict[str, Any], limit: int) -> ProviderRequest: ...

    def execute(self, request: ProviderRequest, limit: int) -> ProviderResult: ...

    def normalize_record(self, raw: dict[str, Any]) -> dict[str, Any]: ...

    def classify_error(self, response: HttpResponse) -> tuple[str, str, dict[str, Any]]: ...


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m ecfinder.skills.external_metadata_discovery.runner"
    )
    parser.add_argument("--input", help="Skill request JSON path.")
    parser.add_argument("--output", required=True, help="Skill result JSON path.")
    parser.add_argument(
        "--health-check",
        action="store_true",
        help="Run a provider connectivity/authentication health check.",
    )
    parser.add_argument(
        "--provider",
        action="append",
        choices=["crossref", "openalex", "semantic_scholar", "pubmed"],
        help="Provider to include in health check. Repeatable.",
    )
    args = parser.parse_args(argv)
    output_path = Path(args.output).resolve()
    if args.health_check:
        result = provider_health_check(args.provider)
    else:
        if not args.input:
            parser.error("--input is required unless --health-check is set")
        request_path = Path(args.input).resolve()
        result = run_skill(cast(dict[str, Any], _read_json(request_path)), output_path)
    _write_json(output_path, result)
    return 0


def provider_health_check(providers: list[str] | None = None) -> dict[str, Any]:
    requested = providers or ["crossref", "openalex", "semantic_scholar", "pubmed"]
    implementations = _provider_implementations()
    context = {
        "canonical_query": {
            "emerging_contaminant_terms": ["emerging contaminants"],
            "surface_water_terms": ["river"],
            "monitoring_and_concentration_terms": ["concentration"],
        },
        "row": {
            "query_text": '"emerging contaminants" AND river AND concentration',
        },
        "date_from": "2025-01-01",
        "date_to": "2026-07-10",
        "document_types": ["journal article", "research article"],
    }
    provider_results: dict[str, Any] = {}
    for provider in requested:
        implementation = implementations.get(provider)
        status: dict[str, Any] = {
            "provider": provider,
            "environment": _auth_status(provider),
            "connectivity": "not-run",
            "authentication": _provider_authentication_status(provider),
            "api_response_status": "not-run",
            "status": "not-run",
            "error": "",
            "diagnostics": {},
        }
        if implementation is None:
            status.update(
                {
                    "connectivity": "not-run",
                    "api_response_status": "unsupported_provider",
                    "status": "not-run",
                    "error": "unsupported provider",
                }
            )
            provider_results[provider] = status
            continue
        try:
            request = implementation.compile_request(dict(context, provider=provider), 1)
            result = implementation.execute(request, 1)
        except Exception as exc:
            status.update(
                {
                    "connectivity": "failed",
                    "api_response_status": "exception",
                    "status": "failed",
                    "error": str(exc),
                }
            )
            provider_results[provider] = status
            continue
        http_status = result.diagnostics.get("http_status")
        status.update(
            {
                "connectivity": _connectivity_status(result.status),
                "api_response_status": _api_response_status(result, http_status),
                "status": result.status,
                "record_count": len(result.records),
                "error_classification": result.diagnostics.get("classification", ""),
                "diagnostics": result.diagnostics,
            }
        )
        provider_results[provider] = status
    return {
        "runner": RUNNER_ID,
        "mode": "provider_health_check",
        "environment_validation": _environment_validation(),
        "providers": provider_results,
        "completed_at": _now(),
    }


def run_skill(request: dict[str, Any], output_path: Path) -> dict[str, Any]:
    if request.get("skill_id") not in {"", None, "external_metadata_discovery_v1"}:
        raise ValueError("skill_id must be external_metadata_discovery_v1")
    run_id = str(request.get("run_id") or "")
    query_id = str(request.get("query_id") or "")
    iteration = int(request.get("iteration") or 1)
    output_root = Path(str(request["output_root"])).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    page_root = output_root / "provider_pages"
    page_root.mkdir(parents=True, exist_ok=True)

    queries = _load_queries_ref(Path(str(request["queries_ref"])))
    query_by_provider = {
        str(row.get("provider") or row.get("source_name")): row for row in queries
    }
    providers = [str(provider) for provider in request.get("providers", [])]
    max_candidates = int(request.get("max_candidates") or request.get("max_results_per_query") or 1)
    page_size = int(request.get("page_size") or max_candidates)
    limit = min(max_candidates, page_size * int(request.get("max_scan_depth_per_provider") or 1))
    context_base = {
        "canonical_query": dict(request.get("canonical_query") or {}),
        "date_from": str(request.get("date_from") or ""),
        "date_to": str(request.get("date_to") or ""),
        "document_types": [str(value) for value in request.get("document_types", [])],
    }

    provider_page_refs: dict[str, list[str]] = {}
    provider_states: dict[str, dict[str, Any]] = {}
    source_status: dict[str, str] = {}
    next_cursor_by_provider: dict[str, str] = {}
    providers_available: list[str] = []
    candidates: list[dict[str, Any]] = []
    implementations = _provider_implementations()

    for provider in providers:
        provider_page_refs[provider] = []
        state = _provider_state(provider, context_base, limit)
        implementation = implementations.get(provider)
        if implementation is None:
            state.update({"status": "not-run", "error": "unsupported provider"})
            provider_states[provider] = state
            source_status[provider] = "not-run"
            next_cursor_by_provider[provider] = ""
            continue

        context = dict(context_base)
        context.update({"provider": provider, "row": query_by_provider.get(provider, {})})
        provider_request = implementation.compile_request(context, limit)
        state["executable_request"] = provider_request.executable_request()
        state["query_text"] = provider_request.query
        result = implementation.execute(provider_request, limit)
        state.update(
            {
                "status": result.status,
                "error": result.error,
                "record_count": len(result.records),
                "diagnostics": result.diagnostics,
                "excluded_counts": result.excluded_counts,
            }
        )
        source_status[provider] = result.status
        if result.available:
            providers_available.append(provider)
        if result.records:
            page_path = page_root / f"{provider}_page_0001.jsonl"
            rows = [
                _normalize_record(
                    raw=implementation.normalize_record(record),
                    provider=provider,
                    rank=rank,
                    run_id=run_id,
                    query_id=query_id,
                    iteration=iteration,
                    executable_query=provider_request.query,
                )
                for rank, record in enumerate(result.records, start=1)
            ]
            _write_jsonl(page_path, rows)
            provider_page_refs[provider].append(str(page_path))
            candidates.extend(rows)
            next_cursor_by_provider[provider] = str(len(rows))
        else:
            next_cursor_by_provider[provider] = ""
        provider_states[provider] = state

    candidates_ref = output_root / "candidates.jsonl"
    provider_states_ref = output_root / "provider_states.json"
    source_status_ref = output_root / "source_status.json"
    memory_usage_ref = output_root / "memory_usage.json"
    _write_jsonl(candidates_ref, candidates)
    _write_json(provider_states_ref, provider_states)
    _write_json(source_status_ref, source_status)
    _write_json(memory_usage_ref, {"runner_pid": os.getpid(), "completed_at": _now()})
    return {
        "candidates_ref": str(candidates_ref),
        "deduped_ref": "",
        "new_sources_ref": "",
        "provider_page_refs": provider_page_refs,
        "provider_states_ref": str(provider_states_ref),
        "next_cursor_by_provider": next_cursor_by_provider,
        "source_status_ref": str(source_status_ref),
        "memory_usage_ref": str(memory_usage_ref),
        "providers_attempted": providers,
        "providers_available": providers_available,
        "total_external_candidates": len(candidates),
        "execution_status": _execution_status(source_status, len(candidates)),
    }


class CrossrefProvider:
    name = "crossref"

    def compile_request(self, context: dict[str, Any], limit: int) -> ProviderRequest:
        query = _crossref_query(context)
        params = {
            "query.bibliographic": query,
            "rows": min(max(limit * 12, limit), 50),
            "filter": _join_filters(
                [
                    _date_filter("from-pub-date", context["date_from"]),
                    _date_filter("until-pub-date", context["date_to"]),
                    "type:journal-article" if _wants_articles(context["document_types"]) else "",
                ]
            ),
            "select": ",".join(
                [
                    "DOI",
                    "title",
                    "abstract",
                    "published-print",
                    "published-online",
                    "published",
                    "container-title",
                    "author",
                    "URL",
                    "link",
                    "type",
                ]
            ),
        }
        mailto = os.environ.get("CROSSREF_MAILTO", "").strip()
        if mailto:
            params["mailto"] = mailto
        sanitized = _sanitize_params(params)
        return ProviderRequest(
            provider=self.name,
            url=_url("https://api.crossref.org/works", params),
            sanitized_url=_url("https://api.crossref.org/works", sanitized),
            query=query,
            params=params,
            sanitized_params=sanitized,
        )

    def execute(self, request: ProviderRequest, limit: int) -> ProviderResult:
        response = _http_json(request.url, JSON_HEADERS)
        if response.status != 200 or not isinstance(response.payload, dict):
            status, error, diagnostics = self.classify_error(response)
            return ProviderResult(self.name, [], status, error, diagnostics)
        records: list[dict[str, Any]] = []
        excluded: dict[str, int] = {}
        items = response.payload.get("message", {}).get("items", []) or []
        for item in items:
            reason = _crossref_exclusion_reason(item)
            if reason:
                excluded[reason] = excluded.get(reason, 0) + 1
                continue
            if _first_text(item.get("title")):
                records.append(item)
            if len(records) >= limit:
                break
        status = "success" if records else "no-results"
        return ProviderResult(self.name, records, status, excluded_counts=excluded)

    def normalize_record(self, raw: dict[str, Any]) -> dict[str, Any]:
        authors = []
        for author in raw.get("author", []) or []:
            name = " ".join(str(author.get(part, "")).strip() for part in ["given", "family"]).strip()
            if name:
                authors.append(name)
        links = raw.get("link", []) or []
        return {
            "source_provider": self.name,
            "provider_record_id": _normalize_doi(raw.get("DOI")),
            "doi": _normalize_doi(raw.get("DOI")),
            "title": _first_text(raw.get("title")),
            "abstract": _strip_markup(str(raw.get("abstract", "") or "")),
            "year": _year_from_date_parts(raw.get("published-print"))
            or _year_from_date_parts(raw.get("published-online"))
            or _year_from_date_parts(raw.get("published")),
            "journal": _first_text(raw.get("container-title")),
            "authors": authors,
            "keywords": [str(value) for value in raw.get("subject", []) or []],
            "url": str(raw.get("URL", "") or ""),
            "open_access_hint": {
                "links": [
                    {"url": link.get("URL", ""), "content_type": link.get("content-type", "")}
                    for link in links[:3]
                ]
            }
            if links
            else None,
            "document_type": raw.get("type"),
            "language": raw.get("language"),
        }

    def classify_error(self, response: HttpResponse) -> tuple[str, str, dict[str, Any]]:
        return _generic_error("crossref", response)


class OpenAlexProvider:
    name = "openalex"

    def compile_request(self, context: dict[str, Any], limit: int) -> ProviderRequest:
        chunks = _openalex_chunks(context["canonical_query"], context["row"])
        filter_parts = []
        if context["date_from"]:
            filter_parts.append(f"from_publication_date:{context['date_from']}")
        if context["date_to"]:
            filter_parts.append(f"to_publication_date:{context['date_to']}")
        if _wants_articles(context["document_types"]):
            filter_parts.append("type:article")
        executable_chunks = []
        for chunk in chunks:
            params = {
                "search": chunk,
                "per-page": min(max(limit * 5, limit), 50),
                "filter": ",".join(filter_parts),
                "select": ",".join(
                    [
                        "id",
                        "doi",
                        "title",
                        "display_name",
                        "abstract_inverted_index",
                        "publication_year",
                        "publication_date",
                        "primary_location",
                        "authorships",
                        "keywords",
                        "open_access",
                        "type",
                        "language",
                    ]
                ),
            }
            api_key = os.environ.get("OPENALEX_API_KEY", "").strip()
            if api_key:
                params["api_key"] = api_key
            executable_chunks.append(
                {
                    "query": chunk,
                    "query_length": len(chunk),
                    "url": _url("https://api.openalex.org/works", _sanitize_params(params)),
                    "params": _sanitize_params(params),
                    "_url": _url("https://api.openalex.org/works", params),
                }
            )
        primary = executable_chunks[0]
        return ProviderRequest(
            provider=self.name,
            url=str(primary["_url"]),
            sanitized_url=str(primary["url"]),
            query=" | ".join(chunks),
            params={"chunks": executable_chunks},
            sanitized_params={"chunks": [_drop_internal(chunk) for chunk in executable_chunks]},
            chunks=[_drop_internal(chunk) for chunk in executable_chunks],
        )

    def execute(self, request: ProviderRequest, limit: int) -> ProviderResult:
        records: list[dict[str, Any]] = []
        seen: set[str] = set()
        diagnostics: dict[str, Any] = {
            "chunks_attempted": len(request.params["chunks"]),
            "excluded_counts": {},
        }
        for chunk in request.params["chunks"]:
            response = _http_json(str(chunk["_url"]), JSON_HEADERS)
            if response.status != 200 or not isinstance(response.payload, dict):
                status, error, error_diagnostics = self.classify_error(response)
                error_diagnostics["chunk_query_length"] = chunk["query_length"]
                error_diagnostics["sanitized_url"] = chunk["url"]
                return ProviderResult(self.name, records, "partial" if records else status, error, error_diagnostics)
            for item in response.payload.get("results", []) or []:
                reason = _openalex_exclusion_reason(item)
                if reason:
                    excluded = cast(dict[str, int], diagnostics["excluded_counts"])
                    excluded[reason] = excluded.get(reason, 0) + 1
                    continue
                key = _dedupe_key(item.get("id"), item.get("doi"))
                if key in seen:
                    continue
                seen.add(key)
                records.append(item)
                if len(records) >= limit:
                    break
            if len(records) >= limit:
                break
        diagnostics["deduped_count"] = len(records)
        return ProviderResult(self.name, records, "success" if records else "no-results", diagnostics=diagnostics)

    def normalize_record(self, raw: dict[str, Any]) -> dict[str, Any]:
        primary = raw.get("primary_location") or {}
        source = primary.get("source") or {}
        open_access = raw.get("open_access") or {}
        authors = []
        for authorship in raw.get("authorships", []) or []:
            author = authorship.get("author") or {}
            if author.get("display_name"):
                authors.append(author["display_name"])
        keywords = [
            str(keyword.get("display_name"))
            for keyword in raw.get("keywords", []) or []
            if isinstance(keyword, dict) and keyword.get("display_name")
        ]
        return {
            "source_provider": self.name,
            "provider_record_id": str(raw.get("id", "") or ""),
            "doi": _normalize_doi(raw.get("doi")),
            "title": str(raw.get("title") or raw.get("display_name") or ""),
            "abstract": _inverted_index_to_text(raw.get("abstract_inverted_index")),
            "year": str(raw.get("publication_year") or ""),
            "journal": str(source.get("display_name", "") or ""),
            "authors": authors,
            "keywords": keywords,
            "url": str(primary.get("landing_page_url") or raw.get("id") or ""),
            "open_access_hint": {
                "is_oa": bool(open_access.get("is_oa")),
                "oa_url": open_access.get("oa_url") or primary.get("pdf_url") or "",
                "pdf_url": primary.get("pdf_url") or "",
            },
            "document_type": raw.get("type"),
            "language": raw.get("language"),
        }

    def classify_error(self, response: HttpResponse) -> tuple[str, str, dict[str, Any]]:
        status, error, diagnostics = _generic_error("openalex", response)
        if response.status == 400:
            diagnostics["classification"] = "request_syntax_or_filter_error"
        return status, error, diagnostics


class SemanticScholarProvider:
    name = "semantic_scholar"

    def compile_request(self, context: dict[str, Any], limit: int) -> ProviderRequest:
        query = _semantic_query(context["canonical_query"], context["row"])
        params = {
            "query": query,
            "limit": min(limit, 100),
            "fields": ",".join(
                [
                    "paperId",
                    "title",
                    "abstract",
                    "year",
                    "journal",
                    "authors",
                    "externalIds",
                    "openAccessPdf",
                    "url",
                    "publicationTypes",
                    "publicationDate",
                    "venue",
                ]
            ),
        }
        year_filter = _year_filter(context["date_from"], context["date_to"])
        if year_filter:
            params["year"] = year_filter
        headers = dict(JSON_HEADERS)
        sanitized_headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "").strip():
            headers["x-api-key"] = os.environ["SEMANTIC_SCHOLAR_API_KEY"]
            sanitized_headers["x-api-key"] = "configured"
        url = _url("https://api.semanticscholar.org/graph/v1/paper/search", params)
        return ProviderRequest(
            provider=self.name,
            url=url,
            sanitized_url=url,
            query=query,
            params=params,
            sanitized_params=params,
            headers=headers,
            sanitized_headers=sanitized_headers,
        )

    def execute(self, request: ProviderRequest, limit: int) -> ProviderResult:
        attempts = 0
        response = HttpResponse(None, {}, "", error="not attempted")
        while attempts < 3:
            attempts += 1
            response = _http_json(request.url, request.headers)
            if response.status == 429 and attempts < 3:
                retry_after = response.headers.get("retry-after") or response.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    time.sleep(min(int(retry_after), 2))
                continue
            break
        if response.status != 200 or not isinstance(response.payload, dict):
            status, error, diagnostics = self.classify_error(response)
            diagnostics["attempts"] = attempts
            return ProviderResult(self.name, [], status, error, diagnostics)
        data = response.payload.get("data")
        if not isinstance(data, list):
            return ProviderResult(
                self.name,
                [],
                "failed",
                "Semantic Scholar response missing data array",
                {"classification": "invalid_response_shape"},
            )
        records = [item for item in data if isinstance(item, dict) and item.get("title")][:limit]
        return ProviderResult(self.name, records, "success" if records else "no-results")

    def normalize_record(self, raw: dict[str, Any]) -> dict[str, Any]:
        external = raw.get("externalIds") or {}
        journal = raw.get("journal") or {}
        open_pdf = raw.get("openAccessPdf") or {}
        publication_types = raw.get("publicationTypes")
        return {
            "source_provider": self.name,
            "provider_record_id": str(raw.get("paperId", "") or ""),
            "doi": _normalize_doi(external.get("DOI")),
            "title": str(raw.get("title", "") or ""),
            "abstract": str(raw.get("abstract", "") or ""),
            "year": str(raw.get("year", "") or ""),
            "journal": str(journal.get("name", "") if isinstance(journal, dict) else raw.get("venue", "") or ""),
            "authors": [
                str(author.get("name", ""))
                for author in raw.get("authors", []) or []
                if author.get("name")
            ],
            "keywords": [],
            "url": str(raw.get("url", "") or ""),
            "open_access_hint": {"pdf_url": open_pdf.get("url", ""), "status": open_pdf.get("status", "")},
            "document_type": publication_types[0] if isinstance(publication_types, list) and publication_types else None,
            "language": raw.get("language"),
        }

    def classify_error(self, response: HttpResponse) -> tuple[str, str, dict[str, Any]]:
        status, error, diagnostics = _generic_error("semantic_scholar", response)
        if response.status == 400:
            diagnostics["classification"] = "request_syntax_error"
        if response.status == 429:
            status = "rate-limited"
            diagnostics["classification"] = "rate_limited"
            diagnostics["retry_after"] = response.headers.get("retry-after") or response.headers.get("Retry-After")
        return status, error, diagnostics


class PubMedProvider:
    name = "pubmed"

    def compile_request(self, context: dict[str, Any], limit: int) -> ProviderRequest:
        query = _pubmed_query(context)
        email = os.environ.get("NCBI_EMAIL", "").strip()
        tool = os.environ.get("NCBI_TOOL", "ECMonitor").strip() or "ECMonitor"
        api_key = os.environ.get("NCBI_API_KEY", "").strip()
        params = {
            "db": "pubmed",
            "term": query,
            "retmax": str(min(limit, 50)),
            "retmode": "json",
            "email": email,
            "tool": tool,
        }
        if api_key:
            params["api_key"] = api_key
        sanitized = _sanitize_params(params)
        return ProviderRequest(
            provider=self.name,
            url=_url("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi", params),
            sanitized_url=_url("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi", sanitized),
            query=query,
            params=params,
            sanitized_params=sanitized,
        )

    def execute(self, request: ProviderRequest, limit: int) -> ProviderResult:
        if not os.environ.get("NCBI_EMAIL", "").strip():
            return ProviderResult(
                self.name,
                [],
                "configuration_required",
                "NCBI_EMAIL missing",
                {"classification": "configuration_required"},
            )
        esearch = _http_text(request.url, JSON_HEADERS)
        if _is_pubmed_blocked_html(esearch) and request.params.get("api_key"):
            retry_params = dict(request.params)
            retry_params.pop("api_key", None)
            retry_url = _url(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                retry_params,
            )
            retry = _http_text(retry_url, JSON_HEADERS)
            if not _is_pubmed_blocked_html(retry):
                esearch = retry
        if _is_pubmed_blocked_html(esearch):
            fallback = _pubmed_html_fallback_search(request, limit)
            if fallback is not None:
                return fallback
        error = _pubmed_response_error(esearch, "esearch", expect_json=True)
        if error is not None:
            return error
        payload = json.loads(esearch.text)
        ids = payload.get("esearchresult", {}).get("idlist", [])
        if not ids:
            return ProviderResult(self.name, [], "no-results")
        efetch_params = {
            "db": "pubmed",
            "id": ",".join(str(item) for item in ids[:limit]),
            "retmode": "xml",
            "email": os.environ.get("NCBI_EMAIL", "").strip(),
            "tool": os.environ.get("NCBI_TOOL", "ECMonitor").strip() or "ECMonitor",
        }
        if os.environ.get("NCBI_API_KEY", "").strip():
            efetch_params["api_key"] = os.environ["NCBI_API_KEY"]
        efetch = _http_text(_url("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi", efetch_params), XML_HEADERS)
        error = _pubmed_response_error(efetch, "efetch", expect_json=False)
        if error is not None:
            return error
        try:
            root = ET.fromstring(efetch.text.strip())
        except ET.ParseError:
            return ProviderResult(
                self.name,
                [],
                "failed",
                "PubMed EFetch returned malformed XML",
                _pubmed_diagnostics(efetch, "malformed_xml", "efetch"),
            )
        records = [
            record
            for record in _pubmed_records(root, request.params.get("term", ""))
            if record.get("title")
        ][:limit]
        return ProviderResult(self.name, records, "success" if records else "no-results")

    def normalize_record(self, raw: dict[str, Any]) -> dict[str, Any]:
        return raw

    def classify_error(self, response: HttpResponse) -> tuple[str, str, dict[str, Any]]:
        status, error, diagnostics = _generic_error("pubmed", response)
        diagnostics["content_type"] = _content_type(response)
        return status, error, diagnostics


def _provider_implementations() -> dict[str, ProviderImplementation]:
    return {
        "crossref": CrossrefProvider(),
        "openalex": OpenAlexProvider(),
        "semantic_scholar": SemanticScholarProvider(),
        "pubmed": PubMedProvider(),
    }


def _provider_state(provider: str, context: dict[str, Any], requested_limit: int) -> dict[str, Any]:
    return {
        "provider": provider,
        "date_from": context["date_from"],
        "date_to": context["date_to"],
        "document_types": context["document_types"],
        "requested_limit": requested_limit,
        "auth": _auth_status(provider),
    }


def _auth_status(provider: str) -> dict[str, str]:
    if provider == "crossref":
        return {"CROSSREF_MAILTO": _configured("CROSSREF_MAILTO")}
    if provider == "openalex":
        return {"OPENALEX_API_KEY": _configured("OPENALEX_API_KEY")}
    if provider == "semantic_scholar":
        return {"SEMANTIC_SCHOLAR_API_KEY": _configured("SEMANTIC_SCHOLAR_API_KEY")}
    if provider == "pubmed":
        return {
            "NCBI_EMAIL": _configured("NCBI_EMAIL"),
            "NCBI_TOOL": _configured("NCBI_TOOL"),
            "NCBI_API_KEY": _configured("NCBI_API_KEY"),
        }
    return {}


def _environment_validation() -> dict[str, str]:
    return {
        name: _configured(name)
        for name in [
            "NCBI_EMAIL",
            "NCBI_TOOL",
            "NCBI_API_KEY",
            "SEMANTIC_SCHOLAR_API_KEY",
            "OPENALEX_API_KEY",
            "CROSSREF_MAILTO",
        ]
    }


def _provider_authentication_status(provider: str) -> str:
    auth = _auth_status(provider)
    if provider == "pubmed" and auth.get("NCBI_EMAIL") != "configured":
        return "configuration_required"
    if any(value == "configured" for value in auth.values()):
        return "configured"
    return "anonymous"


def _api_response_status(result: ProviderResult, http_status: Any) -> str:
    classification = str(result.diagnostics.get("classification") or "")
    if classification:
        return classification
    if http_status is not None:
        return str(http_status)
    return result.status


def _connectivity_status(status: str) -> str:
    if status in {"success", "no-results", "partial"}:
        return "connected"
    if status == "configuration_required":
        return "not-run"
    if status == "rate-limited":
        return "connected_rate_limited"
    return "failed"


def _configured(name: str) -> str:
    return "configured" if os.environ.get(name, "").strip() else "missing"


def _crossref_query(context: dict[str, Any]) -> str:
    canonical = context["canonical_query"]
    terms = []
    terms.extend(_terms(canonical, "emerging_contaminant_terms", limit=4))
    terms.extend(_preferred_surface_water_terms(canonical, limit=4))
    terms.extend(_terms(canonical, "monitoring_and_concentration_terms", limit=3))
    if not terms:
        return str(context["row"].get("query_text") or context["row"].get("compiled_query") or "").strip()
    return " ".join(_plain_term(term) for term in terms)


def _openalex_chunks(canonical: dict[str, Any], row: dict[str, Any]) -> list[str]:
    emerging = _terms(canonical, "emerging_contaminant_terms", limit=3) or ["emerging contaminants"]
    water = _preferred_surface_water_terms(canonical, limit=3) or ["surface water"]
    monitoring = _terms(canonical, "monitoring_and_concentration_terms", limit=2) or ["monitoring"]
    chunks = []
    for index, term in enumerate(emerging):
        chunks.append(
            " ".join(
                [
                    _plain_term(term),
                    _plain_term(water[index % len(water)]),
                    _plain_term(monitoring[index % len(monitoring)]),
                ]
            )
        )
    if not chunks:
        chunks = [_plain_term(str(row.get("query_text") or row.get("compiled_query") or ""))[:180]]
    return [_truncate_query(chunk, 180) for chunk in chunks if chunk.strip()]


def _semantic_query(canonical: dict[str, Any], row: dict[str, Any]) -> str:
    terms = []
    terms.extend(_terms(canonical, "emerging_contaminant_terms", limit=2) or ["emerging contaminants"])
    terms.extend(_preferred_surface_water_terms(canonical, limit=2) or ["surface water"])
    terms.extend(_terms(canonical, "monitoring_and_concentration_terms", limit=1) or ["monitoring"])
    query = " ".join(_plain_term(term) for term in terms)
    if not query.strip():
        query = _plain_term(str(row.get("query_text") or row.get("compiled_query") or ""))
    return _truncate_query(query, 180)


def _pubmed_query(context: dict[str, Any]) -> str:
    canonical = context["canonical_query"]
    blocks = []
    preferred_terms = {
        "emerging_contaminant_terms": ["emerging contaminant", "micropollutant"],
        "surface_water_terms": ["surface water", "river", "lake", "estuary", "marine water"],
        "monitoring_and_concentration_terms": ["monitoring", "occurrence", "concentration"],
    }
    for key, preferred in preferred_terms.items():
        available = {_plain_term(term).lower() for term in _terms(canonical, key, limit=20)}
        terms = [term for term in preferred if term.lower() in available]
        if not terms and key == "surface_water_terms":
            terms = ["surface water"]
        if terms:
            blocks.append("(" + " OR ".join(f'"{term}"[Title/Abstract]' for term in terms[:3]) + ")")
    base = " AND ".join(blocks) or str(context["row"].get("query_text") or context["row"].get("compiled_query") or "")
    additions = []
    if context["date_from"] or context["date_to"]:
        additions.append(
            f'("{context["date_from"] or "1900-01-01"}"[Date - Publication] : '
            f'"{context["date_to"] or "3000-12-31"}"[Date - Publication])'
        )
    if context["document_types"]:
        additions.append("(" + " OR ".join(f'"{item}"[Publication Type]' for item in context["document_types"]) + ")")
    return " AND ".join([part for part in [base, *additions] if part])


def _crossref_exclusion_reason(item: dict[str, Any]) -> str:
    doi = _normalize_doi(item.get("DOI"))
    title = _first_text(item.get("title"))
    abstract = _strip_markup(str(item.get("abstract", "") or ""))
    item_type = str(item.get("type") or "").lower()
    journal = _first_text(item.get("container-title")).lower()
    subtype = " ".join(
        str(item.get(key) or "").lower()
        for key in ["subtype", "genre", "content-domain"]
    )
    if item_type in {"peer-review", "peer_review", "posted-content"}:
        return "crossref_peer_review_or_posted_content"
    if item_type in {"proceedings-article", "proceedings", "editorial", "letter"}:
        return "crossref_ineligible_publication_type"
    if any(token in subtype for token in ["review", "conference", "proceedings"]):
        return "crossref_ineligible_publication_type"
    if re.search(r"/review\d+\b", doi, flags=re.IGNORECASE):
        return "doi_review_artifact"
    if title.lower().startswith("review for "):
        return "title_review_artifact"
    if title.lower().startswith("next step of:") or abstract.lower().startswith("new module based on:"):
        return "crossref_module_artifact"
    if journal == "researchequals":
        return "crossref_module_artifact"
    if _looks_like_editorial_article(title, abstract):
        return "crossref_editorial_article"
    if _looks_like_review_article(title, abstract):
        return "crossref_review_article"
    matrix_reason = _ineligible_matrix_reason(title, abstract)
    if matrix_reason:
        return matrix_reason
    return ""


def _openalex_exclusion_reason(item: dict[str, Any]) -> str:
    title = str(item.get("title") or item.get("display_name") or "")
    abstract = _inverted_index_to_text(item.get("abstract_inverted_index"))
    item_type = str(item.get("type") or "").lower()
    if item_type in {"review", "book-chapter", "proceedings-article"}:
        return "openalex_ineligible_publication_type"
    if _looks_like_review_article(title, abstract):
        return "openalex_review_article"
    matrix_reason = _ineligible_matrix_reason(title, abstract)
    if matrix_reason:
        return matrix_reason
    if not _has_surface_water_signal(title, abstract):
        return "openalex_missing_surface_water_signal"
    if not _has_monitoring_or_concentration_signal(title, abstract):
        return "openalex_missing_monitoring_concentration_signal"
    return ""


def _preferred_surface_water_terms(canonical: dict[str, Any], limit: int) -> list[str]:
    terms = _terms(canonical, "surface_water_terms", limit=100)
    if not terms:
        return []
    broad = {"ocean", "open ocean", "sea"}
    preferred_order = [
        "surface water",
        "ambient surface water",
        "river",
        "stream",
        "creek",
        "lake",
        "reservoir",
        "estuary",
        "wetland",
        "canal",
        "coastal water",
        "seawater",
        "marine water",
        "bay",
        "lagoon",
    ]
    by_plain = {_plain_term(term).lower(): term for term in terms}
    ordered = [by_plain[value] for value in preferred_order if value in by_plain]
    ordered.extend(term for term in terms if _plain_term(term).lower() not in broad and term not in ordered)
    if not ordered and len(ordered) < limit:
        ordered.extend(term for term in terms if term not in ordered)
    return ordered[:limit]


def _looks_like_review_article(title: str, abstract: str) -> bool:
    text = f"{title} {abstract}".lower()
    review_patterns = [
        r"\bcritical review\b",
        r"\bsystematic review\b",
        r"\bscoping review\b",
        r"\breview aims to\b",
        r"\bthis review\b",
        r"\bwe review\b",
        r"\boverview of\b",
        r"\bupdated overview\b",
        r"\bcurrent status of .* research\b",
    ]
    return any(re.search(pattern, text) for pattern in review_patterns)


def _looks_like_editorial_article(title: str, abstract: str) -> bool:
    text = f"{title} {abstract}".lower()
    editorial_patterns = [
        r"\binaugural editorial\b",
        r"\beditorial\b",
        r"\bperspective\b",
        r"\bcommentary\b",
    ]
    return any(re.search(pattern, text) for pattern in editorial_patterns)


def _has_surface_water_signal(title: str, abstract: str) -> bool:
    text = f"{title} {abstract}".lower()
    patterns = [
        r"\bsurface water\b",
        r"\briver(s)?\b",
        r"\blake(s)?\b",
        r"\bestuar(y|ies|ine)\b",
        r"\bstream(s)?\b",
        r"\breservoir(s)?\b",
        r"\bwetland(s)?\b",
        r"\bcanal(s)?\b",
        r"\bcoastal water(s)?\b",
        r"\bseawater\b",
        r"\bmarine water(s)?\b",
        r"\bwater sample(s)?\b",
    ]
    return any(re.search(pattern, text) for pattern in patterns)


def _has_monitoring_or_concentration_signal(title: str, abstract: str) -> bool:
    text = f"{title} {abstract}".lower()
    patterns = [
        r"\bmonitor(ed|ing)?\b",
        r"\boccurrence\b",
        r"\bconcentration(s)?\b",
        r"\bquantif(y|ied|ication)\b",
        r"\bdetected\b",
        r"\bmeasured\b",
        r"\bng/l\b",
        r"\bµg/l\b",
        r"\bug/l\b",
    ]
    return any(re.search(pattern, text) for pattern in patterns)


def _ineligible_matrix_reason(title: str, abstract: str) -> str:
    text = f"{title} {abstract}".lower()
    ineligible_patterns = [
        (r"\bfoodstuff(s)?\b|\bfood(s)?\b|\bfruit(s)?\b|\bvegetable(s)?\b|\bspice(s)?\b|\bcereal(s)?\b|\binfant formula\b|\bdried herb(s)?\b", "ineligible_food_matrix"),
        (r"\bpaint(s)?\b|\bconsumer product(s)?\b|\btextile(s)?\b|\bpackaging\b", "ineligible_product_matrix"),
        (r"\bdrinking water(s)?\b|\bdwtp(s)?\b|\bwater treatment plant(s)?\b|\btreated water(s)?\b|\btap water\b", "ineligible_drinking_or_treatment_water"),
        (r"\bwastewater(s)?\b|\bwaste water(s)?\b|\bsewage\b|\beffluent(s)?\b|\bwwtp(s)?\b", "ineligible_wastewater_matrix"),
        (r"\bsoil(s)?\b|\bsediment(s)?\b|\bsludge\b|\bbiosolid(s)?\b", "ineligible_solid_matrix"),
        (r"\bgroundwater\b|\bground water\b|\baquifer(s)?\b", "ineligible_groundwater_matrix"),
    ]
    for pattern, reason in ineligible_patterns:
        if re.search(pattern, text):
            return reason
    return ""


def _pubmed_response_error(response: HttpResponse, stage: str, *, expect_json: bool) -> ProviderResult | None:
    if response.status != 200:
        return ProviderResult("pubmed", [], "failed", f"PubMed {stage} HTTP status {response.status}", _pubmed_diagnostics(response, "http_error", stage))
    text = response.text.strip()
    content_type = _content_type(response).lower()
    if not text:
        return ProviderResult("pubmed", [], "failed", f"PubMed {stage} returned empty response", _pubmed_diagnostics(response, "empty_response", stage))
    if "html" in content_type or text.lower().startswith("<html"):
        classification = "ncbi_blocked_html" if _is_pubmed_blocked_html(response) else "html_response"
        return ProviderResult("pubmed", [], "failed", f"PubMed {stage} returned HTML response", _pubmed_diagnostics(response, classification, stage))
    if expect_json:
        try:
            json.loads(text)
        except json.JSONDecodeError:
            return ProviderResult("pubmed", [], "failed", f"PubMed {stage} returned non-JSON response", _pubmed_diagnostics(response, "non_json_response", stage))
    return None


def _pubmed_html_fallback_search(
    request: ProviderRequest, limit: int
) -> ProviderResult | None:
    """Fallback when E-utilities are blocked but the PubMed web UI is reachable."""
    html = None
    ids: list[str] = []
    web_query = ""
    for candidate_query in _pubmed_web_queries(request.query):
        html_url = "https://pubmed.ncbi.nlm.nih.gov/?" + urllib.parse.urlencode(
            {"term": candidate_query}
        )
        html = _http_text(html_url, {"User-Agent": USER_AGENT, "Accept": "text/html,*/*"})
        if html.status != 200 or _is_pubmed_blocked_html(html):
            continue
        ids = _pubmed_ids_from_html(html.text)[:limit]
        web_query = candidate_query
        if ids:
            break
    if html is None or html.status != 200 or _is_pubmed_blocked_html(html):
        return None
    if not ids:
        diagnostics = _pubmed_diagnostics(html, "pubmed_html_no_ids", "web_search")
        diagnostics["fallback"] = "pubmed_web_html"
        diagnostics["web_query_attempts"] = len(_pubmed_web_queries(request.query))
        return ProviderResult("pubmed", [], "failed", "PubMed web fallback returned no IDs", diagnostics)

    efetch_params = {
        "db": "pubmed",
        "id": ",".join(ids),
        "retmode": "xml",
        "email": os.environ.get("NCBI_EMAIL", "").strip(),
        "tool": os.environ.get("NCBI_TOOL", "ECMonitor").strip() or "ECMonitor",
    }
    if os.environ.get("NCBI_API_KEY", "").strip():
        efetch_params["api_key"] = os.environ["NCBI_API_KEY"]
    efetch = _http_text(
        _url("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi", efetch_params),
        XML_HEADERS,
    )
    if not _is_pubmed_blocked_html(efetch):
        error = _pubmed_response_error(efetch, "efetch", expect_json=False)
        if error is None:
            try:
                root = ET.fromstring(efetch.text.strip())
            except ET.ParseError:
                root = None
            if root is not None:
                records = [
                    record
                    for record in _pubmed_records(root, request.params.get("term", ""))
                    if record.get("title")
                ][:limit]
                diagnostics = {"fallback": "pubmed_web_html_ids_then_efetch"}
                return ProviderResult(
                    "pubmed",
                    records,
                    "success" if records else "no-results",
                    diagnostics=diagnostics,
                )

    records = _pubmed_records_from_html(html.text, request.params.get("term", ""))[:limit]
    records = _enrich_pubmed_html_records(records)
    diagnostics = _pubmed_diagnostics(html, "eutils_blocked_pubmed_html_fallback", "web_search")
    diagnostics["fallback"] = "pubmed_web_html"
    diagnostics["web_query"] = web_query
    diagnostics["efetch_classification"] = (
        "ncbi_blocked_html" if _is_pubmed_blocked_html(efetch) else "unavailable"
    )
    return ProviderResult(
        "pubmed",
        records,
        "partial" if records else "failed",
        "E-utilities blocked; used PubMed web HTML fallback" if records else "E-utilities and PubMed HTML fallback failed",
        diagnostics,
    )


def _is_pubmed_blocked_html(response: HttpResponse) -> bool:
    return (
        response.status == 200
        and "html" in _content_type(response).lower()
        and "blocked diagnostic" in response.text.lower()
    )


def _pubmed_web_query(query: str) -> str:
    text = re.sub(
        r'\("[^"]+"\[Date - Publication\]\s*:\s*"[^"]+"\[Date - Publication\]\)',
        " ",
        query,
    )
    text = re.sub(
        r'\((?:"[^"]+"\[Publication Type\](?:\s+OR\s+)*)+\)',
        " ",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\[[^\]]+\]", "", text)
    text = text.replace('"', "")
    text = re.sub(r"\bAND\b|\bOR\b", " ", text, flags=re.IGNORECASE)
    text = text.replace("(", " ").replace(")", " ").replace(":", " ")
    return " ".join(text.split())[:180] or "emerging contaminants river concentration"


def _pubmed_web_queries(query: str) -> list[str]:
    base = _pubmed_web_query(query)
    candidates = [base]
    lowered = base.lower()
    water_terms = [
        term
        for term in ["river", "lake", "estuary", "surface water", "ocean", "seawater"]
        if term in lowered
    ] or ["river"]
    measure_terms = [
        term
        for term in ["concentration", "occurrence", "monitoring"]
        if term in lowered
    ] or ["concentration"]
    contaminant_terms = []
    if "emerging contaminant" in lowered or "emerging contaminants" in lowered:
        contaminant_terms.append("emerging contaminants")
    if "micropollutant" in lowered:
        contaminant_terms.append("micropollutant")
    if not contaminant_terms:
        contaminant_terms.append("emerging contaminants")
    for contaminant in contaminant_terms:
        for water in water_terms[:3]:
            candidates.append(f"{contaminant} {water} {measure_terms[0]}")
    return list(dict.fromkeys(candidate[:180] for candidate in candidates if candidate.strip()))


def _pubmed_ids_from_html(text: str) -> list[str]:
    ids: list[str] = []
    for pattern in [
        r'data-article-id="(\d+)"',
        r'class="docsum-title"[^>]+href="/(\d+)/"',
        r'href="/(\d{6,9})/"',
    ]:
        for pmid in re.findall(pattern, text):
            if pmid not in ids:
                ids.append(pmid)
    return ids


def _pubmed_records_from_html(text: str, query: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    allowed = _pubmed_allowed_publication_types(query)
    for body in re.findall(
        r'<div class="docsum-content"[^>]*>(.*?)<div class="result-actions-bar bottom-bar">',
        text,
        flags=re.DOTALL,
    ):
        pmid_match = re.search(r'data-article-id="(\d+)"', body) or re.search(
            r'href="/(\d{6,9})/"', body
        )
        title_match = re.search(
            r'<a\b[^>]*class="docsum-title"[^>]*>(?P<title>.*?)</a>',
            body,
            flags=re.DOTALL,
        )
        if not pmid_match or not title_match:
            continue
        doc_type = "Journal Article" if not allowed or "journal article" in allowed else ""
        if not doc_type:
            continue
        citation = _strip_markup(_first_match(body, r'<div class="docsum-citation[^"]*"[^>]*>(.*?)</div>'))
        records.append(
            {
                "source_provider": "pubmed",
                "provider_record_id": pmid_match.group(1),
                "doi": "",
                "title": _strip_markup(title_match.group("title")),
                "abstract": "",
                "year": _first_match(citation, r"\b(?:19|20)\d{2}\b"),
                "journal": citation,
                "authors": [
                    author.strip()
                    for author in _strip_markup(
                        _first_match(body, r'<span class="docsum-authors[^"]*"[^>]*>(.*?)</span>')
                    ).split(",")
                    if author.strip()
                ],
                "keywords": [],
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid_match.group(1)}/",
                "open_access_hint": None,
                "document_type": doc_type,
                "language": None,
            }
        )
    return records


def _enrich_pubmed_html_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched = []
    for record in records:
        pmid = str(record.get("provider_record_id") or "")
        if not pmid:
            enriched.append(record)
            continue
        detail = _http_text(
            f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            {"User-Agent": USER_AGENT, "Accept": "text/html,*/*"},
        )
        if detail.status != 200 or _is_pubmed_blocked_html(detail):
            enriched.append(record)
            continue
        merged = dict(record)
        detail_payload = _pubmed_record_detail_from_html(detail.text)
        for key, value in detail_payload.items():
            if value not in ("", None) and value != []:
                merged[key] = value
        enriched.append(merged)
    return enriched


def _pubmed_record_detail_from_html(text: str) -> dict[str, Any]:
    abstract = _strip_markup(
        " ".join(
            re.findall(
                r'<div class="abstract-content selected"[^>]*>.*?<p>(.*?)</p>',
                text,
                flags=re.DOTALL,
            )
        )
    )
    meta_description = _html_meta_content(text, "description")
    keywords = [
        item.strip()
        for item in _html_meta_content(text, "keywords").split(",")
        if item.strip() and not item.strip().lower().startswith(("pmid:", "doi:"))
    ]
    doi = ""
    doi_match = re.search(r"\bdoi:\s*([^,\s<]+)", text, flags=re.IGNORECASE)
    if doi_match:
        doi = _normalize_doi(doi_match.group(1))
    journal = _strip_markup(
        _first_match(
            text,
            r'<button[^>]*class="journal-actions-trigger[^"]*"[^>]*>(.*?)</button>',
        )
    )
    return {
        "abstract": abstract or meta_description,
        "doi": doi,
        "journal": journal,
        "keywords": keywords,
        "language": _html_lang(text),
    }


def _html_meta_content(text: str, name: str) -> str:
    match = re.search(
        rf'<meta\s+name="{re.escape(name)}"\s+content="(?P<content>.*?)"',
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        match = re.search(
            rf'<meta\s+property="og:{re.escape(name)}"\s+content="(?P<content>.*?)"',
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
    return _strip_markup(html.unescape(match.group("content"))) if match else ""


def _html_lang(text: str) -> str | None:
    match = re.search(r"<html[^>]+lang=\"([a-zA-Z-]+)\"", text)
    return match.group(1).lower() if match else None


def _first_match(text: str, pattern: str) -> str:
    match = re.search(pattern, text, flags=re.DOTALL)
    if not match:
        return ""
    if match.lastindex:
        return str(match.group(1))
    return str(match.group(0))


def _pubmed_records(root: ET.Element, query: str = "") -> list[dict[str, Any]]:
    records = []
    for article in root.findall(".//PubmedArticle"):
        pmid = article.findtext(".//PMID") or ""
        publication_types = [node.text or "" for node in article.findall(".//PublicationType") if node.text]
        eligible_types = _eligible_pubmed_publication_types(publication_types, query)
        if not eligible_types:
            continue
        records.append(
            {
                "source_provider": "pubmed",
                "provider_record_id": pmid,
                "doi": _pubmed_doi(article),
                "title": _xml_text(article.find(".//ArticleTitle")),
                "abstract": " ".join(_xml_text(node) for node in article.findall(".//AbstractText") if _xml_text(node)),
                "year": article.findtext(".//PubDate/Year") or article.findtext(".//ArticleDate/Year") or "",
                "journal": article.findtext(".//Journal/Title") or "",
                "authors": _pubmed_authors(article),
                "keywords": [],
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
                "open_access_hint": None,
                "document_type": eligible_types[0],
                "language": article.findtext(".//Language"),
            }
        )
    return records


def _eligible_pubmed_publication_types(publication_types: list[str], query: str) -> list[str]:
    if not publication_types:
        return []
    allowed = _pubmed_allowed_publication_types(query)
    if not allowed:
        return publication_types
    return [item for item in publication_types if item.casefold() in allowed]


def _pubmed_allowed_publication_types(query: str) -> set[str]:
    allowed = set()
    marker = '"[Publication Type]'
    for fragment in query.split(marker):
        if '"' not in fragment:
            continue
        term = fragment.rsplit('"', 1)[-1].strip()
        if term:
            allowed.add(term.casefold())
    return allowed


def _pubmed_doi(article: ET.Element) -> str:
    for aid in article.findall(".//ArticleId"):
        if aid.attrib.get("IdType") == "doi" and aid.text:
            return _normalize_doi(aid.text)
    return ""


def _pubmed_authors(article: ET.Element) -> list[str]:
    authors = []
    for author in article.findall(".//Author"):
        name = " ".join([author.findtext("ForeName") or "", author.findtext("LastName") or ""]).strip()
        if name:
            authors.append(name)
    return authors


def _http_json(url: str, headers: dict[str, str]) -> HttpResponse:
    response = _http_text(url, headers)
    if response.status == 200 and response.text.strip():
        try:
            return HttpResponse(
                response.status,
                response.headers,
                response.text,
                json.loads(response.text),
                response.error,
                response.url,
            )
        except json.JSONDecodeError as exc:
            return HttpResponse(response.status, response.headers, response.text, None, str(exc), response.url)
    return response


def _http_text(url: str, headers: dict[str, str]) -> HttpResponse:
    request = urllib.request.Request(url, headers=headers)
    last_error = ""
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                text = response.read().decode("utf-8", errors="replace")
                return HttpResponse(int(response.status), dict(response.headers.items()), text, url=url)
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
            return HttpResponse(int(exc.code), dict(exc.headers.items()), text, error=str(exc), url=url)
        except Exception as exc:  # pragma: no cover - network dependent
            last_error = str(exc)
            if attempt < 2 and _is_retryable_transport_error(last_error):
                time.sleep(0.5 * (attempt + 1))
                continue
            return HttpResponse(None, {}, "", error=last_error, url=url)
    return HttpResponse(None, {}, "", error=last_error, url=url)


def _is_retryable_transport_error(error: str) -> bool:
    lowered = error.lower()
    return any(
        marker in lowered
        for marker in ["unexpected_eof", "eof occurred", "timed out", "connection reset"]
    )


def _generic_error(provider: str, response: HttpResponse) -> tuple[str, str, dict[str, Any]]:
    status = "rate-limited" if response.status == 429 else "failed"
    error = response.error or f"{provider} HTTP status {response.status}"
    diagnostics = {
        "http_status": response.status,
        "classification": "rate_limited" if response.status == 429 else "http_or_transport_error",
        "response_snippet": _snippet(response.text),
    }
    return status, error, diagnostics


def _pubmed_diagnostics(response: HttpResponse, classification: str, stage: str) -> dict[str, Any]:
    return {
        "stage": stage,
        "classification": classification,
        "http_status": response.status,
        "content_type": _content_type(response),
        "response_snippet": _snippet(response.text),
    }


def _execution_status(source_status: dict[str, str], total: int) -> str:
    statuses = set(source_status.values())
    failed_only = {"failed", "rate-limited", "not-run", "configuration_required"}
    if statuses and statuses <= failed_only:
        return "failed"
    if total == 0:
        return "no_results"
    if statuses & {"failed", "rate-limited", "partial", "configuration_required"}:
        return "partial"
    return "success"


def _normalize_record(
    *,
    raw: dict[str, Any],
    provider: str,
    rank: int,
    run_id: str,
    query_id: str,
    iteration: int,
    executable_query: str,
) -> dict[str, Any]:
    provider_record_id = str(raw.get("provider_record_id") or raw.get("doi") or raw.get("url") or f"{provider}:{rank}")
    return {
        **raw,
        "source_provider": provider,
        "source_record_id": provider_record_id,
        "provider_record_id": provider_record_id,
        "rank": rank,
        "retrieval_page": 1,
        "query_text": executable_query,
        "run_id": run_id,
        "query_id": query_id,
        "iteration": iteration,
        "retrieved_at": _now(),
        "document_type": raw.get("document_type"),
        "language": raw.get("language"),
    }


def _load_queries_ref(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    value = _read_json(path)
    if isinstance(value, list):
        return [dict(row) for row in value if isinstance(row, dict)]
    return []


def _terms(canonical: dict[str, Any], key: str, *, limit: int) -> list[str]:
    values = canonical.get(key)
    if not isinstance(values, list):
        return []
    return [str(value) for value in values if str(value).strip()][:limit]


def _plain_term(term: str) -> str:
    return " ".join(term.replace("*", "").replace('"', "").split())


def _truncate_query(query: str, limit: int) -> str:
    query = " ".join(query.split())
    if len(query) > limit and " " in query[:limit]:
        return query[:limit].rsplit(" ", 1)[0]
    return query[:limit]


def _wants_articles(document_types: list[str]) -> bool:
    text = " ".join(document_types).lower()
    return not text or "article" in text


def _date_filter(name: str, value: str) -> str:
    return f"{name}:{value}" if value else ""


def _join_filters(parts: list[str]) -> str:
    return ",".join(part for part in parts if part)


def _year_filter(date_from: str, date_to: str) -> str:
    start = date_from[:4] if date_from else ""
    end = date_to[:4] if date_to else ""
    if start and end:
        return f"{start}-{end}"
    return start or end


def _url(base: str, params: dict[str, Any]) -> str:
    clean = {key: value for key, value in params.items() if value not in {None, ""}}
    return base + "?" + urllib.parse.urlencode(clean)


def _sanitize_params(params: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(params)
    for secret in ["api_key", "email", "mailto"]:
        if sanitized.get(secret):
            sanitized[secret] = "configured"
    return sanitized


def _drop_internal(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if not key.startswith("_")}


def _dedupe_key(*values: Any) -> str:
    for value in values:
        if value:
            return _normalize_doi(value) or str(value).strip().lower()
    return ""


def _content_type(response: HttpResponse) -> str:
    for key, value in response.headers.items():
        if key.lower() == "content-type":
            return value
    return ""


def _snippet(text: str, limit: int = 240) -> str:
    return " ".join((text or "").split())[:limit]


def _strip_markup(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value or "").replace("  ", " ").strip()


def _first_text(value: Any) -> str:
    if isinstance(value, list) and value:
        return _strip_markup(str(value[0]))
    return _strip_markup(str(value or ""))


def _normalize_doi(value: Any) -> str:
    doi = str(value or "").strip()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE)
    return doi.lower()


def _year_from_date_parts(value: Any) -> str:
    try:
        return str(value["date-parts"][0][0])
    except (KeyError, IndexError, TypeError):
        return ""


def _inverted_index_to_text(index: Any) -> str:
    if not isinstance(index, dict):
        return ""
    pairs: list[tuple[int, str]] = []
    for word, positions in index.items():
        if isinstance(positions, list):
            pairs.extend((position, str(word)) for position in positions if isinstance(position, int))
    return " ".join(word for _, word in sorted(pairs))


def _xml_text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return "".join(node.itertext()).strip()


def _read_json(path: Path) -> dict[str, Any] | list[Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    tmp.replace(path)


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
