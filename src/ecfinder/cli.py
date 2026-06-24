"""Command-line entrypoint for ECfinder stage 1."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from ecfinder.agents.codex_extract_agent import prepare_extract_tasks
from ecfinder.agents.codex_reextract_agent import prepare_reextract_tasks
from ecfinder.agents.codex_review_agent import prepare_review_tasks
from ecfinder.agents.codex_screen_agent import prepare_screen_tasks
from ecfinder.download.pdf_downloader import acquire_screened_sources
from ecfinder.download.semantic_screen import screen_search_results
from ecfinder.extract.llm_extractor import extract_from_chunks_stub
from ecfinder.parse.chunker import chunk_parsed_sections
from ecfinder.parse.html_parser import parse_html
from ecfinder.parse.pdf_parser import parse_pdf
from ecfinder.review.export_validated import ENGINEERED_TERMS
from ecfinder.review.export_validated import export_validated
from ecfinder.review.reextractor import build_reextract_tasks
from ecfinder.review.rule_checks import review_records
from ecfinder.review.validate_outputs import validate_outputs
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
            f"- Download/acquisition status: `{json.dumps(download_status, sort_keys=True)}`",
            f"- Ignored raw files present outside `.gitkeep`: {len(raw_files)}",
            "- No copyrighted PDF, publisher HTML, or full parsed text is committed.",
            "- LLM extraction is scaffolded but not executed because no LLM runtime is configured in this repository.",
            "- Parsed section and chunk files committed here are indexes with hashes, not full text.",
            "",
        ]
    )
    (root / "reports" / "stage1_summary.md").write_text("\n".join(lines), encoding="utf-8")


def write_failure_analysis(root: Path) -> None:
    rejected = root / "data" / "reviewed" / "rejected_records.jsonl"
    records = [json.loads(line) for line in rejected.read_text(encoding="utf-8").splitlines() if line.strip()] if rejected.exists() else []
    status_counts: dict[str, int] = {}
    reason_counts: dict[str, int] = {}
    for record in records:
        status = record.get("reviewer_status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        for reason in record.get("review_reasons", []):
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
    (root / "reports" / "failure_analysis.md").write_text(
        "# Failure Analysis\n\n"
        f"Rejected or re-extraction records: {len(records)}\n\n"
        f"Reviewer status counts: `{json.dumps(status_counts, sort_keys=True)}`\n\n"
        f"Reason counts: `{json.dumps(reason_counts, sort_keys=True)}`\n\n"
        "Current pilot uses a conservative regex fallback extractor. All non-empty raw candidates should be treated as re-extraction tasks unless a later LLM or manual review confirms the parent-product relationship against the source chunk.\n",
        encoding="utf-8",
    )


def write_stage1_5_audit(root: Path) -> None:
    extracted = _load_jsonl(root / "data" / "extracted" / "pfas_transformation_records_codex_raw.jsonl")
    validated = _load_jsonl(root / "data" / "reviewed" / "pfas_transformation_records_validated.jsonl")
    manual = _load_jsonl(root / "data" / "reviewed" / "manual_review_records.jsonl")
    rejected = _load_jsonl(root / "data" / "reviewed" / "rejected_records.jsonl")
    reextract = _load_jsonl(root / "data" / "reviewed" / "reextraction_attempts.jsonl")
    status_counts = Counter(record.get("review", {}).get("review_status") or record.get("reviewer_status") for record in rejected)
    lines = [
        "# Stage 1.5 Codex Audit",
        "",
        "- Codex semantic mode does not require `OPENAI_API_KEY`.",
        "- The CLI prepares Codex task packets; the interactive Codex session must write the semantic outputs.",
        "",
        "| Artifact | Count |",
        "|---|---:|",
        f"| codex raw records | {len(extracted)} |",
        f"| validated records | {len(validated)} |",
        f"| manual review records | {len(manual)} |",
        f"| rejected records | {len(rejected)} |",
        f"| re-extraction attempts | {len(reextract)} |",
        "",
        f"Rejected status counts: `{json.dumps(status_counts, sort_keys=True)}`",
        "",
    ]
    (root / "reports" / "stage1_5_codex_summary.md").write_text("\n".join(lines), encoding="utf-8")


def write_stage1_6_audit(root: Path) -> None:
    codex_raw = _load_jsonl(root / "data" / "extracted" / "pfas_transformation_records_codex_raw.jsonl")
    validated = _load_jsonl(root / "data" / "reviewed" / "pfas_transformation_records_validated.jsonl")
    auxiliary = _load_jsonl(root / "data" / "reviewed" / "auxiliary_engineered_biological_records.jsonl")
    manual = _load_jsonl(root / "data" / "reviewed" / "manual_review_records.jsonl")
    rejected = _load_jsonl(root / "data" / "reviewed" / "rejected_records.jsonl")
    reextract = _load_jsonl(root / "data" / "reviewed" / "reextraction_attempts.jsonl")
    validation_report = _load_output_validation(root)
    original_stage1_5_validated_count = sum(
        1
        for record in codex_raw
        if (record.get("review") or {}).get("review_status") in {"validated_high_confidence", "validated_medium_confidence"}
    )
    reclassified_activated_sludge_count = sum(1 for record in auxiliary if "activated sludge" in _record_text(record))
    lines = [
        "# Stage 1.6 Natural Environment Correction Summary",
        "",
        "| Metric | Count |",
        "|---|---:|",
        f"| original_stage1_5_validated_count | {original_stage1_5_validated_count} |",
        f"| reclassified_activated_sludge_count | {reclassified_activated_sludge_count} |",
        f"| natural_environment_validated_count | {len(validated)} |",
        f"| auxiliary_engineered_biological_count | {len(auxiliary)} |",
        f"| manual_review_count | {len(manual)} |",
        f"| rejected_count | {len(rejected)} |",
        f"| reextraction_attempt_count | {len(reextract)} |",
        "",
        "## Reason For Reclassification",
        "",
        "Activated sludge records were reclassified because activated sludge represents an engineered wastewater-treatment matrix, not natural environmental transformation evidence.",
        "",
        "The natural-environment main database now excludes activated sludge, wastewater treatment, WWTP bioreactors, engineered biological treatment, and engineered chemical treatment records.",
        "",
        "## Stage 2 Ready Or Not",
        "",
        "stage2_ready_or_not: not_ready_for_broad_quantitative_synthesis",
        "",
        "Not ready for broad quantitative synthesis. Stage 2 should expand primary full-text retrieval in true natural environment settings before rebuilding the main validated database.",
        "",
        "## Output Validation",
        "",
        f"- validation_ok: {validation_report.get('ok', 'not_run')}",
        f"- zero_validated_reason: {validation_report.get('zero_validated_reason', 'No validation report found.')}",
        "",
    ]
    (root / "reports" / "stage1_6_natural_environment_correction_summary.md").write_text("\n".join(lines), encoding="utf-8")
    _write_auxiliary_summary(root, auxiliary)
    _write_review_quality_audit_stage1_6(root, codex_raw, validated, auxiliary, manual, rejected, reextract)
    _write_stage2_targets(root)


def _write_auxiliary_summary(root: Path, auxiliary: list[dict]) -> None:
    examples = []
    sources = Counter()
    for record in auxiliary:
        sources[record.get("title") or record.get("source_id")] += 1
        examples.append(
            f"- {(record.get('parent_compound') or {}).get('name')} -> {(record.get('product_compound') or {}).get('name')}"
        )
    lines = [
        "# Auxiliary Evidence Summary",
        "",
        f"Auxiliary records: {len(auxiliary)}",
        "",
        "## Source Papers",
        "",
    ]
    lines.extend(f"- {title}: {count}" for title, count in sources.items())
    lines.extend(
        [
            "",
            "## Parent-Product Examples",
            "",
            *(examples[:20] or ["- None"]),
            "",
            "## Why These Records Are Not In The Main Database",
            "",
            "Activated sludge is an engineered wastewater-treatment matrix and is not considered natural environmental transformation evidence.",
            "",
            "## Potential Use",
            "",
            "These records are useful as auxiliary evidence for precursor biotransformation mechanisms, pathway hypotheses, and Stage 2 query expansion, but they must remain outside the natural-environment PFAS transformation database.",
            "",
        ]
    )
    (root / "reports" / "auxiliary_evidence_summary.md").write_text("\n".join(lines), encoding="utf-8")


def _write_stage2_targets(root: Path) -> None:
    targets = [
        "PFAS natural attenuation in groundwater",
        "AFFF-contaminated aquifer transformation",
        "fluorotelomer precursor biotransformation in soil",
        "diPAP / PAP transformation in soil and sediment",
        "FTOH transformation in atmospheric deposition / soil / sediment",
        "FOSA / FOSE environmental biotransformation",
        "FTSA transformation in field-contaminated soil or groundwater",
        "PFAS transformation in wetland, sediment, estuarine, and marine systems",
    ]
    lines = ["# Stage 2 Search Targets", ""]
    lines.extend(f"- {target}" for target in targets)
    lines.extend(
        [
            "",
            "Priority should be primary studies with field sites, natural attenuation, contaminated aquifers, or environmental sample microcosms. Avoid treating activated sludge, WWTP reactors, engineered treatment, or review-only pathway diagrams as main-database evidence.",
            "",
        ]
    )
    (root / "reports" / "stage2_search_targets.md").write_text("\n".join(lines), encoding="utf-8")


def _write_review_quality_audit_stage1_6(
    root: Path,
    codex_raw: list[dict],
    validated: list[dict],
    auxiliary: list[dict],
    manual: list[dict],
    rejected: list[dict],
    reextract: list[dict],
) -> None:
    rejected_status_counts = Counter(
        (record.get("review") or {}).get("review_status") or record.get("reviewer_status") or "unknown"
        for record in rejected
    )
    reextract_outcome_counts = Counter(record.get("outcome") or "unknown" for record in reextract)
    engineered_in_validated = [
        record.get("record_id")
        for record in validated
        if any(term in _record_text(record) for term in ENGINEERED_TERMS)
    ]
    lines = [
        "# Review Quality Audit",
        "",
        "## Stage 1.6 Criteria Correction",
        "",
        "Activated sludge, wastewater treatment, WWTP bioreactors, and engineered biological treatment records are excluded from the natural-environment main database.",
        "",
        "The eight previously validated activated-sludge records were reclassified as auxiliary_engineered_biological_evidence because activated sludge is an engineered wastewater-treatment matrix, not natural environmental transformation evidence.",
        "",
        "## Synchronized Counts",
        "",
        f"- natural_environment_validated_count = {len(validated)}",
        f"- auxiliary_engineered_biological_count = {len(auxiliary)}",
        f"- manual_review_count = {len(manual)}",
        f"- rejected_count = {len(rejected)}",
        f"- reextraction_attempt_count = {len(reextract)}",
        "",
        "| Artifact | Count |",
        "|---|---:|",
        f"| codex raw records reviewed | {len(codex_raw)} |",
        f"| natural-environment validated records | {len(validated)} |",
        f"| auxiliary engineered biological records | {len(auxiliary)} |",
        f"| manual review records | {len(manual)} |",
        f"| rejected records | {len(rejected)} |",
        f"| re-extraction audit attempts | {len(reextract)} |",
        "",
        "## Automated Guardrail",
        "",
        f"- engineered_terms_found_in_validated: {len(engineered_in_validated)}",
        f"- offending_validated_record_ids: `{json.dumps(engineered_in_validated, sort_keys=True)}`",
        "",
        "## Rejected Status Counts",
        "",
        f"`{json.dumps(rejected_status_counts, sort_keys=True)}`",
        "",
        "## Re-extraction Attempt Outcomes",
        "",
        f"`{json.dumps(reextract_outcome_counts, sort_keys=True)}`",
        "",
        "## Review Notes",
        "",
        "- The 8 Stage 1.5 validated activated-sludge records were reclassified as `auxiliary_engineered_biological_evidence` because they are useful mechanistic evidence but not natural-environment evidence.",
        "- Activated-sludge manual candidates with unclear short-chain PFCA attribution were rejected rather than promoted to auxiliary evidence.",
        "- Review/redrawn pathway evidence was rejected as reference-only until the primary source is retrieved and reviewed.",
        "- The main validated database is allowed to contain 0 records at this stage because the corrected corpus does not yet include primary natural-environment records that pass all criteria.",
        "",
    ]
    (root / "reports" / "review_quality_audit.md").write_text("\n".join(lines), encoding="utf-8")


def _record_text(record: dict) -> str:
    return " ".join(str(value) for value in _walk_values(record)).lower()


def _walk_values(value):
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_values(child)
    else:
        yield value


def _load_output_validation(root: Path) -> dict:
    path = root / "reports" / "stage1_7_output_validation.md"
    if not path.exists():
        path = root / "reports" / "output_validation.md"
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    return {
        "ok": "true"
        if "- validation_ok: true" in text or "- ok: True" in text
        else "false"
        if "- validation_ok: false" in text or "- ok: False" in text
        else "unknown",
        "zero_validated_reason": "No records met natural-environment criteria."
        if "No records met natural-environment criteria." in text
        else "",
    }


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def parse_downloaded_sources(root: Path) -> list[dict]:
    from ecfinder.utils.hashing import sha256_text
    from ecfinder.utils.logging import read_jsonl, write_jsonl

    raw_sections = []
    public_index = []
    for item in read_jsonl(root / "data" / "interim" / "download_status.jsonl"):
        if item.get("download_status") != "downloaded" or not item.get("local_path"):
            continue
        local_path = root / item["local_path"]
        if not local_path.exists():
            continue
        suffix = local_path.suffix.lower()
        if suffix == ".pdf":
            sections = parse_pdf(local_path, item["source_id"])
        elif suffix in {".html", ".htm"}:
            sections = parse_html(local_path, item["source_id"])
        else:
            sections = []
        for section in sections:
            text = section.get("text") or ""
            raw_sections.append(section)
            public = {key: value for key, value in section.items() if key != "text"}
            public.update({"text_hash": sha256_text(text), "char_count": len(text), "word_count": len(text.split())})
            public_index.append(public)
    write_jsonl(root / "data" / "raw" / "text" / "parsed_sections_text.jsonl", raw_sections)
    write_jsonl(root / "data" / "interim" / "parsed_sections.jsonl", public_index)
    return public_index


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ecfinder")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("inventory")
    sub.add_parser("init-stage1-files")

    search = sub.add_parser("search")
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--sources", default="crossref,openalex")

    screen = sub.add_parser("screen")
    screen.add_argument("--mode", choices=["fallback", "codex"], default="fallback")
    screen.add_argument("--limit", type=int, default=None)

    download = sub.add_parser("download")
    download.add_argument("--limit", type=int, default=10)
    download.add_argument("--execute", action="store_true", help="Actually download open PDF URLs.")

    sub.add_parser("parse")
    sub.add_parser("chunk")
    extract = sub.add_parser("extract")
    extract.add_argument("--mode", choices=["fallback", "codex"], default="fallback")
    extract.add_argument("--top-chunks", type=int, default=30)
    extract.add_argument("--include-reextract-chunks", action="store_true")

    sub.add_parser("extract-stub")

    review = sub.add_parser("review")
    review.add_argument("--mode", choices=["fallback", "codex"], default="fallback")

    reextract = sub.add_parser("reextract")
    reextract.add_argument("--mode", choices=["fallback", "codex"], default="fallback")
    reextract.add_argument("--max-attempts", type=int, default=2)

    sub.add_parser("audit-stage1-5")
    sub.add_parser("export-validated")
    sub.add_parser("validate-outputs")
    sub.add_parser("audit-stage1-6")
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
        if args.mode == "codex":
            prepare_screen_tasks(root, limit=args.limit)
        else:
            screen_search_results(root)
    elif args.command == "download":
        acquire_screened_sources(root, limit=args.limit, dry_run=not args.execute)
    elif args.command == "parse":
        parse_downloaded_sources(root)
    elif args.command == "chunk":
        chunk_parsed_sections(root)
    elif args.command == "extract":
        if args.mode == "codex":
            prepare_extract_tasks(root, top_chunks=args.top_chunks, include_reextract_chunks=args.include_reextract_chunks)
        else:
            extract_from_chunks_stub(root)
    elif args.command == "extract-stub":
        extract_from_chunks_stub(root)
    elif args.command == "review":
        if args.mode == "codex":
            prepare_review_tasks(root)
        else:
            review_records(root)
            build_reextract_tasks(root)
            write_failure_analysis(root)
    elif args.command == "reextract":
        if args.mode == "codex":
            prepare_reextract_tasks(root, max_attempts=args.max_attempts)
        else:
            build_reextract_tasks(root)
    elif args.command == "audit-stage1-5":
        write_stage1_5_audit(root)
    elif args.command == "export-validated":
        export_validated(root)
    elif args.command == "validate-outputs":
        result = validate_outputs(root)
        report = [
            "# Stage 1.7 Output Validation",
            "",
            f"- validated_jsonl_count: {result['validated_jsonl_count']}",
            f"- validated_csv_data_row_count: {result['validated_csv_data_row_count']}",
            f"- auxiliary_jsonl_count: {result['auxiliary_jsonl_count']}",
            f"- auxiliary_csv_data_row_count: {result['auxiliary_csv_data_row_count']}",
            f"- manual_review_count: {result['manual_review_count']}",
            f"- rejected_count: {result['rejected_count']}",
            f"- reextraction_attempt_count: {result['reextraction_attempt_count']}",
            f"- validated_contains_activated_sludge: {str(result['validated_contains_activated_sludge']).lower()}",
            f"- validated_contains_wastewater_treatment: {str(result['validated_contains_wastewater_treatment']).lower()}",
            f"- jsonl_parse_ok: {str(result['jsonl_parse_ok']).lower()}",
            f"- csv_row_count_ok: {str(result['csv_row_count_ok']).lower()}",
            f"- validation_ok: {str(result['validation_ok']).lower()}",
            f"- stage2_ready_or_not: {result['stage2_ready_or_not']}",
            f"- zero_validated_reason: {result['zero_validated_reason']}",
            "",
            "## Errors",
            "",
            *(f"- {error}" for error in result["errors"]),
            "",
        ]
        (root / "reports" / "stage1_7_output_validation.md").write_text("\n".join(report), encoding="utf-8")
        (root / "reports" / "output_validation.md").write_text("\n".join(report), encoding="utf-8")
        if not result["ok"]:
            return 1
    elif args.command == "audit-stage1-6":
        write_stage1_6_audit(root)
    elif args.command == "summary":
        write_stage1_summary(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
