"""Build and normalize search queries."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ecfinder.utils.hashing import normalize_doi, normalize_title, stable_id


@dataclass(frozen=True)
class QuerySpec:
    query_id: str
    boolean: str
    priority: str = "medium"


DEFAULT_QUERIES = [
    QuerySpec(
        "core_pathway",
        '("PFAS" OR "per- and polyfluoroalkyl substances" OR fluorotelomer) AND (transformation OR degradation OR biotransformation OR "transformation product") AND (environment OR soil OR sediment OR water OR groundwater)',
        "high",
    ),
    QuerySpec(
        "precursor_products",
        '("PFAS precursor" OR fluorotelomer OR FOSA OR FOSE) AND ("transformation product" OR metabolite OR pathway) AND (soil OR sediment OR wastewater OR groundwater OR "surface water")',
        "high",
    ),
    QuerySpec(
        "natural_attenuation",
        '("perfluoroalkyl" OR PFAS) AND ("natural attenuation" OR "environmental conditions" OR field OR microcosm) AND (biodegradation OR transformation)',
        "medium",
    ),
]


def load_queries(path: str | Path | None = None) -> list[QuerySpec]:
    if not path:
        return DEFAULT_QUERIES
    config_path = Path(path)
    if not config_path.exists():
        return DEFAULT_QUERIES
    try:
        import yaml  # type: ignore
    except Exception:
        return DEFAULT_QUERIES
    data: dict[str, Any] = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    queries = []
    for item in data.get("queries", []):
        if item.get("id") and item.get("boolean"):
            queries.append(QuerySpec(item["id"], item["boolean"], item.get("priority", "medium")))
    return queries or DEFAULT_QUERIES


def source_id_for(metadata: dict) -> str:
    doi = normalize_doi(metadata.get("doi"))
    if doi:
        return stable_id("src", "doi", doi)
    title = normalize_title(metadata.get("title"))
    first_author = (metadata.get("authors") or [""])[0] if isinstance(metadata.get("authors"), list) else ""
    return stable_id("src", "title", title, first_author, metadata.get("year"))


def dedup_key(metadata: dict) -> str:
    doi = normalize_doi(metadata.get("doi"))
    if doi:
        return f"doi:{doi}"
    title = normalize_title(metadata.get("title"))
    authors = metadata.get("authors") or []
    first = authors[0].lower().split(",")[0].strip() if authors else ""
    return f"title:{title}|first:{first}"
