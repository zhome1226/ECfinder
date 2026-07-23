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


def pfas_canonical() -> dict[str, Any]:
    return {
        "emerging_contaminant_terms": [
            "emerging contaminant*",
            "contaminant* of emerging concern",
            "micropollutant*",
            "PFAS",
            "per- and polyfluoroalkyl substances",
            "perfluoroalkyl substances",
            "fluorinated surfactant*",
        ],
        "surface_water_terms": ["surface water", "river", "lake", "estuary"],
        "monitoring_and_concentration_terms": ["monitoring", "occurrence", "concentration"],
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


def test_crossref_filters_review_like_journal_article(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "message": {
            "items": [
                {
                    "DOI": "10.1000/review-article",
                    "title": ["Ibuprofen as an Emerging Contaminant of Concern"],
                    "abstract": "This review aims to inform the current status of ibuprofen research.",
                    "type": "journal-article",
                },
                {
                    "DOI": "10.1000/field-article",
                    "title": ["Emerging contaminants in river water"],
                    "abstract": "Field monitoring measured concentrations in river water.",
                    "type": "journal-article",
                },
            ]
        }
    }
    fake = FakeHTTP([runner.HttpResponse(200, {"content-type": "application/json"}, "", payload)])
    monkeypatch.setattr(runner, "_http_json", fake.json)

    provider = runner.CrossrefProvider()
    result = provider.execute(provider.compile_request(context(), 1), 1)

    assert result.status == "success"
    assert result.excluded_counts == {"crossref_review_article": 1}
    assert result.records[0]["DOI"] == "10.1000/field-article"


def test_crossref_filters_ineligible_food_matrix(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "message": {
            "items": [
                {
                    "DOI": "10.1000/food",
                    "title": ["Perchlorate an Emerging Contaminant in Foodstuff and Environment"],
                    "abstract": "Samples included fruit and vegetables, dried spices, cereals and infant formula.",
                    "type": "journal-article",
                },
                {
                    "DOI": "10.1000/river",
                    "title": ["Emerging contaminants in river water"],
                    "abstract": "Measured concentrations in river water samples.",
                    "type": "journal-article",
                },
            ]
        }
    }
    fake = FakeHTTP([runner.HttpResponse(200, {"content-type": "application/json"}, "", payload)])
    monkeypatch.setattr(runner, "_http_json", fake.json)

    provider = runner.CrossrefProvider()
    result = provider.execute(provider.compile_request(context(), 1), 1)

    assert result.status == "success"
    assert result.excluded_counts == {"ineligible_food_matrix": 1}
    assert result.records[0]["DOI"] == "10.1000/river"


def test_crossref_applies_canonical_negative_terms_client_side(monkeypatch: pytest.MonkeyPatch) -> None:
    negative_context = context()
    negative_context["canonical_query"] = {
        **canonical(),
        "prohibited_or_rejected_terms": ["constructed wetlands"],
    }
    payload = {
        "message": {
            "items": [
                {
                    "DOI": "10.1000/wetland-treatment",
                    "title": ["Emerging contaminants in constructed wetlands"],
                    "abstract": "Treatment performance for constructed wetlands.",
                    "type": "journal-article",
                },
                {
                    "DOI": "10.1000/river",
                    "title": ["Emerging contaminants in river water"],
                    "abstract": "Measured concentrations in river water samples.",
                    "type": "journal-article",
                },
            ]
        }
    }
    fake = FakeHTTP([runner.HttpResponse(200, {"content-type": "application/json"}, "", payload)])
    monkeypatch.setattr(runner, "_http_json", fake.json)

    provider = runner.CrossrefProvider()
    request = provider.compile_request(negative_context, 1)
    result = provider.execute(request, 1)

    assert "constructed wetlands" not in request.url
    assert request.executable_request()["params"].get("client_side_negative_terms") is None
    assert result.records[0]["DOI"] == "10.1000/river"
    assert result.excluded_counts == {"client_side_negative_term": 1}
    assert result.diagnostics["client_side_negative_terms"] == ["constructed wetlands"]


def test_crossref_filters_editorial_article(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "message": {
            "items": [
                {
                    "DOI": "10.1000/editorial",
                    "title": ["Inaugural Editorial: Uniting forces to curb emerging contaminant risks"],
                    "abstract": "Editorial introduction.",
                    "type": "journal-article",
                },
                {
                    "DOI": "10.1000/river",
                    "title": ["Emerging contaminants in river water"],
                    "abstract": "Measured concentrations in river water samples.",
                    "type": "journal-article",
                },
            ]
        }
    }
    fake = FakeHTTP([runner.HttpResponse(200, {"content-type": "application/json"}, "", payload)])
    monkeypatch.setattr(runner, "_http_json", fake.json)

    provider = runner.CrossrefProvider()
    result = provider.execute(provider.compile_request(context(), 1), 1)

    assert result.status == "success"
    assert result.excluded_counts == {"crossref_editorial_article": 1}
    assert result.records[0]["DOI"] == "10.1000/river"


def test_provider_queries_prefer_specific_surface_water_over_broad_ocean_terms() -> None:
    broad_context = context()
    broad_context["canonical_query"] = {
        **canonical(),
        "surface_water_terms": [
            "ocean",
            "open ocean",
            "sea",
            "river",
            "lake",
            "ambient surface water",
        ],
    }

    crossref_request = runner.CrossrefProvider().compile_request(broad_context, 2)
    openalex_request = runner.OpenAlexProvider().compile_request(broad_context, 2)
    semantic_request = runner.SemanticScholarProvider().compile_request(broad_context, 2)

    assert "river" in crossref_request.query
    assert "ocean" not in crossref_request.query
    assert any("river" in chunk["query"] for chunk in openalex_request.chunks)
    assert "ocean" not in " ".join(chunk["query"] for chunk in openalex_request.chunks)
    assert "river" in semantic_request.query
    assert "ocean" not in semantic_request.query


def test_provider_queries_include_later_pollutant_family_terms() -> None:
    pfas_context = context()
    pfas_context["canonical_query"] = pfas_canonical()

    crossref_request = runner.CrossrefProvider().compile_request(pfas_context, 5)
    openalex_request = runner.OpenAlexProvider().compile_request(pfas_context, 5)
    semantic_request = runner.SemanticScholarProvider().compile_request(pfas_context, 5)
    pubmed_request = runner.PubMedProvider().compile_request(pfas_context, 5)

    assert "PFAS" in crossref_request.query
    assert any("PFAS" in chunk["query"] for chunk in openalex_request.chunks)
    assert "PFAS" in semantic_request.query
    assert '"PFAS"[Title/Abstract]' in pubmed_request.query
    assert "per- and polyfluoroalkyl substances" in pubmed_request.query


def test_openalex_uses_short_chunks_not_raw_boolean_and_dedupes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    provider = runner.OpenAlexProvider()
    request = provider.compile_request(context(), 3)
    raw_boolean = context()["row"]["query_text"]
    assert raw_boolean not in request.query
    assert all(" OR " not in chunk["query"] for chunk in request.chunks)

    abstract = {"Measured": [0], "concentrations": [1], "in": [2], "river": [3], "water": [4]}
    payload1 = {
        "results": [
            {
                "id": "https://openalex.org/W1",
                "doi": "https://doi.org/10.1/a",
                "title": "Emerging contaminants in river water",
                "abstract_inverted_index": abstract,
                "type": "article",
                "language": "en",
            }
        ]
    }
    payload2 = {
        "results": [
            {
                "id": "https://openalex.org/W1",
                "doi": "https://doi.org/10.1/a",
                "title": "Emerging contaminants in river water duplicate",
                "abstract_inverted_index": abstract,
                "type": "article",
                "language": "en",
            },
            {
                "id": "https://openalex.org/W2",
                "doi": "https://doi.org/10.1/b",
                "title": "Emerging pollutants in lake water",
                "abstract_inverted_index": abstract,
                "type": "article",
                "language": "fr",
            },
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


def test_openalex_filters_review_and_missing_surface_water_signal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = runner.OpenAlexProvider()
    request = provider.compile_request(context(), 2)
    payload = {
        "results": [
            {
                "id": "https://openalex.org/Wreview",
                "doi": "https://doi.org/10.1/review",
                "title": "Microbial Degradation of Petroleum Hydrocarbon Contaminants: An Overview",
                "abstract_inverted_index": {"This": [0], "overview": [1], "soil": [2]},
                "type": "article",
                "language": "en",
            },
            {
                "id": "https://openalex.org/Wnosignal",
                "doi": "https://doi.org/10.1/nosignal",
                "title": "Present and Future of Surface-Enhanced Raman Scattering",
                "abstract_inverted_index": {"This": [0], "Review": [1], "spectroscopy": [2]},
                "type": "article",
                "language": "en",
            },
            {
                "id": "https://openalex.org/Wfield",
                "doi": "https://doi.org/10.1/field",
                "title": "Emerging contaminants in river water",
                "abstract_inverted_index": {
                    "Measured": [0],
                    "concentrations": [1],
                    "in": [2],
                    "river": [3],
                    "water": [4],
                },
                "type": "article",
                "language": "en",
            },
        ]
    }
    fake = FakeHTTP([runner.HttpResponse(200, {"content-type": "application/json"}, "", payload)])
    monkeypatch.setattr(runner, "_http_json", fake.json)

    result = provider.execute(request, 1)

    assert result.status == "success"
    assert result.records[0]["id"] == "https://openalex.org/Wfield"
    assert result.diagnostics["excluded_counts"] == {
        "ineligible_solid_matrix": 1,
        "openalex_review_article": 1,
    }


def test_openalex_filters_ineligible_treatment_water_matrix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = runner.OpenAlexProvider()
    request = provider.compile_request(context(), 1)
    payload = {
        "results": [
            {
                "id": "https://openalex.org/Wdrinking",
                "doi": "https://doi.org/10.1/drinking",
                "title": "Contaminants of emerging concern in source and treated drinking waters",
                "abstract_inverted_index": {
                    "drinking": [0],
                    "water": [1],
                    "treatment": [2],
                    "plants": [3],
                    "detected": [4],
                },
                "type": "article",
                "language": "en",
            },
            {
                "id": "https://openalex.org/Wriver",
                "doi": "https://doi.org/10.1/river",
                "title": "Contaminants of emerging concern in receiving river water",
                "abstract_inverted_index": {
                    "Measured": [0],
                    "concentrations": [1],
                    "in": [2],
                    "river": [3],
                    "water": [4],
                },
                "type": "article",
                "language": "en",
            },
        ]
    }
    fake = FakeHTTP([runner.HttpResponse(200, {"content-type": "application/json"}, "", payload)])
    monkeypatch.setattr(runner, "_http_json", fake.json)

    result = provider.execute(request, 1)

    assert result.status == "success"
    assert result.records[0]["id"] == "https://openalex.org/Wriver"
    assert result.diagnostics["excluded_counts"] == {
        "ineligible_drinking_or_treatment_water": 1,
    }


def test_openalex_applies_negative_terms_after_source_specific_retrieval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    negative_context = context()
    negative_context["canonical_query"] = {
        **canonical(),
        "prohibited_or_rejected_terms": ["fish"],
    }
    provider = runner.OpenAlexProvider()
    request = provider.compile_request(negative_context, 1)
    abstract = {
        "Measured": [0],
        "concentrations": [1],
        "in": [2],
        "river": [3],
        "water": [4],
    }
    payload = {
        "results": [
            {
                "id": "https://openalex.org/Wfish",
                "doi": "https://doi.org/10.1/fish",
                "title": "Emerging contaminants in river fish",
                "abstract_inverted_index": abstract,
                "type": "article",
                "language": "en",
            },
            {
                "id": "https://openalex.org/Wriver",
                "doi": "https://doi.org/10.1/river",
                "title": "Emerging contaminants in river water",
                "abstract_inverted_index": abstract,
                "type": "article",
                "language": "en",
            },
        ]
    }
    fake = FakeHTTP([runner.HttpResponse(200, {"content-type": "application/json"}, "", payload)])
    monkeypatch.setattr(runner, "_http_json", fake.json)

    result = provider.execute(request, 1)

    assert "fish" not in request.url
    assert request.chunks[0]["client_side_negative_terms"] == ["fish"]
    assert result.records[0]["id"] == "https://openalex.org/Wriver"
    assert result.diagnostics["excluded_counts"] == {"client_side_negative_term": 1}


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


def test_semantic_scholar_review_and_matrix_records_are_filtered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "data": [
            {
                "paperId": "review",
                "title": "PFAS as a contaminant of emerging concern in surface water: a review",
                "abstract": "This review summarizes occurrence in surface water.",
                "publicationTypes": ["Review"],
            },
            {
                "paperId": "drinking",
                "title": "Emerging contaminants in drinking water",
                "abstract": "Measured concentrations in drinking water treatment plants.",
                "publicationTypes": ["JournalArticle"],
            },
            {
                "paperId": "river",
                "title": "Emerging contaminants in river surface water",
                "abstract": "Measured concentrations and occurrence in river water.",
                "publicationTypes": ["JournalArticle"],
                "externalIds": {"DOI": "10.1/river"},
            },
        ]
    }
    fake = FakeHTTP([runner.HttpResponse(200, {"content-type": "application/json"}, "", payload)])
    monkeypatch.setattr(runner, "_http_json", fake.json)

    provider = runner.SemanticScholarProvider()
    result = provider.execute(provider.compile_request(context(), 1), 1)

    assert result.status == "success"
    assert result.records[0]["paperId"] == "river"
    assert result.excluded_counts == {
        "semantic_scholar_ineligible_publication_type": 1,
        "ineligible_drinking_or_treatment_water": 1,
    }


def test_semantic_scholar_applies_negative_terms_without_query_pollution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    negative_context = context()
    negative_context["canonical_query"] = {
        **canonical(),
        "prohibited_or_rejected_terms": ["resource recovery"],
    }
    payload = {
        "data": [
            {
                "paperId": "recovery",
                "title": "Resource recovery from emerging contaminant treatment in river water",
                "abstract": "Resource recovery process measured concentrations in river water.",
                "publicationTypes": ["JournalArticle"],
            },
            {
                "paperId": "river",
                "title": "Emerging contaminants in river surface water",
                "abstract": "Measured concentrations and occurrence in river water.",
                "publicationTypes": ["JournalArticle"],
            },
        ]
    }
    fake = FakeHTTP([runner.HttpResponse(200, {"content-type": "application/json"}, "", payload)])
    monkeypatch.setattr(runner, "_http_json", fake.json)

    provider = runner.SemanticScholarProvider()
    request = provider.compile_request(negative_context, 1)
    result = provider.execute(request, 1)

    assert "resource+recovery" not in request.url
    assert request.sanitized_params["client_side_negative_terms"] == ["resource recovery"]
    assert result.records[0]["paperId"] == "river"
    assert result.excluded_counts == {"client_side_negative_term": 1}


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
    detail = runner.HttpResponse(
        200,
        {"content-type": "text/html"},
        """
        <html lang="en">
          <meta name="description" content="Detailed PubMed abstract text.">
          <meta name="keywords" content="pmid:33839659, doi:10.1000/example, Rivers, Water Pollutants">
          <button class="journal-actions-trigger">Water Research</button>
        </html>
        """,
    )
    fake = FakeHTTP([blocked, blocked, html, blocked, detail])
    monkeypatch.setattr(runner, "_http_text", fake.text)
    provider = runner.PubMedProvider()

    result = provider.execute(provider.compile_request(context(), 1), 1)

    assert result.status == "partial"
    assert result.diagnostics["fallback"] == "pubmed_web_html"
    assert result.records[0]["provider_record_id"] == "33839659"
    assert result.records[0]["doi"] == "10.1000/example"
    assert result.records[0]["abstract"] == "Detailed PubMed abstract text."
    assert result.records[0]["language"] == "en"
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
    detail = runner.HttpResponse(
        200,
        {"content-type": "text/html"},
        '<html lang="en"><meta name="description" content="Detailed abstract."></html>',
    )
    fake = FakeHTTP([blocked, blocked, empty_html, hit_html, blocked, detail])
    monkeypatch.setattr(runner, "_http_text", fake.text)

    provider = runner.PubMedProvider()
    result = provider.execute(provider.compile_request(context(), 1), 1)

    assert result.status == "partial"
    assert result.records[0]["provider_record_id"] == "33839659"
    assert result.diagnostics["web_query"] == "emerging contaminants river concentration"


def test_pubmed_web_fallback_continues_after_ineligible_first_hit_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NCBI_EMAIL", "configured@example.invalid")
    monkeypatch.setenv("NCBI_TOOL", "ECMonitor")
    blocked = runner.HttpResponse(
        200,
        {"content-type": "text/html"},
        "<html><title>NCBI - WWW Error Blocked Diagnostic</title></html>",
    )
    review_html = runner.HttpResponse(
        200,
        {"content-type": "text/html"},
        """
        <div class="docsum-content">
          <a class="docsum-title" href="/111/" data-article-id="111">
            A review on environmental monitoring of water organic pollutants identified by EU guidelines.
          </a>
          <div class="docsum-citation full-citation">Water Rev. 2020.</div>
        </div>
        <div class="result-actions-bar bottom-bar"></div>
        """,
    )
    review_detail = runner.HttpResponse(
        200,
        {"content-type": "text/html"},
        """
        <html lang="en">
          <meta name="description" content="This review summarizes environmental monitoring of water organic pollutants.">
        </html>
        """,
    )
    field_html = runner.HttpResponse(
        200,
        {"content-type": "text/html"},
        """
        <div class="docsum-content">
          <a class="docsum-title" href="/222/" data-article-id="222">
            Occurrence of emerging contaminants in highly anthropogenically influenced river Yamuna in India.
          </a>
          <div class="docsum-citation full-citation">Water Res. 2021.</div>
        </div>
        <div class="result-actions-bar bottom-bar"></div>
        """,
    )
    field_detail = runner.HttpResponse(
        200,
        {"content-type": "text/html"},
        """
        <html lang="en">
          <meta name="description" content="Measured concentrations in river water samples.">
          <meta name="keywords" content="doi:10.1000/field, Rivers">
        </html>
        """,
    )
    fake = FakeHTTP([blocked, blocked, review_html, blocked, review_detail, field_html, blocked, field_detail])
    monkeypatch.setattr(runner, "_http_text", fake.text)

    provider = runner.PubMedProvider()
    result = provider.execute(provider.compile_request(context(), 1), 1)

    assert result.status == "partial"
    assert result.records[0]["provider_record_id"] == "222"
    assert result.diagnostics["web_query"] == "emerging contaminants river concentration"


def test_pubmed_web_fallback_filters_review_records(
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
          <a class="docsum-title" href="/111/" data-article-id="111">
            A review on environmental monitoring of water organic pollutants identified by EU guidelines.
          </a>
          <div class="docsum-citation full-citation">Water Rev. 2020.</div>
        </div>
        <div class="result-actions-bar bottom-bar"></div>
        <div class="docsum-content">
          <a class="docsum-title" href="/222/" data-article-id="222">
            Occurrence of contaminants of emerging concern in lake and river water.
          </a>
          <div class="docsum-citation full-citation">Water Res. 2021.</div>
        </div>
        <div class="result-actions-bar bottom-bar"></div>
        """,
    )
    review_detail = runner.HttpResponse(
        200,
        {"content-type": "text/html"},
        """
        <html lang="en">
          <meta name="description" content="This review summarizes environmental monitoring of water organic pollutants.">
        </html>
        """,
    )
    field_detail = runner.HttpResponse(
        200,
        {"content-type": "text/html"},
        """
        <html lang="en">
          <meta name="description" content="Measured concentrations in lake and river water samples.">
          <meta name="keywords" content="doi:10.1000/field, Rivers, Lakes">
        </html>
        """,
    )
    fake = FakeHTTP([blocked, blocked, html, blocked, review_detail, field_detail])
    monkeypatch.setattr(runner, "_http_text", fake.text)

    provider = runner.PubMedProvider()
    result = provider.execute(provider.compile_request(context(), 2), 2)

    assert result.status == "partial"
    assert [record["provider_record_id"] for record in result.records] == ["222"]


def test_pubmed_web_fallback_no_eligible_records_remains_partial(
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
          <a class="docsum-title" href="/111/" data-article-id="111">
            A review on environmental monitoring of water organic pollutants identified by EU guidelines.
          </a>
          <div class="docsum-citation full-citation">Water Rev. 2020.</div>
        </div>
        <div class="result-actions-bar bottom-bar"></div>
        """,
    )
    review_detail = runner.HttpResponse(
        200,
        {"content-type": "text/html"},
        """
        <html lang="en">
          <meta name="description" content="This review summarizes environmental monitoring of water organic pollutants.">
        </html>
        """,
    )
    empty_html = runner.HttpResponse(200, {"content-type": "text/html"}, "<html></html>")
    fake = FakeHTTP(
        [
            blocked,
            blocked,
            html,
            blocked,
            review_detail,
            *[empty_html for _ in range(20)],
        ]
    )
    monkeypatch.setattr(runner, "_http_text", fake.text)

    provider = runner.PubMedProvider()
    result = provider.execute(provider.compile_request(context(), 2), 2)

    assert result.status == "partial"
    assert result.records == []
    assert "no eligible records" in result.error


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


def test_pubmed_misuse_redirect_is_classified_as_ncbi_blocked_html(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NCBI_EMAIL", "configured@example.invalid")
    blocked = runner.HttpResponse(
        200,
        {"content-type": "text/html"},
        "<html><title>NCBI - WWW Error Blocked Diagnostic</title></html>",
        url="https://misuse.ncbi.nlm.nih.gov/error/abuse.shtml?orig_args=/entrez/eutils/esearch.fcgi",
    )
    fake = FakeHTTP([blocked, blocked, blocked, blocked, blocked, blocked])
    monkeypatch.setattr(runner, "_http_text", fake.text)
    monkeypatch.setattr(runner, "_pubmed_html_fallback_search", lambda _request, _limit: None)
    provider = runner.PubMedProvider()

    result = provider.execute(provider.compile_request(context(), 1), 1)

    assert result.status == "failed"
    assert result.diagnostics["classification"] == "ncbi_blocked_html"
    assert result.diagnostics["blocked_by_ncbi"] is True
    assert result.diagnostics["final_url_host"] in {
        "eutils.ncbi.nlm.nih.gov",
        "misuse.ncbi.nlm.nih.gov",
    }
    assert "suggested_action" in result.diagnostics


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


def test_run_skill_persists_multiple_provider_pages_before_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    queries_ref = tmp_path / "queries.json"
    queries_ref.write_text(json.dumps([{"provider": "crossref", "query_text": "raw"}]), encoding="utf-8")
    payload = {
        "message": {
            "items": [
                {"DOI": "10.1/a", "title": ["River A"], "type": "journal-article"},
                {"DOI": "10.1/b", "title": ["River B"], "type": "journal-article"},
            ]
        }
    }
    fake = FakeHTTP([runner.HttpResponse(200, {"content-type": "application/json"}, "", payload)])
    monkeypatch.setattr(runner, "_http_json", fake.json)

    result = runner.run_skill(
        {
            "skill_id": "external_metadata_discovery_v1",
            "run_id": "run",
            "query_id": "Q0001",
            "iteration": 1,
            "output_root": str(tmp_path / "out"),
            "queries_ref": str(queries_ref),
            "providers": ["crossref"],
            "max_candidates": 2,
            "page_size": 1,
            "max_scan_depth_per_provider": 2,
            "canonical_query": canonical(),
            "date_from": "2006-01-01",
            "date_to": "2026-07-10",
            "document_types": ["journal article"],
        },
        tmp_path / "result.json",
    )

    pages = [Path(path) for path in result["provider_page_refs"]["crossref"]]
    assert [page.name for page in pages] == ["crossref_page_0001.jsonl", "crossref_page_0002.jsonl"]
    assert json.loads(pages[0].read_text(encoding="utf-8"))["retrieval_page"] == 1
    assert json.loads(pages[1].read_text(encoding="utf-8"))["retrieval_page"] == 2
    assert result["next_cursor_by_provider"]["crossref"] == "2"


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


def test_crossref_uses_ncbi_email_as_mailto_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CROSSREF_MAILTO", raising=False)
    monkeypatch.setenv("NCBI_EMAIL", "configured@example.invalid")

    request = runner.CrossrefProvider().compile_request(context(), 1)

    assert request.params["mailto"] == "configured@example.invalid"
    assert request.sanitized_params["mailto"] == "configured"
    assert "configured@example.invalid" not in request.sanitized_url
    assert runner._auth_status("crossref") == {"CROSSREF_MAILTO": "configured"}
