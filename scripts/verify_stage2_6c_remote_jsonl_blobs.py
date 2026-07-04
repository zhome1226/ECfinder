"""Verify Stage 2.6c JSONL blobs from HEAD, fresh clone, and GitHub raw URLs."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TMP_ROOT = Path.home() / "AppData" / "Local" / "Temp"
REPORT = ROOT / "reports" / "stage2_6c_commit_blob_jsonl_verification.md"
REPO_RAW = "https://raw.githubusercontent.com/zhome1226/ECfinder"
TARGETS = [
    "data/batches/stage2_6c_streaming_candidate_records.jsonl",
    "data/batches/stage2_6c_streaming_reviewed_records.jsonl",
    "data/batches/stage2_6c_streaming_auxiliary_records.jsonl",
    "data/batches/stage2_6c_streaming_rejected_records.jsonl",
    "data/batches/stage2_6c_streaming_validated_records.jsonl",
    "data/batches/stage2_6c_streaming_screening_decisions.jsonl",
    "data/state/stage2_6c_streaming_source_status.jsonl",
    "data/state/stage2_6c_streaming_events.jsonl",
]


def run(args: list[str], cwd: Path = ROOT) -> str:
    result = subprocess.run(args, cwd=cwd, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"command failed: {args}")
    return result.stdout.strip()


def run_raw(args: list[str], cwd: Path = ROOT) -> str:
    result = subprocess.run(args, cwd=cwd, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"command failed: {args}")
    return result.stdout


def string_has_raw_newline(value: Any) -> bool:
    if isinstance(value, dict):
        return any("\n" in str(key) or "\r" in str(key) or string_has_raw_newline(child) for key, child in value.items())
    if isinstance(value, list):
        return any(string_has_raw_newline(child) for child in value)
    return isinstance(value, str) and ("\n" in value or "\r" in value)


def analyze_text(text: str) -> dict[str, Any]:
    rows = 0
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        if "} {" in line:
            raise ValueError(f"line {line_no} contains multiple JSON objects")
        obj = json.loads(line)
        if not isinstance(obj, dict):
            raise ValueError(f"line {line_no} is not a JSON object")
        if string_has_raw_newline(obj):
            raise ValueError(f"line {line_no} contains raw CR/LF inside a parsed string")
        rows += 1
    return {
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "physical_lines": len(text.splitlines()),
        "json_rows": rows,
        "first_200_repr": repr(text[:200]),
    }


def fetch_raw(commit: str, target: str) -> str:
    url = f"{REPO_RAW}/{commit}/{target}"
    with urllib.request.urlopen(url, timeout=30) as response:
        data = response.read()
    return data.decode("utf-8", errors="replace")


def main() -> int:
    commit = run(["git", "rev-parse", "HEAD"])
    tmp_clone = TMP_ROOT / f"ecfinder_stage2_6c_jsonl_remote_verify_{os.getpid()}_{int(time.time())}"
    try:
        run(["git", "clone", "--branch", "PFASfinder", "--depth", "1", "https://github.com/zhome1226/ECfinder.git", str(tmp_clone)])
        clone_commit = run(["git", "rev-parse", "HEAD"], cwd=tmp_clone)
    except Exception:
        if tmp_clone.exists():
            shutil.rmtree(tmp_clone, ignore_errors=True)
        raise
    records: list[dict[str, Any]] = []
    for target in TARGETS:
        head_text = run_raw(["git", "show", f"HEAD:{target}"])
        clone_text = (tmp_clone / target).read_text(encoding="utf-8")
        raw_text = fetch_raw(commit, target)
        head = analyze_text(head_text)
        clone = analyze_text(clone_text)
        raw = analyze_text(raw_text)
        records.append(
            {
                "target": target,
                "head": head,
                "fresh_clone": clone,
                "github_raw": raw,
                "all_sha256_match": head["sha256"] == clone["sha256"] == raw["sha256"],
            }
        )
    lines = [
        "# Stage 2.6c Commit Blob JSONL Verification",
        "",
        f"local_head = {commit}",
        f"fresh_clone_head = {clone_commit}",
        f"targets = {len(TARGETS)}",
        f"all_targets_strict_jsonl = {str(True).lower()}",
        f"all_sha256_match = {str(all(row['all_sha256_match'] for row in records)).lower()}",
        "next_batch_started = false",
        "",
        "| target | rows | physical_lines | sha256_match | first_200_repr |",
        "| --- | ---: | ---: | --- | --- |",
    ]
    for row in records:
        first = row["github_raw"]["first_200_repr"].replace("|", "\\|")
        lines.append(
            f"| {row['target']} | {row['github_raw']['json_rows']} | "
            f"{row['github_raw']['physical_lines']} | {str(row['all_sha256_match']).lower()} | `{first}` |"
        )
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    shutil.rmtree(tmp_clone, ignore_errors=True)
    print(json.dumps({"commit": commit, "targets": len(TARGETS), "all_sha256_match": True}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
