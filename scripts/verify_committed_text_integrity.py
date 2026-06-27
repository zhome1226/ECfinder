"""Byte-level text, JSONL, CSV, and clean-boundary integrity checks."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEXT_EXTENSIONS = {".py", ".json", ".jsonl", ".csv", ".md", ".yaml", ".yml", ".txt"}
SKIP_PARTS = {".git", "__pycache__"}
SKIP_PREFIXES = {
    ROOT / "data" / "raw" / "pdfs",
}
KEY_PYTHON_FILES = [
    "src/ecfinder/cli.py",
    "src/ecfinder/pipeline/gates.py",
    "src/ecfinder/pipeline/contracts.py",
    "src/ecfinder/pipeline/orchestrator.py",
]
CLEAN_JSONL = ROOT / "data" / "clean" / "pfas_natural_transformation_records_v1.jsonl"
CLEAN_CSV = ROOT / "data" / "clean" / "pfas_natural_transformation_records_v1.csv"
FORBIDDEN = [
    re.compile(rb"activated sludge", re.IGNORECASE),
    re.compile(rb"wastewater treatment", re.IGNORECASE),
    re.compile(rb"\bWWTP\b", re.IGNORECASE),
]


def should_skip(path: Path) -> bool:
    if any(part in SKIP_PARTS for part in path.parts):
        return True
    return any(path == prefix or prefix in path.parents for prefix in SKIP_PREFIXES)


def text_files() -> list[Path]:
    return [
        path
        for path in sorted(ROOT.rglob("*"))
        if path.is_file() and path.suffix.lower() in TEXT_EXTENSIONS and not should_skip(path)
    ]


def check_text_file(path: Path) -> str:
    rel = path.relative_to(ROOT).as_posix()
    data = path.read_bytes()
    if b"\r" in data:
        raise ValueError(f"{rel} contains CR byte")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{rel} is not UTF-8: {exc}") from exc
    if rel in KEY_PYTHON_FILES:
        line_count = len(text.split("\n")) - (1 if text.endswith("\n") else 0)
        if line_count < 20:
            raise ValueError(f"{rel} has suspiciously few LF lines: {line_count}")
    return text


def check_jsonl(path: Path) -> int:
    rel = path.relative_to(ROOT).as_posix()
    data = path.read_bytes()
    if b"\r" in data:
        raise ValueError(f"{rel} contains CR byte")
    text = data.decode("utf-8")
    count = 0
    for line_no, line in enumerate(text.split("\n"), start=1):
        if not line.strip():
            continue
        if "} {" in line:
            raise ValueError(f"{rel}:{line_no} has multiple JSON objects on one line")
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{rel}:{line_no} invalid JSONL: {exc}") from exc
        if not isinstance(obj, dict):
            raise ValueError(f"{rel}:{line_no} is not a JSON object")
        count += 1
    return count


def check_csv() -> int:
    with CLEAN_CSV.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    if not reader.fieldnames:
        raise ValueError("clean CSV missing header")
    if len(rows) != 9:
        raise ValueError(f"clean CSV expected 9 data rows, found {len(rows)}")
    return len(rows)


def check_clean_forbidden_terms() -> None:
    data = CLEAN_JSONL.read_bytes()
    for pattern in FORBIDDEN:
        if pattern.search(data):
            raise ValueError(f"forbidden clean main term found: {pattern.pattern!r}")


def main() -> int:
    files = text_files()
    for path in files:
        check_text_file(path)
    jsonl_counts = {path.relative_to(ROOT).as_posix(): check_jsonl(path) for path in files if path.suffix == ".jsonl"}
    clean_count = jsonl_counts.get(CLEAN_JSONL.relative_to(ROOT).as_posix())
    if clean_count != 9:
        raise ValueError(f"clean JSONL expected 9 records, found {clean_count}")
    csv_rows = check_csv()
    check_clean_forbidden_terms()
    print(f"text_files_checked {len(files)}")
    print(f"jsonl_files_checked {len(jsonl_counts)}")
    print(f"clean_jsonl_records {clean_count}")
    print(f"clean_csv_rows {csv_rows}")
    print("no_cr_bytes true")
    print("validation_ok true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
