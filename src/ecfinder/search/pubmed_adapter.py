"""PubMed metadata adapter."""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
import urllib.parse
import urllib.request

from .common import AdapterResult, USER_AGENT


def _fetch_text(url: str, timeout: int = 20) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def search(query: str, *, max_results: int) -> AdapterResult:
    email = os.environ.get("NCBI_EMAIL", "").strip()
    if not email:
        return AdapterResult(provider="pubmed", records=[], available=False, error="NCBI_EMAIL not configured")
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": str(min(max_results, 50)),
        "retmode": "json",
        "email": email,
    }
    try:
        esearch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?" + urllib.parse.urlencode(params)
        import json

        search_payload = json.loads(_fetch_text(esearch_url))
        ids = search_payload.get("esearchresult", {}).get("idlist", [])
        if not ids:
            return AdapterResult(provider="pubmed", records=[], available=True)
        efetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?" + urllib.parse.urlencode(
            {"db": "pubmed", "id": ",".join(ids), "retmode": "xml", "email": email}
        )
        root = ET.fromstring(_fetch_text(efetch_url))
    except Exception as exc:  # pragma: no cover - network dependent
        return AdapterResult(provider="pubmed", records=[], available=False, error=str(exc))
    records = []
    for article in root.findall(".//PubmedArticle"):
        pmid = "".join(article.findtext(".//PMID") or "")
        title = "".join(article.findtext(".//ArticleTitle") or "")
        abstract = " ".join(node.text or "" for node in article.findall(".//AbstractText"))
        journal = "".join(article.findtext(".//Journal/Title") or "")
        year = "".join(article.findtext(".//PubDate/Year") or "")
        doi = ""
        for aid in article.findall(".//ArticleId"):
            if aid.attrib.get("IdType") == "doi" and aid.text:
                doi = aid.text
        authors = []
        for author in article.findall(".//Author"):
            last = author.findtext("LastName") or ""
            fore = author.findtext("ForeName") or ""
            name = " ".join([fore, last]).strip()
            if name:
                authors.append(name)
        records.append(
            {
                "source_provider": "pubmed",
                "provider_record_id": pmid,
                "doi": doi.lower(),
                "title": title,
                "abstract": abstract,
                "year": year,
                "journal": journal,
                "authors": authors,
                "keywords": [],
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
                "open_access_hint": None,
            }
        )
    return AdapterResult(provider="pubmed", records=[row for row in records if row.get("title")], available=True)
