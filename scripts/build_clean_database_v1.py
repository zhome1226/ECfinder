"""Build the clean PFAS natural-transformation database v1."""

from __future__ import annotations

import csv
import json
from copy import deepcopy
from pathlib import Path

from validate_clean_database_v1 import validate_clean_database


ROOT = Path(__file__).resolve().parents[1]
CLEAN_DIR = ROOT / "data" / "clean"
RECORDS_JSONL = CLEAN_DIR / "pfas_natural_transformation_records_v1.jsonl"
RECORDS_CSV = CLEAN_DIR / "pfas_natural_transformation_records_v1.csv"
SOURCES_JSONL = CLEAN_DIR / "pfas_natural_transformation_sources_v1.jsonl"
REJECTED_JSONL = CLEAN_DIR / "pfas_natural_transformation_rejected_v1.jsonl"
MANUAL_JSONL = CLEAN_DIR / "pfas_natural_transformation_manual_review_v1.jsonl"
AUXILIARY_JSONL = CLEAN_DIR / "pfas_auxiliary_engineered_biological_v1.jsonl"
SCHEMA_YAML = CLEAN_DIR / "schema_clean_v1.yaml"
SUMMARY_REPORT = ROOT / "reports" / "clean_database_v1_summary.md"
FREEZE_NOTICE = ROOT / "reports" / "legacy_stage2_output_freeze_notice.md"


CSV_FIELDS = [
    "record_id",
    "source_id",
    "source_type",
    "query_family",
    "doi",
    "title",
    "year",
    "journal",
    "chunk_id",
    "section",
    "table",
    "parent_name",
    "parent_synonyms",
    "parent_class",
    "product_name",
    "product_synonyms",
    "product_class",
    "reaction_type",
    "reaction_description",
    "setting_type",
    "environment_matrix",
    "environment_type",
    "redox_condition",
    "microbial_condition",
    "duration",
    "identification_confidence",
    "evidence_tier",
    "requires_manual_confirmation",
    "main_database_use",
    "review_status",
    "review_confidence",
    "evidence_quote",
]


SOURCE_ID = "clean_source_estlett_2018_fttaos_sulfate_reducing_microcosm"
SOURCE_TITLE = (
    "Biotransformation of AFFF Component 6:2 Fluorotelomer Thioether Amido "
    "Sulfonate Generates 6:2 Fluorotelomer Thioether Carboxylate under "
    "Sulfate-Reducing Conditions"
)
SOURCE_DOI = "10.1021/acs.estlett.8b00148"


def normalize_value(value):
    if isinstance(value, dict):
        return {key: normalize_value(child) for key, child in value.items()}
    if isinstance(value, list):
        return [normalize_value(child) for child in value]
    if isinstance(value, str):
        return value.replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n")
    return value


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(normalize_value(record), ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def seed_records() -> list[dict]:
    base = {
        "source_id": SOURCE_ID,
        "source_type": "primary_study",
        "doi": SOURCE_DOI,
        "title": SOURCE_TITLE,
        "year": 2018,
        "journal": "Environmental Science & Technology Letters",
        "query_family": "C",
        "parent_compound": {
            "name": "6:2 fluorotelomer thioether amido sulfonate",
            "synonyms": ["6:2 FtTAoS", "Lodyne component"],
            "compound_class": "PFAS precursor; fluorotelomer thioether amido sulfonate",
            "cas": "",
            "smiles": "",
            "inchi": "",
            "inchikey": "",
        },
        "transformation": {
            "reaction_name": "6:2 FtTAoS sulfate-reducing biotransformation",
            "reaction_type": "microbial biotransformation of fluorotelomer thioether precursor",
            "direction": "parent_to_product",
            "is_precursor_transformation": True,
            "defluorination_involved": False,
        },
        "conditions": {
            "environment_matrix": "pristine or AFFF-impacted environmental solids used as microbial inocula",
            "environment_type": "environmental solids microcosm",
            "setting_type": "soil_microcosm_from_field_sample",
            "location": "AFFF-impacted and pristine environmental solids",
            "temperature": "",
            "pH": "",
            "light_condition": "dark/incubation not specified",
            "redox_condition": "sulfate-reducing; anaerobic",
            "microbial_condition": "live microcosms inoculated with pristine or AFFF-impacted solids; autoclaved controls used",
            "duration": "incubation experiment; separate FtTP-amended microcosms observed over 150 days",
            "other_conditions": "50 mM sodium sulfate; AFFF amendment; defined mineral salts medium; environmental solids inocula",
        },
        "evidence": {
            "analytical_method": "high-resolution mass spectrometry with suspect-screening and nontargeted identification",
            "kinetic_info": "product observed or increased in live microcosms during incubation",
            "mass_balance": "PFAS mass balance achieved in pristine microcosms; incomplete in contaminated microcosms",
            "authors_claim": "Biotransformation products were identified in live environmental-solids microcosms.",
        },
    }
    seeds = [
        {
            "record_id": "clean_seed_stage2_001",
            "chunk_id": "stage2chunk_51fe433c893c3e24",
            "source_chunk_id": "stage2chunk_51fe433c893c3e24",
            "product_compound": {
                "name": "6:2 fluorotelomer thioether propionate",
                "synonyms": ["6:2 FtTP"],
                "compound_class": "polyfluoroalkyl transformation product; fluorotelomer thioether carboxylate",
                "cas": "",
                "smiles": "",
                "inchi": "",
                "inchikey": "",
            },
            "reaction_description": "6:2 FtTAoS was transformed primarily to 6:2 FtTP.",
            "identification_confidence": "level 1; confirmed by standard reference",
            "quantitative_data": "6:2 FtTP accounted for approximately 36% and 30% by mole of initial 6:2 FtTAoS in pristine and contaminated microcosms, respectively",
            "yield_or_formation_fraction": "~36% pristine microcosms; ~30% contaminated microcosms",
            "evidence_quote": "These analyses demonstrated that 6:2 FtTAoS was transformed primarily to a stable polyfluoroalkyl compound, 6:2 fluorotelomer thioether propionate (6:2 FtTP).",
            "review": {
                "review_status": "validated_high_confidence",
                "review_reason": "Primary source directly states 6:2 FtTAoS was transformed primarily to 6:2 FtTP in environmental-solid microcosms under sulfate-reducing conditions.",
                "review_confidence": 0.94,
                "evidence_tier": "confirmed_product",
                "requires_manual_confirmation": False,
                "main_database_use": "core_evidence",
            },
        },
        {
            "record_id": "clean_seed_stage2_002",
            "chunk_id": "stage2chunk_03e15b585d33db44",
            "source_chunk_id": "stage2chunk_03e15b585d33db44",
            "product_compound": {
                "name": "6:2 fluorotelomer thioether propanoyl alaninate",
                "synonyms": ["6:2 FtTPlA", "m/z 522"],
                "compound_class": "tentative polyfluoroalkyl biotransformation product",
                "cas": "",
                "smiles": "",
                "inchi": "",
                "inchikey": "",
            },
            "reaction_description": "Suspect-screening evidence suggests formation of 6:2 FtTPlA from 6:2 FtTAoS in live microcosms.",
            "identification_confidence": "level 3 tentative identification",
            "quantitative_data": "low abundance product identified by suspect screening",
            "yield_or_formation_fraction": "",
            "evidence_quote": "Suspect screening suggested that the ion at m / z 522 was 6:2 fluorotelomer thioether propanoyl alaninate (6:2 FtTPlA).",
            "review": {
                "review_status": "validated_medium_confidence",
                "review_reason": "Primary source identifies this as a potential biotransformation product in live microcosms, but structural assignment is tentative at confidence level 3.",
                "review_confidence": 0.74,
                "evidence_tier": "tentative_product",
                "requires_manual_confirmation": True,
                "main_database_use": "tentative_evidence",
            },
        },
        {
            "record_id": "clean_seed_stage2_003",
            "chunk_id": "stage2chunk_03e15b585d33db44",
            "source_chunk_id": "stage2chunk_03e15b585d33db44",
            "product_compound": {
                "name": "6:2 fluorotelomer thioether propanoyl oxy propanoate",
                "synonyms": ["6:2 FtTPoP", "m/z 523"],
                "compound_class": "tentative polyfluoroalkyl biotransformation product with carboxylate group",
                "cas": "",
                "smiles": "",
                "inchi": "",
                "inchikey": "",
            },
            "reaction_description": "Nontargeted evidence implies formation of 6:2 FtTPoP in 6:2 FtTAoS live microcosms.",
            "identification_confidence": "level 3 tentative identification",
            "quantitative_data": "low abundance product identified by nontargeted analysis",
            "yield_or_formation_fraction": "",
            "evidence_quote": "The nontargeted analysis implied that the ions at m / z 523 and 593 were fluorotelomer thioether propanoyl oxy propanoate (6:2 FtTPoP) and 6:2 fluorotelomer thioether propanoylalanylalaninate (6:2 FtTPlAA), respectively.",
            "review": {
                "review_status": "validated_medium_confidence",
                "review_reason": "Primary source identifies this as a potential biotransformation product in live microcosms, but assignment is tentative and low abundance.",
                "review_confidence": 0.72,
                "evidence_tier": "tentative_product",
                "requires_manual_confirmation": True,
                "main_database_use": "tentative_evidence",
            },
        },
        {
            "record_id": "clean_seed_stage2_004",
            "chunk_id": "stage2chunk_f1465a98c26fa66f",
            "source_chunk_id": "stage2chunk_f1465a98c26fa66f",
            "product_compound": {
                "name": "6:2 fluorotelomer thioether propanoylalanylalaninate",
                "synonyms": ["6:2 FtTPlAA", "m/z 593"],
                "compound_class": "tentative polyfluoroalkyl biotransformation product",
                "cas": "",
                "smiles": "",
                "inchi": "",
                "inchikey": "",
            },
            "reaction_description": "6:2 FtTPlAA increased in live environmental-solid microcosms during 6:2 FtTAoS incubation.",
            "identification_confidence": "level 3 tentative identification",
            "quantitative_data": "increase observed at end of incubation in both live microcosm sets",
            "yield_or_formation_fraction": "",
            "evidence_quote": "Although an increase in the level of 6:2 FtTPlAA (m/z 593) at the end of the incubation was observed in both sets of live microcosms, increases of m/z 522 and 523 were detected only in pristine and contaminated microcosms, respectively.",
            "review": {
                "review_status": "validated_medium_confidence",
                "review_reason": "Primary source reports an increase of 6:2 FtTPlAA in both live microcosm sets; assignment remains confidence level 3.",
                "review_confidence": 0.77,
                "evidence_tier": "tentative_product",
                "requires_manual_confirmation": True,
                "main_database_use": "tentative_evidence",
            },
        },
    ]
    records = []
    for seed in seeds:
        record = deepcopy(base)
        record.update(
            {
                "record_id": seed["record_id"],
                "chunk_id": seed["chunk_id"],
                "product_compound": seed["product_compound"],
                "evidence_quote": seed["evidence_quote"],
                "review": seed["review"],
                "provenance": {
                    "stage": "stage2_seed",
                    "source_chunk_id": seed["source_chunk_id"],
                    "evidence_location": {"section": "html_text", "page": "", "table": "Table 1", "figure": "", "caption": ""},
                    "added_by": "codex_gpt5_5",
                    "notes": "Seed record reconstructed from the confirmed Stage 2 natural-environment evidence set.",
                },
            }
        )
        record["transformation"]["reaction_description"] = seed["reaction_description"]
        record["evidence"]["identification_confidence"] = seed["identification_confidence"]
        record["evidence"]["quantitative_data"] = seed["quantitative_data"]
        record["evidence"]["yield_or_formation_fraction"] = seed["yield_or_formation_fraction"]
        records.append(record)
    return records


def source_records(records: list[dict]) -> list[dict]:
    existing_sources = {
        source.get("source_id"): source
        for source in read_jsonl(CLEAN_DIR / "stage2_2_sources.jsonl")
        if source.get("source_id")
    }
    grouped: dict[str, list[dict]] = {}
    for record in records:
        grouped.setdefault(record["source_id"], []).append(record)

    sources = []
    for source_id, source_records_for_id in sorted(grouped.items()):
        first = source_records_for_id[0]
        base = existing_sources.get(source_id, {})
        if source_id == SOURCE_ID:
            base = {
                "source_id": SOURCE_ID,
                "source_type": "primary_study",
                "doi": SOURCE_DOI,
                "title": SOURCE_TITLE,
                "year": 2018,
                "journal": "Environmental Science & Technology Letters",
                "query_family": "C",
                "source_status": "validated_seed_source",
                "notes": "Initial clean-database source containing 4 environmental-solids microcosm PFAS transformation records.",
            }
        source = {
            "source_id": source_id,
            "source_type": base.get("source_type") or first.get("source_type") or "primary_study",
            "doi": base.get("doi") or first.get("doi"),
            "title": base.get("title") or first.get("title"),
            "year": base.get("year") or first.get("year"),
            "journal": base.get("journal") or first.get("journal"),
            "query_family": base.get("query_family") or first.get("query_family"),
            "record_ids": [record["record_id"] for record in source_records_for_id],
            "source_status": base.get("source_status") or "validated_clean_source",
            "notes": base.get("notes") or "Clean database source generated from validated records.",
        }
        sources.append(source)
    return sources


def merge_by_record_id(existing: list[dict], additions: list[dict]) -> list[dict]:
    merged = {record["record_id"]: record for record in existing if record.get("record_id")}
    for record in additions:
        merged[record["record_id"]] = record
    return list(merged.values())


def csv_row(record: dict) -> dict:
    parent = record.get("parent_compound") or {}
    product = record.get("product_compound") or {}
    transformation = record.get("transformation") or {}
    conditions = record.get("conditions") or {}
    evidence = record.get("evidence") or {}
    provenance = record.get("provenance") or {}
    location = provenance.get("evidence_location") or {}
    review = record.get("review") or {}
    return {
        "record_id": record.get("record_id"),
        "source_id": record.get("source_id"),
        "source_type": record.get("source_type"),
        "query_family": record.get("query_family"),
        "doi": record.get("doi"),
        "title": record.get("title"),
        "year": record.get("year"),
        "journal": record.get("journal"),
        "chunk_id": record.get("chunk_id"),
        "section": location.get("section"),
        "table": location.get("table"),
        "parent_name": parent.get("name"),
        "parent_synonyms": json.dumps(parent.get("synonyms") or [], ensure_ascii=False),
        "parent_class": parent.get("compound_class"),
        "product_name": product.get("name"),
        "product_synonyms": json.dumps(product.get("synonyms") or [], ensure_ascii=False),
        "product_class": product.get("compound_class"),
        "reaction_type": transformation.get("reaction_type"),
        "reaction_description": transformation.get("reaction_description"),
        "setting_type": conditions.get("setting_type"),
        "environment_matrix": conditions.get("environment_matrix"),
        "environment_type": conditions.get("environment_type"),
        "redox_condition": conditions.get("redox_condition"),
        "microbial_condition": conditions.get("microbial_condition"),
        "duration": conditions.get("duration"),
        "identification_confidence": evidence.get("identification_confidence"),
        "evidence_tier": review.get("evidence_tier"),
        "requires_manual_confirmation": review.get("requires_manual_confirmation"),
        "main_database_use": review.get("main_database_use"),
        "review_status": review.get("review_status"),
        "review_confidence": review.get("review_confidence"),
        "evidence_quote": record.get("evidence_quote"),
    }


def write_csv(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        for record in records:
            writer.writerow({key: normalize_value(value) for key, value in csv_row(record).items()})


def write_schema() -> None:
    SCHEMA_YAML.write_text(
        """version: clean_v1
record_required_fields:
  - record_id
  - source_id
  - source_type
  - doi
  - title
  - year
  - journal
  - parent_compound.name
  - product_compound.name
  - transformation.reaction_type
  - conditions.setting_type
  - evidence.identification_confidence
  - evidence_quote
  - review.evidence_tier
  - provenance.stage
allowed_evidence_tiers:
  - confirmed_product
  - probable_product
  - tentative_product
excluded_from_clean_main:
  - activated_sludge
  - wastewater_treatment
  - WWTP
  - engineered_biological_treatment
  - engineered_chemical_treatment
jsonl_rule: one complete JSON object per line
csv_rule: csv.DictWriter with header
""",
        encoding="utf-8",
    )


def write_freeze_notice() -> None:
    FREEZE_NOTICE.parent.mkdir(parents=True, exist_ok=True)
    FREEZE_NOTICE.write_text(
        "# Legacy Stage 2 Output Freeze Notice\n\n"
        "The legacy files under `data/reviewed/stage2_*` and "
        "`data/reviewed/pfas_transformation_records_validated.*` have a history of "
        "JSONL/CSV serialization problems. They are retained as development history "
        "but are no longer used as the authoritative database for downstream "
        "statistics or Stage 3 readiness decisions.\n\n"
        "From Stage 2.2 onward, the clean natural-environment database is maintained "
        "under `data/clean/`. New validated records, source metadata, manual-review "
        "records, rejected records, auxiliary records, validation reports, and Stage "
        "3 readiness decisions must use `data/clean/` as the source of truth.\n\n"
        "Do not delete the legacy reviewed outputs, but do not continue repairing "
        "them. They may be read only to recover already confirmed seed evidence.\n",
        encoding="utf-8",
    )


def write_summary(validation: dict) -> None:
    SUMMARY_REPORT.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_REPORT.write_text(
        "# Clean Database v1 Summary\n\n"
        f"- clean_database_records = {validation['record_count']}\n"
        f"- clean_database_sources = {validation['source_count']}\n"
        f"- confirmed_product_count = {validation['confirmed_product_count']}\n"
        f"- probable_product_count = {validation['probable_product_count']}\n"
        f"- tentative_product_count = {validation['tentative_product_count']}\n"
        f"- requires_manual_confirmation_count = {validation['requires_manual_confirmation_count']}\n"
        f"- validation_ok = {str(validation['validation_ok']).lower()}\n\n"
        "The clean database is initialized with 4 seed records from one primary "
        "environmental-solids microcosm study. These records establish a clean, "
        "traceable pipeline baseline and do not imply broad coverage of PFAS "
        "natural transformation evidence.\n",
        encoding="utf-8",
    )


def build() -> dict:
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    seeds = seed_records()
    existing = read_jsonl(RECORDS_JSONL)
    stage2_2 = read_jsonl(CLEAN_DIR / "stage2_2_validated_records.jsonl")
    records = merge_by_record_id(existing, seeds + stage2_2)
    write_jsonl(RECORDS_JSONL, records)
    write_csv(RECORDS_CSV, records)
    write_jsonl(SOURCES_JSONL, source_records(records))
    for path in [REJECTED_JSONL, MANUAL_JSONL, AUXILIARY_JSONL]:
        if not path.exists():
            write_jsonl(path, [])
    write_schema()
    write_freeze_notice()
    validation = validate_clean_database(ROOT)
    write_summary(validation)
    if not validation["validation_ok"]:
        raise SystemExit(1)
    return validation


def main() -> int:
    result = build()
    for key, value in result.items():
        if key != "errors":
            print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
