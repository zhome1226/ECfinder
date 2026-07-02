"""Repair Stage 2.6c streaming JSONL files into strict one-object-per-line records.

This script intentionally does not parse the input line by line. It scans the
whole file with JSONDecoder.raw_decode so it can recover objects that were
serialized with raw CR/LF characters inside JSON strings.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TARGETS = [
    ROOT / "data" / "batches" / "stage2_6c_streaming_candidate_records.jsonl",
    ROOT / "data" / "batches" / "stage2_6c_streaming_reviewed_records.jsonl",
    ROOT / "data" / "batches" / "stage2_6c_streaming_auxiliary_records.jsonl",
    ROOT / "data" / "batches" / "stage2_6c_streaming_rejected_records.jsonl",
    ROOT / "data" / "batches" / "stage2_6c_streaming_validated_records.jsonl",
    ROOT / "data" / "batches" / "stage2_6c_streaming_screening_decisions.jsonl",
    ROOT / "data" / "state" / "stage2_6c_streaming_source_status.jsonl",
    ROOT / "data" / "state" / "stage2_6c_streaming_events.jsonl",
]
SUMMARY = ROOT / "reports" / "stage2_6c_streaming_autonomous_summary.md"
AUDIT = ROOT / "reports" / "stage2_6c_jsonl_serialization_repair_audit.md"


def clean_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {clean_string(str(key)): clean_value(child) for key, child in value.items()}
    if isinstance(value, list):
        return [clean_value(child) for child in value]
    if isinstance(value, str):
        return clean_string(value)
    return value


def clean_string(value: str) -> str:
    return re.sub(r"[\r\n]+", " ", value).strip()


def recover_objects(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    decoder = json.JSONDecoder(strict=False)
    records: list[dict[str, Any]] = []
    idx = 0
    length = len(text)
    while idx < length:
        while idx < length and text[idx].isspace():
            idx += 1
        if idx >= length:
            break
        obj, end = decoder.raw_decode(text, idx)
        if not isinstance(obj, dict):
            raise ValueError(f"{path} contains a non-object JSON value at character {idx}")
        records.append(clean_value(obj))
        idx = end
    return records


def string_has_raw_newline(value: Any) -> bool:
    if isinstance(value, dict):
        return any("\n" in str(key) or "\r" in str(key) or string_has_raw_newline(child) for key, child in value.items())
    if isinstance(value, list):
        return any(string_has_raw_newline(child) for child in value)
    return isinstance(value, str) and ("\n" in value or "\r" in value)


def write_strict_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def validate_strict(path: Path) -> int:
    count = 0
    with path.open("r", encoding="utf-8", newline="") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                continue
            if "} {" in raw_line:
                raise ValueError(f"{path}:{line_no} contains multiple JSON objects on one physical line")
            if raw_line.count("\n") != 1 or "\r" in raw_line:
                raise ValueError(f"{path}:{line_no} has a non-normalized physical line ending")
            obj = json.loads(raw_line.rstrip("\n"))
            if not isinstance(obj, dict):
                raise ValueError(f"{path}:{line_no} is not a JSON object")
            if string_has_raw_newline(obj):
                raise ValueError(f"{path}:{line_no} contains raw CR/LF inside a parsed string")
            count += 1
    return count


def update_summary_flag() -> None:
    if not SUMMARY.exists():
        return
    lines = SUMMARY.read_text(encoding="utf-8").splitlines()
    desired = {
        "streaming_jsonl_serialization_fixed": "true",
        "ready_for_next_streaming_batch": "true",
    }
    seen: set[str] = set()
    updated: list[str] = []
    for line in lines:
        key = line.split(" = ", 1)[0] if " = " in line else ""
        if key in desired:
            updated.append(f"{key} = {desired[key]}")
            seen.add(key)
        else:
            updated.append(line)
    for key, value in desired.items():
        if key not in seen:
            updated.append(f"{key} = {value}")
    SUMMARY.write_text("\n".join(updated) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    audit_rows: list[dict[str, Any]] = []
    for path in TARGETS:
        before_text = path.read_text(encoding="utf-8") if path.exists() else ""
        records = recover_objects(path)
        write_strict_jsonl(path, records)
        objects_after = validate_strict(path)
        audit_rows.append(
            {
                "file": str(path.relative_to(ROOT)).replace("\\", "/"),
                "objects_recovered": len(records),
                "objects_after_rewrite": objects_after,
                "physical_lines_before": len(before_text.splitlines()),
                "physical_lines_after": objects_after,
                "strict_one_object_per_line": True,
            }
        )
    update_summary_flag()
    lines = ["# Stage 2.6c JSONL Serialization Repair Audit", ""]
    for row in audit_rows:
        lines.append(
            f"- {row['file']}: objects_recovered={row['objects_recovered']}; "
            f"physical_lines_after={row['physical_lines_after']}; strict_one_object_per_line=true"
        )
    AUDIT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"files_repaired": len(audit_rows), "strict_one_object_per_line": True}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
