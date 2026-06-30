"""Record Stage 2.4c campus-authenticated browser acquisition attempts.

This script does not download full text. It records browser-observed access
outcomes and reconciles any user-provided local full-text files already present
in the ignored Stage 2.4b local cache.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ecfinder.state.common import read_jsonl, sha256_file, write_jsonl


ROOT = Path(__file__).resolve().parents[1]
LOCAL_ROOT = ROOT / "data" / "local_fulltext" / "stage2_4b"
MANIFEST_PATH = LOCAL_ROOT / "fulltext_manifest.jsonl"
BATCH_DIR = ROOT / "data" / "batches"
REPORTS_DIR = ROOT / "reports"
STATUS_PATH = BATCH_DIR / "stage2_4c_campus_fulltext_acquisition_status.jsonl"
SUMMARY_PATH = REPORTS_DIR / "stage2_4c_campus_fulltext_acquisition_summary.md"
STATUS_REPORT_PATH = REPORTS_DIR / "stage2_4c_campus_fulltext_acquisition_status.md"

LICENSE_NOTE = (
    "Accessed through user-authorized campus/library subscription. "
    "Raw file is local only and ignored by Git."
)

BROWSER_ATTEMPTS = {
    "stage2_4_src_002": {
        "final_url": "https://www.sciencedirect.com/science/article/pii/S0043135423013817",
        "failure_reason": "captcha_or_mfa_required",
        "publisher_page_reached": True,
    },
    "stage2_4_src_003": {
        "final_url": "https://linkinghub.elsevier.com/retrieve/pii/S0269749116300707",
        "failure_reason": "download_button_missing",
        "publisher_page_reached": True,
    },
    "stage2_4_src_004": {
        "final_url": "https://linkinghub.elsevier.com/retrieve/pii/S0045653516303770",
        "failure_reason": "download_button_missing",
        "publisher_page_reached": True,
    },
    "stage2_4_src_005": {
        "final_url": "https://linkinghub.elsevier.com/retrieve/pii/S0045653514011345",
        "failure_reason": "download_button_missing",
        "publisher_page_reached": True,
    },
    "stage2_4_src_006": {
        "final_url": "https://www.sciencedirect.com/science/article/pii/S026974911632259X",
        "failure_reason": "captcha_or_mfa_required",
        "publisher_page_reached": True,
    },
    "stage2_4_src_007": {
        "final_url": "https://pubs.acs.org/doi/10.1021/es0708722",
        "failure_reason": "captcha_or_mfa_required",
        "publisher_page_reached": True,
    },
    "stage2_4_src_009": {
        "final_url": "https://pubs.acs.org/doi/10.1021/acsestwater.5c00033",
        "failure_reason": "captcha_or_mfa_required",
        "publisher_page_reached": True,
    },
    "stage2_4_src_013": {
        "final_url": "https://linkinghub.elsevier.com/retrieve/pii/S0045653512008429",
        "failure_reason": "download_button_missing",
        "publisher_page_reached": True,
    },
    "stage2_4_src_018": {
        "final_url": "https://linkinghub.elsevier.com/retrieve/pii/S0304389424018405",
        "failure_reason": "download_button_missing",
        "publisher_page_reached": True,
    },
    "stage2_4_src_021": {
        "final_url": "https://pubs.acs.org/doi/10.1021/es403949z",
        "failure_reason": "captcha_or_mfa_required",
        "publisher_page_reached": True,
    },
    "stage2_4_src_028": {
        "final_url": "https://linkinghub.elsevier.com/retrieve/pii/S004565351831422X",
        "failure_reason": "download_button_missing",
        "publisher_page_reached": True,
    },
    "stage2_4_src_029": {
        "final_url": "https://linkinghub.elsevier.com/retrieve/pii/S0048969718336593",
        "failure_reason": "download_button_missing",
        "publisher_page_reached": True,
    },
}

ZOTERO_LOOKUP_ATTEMPTS = {
    "stage2_4_src_002": {
        "zotero_item_key": "EQYEH74D",
        "zotero_fulltext_status": "not_found",
    },
    "stage2_4_src_003": {
        "zotero_item_key": "SFEYNLDG",
        "zotero_fulltext_status": "not_found",
    },
    "stage2_4_src_004": {
        "zotero_item_key": "AK5YAY7Y",
        "zotero_fulltext_status": "not_found",
    },
    "stage2_4_src_005": {
        "zotero_item_key": "PHNA47MP",
        "zotero_fulltext_status": "not_found",
    },
    "stage2_4_src_007": {
        "zotero_item_key": "APIFT48L",
        "zotero_fulltext_status": "not_found",
    },
}


def git_tracked(path: Path) -> bool:
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(path.relative_to(ROOT)).replace("\\", "/")],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def local_files_for_source(source_id: str) -> list[dict[str, Any]]:
    files: list[tuple[str, Path]] = []
    pdf = LOCAL_ROOT / "pdf" / f"{source_id}.pdf"
    html = LOCAL_ROOT / "html" / f"{source_id}.html"
    if pdf.exists():
        files.append(("pdf", pdf))
    if html.exists():
        files.append(("html", html))
    files.extend(("si", path) for path in sorted((LOCAL_ROOT / "si").glob(f"{source_id}_si_*")) if path.is_file())
    downloaded: list[dict[str, Any]] = []
    for file_type, path in files:
        downloaded.append(
            {
                "file_type": file_type,
                "local_path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha256_file(path),
                "git_tracked": git_tracked(path),
            }
        )
    return downloaded


def build_status_records(manifest_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in manifest_rows:
        source_id = str(row.get("source_id", ""))
        attempt = BROWSER_ATTEMPTS.get(source_id, {})
        zotero_attempt = ZOTERO_LOOKUP_ATTEMPTS.get(source_id, {})
        downloaded = local_files_for_source(source_id)
        fulltext_accessible = bool(downloaded)
        failure_reason = None if fulltext_accessible else attempt.get("failure_reason", "other")
        if not fulltext_accessible and zotero_attempt.get("zotero_fulltext_status") == "not_found":
            failure_reason = "zotero_fulltext_not_found"
        records.append(
            {
                "source_id": source_id,
                "doi": row.get("doi", ""),
                "title": row.get("title", ""),
                "attempted": True,
                "browser_access_method": "campus_authenticated_browser",
                "landing_url": f"https://doi.org/{row.get('doi', '')}",
                "final_url": attempt.get("final_url", ""),
                "publisher_page_reached": bool(attempt.get("publisher_page_reached", False)),
                "fulltext_accessible": fulltext_accessible,
                "downloaded_files": downloaded,
                "failure_reason": failure_reason,
                "next_action": "ingest" if fulltext_accessible else "manual_user_fulltext",
                "zotero_lookup_attempted": bool(zotero_attempt),
                "zotero_item_key": zotero_attempt.get("zotero_item_key", ""),
                "zotero_fulltext_status": zotero_attempt.get("zotero_fulltext_status", ""),
            }
        )
    return records


def update_manifest_from_status(manifest_rows: list[dict[str, Any]], statuses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_source = {status["source_id"]: status for status in statuses}
    updated: list[dict[str, Any]] = []
    for row in manifest_rows:
        status = by_source[str(row.get("source_id", ""))]
        if status["downloaded_files"]:
            for downloaded in status["downloaded_files"]:
                updated.append(
                    {
                        "source_id": row.get("source_id", ""),
                        "doi": row.get("doi", ""),
                        "title": row.get("title", ""),
                        "file_type": downloaded["file_type"],
                        "local_path": downloaded["local_path"],
                        "access_method": "campus_authenticated_browser",
                        "license_or_access_note": LICENSE_NOTE,
                        "sha256": downloaded["sha256"],
                        "status": "pending_ingest",
                    }
                )
        else:
            updated.append(
                {
                    "source_id": row.get("source_id", ""),
                    "doi": row.get("doi", ""),
                    "title": row.get("title", ""),
                    "file_type": None,
                    "local_path": "",
                    "access_method": "campus_authenticated_browser",
                    "license_or_access_note": "",
                    "sha256": "",
                    "status": "missing_fulltext",
                    "rescue_attempted": True,
                    "rescue_failure_reason": status["failure_reason"],
                }
            )
    return updated


def raw_files_ignored_by_git() -> bool:
    tracked = subprocess.run(
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
    if tracked.returncode != 0:
        return False
    paths = [line.strip().replace("\\", "/") for line in tracked.stdout.splitlines() if line.strip()]
    return all(path.endswith("/.gitkeep") for path in paths)


def summarize(statuses: list[dict[str, Any]]) -> dict[str, Any]:
    downloaded_files = [file for status in statuses for file in status.get("downloaded_files", [])]
    found_total = len(downloaded_files)
    return {
        "targets_attempted": sum(1 for status in statuses if status.get("attempted")),
        "publisher_pages_reached": sum(1 for status in statuses if status.get("publisher_page_reached")),
        "campus_access_success": sum(1 for status in statuses if status.get("fulltext_accessible")),
        "pdf_downloaded": sum(1 for file in downloaded_files if file.get("file_type") == "pdf"),
        "html_saved": sum(1 for file in downloaded_files if file.get("file_type") == "html"),
        "si_downloaded": sum(1 for file in downloaded_files if file.get("file_type") == "si"),
        "fulltext_found_total": found_total,
        "fulltext_missing_total": sum(1 for status in statuses if not status.get("fulltext_accessible")),
        "manual_login_required": sum(1 for status in statuses if status.get("failure_reason") == "manual_login_required"),
        "captcha_or_mfa_required": sum(1 for status in statuses if status.get("failure_reason") == "captcha_or_mfa_required"),
        "access_denied": sum(1 for status in statuses if status.get("failure_reason") == "publisher_access_denied"),
        "download_button_missing": sum(1 for status in statuses if status.get("failure_reason") == "download_button_missing"),
        "zotero_lookup_attempted": sum(1 for status in statuses if status.get("zotero_lookup_attempted")),
        "zotero_fulltext_found": sum(1 for status in statuses if status.get("zotero_fulltext_status") == "found"),
        "zotero_fulltext_not_found": sum(1 for status in statuses if status.get("zotero_fulltext_status") == "not_found"),
        "files_ignored_by_git": raw_files_ignored_by_git(),
        "manifest_updated": True,
        "can_scale_to_100_sources": False,
        "reason": "insufficient_campus_fulltext_access" if found_total < 5 else "fulltext_acquired_waiting_for_extraction_review",
    }


def markdown_cell(value: Any) -> str:
    return str(value).replace("\n", " ").replace("|", "\\|")


def write_reports(statuses: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    summary_lines = ["# Stage 2.4c Campus Full-text Acquisition Summary", ""]
    for key, value in summary.items():
        rendered = str(value).lower() if isinstance(value, bool) else str(value)
        summary_lines.append(f"{key} = {rendered}")
    summary_lines.extend(
        [
            "",
            "compliance_note = No Sci-Hub, mirror, cookie export, paywall bypass, account sharing, or CAPTCHA/MFA solving was used.",
            "raw_file_note = Raw PDF/HTML/SI files remain in ignored local cache and are not committed.",
        ]
    )
    SUMMARY_PATH.write_text("\n".join(summary_lines) + "\n", encoding="utf-8", newline="\n")

    status_lines = [
        "# Stage 2.4c Campus Full-text Acquisition Status",
        "",
        "| source_id | doi | publisher_page_reached | fulltext_accessible | files | failure_reason | next_action |",
        "| --- | --- | ---: | ---: | ---: | --- | --- |",
    ]
    for status in statuses:
        status_lines.append(
            "| {source_id} | {doi} | {publisher_page_reached} | {fulltext_accessible} | {files} | {failure_reason} | {next_action} |".format(
                source_id=markdown_cell(status.get("source_id", "")),
                doi=markdown_cell(status.get("doi", "")),
                publisher_page_reached=str(bool(status.get("publisher_page_reached"))).lower(),
                fulltext_accessible=str(bool(status.get("fulltext_accessible"))).lower(),
                files=len(status.get("downloaded_files", [])),
                failure_reason=markdown_cell(status.get("failure_reason", "")),
                next_action=markdown_cell(status.get("next_action", "")),
            )
        )
    STATUS_REPORT_PATH.write_text("\n".join(status_lines) + "\n", encoding="utf-8", newline="\n")


def run() -> dict[str, Any]:
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    manifest_rows = read_jsonl(MANIFEST_PATH)
    statuses = build_status_records(manifest_rows)
    updated_manifest = update_manifest_from_status(manifest_rows, statuses)
    write_jsonl(STATUS_PATH, statuses)
    write_jsonl(MANIFEST_PATH, updated_manifest)
    summary = summarize(statuses)
    write_reports(statuses, summary)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return summary


def main() -> int:
    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
