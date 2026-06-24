"""Command-line entrypoint for ECfinder stage 1."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ecfinder.download.pdf_downloader import acquire_screened_sources
from ecfinder.download.semantic_screen import screen_search_results
from ecfinder.extract.llm_extractor import extract_from_chunks_stub
from ecfinder.parse.chunker import chunk_parsed_sections
from ecfinder.review.reextractor import build_reextract_tasks
from ecfinder.review.rule_checks import review_records
from ecfinder.search.search_runner import run_search
from ecfinder.skills_inventory import write_inventory
from ecfinder.utils.logging import write_jsonl


def repo_root_from_cwd() -> Path:
    cwd = Path.cwd()
    if (cwd / "pyproject.toml").exists():
        return cwd
    for parent in cwd.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return cwd


def ensure_stage1_files(root: Path) -> None:
    paths = [
        "data/interim/search_results.jsonl",
        "data/interim/screened_sources.jsonl",
        "data/interim/download_status.jsonl",
        "data/interim/parsed_sections.jsonl",
        "data/interim/chunks.jsonl",
        "data/extracted/pfas_transformation_records_raw.jsonl",
        "data/reviewed/pfas_transformation_records_validated.jsonl",
        "data/reviewed/rejected_records.jsonl",
    ]
    for rel in paths:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text("", encoding="utf-8")
    csv_path = root / "data" / "reviewed" / "pfas_transformation_records_validated.csv"
    if not csv_path.exists():
        csv_path.write_text(
            "record_id,source_id,chunk_id,doi,parent_name,product_name,transformation_process,matrix,condition_type,natural_environment_context,evidence_quote,confidence,reviewer_status\n",
            encoding="utf-8",
        )


def write_stage1_summary(root: Path) -> None:
    counts = {}
    for rel in [
        "data/interim/search_results.jsonl",
        "data/interim/screened_sources.jsonl",
        "data/interim/download_status.jsonl",
        "data/interim/parsed_sections.jsonl",
        "data/interim/chunks.jsonl",
        "data/extracted/pfas_transformation_records_raw.jsonl",
        "data/reviewed/pfas_transformation_records_validated.jsonl",
        "data/reviewed/rejected_records.jsonl",
    ]:
        path = root / rel
        counts[rel] = sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip()) if path.exists() else 0
    decisions: dict[str, int] = {}
    screened_path = root / "data" / "interim" / "screened_sources.jsonl"
    if screened_path.exists():
        for line in screened_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                decisions[item.get("decision", "unknown")] = decisions.get(item.get("decision", "unknown"), 0) + 1

    download_status: dict[str, int] = {}
    download_path = root / "data" / "interim" / "download_status.jsonl"
    if download_path.exists():
        for line in download_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                key = f"{item.get('download_status', 'unknown')}:{item.get('candidate_kind', 'unknown')}"
                download_status[key] = download_status.get(key, 0) + 1

    raw_files = [
        path
        for path in (root / "data" / "raw").rglob("*")
        if path.is_file() and path.name != ".gitkeep"
    ]

    lines = ["# Stage 1 Summary", "", "| Artifact | Records |", "|---|---:|"]
    lines.extend(f"| `{rel}` | {count} |" for rel, count in counts.items())
    lines.extend(
        [
            "",
            "## Pilot Status",
            "",
            f"- Screening decisions: `{json.dumps(decisions, sort_keys=True)}`",
            f"- Download dry-run candidates: `{json.dumps(download_status, sort_keys=True)}`",
            f"- Raw files present outside `.gitkeep`: {len(raw_files)}",
            "- No copyrighted PDF or publisher HTML is committed.",
            "- LLM extraction is scaffolded but not executed because no LLM runtime is configured in this repository.",
            "- Full-text parsing and chunking remain empty until lawful full text is acquired.",
            "",
        ]
    )
    (root / "reports" / "stage1_summary.md").write_text("\n".join(lines), encoding="utf-8")


def write_failure_analysis(root: Path) -> None:
    rejected = root / "data" / "reviewed" / "rejected_records.jsonl"
    count = sum(1 for line in rejected.read_text(encoding="utf-8").splitlines() if line.strip()) if rejected.exists() else 0
    (root / "reports" / "failure_analysis.md").write_text(
        "# Failure Analysis\n\n"
        f"Rejected or re-extraction records: {count}\n\n"
        "Common reasons will be summarized after ReviewAgent has non-empty input.\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ecfinder")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("inventory")
    sub.add_parser("init-stage1-files")

    search = sub.add_parser("search")
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--sources", default="crossref,openalex")

    sub.add_parser("screen")

    download = sub.add_parser("download")
    download.add_argument("--limit", type=int, default=10)
    download.add_argument("--execute", action="store_true", help="Actually download open PDF URLs.")

    sub.add_parser("chunk")
    sub.add_parser("extract-stub")
    sub.add_parser("review")
    sub.add_parser("summary")

    args = parser.parse_args(argv)
    root = repo_root_from_cwd()

    if args.command == "inventory":
        write_inventory(root / "reports" / "skill_inventory.md", root / "data" / "interim" / "skill_inventory.json")
    elif args.command == "init-stage1-files":
        ensure_stage1_files(root)
        write_stage1_summary(root)
        write_failure_analysis(root)
    elif args.command == "search":
        run_search(root, limit=args.limit, sources=[item.strip() for item in args.sources.split(",") if item.strip()])
    elif args.command == "screen":
        screen_search_results(root)
    elif args.command == "download":
        acquire_screened_sources(root, limit=args.limit, dry_run=not args.execute)
    elif args.command == "chunk":
        chunk_parsed_sections(root)
    elif args.command == "extract-stub":
        extract_from_chunks_stub(root)
    elif args.command == "review":
        review_records(root)
        build_reextract_tasks(root)
        write_failure_analysis(root)
    elif args.command == "summary":
        write_stage1_summary(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
