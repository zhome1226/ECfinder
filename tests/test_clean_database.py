from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RECORDS_JSONL = ROOT / "data" / "clean" / "pfas_natural_transformation_records_v1.jsonl"
RECORDS_CSV = ROOT / "data" / "clean" / "pfas_natural_transformation_records_v1.csv"
SUMMARY = ROOT / "reports" / "clean_database_v1_summary.md"
FORBIDDEN = ["activated sludge", "wastewater treatment", "wwtp"]


def read_records() -> list[dict]:
    records = []
    for line_no, line in enumerate(RECORDS_JSONL.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        assert "} {" not in line, f"{RECORDS_JSONL}:{line_no} has multiple JSON objects"
        obj = json.loads(line)
        assert isinstance(obj, dict), f"{RECORDS_JSONL}:{line_no} is not an object"
        records.append(obj)
    return records


def parse_summary_counts() -> dict[str, int]:
    counts = {}
    for line in SUMMARY.read_text(encoding="utf-8").splitlines():
        if not line.startswith("- ") or " = " not in line:
            continue
        key, value = line[2:].split(" = ", 1)
        if value.isdigit():
            counts[key] = int(value)
    return counts


def test_clean_jsonl_has_exactly_nine_records() -> None:
    assert len(read_records()) == 9


def test_clean_csv_has_exactly_nine_data_rows() -> None:
    with RECORDS_CSV.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 9


def test_clean_records_are_complete_and_unique() -> None:
    records = read_records()
    record_ids = [record.get("record_id") for record in records]
    assert len(record_ids) == len(set(record_ids))
    for record in records:
        assert record.get("record_id")
        assert record.get("source_id")
        assert record.get("doi")
        assert (record.get("parent_compound") or {}).get("name")
        assert (record.get("product_compound") or {}).get("name")
        assert record.get("evidence_quote")
        review = record.get("review") or {}
        assert review.get("review_status")
        assert review.get("evidence_tier")


def test_evidence_tier_counts_match_summary() -> None:
    records = read_records()
    summary = parse_summary_counts()
    counts = {
        "confirmed_product_count": sum(
            1 for record in records if (record.get("review") or {}).get("evidence_tier") == "confirmed_product"
        ),
        "probable_product_count": sum(
            1 for record in records if (record.get("review") or {}).get("evidence_tier") == "probable_product"
        ),
        "tentative_product_count": sum(
            1 for record in records if (record.get("review") or {}).get("evidence_tier") == "tentative_product"
        ),
    }
    for key, value in counts.items():
        assert summary[key] == value


def test_clean_main_excludes_engineered_terms() -> None:
    text = RECORDS_JSONL.read_text(encoding="utf-8").lower()
    for forbidden in FORBIDDEN:
        assert forbidden not in text
