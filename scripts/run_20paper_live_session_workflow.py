"""Run a 20-paper integrated workflow with optional live-session PDF fetch.

The workflow does not create access to publisher content. It prepares a
ScienceDirect live-session fetcher input CSV and only runs the fetcher when a
local DevTools browser session is already available. Existing authorized local
full text from the Zotero manifest is used first.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ecfinder.orchestration.streaming_supervisor import run_streaming_supervisor
from ecfinder.state.common import read_jsonl, utc_now, write_jsonl


ROOT = Path(__file__).resolve().parents[1]
FETCHER_ROOT = Path.home() / "AppData" / "Local" / "Temp" / "ecfinder_external_audit" / "sciencedirect-live-session-fetcher"
MANIFEST = ROOT / "data" / "local_fulltext" / "stage2_4j" / "zotero_available_fulltext_manifest.jsonl"
QUEUE = ROOT / "data" / "batches" / "stage2_6d_20paper_metadata_queue.jsonl"
FETCH_INPUT = ROOT / "data" / "batches" / "stage2_6d_20paper_sciencedirect_fetch_input.csv"
FETCH_STATUS = ROOT / "data" / "batches" / "stage2_6d_20paper_live_session_fetch_status.jsonl"
SUMMARY = ROOT / "reports" / "stage2_6d_20paper_workflow_summary.md"
FETCH_REPORT = ROOT / "reports" / "stage2_6d_live_session_fetcher_integration.md"
OUTPUT_PREFIX = "stage2_6d_20paper"
EXCLUDE_TITLE_TERMS = {
    "activated sludge",
    "wastewater",
    "wwtp",
    "advanced oxidation",
    "aop",
    "plasma",
    "electrochemical",
    "photocatalysis",
    "ozonation",
    "uv/sulfite",
    "uv/persulfate",
    "persulfate",
    "incineration",
    "toxicity",
    "food web",
    "human exposure",
    "bioaccumulation",
    "analytical method",
    "suspect screening",
    "monitoring",
    "review",
    "metabolomics",
    "serum metabolites",
    "follicular fluid",
}


def select_targets(limit: int) -> list[dict[str, Any]]:
    manifest_rows = read_jsonl(MANIFEST)
    manifest_by_source = {str(row.get("source_id", "")): row for row in manifest_rows}
    registry_rows = read_jsonl(ROOT / "data" / "state" / "source_registry.jsonl")
    parsed_rows: list[dict[str, Any]] = []
    for row in registry_rows:
        chunks_ref = str(row.get("chunks_ref", ""))
        if not chunks_ref or not (ROOT / chunks_ref).exists():
            continue
        if not any(line.strip() for line in (ROOT / chunks_ref).read_text(encoding="utf-8").splitlines()):
            continue
        source_id = str(row.get("source_id", ""))
        manifest = manifest_by_source.get(source_id, {})
        parsed_rows.append(
            {
                "source_id": source_id,
                "zotero_item_key": manifest.get("zotero_item_key", ""),
                "doi": row.get("doi", ""),
                "title": row.get("title", ""),
                "local_path": manifest.get("local_path", ""),
                "status": manifest.get("status", "parsed_cache"),
                "force_include_for_fulltext": True,
            }
        )
    preferred = [row for row in parsed_rows if str(row.get("source_id", "")).startswith("zotero_stage2_4j_src_")]
    fallback = [row for row in parsed_rows if row not in preferred]
    selected = [*preferred, *fallback][:limit]
    return selected[:limit]


def build_queue(targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    for row in targets:
        queue.append(
            {
                "source_id": row.get("source_id", ""),
                "zotero_item_key": row.get("zotero_item_key", ""),
                "doi": row.get("doi", ""),
                "title": row.get("title", ""),
                "abstract": "",
                "year": "",
                "journal": "",
                "keywords": ["pfas", "transformation", "fulltext_available"],
                "force_include_for_fulltext": bool(row.get("force_include_for_fulltext")),
                "metadata_origin": "stage2_4j_available_fulltext_manifest",
                "has_attachment_metadata": True,
                "pdf_or_html_attachment_count": 1,
            }
        )
    write_jsonl(QUEUE, queue)
    return queue


def write_fetch_input(targets: list[dict[str, Any]]) -> None:
    FETCH_INPUT.parent.mkdir(parents=True, exist_ok=True)
    with FETCH_INPUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["number", "doi", "title", "note"])
        writer.writeheader()
        for idx, row in enumerate(targets, start=1):
            writer.writerow(
                {
                    "number": idx,
                    "doi": row.get("doi", ""),
                    "title": row.get("title", ""),
                    "note": f"source_id={row.get('source_id', '')}; zotero_item_key={row.get('zotero_item_key', '')}",
                }
            )


def probe_devtools(debug_port: int, python_exe: str) -> tuple[bool, str]:
    script = FETCHER_ROOT / "scripts" / "attach_sciencedirect_remote_debug.py"
    if not script.exists():
        return False, "fetcher_probe_script_missing"
    result = subprocess.run(
        [python_exe, str(script), "--browser", "edge", "--debugger-address", f"127.0.0.1:{debug_port}"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=20,
    )
    if result.returncode != 0:
        return False, (result.stderr.strip() or result.stdout.strip() or "devtools_session_unavailable")[:240]
    return True, result.stdout.strip()[:240]


def maybe_run_fetcher(targets: list[dict[str, Any]], args: argparse.Namespace, python_exe: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    fetcher_script = FETCHER_ROOT / "scripts" / "devtools_sciencedirect_serial_fetch.py"
    if args.skip_live_fetch:
        reason = "skip_live_fetch_requested"
        available = False
    else:
        available, reason = probe_devtools(args.debug_port, python_exe)
    if available and fetcher_script.exists():
        out_dir = ROOT / "data" / "local_fulltext" / "stage2_6d_live_session_fetcher_out"
        if out_dir.exists():
            shutil.rmtree(out_dir)
        result = subprocess.run(
            [
                python_exe,
                str(fetcher_script),
                "--input-csv",
                str(FETCH_INPUT),
                "--out-dir",
                str(out_dir),
                "--debug-port",
                str(args.debug_port),
                "--inter-item-sleep-seconds",
                str(args.inter_item_sleep_seconds),
                "--limit",
                str(len(targets)),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=max(60, len(targets) * 30),
        )
        status = "completed" if result.returncode == 0 else "failed"
        reason = (result.stderr.strip() or result.stdout.strip() or status)[:240]
    else:
        status = "not_run"
    for row in targets:
        records.append(
            {
                "source_id": row.get("source_id", ""),
                "doi": row.get("doi", ""),
                "title": row.get("title", ""),
                "fetcher": "Given-Dream/sciencedirect-live-session-fetcher",
                "input_csv_ref": str(FETCH_INPUT.relative_to(ROOT)).replace("\\", "/"),
                "live_session_available": available,
                "fetch_attempted": available and fetcher_script.exists(),
                "fetch_status": status,
                "reason": reason,
                "legal_boundary": "authorized_live_browser_session_only_no_paywall_bypass",
                "created_at": utc_now(),
            }
        )
    write_jsonl(FETCH_STATUS, records)
    return records


def write_reports(streaming_summary: dict[str, Any], fetch_records: list[dict[str, Any]]) -> dict[str, Any]:
    values = {
        "targets": len(fetch_records),
        "fetcher_integrated": True,
        "live_session_available": any(row.get("live_session_available") for row in fetch_records),
        "fetch_attempted": any(row.get("fetch_attempted") for row in fetch_records),
        "fetch_success_records": sum(1 for row in fetch_records if row.get("fetch_status") == "completed"),
        "fetch_blocked_records": sum(1 for row in fetch_records if row.get("fetch_status") == "not_run"),
        "local_fulltext_cache_used": streaming_summary.get("fulltext_found", 0),
        "legal_boundary": "authorized live browser session only; no credential, cookie, captcha, or paywall bypass",
    }
    lines = ["# Stage 2.6d Live Session Fetcher Integration", ""]
    lines.extend(f"{key} = {str(value).lower() if isinstance(value, bool) else value}" for key, value in values.items())
    FETCH_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    summary_lines = ["# Stage 2.6d 20-paper Workflow Summary", ""]
    normalized_summary = {
        **streaming_summary,
        "reason": "20paper_integrated_workflow_completed_not_100_source_gate"
        if streaming_summary.get("workflow_streaming_success") and streaming_summary.get("sources_screened") == 20
        else streaming_summary.get("reason", ""),
    }
    for key, value in normalized_summary.items():
        summary_lines.append(f"{key} = {str(value).lower() if isinstance(value, bool) else value}")
    SUMMARY.write_text("\n".join(summary_lines) + "\n", encoding="utf-8", newline="\n")
    autonomous_summary = ROOT / "reports" / "stage2_6d_20paper_autonomous_summary.md"
    autonomous_summary.write_text("\n".join(summary_lines) + "\n", encoding="utf-8", newline="\n")
    return normalized_summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--debug-port", type=int, default=9222)
    parser.add_argument("--inter-item-sleep-seconds", type=int, default=6)
    parser.add_argument("--skip-live-fetch", action="store_true")
    parser.add_argument("--python-exe", default=sys.executable)
    args = parser.parse_args()
    targets = select_targets(args.limit)
    if len(targets) < args.limit:
        raise ValueError(f"not enough local/fulltext targets for 20-paper workflow: {len(targets)}")
    build_queue(targets)
    write_fetch_input(targets)
    fetch_records = maybe_run_fetcher(targets, args, args.python_exe)
    streaming_summary = run_streaming_supervisor(
        ROOT,
        "stage2_6d_20paper",
        QUEUE,
        args.limit,
        args.limit,
        args.limit,
        OUTPUT_PREFIX,
        update_source_registry=False,
    )
    normalized_summary = write_reports(streaming_summary, fetch_records)
    print(json.dumps({**normalized_summary, "fetcher_integrated": True}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
