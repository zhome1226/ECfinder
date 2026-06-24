"""Title/abstract screening for DownloadAgent."""

from __future__ import annotations

from pathlib import Path

from ecfinder.utils.logging import read_jsonl, write_jsonl


PFAS_TERMS = ["pfas", "perfluoro", "polyfluoro", "fluorotelomer", "pfoa", "pfos", "fosa", "fose"]
TRANSFORMATION_TERMS = [
    "transformation",
    "degradation",
    "biotransformation",
    "biodegradation",
    "photolysis",
    "phototransformation",
    "precursor",
    "metabolite",
    "transformation product",
]
ENV_TERMS = [
    "soil",
    "sediment",
    "groundwater",
    "surface water",
    "wastewater",
    "sludge",
    "biosolids",
    "landfill",
    "environment",
    "natural attenuation",
    "microcosm",
]


def deterministic_screen(record: dict) -> dict:
    text = " ".join(str(record.get(key) or "") for key in ["title", "abstract", "journal"]).lower()
    pfas = [term for term in PFAS_TERMS if term in text]
    transformation = [term for term in TRANSFORMATION_TERMS if term in text]
    env = [term for term in ENV_TERMS if term in text]
    if pfas and transformation and env:
        decision = "include"
        confidence = 0.78
    elif pfas and transformation:
        decision = "maybe"
        confidence = 0.55
    else:
        decision = "exclude"
        confidence = 0.30
    return {
        "source_id": record.get("source_id"),
        "decision": decision,
        "confidence": confidence,
        "reason": f"pfas={bool(pfas)} transformation={bool(transformation)} environment={bool(env)}",
        "matched_terms": sorted(set(pfas + transformation + env)),
        "screening_method": "deterministic_terms",
    }


def screen_search_results(root: str | Path) -> list[dict]:
    repo_root = Path(root)
    source_path = repo_root / "data" / "interim" / "search_results.jsonl"
    records = []
    by_source = {record.get("source_id"): record for record in read_jsonl(source_path)}
    for source_id, source in by_source.items():
        screened = deterministic_screen(source)
        screened["title"] = source.get("title")
        screened["doi"] = source.get("doi")
        records.append(screened)
    write_jsonl(repo_root / "data" / "interim" / "screened_sources.jsonl", records)
    return records
