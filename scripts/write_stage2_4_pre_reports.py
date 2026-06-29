"""Write Stage 2.4-pre cache and prompt layer reports from state files."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ecfinder.state.common import read_jsonl


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
STATE = ROOT / "data" / "state"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def average_task_payload_size() -> int:
    payloads = list((ROOT / "data" / "tasks").glob("*.json"))
    if not payloads:
        return 0
    return sum(path.stat().st_size for path in payloads) // len(payloads)


def main() -> int:
    source_registry = read_jsonl(STATE / "source_registry.jsonl")
    artifact_index = read_jsonl(STATE / "artifact_index.jsonl")
    decision_cache = read_jsonl(STATE / "decision_cache.jsonl")
    task_registry = read_jsonl(STATE / "task_registry.jsonl")
    cache_stats = read_json(STATE / "cache_stats.json")
    status_records = read_jsonl(ROOT / "data" / "batches" / "stage2_3_10source_status.jsonl")
    long_text_removed = all(
        key not in record for record in status_records for key in ["stdout", "stderr", "abstract", "text", "evidence_quote"]
    )
    ready = bool(source_registry and artifact_index and long_text_removed and cache_stats.get("tasks_created", 0) >= 0)

    summary_lines = [
        "# Stage 2.4-pre Cache and Prompt Layer",
        "",
        f"source_registry_records = {len(source_registry)}",
        f"artifact_index_records = {len(artifact_index)}",
        f"decision_cache_records = {len(decision_cache)}",
        f"task_registry_records = {len(task_registry)}",
        f"metadata_cache_hits = {cache_stats.get('metadata_cache_hits', 0)}",
        f"metadata_cache_misses = {cache_stats.get('metadata_cache_misses', 0)}",
        f"tasks_created = {cache_stats.get('tasks_created', 0)}",
        f"average_task_payload_size = {average_task_payload_size()}",
        f"long_text_removed_from_batch_status = {str(long_text_removed).lower()}",
        f"ready_for_30_source_loop = {str(ready).lower()}",
        "",
        "The Stage 2.3 run outputs remain run-local artifacts. Stage 2.4-pre adds source/artifact/decision/task references for reuse before any 30-source expansion.",
    ]
    (REPORTS / "stage2_4_pre_cache_and_prompt_layer.md").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    design_lines = [
        "# Cache State Design",
        "",
        "- `data/state/source_registry.jsonl` stores one source-level row per DOI/title with artifact references.",
        "- `data/state/artifact_index.jsonl` stores reusable metadata, screening, download, chunk, extraction, and review artifacts with SHA-256 hashes.",
        "- `data/state/decision_cache.jsonl` stores short decision references keyed by task type, input hash, prompt version, and schema version.",
        "- `data/state/task_registry.jsonl` stores task payload paths only; long text remains in artifact files.",
        "- `data/tasks/*.json` stores agent handoff payloads with `prompt_refs`, `schema_ref`, and input artifact references.",
        "- `data/state/cache_stats.json` summarizes cache hits, misses, tasks created, and a conservative token-saved estimate.",
    ]
    (REPORTS / "cache_state_design.md").write_text("\n".join(design_lines) + "\n", encoding="utf-8")

    contracts_lines = [
        "# Agent Prompt and Schema Contracts",
        "",
        "Prompt refs:",
        "- `prompts/system/global_agent_policy.md`",
        "- `prompts/system/natural_environment_boundary.md`",
        "- `prompts/system/pfas_transformation_extraction.md`",
        "- `prompts/system/evidence_grounded_review.md`",
        "- `prompts/system/json_output_rules.md`",
        "",
        "Schema refs:",
        "- `schemas/source_metadata.schema.json`",
        "- `schemas/screening_decision.schema.json`",
        "- `schemas/chunk.schema.json`",
        "- `schemas/transformation_record.schema.json`",
        "- `schemas/review_decision.schema.json`",
        "- `schemas/agent_task.schema.json`",
        "- `schemas/batch_status.schema.json`",
        "",
        "Agent tasks must pass refs rather than full source text. Extraction tasks reference metadata and chunk artifacts. Review tasks reference candidate record artifacts and evidence chunk artifacts.",
    ]
    (REPORTS / "agent_prompt_schema_contracts.md").write_text("\n".join(contracts_lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
