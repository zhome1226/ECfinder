from __future__ import annotations

import json
import urllib.parse
from pathlib import Path
from typing import Any

import pytest

from ecfinder.skills.external_metadata_discovery import runner


class FakeHTTP:
    def __init__(self, responses: list[runner.HttpResponse]) -> None:
        self.responses = responses
        self.urls: list[str] = []
        self.headers: list[dict[str, str]] = []

    def json(self, url: str, headers: dict[str, str]) -> runner.HttpResponse:
        self.urls.append(url)
        self.headers.append(headers)
        response = self.responses.pop(0)
        if isinstance(response.payload, str):
            return runner.HttpResponse(response.status, response.headers, response.payload, json.loads(response.payload), response.error, url)
        return runner.HttpResponse(response.status, response.headers, response.text, response.payload, response.error, url)

    def text(self, url: str, headers: dict[str, str]) -> runner.HttpResponse:
        self.urls.append(url)
        self.headers.append(headers)
        response = self.responses.pop(0)
        return runner.HttpResponse(response.status, response.headers, response.text, response.payload, response.error, url)


def canonical() -> dict[str, Any]:
    return {
        "emerging_contaminant_terms": [
            "emerging contaminant*",
            "contaminant* of emerging concern",
            "micropollutant*",
            "emerging pollutant*",
        ],
        "surface_water_terms": ["river", "lake", "estuary"],
        "monitoring_and_concentration_terms": ["monitoring", "concentration"],
    }


def context() -> dict[str, Any]:
    return {
        "canonical_query": canonical(),
        "row": {"query_text": '("emerging contaminant*" OR "micropollutant*") AND ("river")'},
        "date_from": "2006-01-01",
        "date_to": "2026-07-10",
        "document_types": ["journal article", "research article"],
    }


def test_crossref_review_artifact_is_excluded_and_article_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "message": {
            "items": [
                {"DOI": "10.1039/x/v1/review1", "title": ["Review for paper"], "type": "peer-review"},
                {
                    "DOI": "10.1000/article",
                    "title": ["Emerging contaminants in rivers"],
                    "type": "journal-article",
                    "language": "en",
                    "published": {"date-parts": [[2024]]},
                },
            ]
        }
    }
    fake = FakeHTTP([runner.HttpResponse(200, {"content-type": "application/json"}, "", payload)])
    monkeypatch.setattr(runner, "_http_json", fake.json)
    provider = runner.CrossrefProvider()
    result = provider.execute(provider.compile_request(context(), 1), 1)

    assert result.status == "success"
    assert len(result.records) == 1
    assert result.excluded_counts == {"crossref_peer_review_or_posted_content": 1}
    normalized = provider.normalize_record(result.records[0])
    assert normalized["document_type"] == "journal-article"
    assert normalized["language"] == "en"


def test_crossref_select_omits_unsupported_language_and_subject() -> None:
    provider = runner.CrossrefProvider()
    request = provider.compile_request(context(), 2)
    select = request.params["select"]
    assert "language" not in select
    assert "subject" not in select
    assert "type" in select


def test_openalex_uses_short_chunks_not_raw_boolean_and_dedupes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    provider = runner.OpenAlexProvider()
    request = provider.compile_request(context(), 3)
    raw_boolean = context()["row"]["query_text"]
    assert raw_boolean not in request.query
    assert all(" OR " not in chunk["query"] for chunk in request.chunks)

    payload1 = {
        "results": [
            {"id": "https://openalex.org/W1", "doi": "https://doi.org/10.1/a", "title": "A", "type": "article", "language": "en"}
        ]
    }
    payload2 = {
        "results": [
            {"id": "https://openalex.org/W1", "doi": "https://doi.org/10.1/a", "title": "A duplicate", "type": "article", "language": "en"},
            {"id": "https://openalex.org/W2", "doi": "https://doi.org/10.1/b", "title": "B", "type": "article", "language": "fr"},
        ]
    }
    fake = FakeHTTP(
        [
            runner.HttpResponse(200, {"content-type": "application/json"}, "", payload1),
            runner.HttpResponse(200, {"content-type": "application/json"}, "", payload2),
            runner.HttpResponse(200, {"content-type": "application/json"}, "", {"results": []}),
        ]
    )
    monkeypatch.setattr(runner, "_http_json", fake.json)
    result = provider.execute(request, 3)
    assert result.status == "success"
    assert len(result.records) == 2
    assert all("%28%22" not in urllib.parse.urlparse(url).query for url in fake.urls)


def test_semantic_scholar_bad_request_is_not_no_results(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeHTTP([runner.HttpResponse(400, {"content-type": "application/json"}, '{"error":"bad query"}')])
    monkeypatch.setattr(runner, "_http_json", fake.json)
    provider = runner.SemanticScholarProvider()
    result = provider.execute(provider.compile_request(context(), 2), 2)
    assert result.status == "failed"
    assert result.diagnostics["classification"] == "request_syntax_error"


def test_semantic_scholar_429_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeHTTP(
        [
            runner.HttpResponse(429, {"Retry-After": "0"}, ""),
            runner.HttpResponse(429, {"Retry-After": "0"}, ""),
            runner.HttpResponse(200, {"content-type": "application/json"}, "", {"data": []}),
        ]
    )
    monkeypatch.setattr(runner, "_http_json", fake.json)
    monkeypatch.setattr(runner.time, "sleep", lambda _seconds: None)
    provider = runner.SemanticScholarProvider()
    result = provider.execute(provider.compile_request(context(), 2), 2)
    assert len(fake.urls) == 3
    assert result.status == "no-results"


def test_pubmed_json_esearch_and_xml_efetch_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NCBI_EMAIL", "configured@example.invalid")
    monkeypatch.setenv("NCBI_TOOL", "ECMonitor")
    esearch = runner.HttpResponse(
        200,
        {"content-type": "application/json"},
        '{"esearchresult":{"idlist":["123"]}}',
    )
    efetch = runner.HttpResponse(
        200,
        {"content-type": "text/xml"},
        """
        <PubmedArticleSet><PubmedArticle><MedlineCitation>
        <PMID>123</PMID><Article><ArticleTitle>PFAS in river water</ArticleTitle>
        <Abstract><AbstractText>Measured concentrations.</AbstractText></Abstract>
        <Journal><Title>Water Research</Title><JournalIssue><PubDate><Year>2024</Year></PubDate></JournalIssue></Journal>
        <Language>eng</Language><PublicationTypeList><PublicationType>Journal Article</PublicationType></PublicationTypeList>
        <AuthorList><Author><ForeName>Ada</ForeName><LastName>Lovelace</LastName></Author></AuthorList>
        </Article></MedlineCitation><PubmedData><ArticleIdList><ArticleId IdType="doi">10.1/pub</ArticleId></ArticleIdList></PubmedData>
        </PubmedArticle></PubmedArticleSet>
        """,
    )
    fake = FakeHTTP([esearch, efetch])
    monkeypatch.setattr(runner, "_http_text", fake.text)
    provider = runner.PubMedProvider()
    result = provider.execute(provider.compile_request(context(), 1), 1)
    assert result.status == "success"
    normalized = provider.normalize_record(result.records[0])
    assert normalized["document_type"] == "Journal Article"
    assert normalized["language"] == "eng"


def test_pubmed_filters_publication_types_after_efetch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NCBI_EMAIL", "configured@example.invalid")
    monkeypatch.setenv("NCBI_TOOL", "ECMonitor")
    esearch = runner.HttpResponse(
        200,
        {"content-type": "application/json"},
        '{"esearchresult":{"idlist":["123","456"]}}',
    )
    efetch = runner.HttpResponse(
        200,
        {"content-type": "text/xml"},
        """
        <PubmedArticleSet>
        <PubmedArticle><MedlineCitation>
        <PMID>123</PMID><Article><ArticleTitle>Dataset only</ArticleTitle>
        <Abstract><AbstractText>Dataset record.</AbstractText></Abstract>
        <Journal><Title>Scientific Data</Title><JournalIssue><PubDate><Year>2025</Year></PubDate></JournalIssue></Journal>
        <Language>eng</Language><PublicationTypeList><PublicationType>Dataset</PublicationType></PublicationTypeList>
        </Article></MedlineCitation></PubmedArticle>
        <PubmedArticle><MedlineCitation>
        <PMID>456</PMID><Article><ArticleTitle>Article record</ArticleTitle>
        <Abstract><AbstractText>Article record.</AbstractText></Abstract>
        <Journal><Title>Water Research</Title><JournalIssue><PubDate><Year>2026</Year></PubDate></JournalIssue></Journal>
        <Language>eng</Language><PublicationTypeList><PublicationType>Journal Article</PublicationType><PublicationType>Dataset</PublicationType></PublicationTypeList>
        </Article></MedlineCitation></PubmedArticle>
        </PubmedArticleSet>
        """,
    )
    fake = FakeHTTP([esearch, efetch])
    monkeypatch.setattr(runner, "_http_text", fake.text)
    provider = runner.PubMedProvider()
    result = provider.execute(provider.compile_request(context(), 2), 2)
    assert result.status == "success"
    assert len(result.records) == 1
    assert result.records[0]["provider_record_id"] == "456"
    assert result.records[0]["document_type"] == "Journal Article"


def test_pubmed_blocked_html_retries_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NCBI_EMAIL", "configured@example.invalid")
    monkeypatch.setenv("NCBI_TOOL", "ECMonitor")
    monkeypatch.setenv("NCBI_API_KEY", "secret")
    blocked = runner.HttpResponse(
        200,
        {"content-type": "text/html"},
        "<html><title>NCBI - WWW Error Blocked Diagnostic</title></html>",
    )
    esearch = runner.HttpResponse(
        200,
        {"content-type": "application/json"},
        '{"esearchresult":{"idlist":[]}}',
    )
    fake = FakeHTTP([blocked, esearch])
    monkeypatch.setattr(runner, "_http_text", fake.text)
    provider = runner.PubMedProvider()
    result = provider.execute(provider.compile_request(context(), 1), 1)
    assert result.status == "no-results"
    assert len(fake.urls) == 2
    assert "api_key=" in fake.urls[0]
    assert "api_key=" not in fake.urls[1]


def test_pubmed_blocked_eutilities_uses_web_html_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NCBI_EMAIL", "configured@example.invalid")
    monkeypatch.setenv("NCBI_TOOL", "ECMonitor")
    blocked = runner.HttpResponse(
        200,
        {"content-type": "text/html"},
        "<html><title>NCBI - WWW Error Blocked Diagnostic</title></html>",
    )
    html = runner.HttpResponse(
        200,
        {"content-type": "text/html"},
        """
        <div class="docsum-content">
          <a class="docsum-title" href="/33839659/" data-article-id="33839659">
            Occurrence of emerging contaminants in river water.
          </a>
          <div class="docsum-citation full-citation">Water Res. 2021.</div>
          <span class="docsum-authors full-authors">Biswas P, Vellanki BP.</span>
        </div>
        <div class="result-actions-bar bottom-bar"></div>
        """,
    )
    fake = FakeHTTP([blocked, blocked, html, blocked])
    monkeypatch.setattr(runner, "_http_text", fake.text)
    provider = runner.PubMedProvider()

    result = provider.execute(provider.compile_request(context(), 1), 1)

    assert result.status == "partial"
    assert result.diagnostics["fallback"] == "pubmed_web_html"
    assert result.records[0]["provider_record_id"] == "33839659"
    assert result.records[0]["document_type"] == "Journal Article"


def test_pubmed_web_fallback_tries_broader_queries_when_strict_query_has_no_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NCBI_EMAIL", "configured@example.invalid")
    monkeypatch.setenv("NCBI_TOOL", "ECMonitor")
    blocked = runner.HttpResponse(
        200,
        {"content-type": "text/html"},
        "<html><title>NCBI - WWW Error Blocked Diagnostic</title></html>",
    )
    empty_html = runner.HttpResponse(200, {"content-type": "text/html"}, "<html></html>")
    hit_html = runner.HttpResponse(
        200,
        {"content-type": "text/html"},
        """
        <div class="docsum-content">
          <a class="docsum-title" href="/33839659/" data-article-id="33839659">
            Occurrence of emerging contaminants in river water.
          </a>
          <div class="docsum-citation full-citation">Water Res. 2021.</div>
        </div>
        <div class="result-actions-bar bottom-bar"></div>
        """,
    )
    fake = FakeHTTP([blocked, blocked, empty_html, hit_html, blocked])
    monkeypatch.setattr(runner, "_http_text", fake.text)

    provider = runner.PubMedProvider()
    result = provider.execute(provider.compile_request(context(), 1), 1)

    assert result.status == "partial"
    assert result.records[0]["provider_record_id"] == "33839659"
    assert result.diagnostics["web_query"] == "emerging contaminants river concentration"


@pytest.mark.parametrize(
    ("body", "content_type", "classification"),
    [
        ("", "application/json", "empty_response"),
        ("<html>error</html>", "text/html", "html_response"),
    ],
)
def test_pubmed_html_or_empty_response_is_clear_error(
    monkeypatch: pytest.MonkeyPatch, body: str, content_type: str, classification: str
) -> None:
    monkeypatch.setenv("NCBI_EMAIL", "configured@example.invalid")
    fake = FakeHTTP([runner.HttpResponse(200, {"content-type": content_type}, body)])
    monkeypatch.setattr(runner, "_http_text", fake.text)
    provider = runner.PubMedProvider()
    result = provider.execute(provider.compile_request(context(), 1), 1)
    assert result.status == "failed"
    assert result.diagnostics["classification"] == classification


def test_run_skill_preserves_missing_document_type_and_language(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    queries_ref = tmp_path / "queries.json"
    queries_ref.write_text(json.dumps([{"provider": "crossref", "query_text": "raw"}]), encoding="utf-8")
    payload = {"message": {"items": [{"DOI": "10.1/a", "title": ["A"], "published": {"date-parts": [[2024]]}}]}}
    fake = FakeHTTP([runner.HttpResponse(200, {"content-type": "application/json"}, "", payload)])
    monkeypatch.setattr(runner, "_http_json", fake.json)
    output = tmp_path / "result.json"
    result = runner.run_skill(
        {
            "skill_id": "external_metadata_discovery_v1",
            "run_id": "run",
            "query_id": "Q0001",
            "iteration": 1,
            "output_root": str(tmp_path / "out"),
            "queries_ref": str(queries_ref),
            "providers": ["crossref"],
            "max_candidates": 1,
            "page_size": 1,
            "max_scan_depth_per_provider": 1,
            "canonical_query": canonical(),
            "date_from": "2006-01-01",
            "date_to": "2026-07-10",
            "document_types": ["journal article"],
        },
        output,
    )
    page = Path(result["provider_page_refs"]["crossref"][0])
    record = json.loads(page.read_text(encoding="utf-8").strip())
    assert record["document_type"] is None
    assert record["language"] is None


def test_provider_health_check_reports_configuration_without_secret_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NCBI_EMAIL", "configured@example.invalid")
    monkeypatch.setenv("NCBI_TOOL", "ECMonitor")
    monkeypatch.setenv("NCBI_API_KEY", "secret")
    monkeypatch.setenv("OPENALEX_API_KEY", "secret")
    monkeypatch.setenv("CROSSREF_MAILTO", "configured@example.invalid")
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)

    class FakeProvider:
        name = "crossref"

        def compile_request(self, context: dict[str, Any], limit: int) -> runner.ProviderRequest:
            return runner.ProviderRequest(
                provider="crossref",
                url="https://example.invalid/?api_key=secret",
                sanitized_url="https://example.invalid/?api_key=configured",
                query="health",
                params={"api_key": "secret"},
                sanitized_params={"api_key": "configured"},
            )

        def execute(
            self, request: runner.ProviderRequest, limit: int
        ) -> runner.ProviderResult:
            return runner.ProviderResult(
                "crossref",
                [{"title": "ok"}],
                "success",
                diagnostics={"http_status": 200},
            )

        def normalize_record(self, raw: dict[str, Any]) -> dict[str, Any]:
            return raw

        def classify_error(
            self, response: runner.HttpResponse
        ) -> tuple[str, str, dict[str, Any]]:
            return "failed", "failed", {}

    monkeypatch.setattr(runner, "_provider_implementations", lambda: {"crossref": FakeProvider()})
    result = runner.provider_health_check(["crossref", "semantic_scholar"])
    dumped = json.dumps(result, sort_keys=True)
    assert result["environment_validation"]["NCBI_EMAIL"] == "configured"
    assert result["environment_validation"]["SEMANTIC_SCHOLAR_API_KEY"] == "missing"
    assert result["providers"]["crossref"]["connectivity"] == "connected"
    assert result["providers"]["crossref"]["authentication"] == "configured"
    assert result["providers"]["crossref"]["api_response_status"] == "200"
    assert result["providers"]["semantic_scholar"]["status"] == "not-run"
    assert "secret" not in dumped
    assert "configured@example.invalid" not in dumped
