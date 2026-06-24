"""Literature source registry and routing policy."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    name: str
    tier: str
    api_backed: bool
    notes: str


SOURCES: dict[str, Source] = {
    "crossref": Source("crossref", "T1", True, "Cross-disciplinary DOI metadata."),
    "pubmed": Source("pubmed", "T1", True, "Biomedical/life-science metadata; not implemented locally yet."),
    "openalex": Source("openalex", "T1_fallback", True, "Public metadata index covering many CrossRef/PubMed/arXiv works."),
    "semantic_scholar": Source("semantic_scholar", "T2", True, "Citation graph and abstracts; rate limited without key."),
    "google_scholar": Source("google_scholar", "T3", False, "Manual last resort only."),
}


def ordered_sources(requested: list[str] | None = None) -> list[Source]:
    if requested:
        return [SOURCES[name] for name in requested if name in SOURCES]
    return [SOURCES["crossref"], SOURCES["openalex"]]
