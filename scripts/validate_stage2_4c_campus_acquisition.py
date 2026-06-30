"""Validate Stage 2.4c campus-authenticated acquisition records."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ecfinder.state.common import read_jsonl, sha256_file


ROOT = Path(__file__).resolve().parents[1]
LOCAL_ROOT = ROOT / "data" / "local_fulltext" / "stage2_4b"
MANIFEST_PATH = LOCAL_ROOT / "fulltext_manifest.jsonl"
STATUS_PATH = ROOT / "data" / "batches" / "stage2_4c_campus_fulltext_acquisition_status.jsonl"
SUMMARY_PATH = ROOT / "reports" / "stage2_4c_campus_fulltext_acquisition_summary.md"
VALIDATE_24B = ROOT / "scripts" / "validate_stage2_4b_fulltext_ingest.py"
VALIDATE_STATE = ROOT / "scripts" / "validate_state_cache_layer.py"

FORBIDDEN_SOURCES = ["sci-hub", "scihub", "libgen", "z-library", "annas-archive"]
FAILURE_REASONS = {
    "not_subscribed",
    "manual_login_required",
    "captcha_or_mfa_required",
    "download_button_missing",
    "publisher_access_denied",
    "other",
}


def read_jsonl_strict(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise ValueError(f"missing JSONL file: {path}")
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            if "} {" in line:
                raise ValueError(f"{path}:{line_no} contains multiple JSON objects on one line")
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_no} is not a JSON object")
            rows.append(value)
    return rows


def repo_path(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return ROOT / path


def git_tracked(path: Path) -> bool:
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(path.relative_to(ROOT)).replace("\\", "/")],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def validate_no_raw_fulltext_tracked() -> None:
    result = subprocess.run(
        [
            "git",
            "ls-files",
            "data/local_fulltext/stage2_4b/pdf",
            "data/local_fulltext/stage2_4b/html",
            "data/local_fulltext/stage2_4b/si",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(f"git ls-files failed: {result.stderr.strip()}")
    tracked = [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]
    bad = [path for path in tracked if not path.endswith("/.gitkeep")]
    if bad:
        raise ValueError(f"raw full-text files are tracked by Git: {bad}")


def validate_status() -> list[dict[str, Any]]:
    statuses = read_jsonl_strict(STATUS_PATH)
    if len(statuses) != 12:
        raise ValueError(f"acquisition status must contain 12 targets; found {len(statuses)}")
    seen: set[str] = set()
    for row in statuses:
        source_id = row.get("source_id")
        if not source_id:
            raise ValueError("status record missing source_id")
        if source_id in seen:
            raise ValueError(f"duplicate status source_id: {source_id}")
        seen.add(source_id)
        if row.get("attempted") is not True:
            raise ValueError(f"status not attempted: {source_id}")
        if row.get("browser_access_method") != "campus_authenticated_browser":
            raise ValueError(f"wrong browser_access_method: {source_id}")
        if not isinstance(row.get("publisher_page_reached"), bool):
            raise ValueError(f"publisher_page_reached must be boolean: {source_id}")
        downloaded = row.get("downloaded_files", [])
        if row.get("fulltext_accessible") is True:
            if not downloaded:
                raise ValueError(f"accessible source missing downloaded_files: {source_id}")
            if row.get("failure_reason") is not None:
                raise ValueError(f"accessible source has failure_reason: {source_id}")
            if row.get("next_action") != "ingest":
                raise ValueError(f"accessible source next_action must be ingest: {source_id}")
        else:
            if downloaded:
                raise ValueError(f"inaccessible source has downloaded files: {source_id}")
            if row.get("failure_reason") not in FAILURE_REASONS:
                raise ValueError(f"invalid failure_reason for {source_id}: {row.get('failure_reason')}")
            if row.get("next_action") != "manual_user_fulltext":
                raise ValueError(f"inaccessible source next_action must be manual_user_fulltext: {source_id}")
        for key in ["landing_url", "final_url"]:
            url = str(row.get(key, "")).lower()
            if any(term in url for term in FORBIDDEN_SOURCES):
                raise ValueError(f"forbidden acquisition source in {source_id}: {url}")
        for downloaded_file in downloaded:
            local_path = repo_path(str(downloaded_file.get("local_path", "")))
            if not local_path.exists():
                raise ValueError(f"downloaded file missing locally: {source_id} {local_path}")
            if not downloaded_file.get("sha256"):
                raise ValueError(f"downloaded file missing sha256: {source_id}")
            if sha256_file(local_path) != downloaded_file.get("sha256"):
                raise ValueError(f"downloaded file sha256 mismatch: {source_id}")
            if git_tracked(local_path) or downloaded_file.get("git_tracked") is not False:
                raise ValueError(f"downloaded raw file is tracked by Git: {local_path}")
    return statuses


def validate_manifest(statuses: list[dict[str, Any]]) -> None:
    manifest = read_jsonl_strict(MANIFEST_PATH)
    status_by_source = {row["source_id"]: row for row in statuses}
    manifest_by_source: dict[str, list[dict[str, Any]]] = {}
    for row in manifest:
        manifest_by_source.setdefault(str(row.get("source_id", "")), []).append(row)
    if set(manifest_by_source) != set(status_by_source):
        raise ValueError("manifest source set does not match acquisition status source set")
    for source_id, status in status_by_source.items():
        rows = manifest_by_source[source_id]
        if status["fulltext_accessible"]:
            for row in rows:
                if not row.get("local_path") or not row.get("sha256"):
                    raise ValueError(f"successful manifest row missing local_path/sha256: {source_id}")
                path = repo_path(str(row["local_path"]))
                if not path.exists():
                    raise ValueError(f"manifest local_path missing: {source_id}")
                if sha256_file(path) != row["sha256"]:
                    raise ValueError(f"manifest sha256 mismatch: {source_id}")
                if row.get("access_method") != "campus_authenticated_browser":
                    raise ValueError(f"manifest access_method not campus browser: {source_id}")
        else:
            row = rows[0]
            if row.get("status") != "missing_fulltext":
                raise ValueError(f"failed manifest row not missing_fulltext: {source_id}")
            if row.get("rescue_attempted") is not True:
                raise ValueError(f"failed manifest row missing rescue_attempted: {source_id}")
            if not row.get("rescue_failure_reason"):
                raise ValueError(f"failed manifest row missing rescue_failure_reason: {source_id}")


def parse_report_counts(path: Path) -> dict[str, str]:
    counts: dict[str, str] = {}
    pattern = re.compile(r"^([A-Za-z0-9_]+)\s*=\s*(.+?)\s*$")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            counts[match.group(1)] = match.group(2)
    return counts


def validate_report_counts(statuses: list[dict[str, Any]]) -> dict[str, Any]:
    downloaded = [file for row in statuses for file in row.get("downloaded_files", [])]
    expected = {
        "targets_attempted": sum(1 for row in statuses if row.get("attempted")),
        "publisher_pages_reached": sum(1 for row in statuses if row.get("publisher_page_reached")),
        "campus_access_success": sum(1 for row in statuses if row.get("fulltext_accessible")),
        "pdf_downloaded": sum(1 for file in downloaded if file.get("file_type") == "pdf"),
        "html_saved": sum(1 for file in downloaded if file.get("file_type") == "html"),
        "si_downloaded": sum(1 for file in downloaded if file.get("file_type") == "si"),
        "fulltext_found_total": len(downloaded),
        "fulltext_missing_total": sum(1 for row in statuses if not row.get("fulltext_accessible")),
        "files_ignored_by_git": True,
        "manifest_updated": True,
        "can_scale_to_100_sources": False,
        "reason": "insufficient_campus_fulltext_access" if len(downloaded) < 5 else "fulltext_acquired_waiting_for_extraction_review",
    }
    report = parse_report_counts(SUMMARY_PATH)
    for key, value in expected.items():
        expected_value = str(value).lower() if isinstance(value, bool) else str(value)
        actual = report.get(key)
        if actual != expected_value:
            raise ValueError(f"summary count mismatch for {key}: expected {expected_value}, got {actual}")
    return expected


def run_subvalidator(path: Path) -> None:
    result = subprocess.run([sys.executable, str(path)], cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise ValueError(f"{path.name} failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")


def main() -> int:
    validate_no_raw_fulltext_tracked()
    statuses = validate_status()
    validate_manifest(statuses)
    summary = validate_report_counts(statuses)
    run_subvalidator(VALIDATE_24B)
    run_subvalidator(VALIDATE_STATE)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
