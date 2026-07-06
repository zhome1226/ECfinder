"""Run Stage 2.8 external metadata discovery and dedup pilot."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ecfinder.search import crossref_adapter, openalex_adapter, pubmed_adapter, semantic_scholar_adapter
from ecfinder.search.common import normalize_doi, normalize_title
from ecfinder.state.common import read_jsonl, sha256_text, utc_now, write_jsonl


ROOT = Path(__file__).resolve().parents[1]
METADATA_QUEUE = ROOT / "data" / "batches" / "stage2_6b_zotero_metadata_screening_queue.jsonl"
CANDIDATES = ROOT / "data" / "batches" / "stage2_8_external_metadata_candidates.jsonl"
DEDUPED = ROOT / "data" / "batches" / "stage2_8_external_metadata_deduped.jsonl"
NEW_SOURCES = ROOT / "data" / "batches" / "stage2_8_external_metadata_new_sources.jsonl"
SUMMARY = ROOT / "reports" / "stage2_8_external_metadata_discovery_summary.md"
DEDUP_AUDIT = ROOT / "reports" / "stage2_8_external_dedup_audit.md"
INVENTORY_JSONL = ROOT / "data" / "state" / "stage2_8_existing_agent_skill_inventory.jsonl"
INVENTORY_REPORT = ROOT / "reports" / "stage2_8_existing_agent_skill_inventory.md"


def git_files(*patterns: str) -> list[str]:
    result = subprocess.run(["git", "ls-files", *patterns], cwd=ROOT, text=True, capture_output=True, check=False)
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def classify_path(path_text: str) -> tuple[str, str, str]:
    path = path_text.replace("\\", "/")
    lowered = path.lower()
    if lowered.startswith("agents/") and lowered.endswith(".md"):
        item_type = "agent_md"
    elif "/skill.yaml" in lowered:
        item_type = "skill"
    elif lowered.startswith("prompts/"):
        item_type = "prompt"
    elif lowered.startswith("scripts/"):
        item_type = "script"
    elif lowered.startswith("schemas/"):
        item_type = "schema"
    elif lowered.startswith("configs/"):
        item_type = "config"
    else:
        item_type = "unknown"
    if any(term in lowered for term in ["search", "metadata", "zotero"]):
        purpose = "search" if "search" in lowered else "metadata"
    elif any(term in lowered for term in ["download", "fulltext", "attachment"]):
        purpose = "download"
    elif "screen" in lowered:
        purpose = "screening"
    elif "parse" in lowered or "chunk" in lowered:
        purpose = "parse"
    elif "extract" in lowered:
        purpose = "extraction"
    elif "review" in lowered:
        purpose = "review"
    elif "database" in lowered:
        purpose = "database"
    elif "supervisor" in lowered:
        purpose = "supervisor"
    else:
        purpose = "other"
    agent_name = ""
    if item_type == "agent_md":
        agent_name = Path(path).stem
    elif item_type == "skill":
        try:
            text = (ROOT / path).read_text(encoding="utf-8")
            match = re.search(r"agent_name:\s*([A-Za-z0-9_]+)", text)
            agent_name = match.group(1) if match else ""
        except OSError:
            agent_name = ""
    return item_type, purpose, agent_name


def skill_dir(path: Path) -> Path:
    if path.name == "skill.yaml":
        return path.parent
    return path


def inventory_existing_items() -> list[dict[str, Any]]:
    tracked = set(
        git_files("agents/*")
        + git_files("skills/**")
        + git_files("prompts/**")
        + git_files("configs/**")
        + git_files("schemas/**")
        + git_files("scripts/*search*", "scripts/*download*", "scripts/*zotero*")
    )
    for skill_yaml in ROOT.glob("skills/**/skill.yaml"):
        tracked.add(str(skill_yaml.relative_to(ROOT)).replace("\\", "/"))
    rows: list[dict[str, Any]] = []
    for index, path_text in enumerate(sorted(tracked), start=1):
        path = ROOT / path_text
        item_type, purpose, agent_name = classify_path(path_text)
        candidate_skill_id = ""
        if item_type == "skill" and path.exists():
            text = path.read_text(encoding="utf-8")
            match = re.search(r"skill_id:\s*([A-Za-z0-9_]+)", text)
            candidate_skill_id = match.group(1) if match else ""
        base = skill_dir(path)
        has_instruction = path.exists() and (path.name == "instruction.md" or (base / "instruction.md").exists() or path.suffix.lower() == ".md")
        has_input_schema = (base / "input.schema.json").exists() or path.name == "input.schema.json"
        has_output_schema = (base / "output.schema.json").exists() or path.name == "output.schema.json"
        has_version = bool(candidate_skill_id and path.exists() and "version:" in path.read_text(encoding="utf-8")) if item_type == "skill" else False
        has_token_policy = bool(path.exists() and "token_policy" in path.read_text(encoding="utf-8", errors="replace")) if item_type == "skill" else False
        migration_action = "keep"
        notes = "Existing tracked artifact."
        if item_type == "agent_md" and agent_name == "SearchAgent":
            migration_action = "merge_with_existing"
            notes = "Legacy SearchAgent strategy merged into search_planning and external metadata discovery contracts."
        elif item_type == "agent_md" and agent_name == "DownloadAgent":
            migration_action = "merge_with_existing"
            notes = "Legacy DownloadAgent lawful access constraints merged into lawful and external fulltext resolution contracts."
        elif item_type in {"prompt", "unknown"}:
            migration_action = "manual_review"
        rows.append(
            {
                "item_id": f"stage2_8_inventory_{index:04d}",
                "path": path_text,
                "item_type": item_type,
                "agent_name": agent_name,
                "candidate_skill_id": candidate_skill_id,
                "purpose": purpose,
                "has_instruction": bool(has_instruction),
                "has_input_schema": bool(has_input_schema),
                "has_output_schema": bool(has_output_schema),
                "has_version": bool(has_version),
                "has_token_policy": bool(has_token_policy),
                "can_be_registered_as_skill": item_type == "skill" and has_instruction and has_input_schema and has_output_schema and has_version,
                "migration_action": migration_action,
                "notes": notes,
            }
        )
    write_jsonl(INVENTORY_JSONL, rows)
    write_inventory_report(rows)
    return rows


def write_inventory_report(rows: list[dict[str, Any]]) -> None:
    agents = sum(1 for row in rows if row["item_type"] == "agent_md")
    skills = sum(1 for row in rows if row["item_type"] == "skill")
    merged = sum(1 for row in rows if row["migration_action"] == "merge_with_existing")
    lines = [
        "# Stage 2.8 Existing Agent Skill Inventory",
        "",
        f"existing_agents_found = {agents}",
        f"existing_skills_found = {skills}",
        f"agents_converted_or_merged = {merged}",
        "",
        "| path | type | agent | skill_id | purpose | migration_action | notes |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row['path']} | {row['item_type']} | {row['agent_name']} | {row['candidate_skill_id']} | "
            f"{row['purpose']} | {row['migration_action']} | {row['notes']} |"
        )
    INVENTORY_REPORT.parent.mkdir(parents=True, exist_ok=True)
    INVENTORY_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def load_queries(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    payload = json.loads(text)
    if not isinstance(payload, list):
        raise ValueError("query config must be a list")
    return [dict(item) for item in payload]


def metadata_hash(row: dict[str, Any]) -> str:
    payload = {
        "doi": normalize_doi(row.get("doi")),
        "title": row.get("title", ""),
        "abstract": row.get("abstract", ""),
        "year": row.get("year", ""),
        "journal": row.get("journal", ""),
    }
    return sha256_text(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def title_abstract_hash(row: dict[str, Any]) -> str:
    payload = {"title": normalize_title(str(row.get("title", ""))), "abstract": " ".join(str(row.get("abstract", "")).split()).lower()}
    return sha256_text(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def dedup_key(row: dict[str, Any]) -> str:
    doi = normalize_doi(row.get("doi"))
    if doi:
        return f"doi:{doi}"
    title = normalize_title(str(row.get("title", "")))
    return f"title:{sha256_text(title)}" if title else ""


def existing_keys() -> tuple[set[str], set[str]]:
    zotero_keys: set[str] = set()
    existing_batch_keys: set[str] = set()
    for row in read_jsonl(METADATA_QUEUE):
        key = dedup_key(row)
        if key:
            zotero_keys.add(key)
    for path in [
        ROOT / "data" / "state" / "stage2_6c_streaming_source_status.jsonl",
        ROOT / "data" / "state" / "stage2_6d_streaming_source_status.jsonl",
        ROOT / "data" / "state" / "stage2_6e_streaming_source_status.jsonl",
        ROOT / "data" / "state" / "stage2_6f_streaming_source_status.jsonl",
        ROOT / "data" / "state" / "stage2_7_library_source_status.jsonl",
        ROOT / "data" / "cache" / "decision_cache.jsonl",
    ]:
        for row in read_jsonl(path):
            key = dedup_key(row)
            if key:
                existing_batch_keys.add(key)
    return zotero_keys, existing_batch_keys


def to_candidate(record: dict[str, Any], query: dict[str, Any], rank: int) -> dict[str, Any]:
    row = dict(record)
    row.setdefault("abstract", "")
    row.setdefault("keywords", [])
    row["doi"] = normalize_doi(row.get("doi"))
    row["external_source_id"] = f"external_stage2_8_{row.get('source_provider', 'other')}_{sha256_text((row.get('doi') or row.get('title') or '') + str(rank))[:12]}"
    row["source_id"] = row["external_source_id"]
    row["source_origin"] = "external_search"
    row["query_id"] = query["query_id"]
    row["query_text"] = query["query_text"]
    row["metadata_hash"] = metadata_hash(row)
    row["title_abstract_hash"] = title_abstract_hash(row)
    row["dedup_key"] = dedup_key(row)
    row["discovery_status"] = "candidate"
    row["retrieved_at"] = utc_now()
    row["hit_rank"] = rank
    row["has_pdf_or_html_attachment"] = False
    row["attachment_count"] = 0
    row["pdf_or_html_attachment_count"] = 0
    row["source_provider"] = row.get("source_provider") or "other"
    return row


def run_provider_search(query: dict[str, Any], max_results: int) -> list[dict[str, Any]]:
    adapters = [crossref_adapter.search, openalex_adapter.search, semantic_scholar_adapter.search, pubmed_adapter.search]
    candidates: list[dict[str, Any]] = []
    for adapter in adapters:
        result = adapter(query["query_text"], max_results=max_results)
        for rank, record in enumerate(result.records[:max_results], start=1):
            candidate = to_candidate(record, query, rank)
            candidate["provider_available"] = result.available
            candidate["provider_error"] = result.error
            candidates.append(candidate)
    return candidates


def discover_external_metadata(queries: list[dict[str, Any]], max_results_per_query: int, max_candidates: int) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for query in queries:
        candidates.extend(run_provider_search(query, max_results_per_query))
        if len(candidates) >= max_candidates:
            break
    return candidates[:max_candidates]


def deduplicate(candidates: list[dict[str, Any]], max_new_sources: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    zotero_keys, existing_batch_keys = existing_keys()
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    new_sources: list[dict[str, Any]] = []
    counts = {
        "duplicates_against_zotero": 0,
        "duplicates_against_existing_batches": 0,
        "duplicates_within_external_candidates": 0,
    }
    for row in candidates:
        key = str(row.get("dedup_key", ""))
        status = "new_unique_external_source"
        if not key:
            status = "missing_dedup_key"
        elif key in zotero_keys:
            counts["duplicates_against_zotero"] += 1
            status = "duplicate_against_zotero"
        elif key in existing_batch_keys:
            counts["duplicates_against_existing_batches"] += 1
            status = "duplicate_against_existing_batches"
        elif key in seen:
            counts["duplicates_within_external_candidates"] += 1
            status = "duplicate_within_external_candidates"
        else:
            seen.add(key)
        out = dict(row)
        out["dedup_status"] = status
        deduped.append(out)
        if status == "new_unique_external_source" and len(new_sources) < max_new_sources:
            source = dict(out)
            source["discovery_status"] = "new_unique_external_source"
            new_sources.append(source)
    counts["new_unique_external_sources"] = len(new_sources)
    return deduped, new_sources, counts


def write_summary(candidates: list[dict[str, Any]], deduped: list[dict[str, Any]], new_sources: list[dict[str, Any]], dedup_counts: dict[str, int], queries: list[dict[str, Any]]) -> None:
    providers = sorted({str(row.get("source_provider", "")) for row in candidates if row.get("source_provider")})
    total = len(candidates)
    with_abs = sum(1 for row in candidates if row.get("abstract"))
    with_oa = sum(1 for row in candidates if row.get("open_access_hint"))
    lines = [
        "# Stage 2.8 External Metadata Discovery Summary",
        "",
        f"external_query_families = {len(queries)}",
        f"providers_attempted = crossref,openalex,semantic_scholar,pubmed",
        f"providers_returned_records = {','.join(providers)}",
        f"total_external_candidates = {total}",
        f"duplicates_against_zotero = {dedup_counts['duplicates_against_zotero']}",
        f"duplicates_against_existing_batches = {dedup_counts['duplicates_against_existing_batches']}",
        f"duplicates_within_external_candidates = {dedup_counts['duplicates_within_external_candidates']}",
        f"new_unique_external_sources = {len(new_sources)}",
        f"sources_with_abstract = {with_abs}",
        f"sources_without_abstract = {total - with_abs}",
        f"sources_with_open_access_hint = {with_oa}",
        f"candidates_ref = {CANDIDATES.relative_to(ROOT).as_posix()}",
        f"deduped_ref = {DEDUPED.relative_to(ROOT).as_posix()}",
        f"new_sources_ref = {NEW_SOURCES.relative_to(ROOT).as_posix()}",
    ]
    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    audit_lines = [
        "# Stage 2.8 External Dedup Audit",
        "",
        f"total_external_candidates = {total}",
        f"duplicates_against_zotero = {dedup_counts['duplicates_against_zotero']}",
        f"duplicates_against_existing_batches = {dedup_counts['duplicates_against_existing_batches']}",
        f"new_unique_external_sources = {len(new_sources)}",
        "",
        "| dedup_status | count |",
        "| --- | ---: |",
    ]
    status_counts: dict[str, int] = {}
    for row in deduped:
        status_counts[str(row.get("dedup_status", ""))] = status_counts.get(str(row.get("dedup_status", "")), 0) + 1
    for key in sorted(status_counts):
        audit_lines.append(f"| {key} | {status_counts[key]} |")
    DEDUP_AUDIT.write_text("\n".join(audit_lines) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Stage 2.8 external metadata discovery.")
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--max-results-per-query", type=int, default=20)
    parser.add_argument("--max-candidates", type=int, default=300)
    parser.add_argument("--max-new-sources", type=int, default=100)
    args = parser.parse_args()
    inventory_existing_items()
    query_path = args.queries if args.queries.is_absolute() else ROOT / args.queries
    queries = sorted(load_queries(query_path), key=lambda row: int(row.get("priority", 0)), reverse=True)[:15]
    candidates = discover_external_metadata(queries, args.max_results_per_query, args.max_candidates)
    deduped, new_sources, dedup_counts = deduplicate(candidates, args.max_new_sources)
    write_jsonl(CANDIDATES, candidates)
    write_jsonl(DEDUPED, deduped)
    write_jsonl(NEW_SOURCES, new_sources)
    write_summary(candidates, deduped, new_sources, dedup_counts, queries)
    print(
        json.dumps(
            {
                "external_candidates_found": len(candidates),
                "external_query_families": len(queries),
                "new_unique_external_sources": len(new_sources),
                "duplicates_against_zotero": dedup_counts["duplicates_against_zotero"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
