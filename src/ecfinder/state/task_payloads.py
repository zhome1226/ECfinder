"""Task payload creation for Codex/agent handoff by reference."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import read_jsonl, relative_path, utc_now, write_json, write_jsonl


TASK_REGISTRY_PATH = Path("data/state/task_registry.jsonl")


EXTRACT_PROMPTS = [
    "prompts/system/global_agent_policy.md",
    "prompts/system/natural_environment_boundary.md",
    "prompts/system/pfas_transformation_extraction.md",
    "prompts/system/json_output_rules.md",
]

REVIEW_PROMPTS = [
    "prompts/system/global_agent_policy.md",
    "prompts/system/natural_environment_boundary.md",
    "prompts/system/evidence_grounded_review.md",
    "prompts/system/json_output_rules.md",
]


def create_task_payload(
    root: Path,
    tasks_dir: Path,
    registry_path: Path,
    task_id: str,
    task_type: str,
    agent: str,
    source_id: str,
    input_refs: dict[str, str],
    output_expected: str,
    reason: str,
    chunk_id: str | None = None,
) -> dict[str, Any]:
    prompt_refs = REVIEW_PROMPTS if task_type == "review" else EXTRACT_PROMPTS
    schema_ref = "schemas/review_decision.schema.json" if task_type == "review" else "schemas/transformation_record.schema.json"
    payload = {
        "task_id": task_id,
        "task_type": task_type,
        "agent": agent,
        "source_id": source_id,
        "chunk_id": chunk_id,
        "input_refs": input_refs,
        "prompt_refs": prompt_refs,
        "schema_ref": schema_ref,
        "output_expected": output_expected,
        "status": "pending",
        "created_at": utc_now(),
        "reason": reason,
    }
    path = tasks_dir / f"{task_id}.json"
    write_json(path, payload)
    registry_record = {
        "task_id": task_id,
        "task_type": task_type,
        "agent": agent,
        "source_id": source_id,
        "task_path": relative_path(root, path),
        "status": "pending",
        "created_at": payload["created_at"],
    }
    records = [item for item in read_jsonl(registry_path) if item.get("task_id") != task_id]
    records.append(registry_record)
    write_jsonl(registry_path, records)
    return payload
