"""SupervisorAgent that maps runnable tasks to registered skills by refs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ecfinder.skills.skill_registry import SkillRegistry
from ecfinder.state.common import read_jsonl


class SupervisorAgent:
    """Select skills for runnable tasks without passing long context."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.registry = SkillRegistry(root)

    def build_task_payload(self, task: dict[str, Any]) -> dict[str, Any]:
        skill = self.registry.by_task_type(str(task.get("task_type", "")))
        if not skill:
            return {
                "task_id": task.get("task_id", ""),
                "skill_id": "",
                "input_refs": task.get("input_refs", {}),
                "schema_refs": {},
                "short_context": {"reason": "no registered skill"},
                "runnable": False,
            }
        return {
            "task_id": task.get("task_id", ""),
            "skill_id": skill.skill_id,
            "input_refs": task.get("input_refs", {}),
            "schema_refs": {
                "input_schema_ref": skill.input_schema_ref,
                "output_schema_ref": skill.output_schema_ref,
            },
            "short_context": {
                "source_id": task.get("source_id", ""),
                "task_type": task.get("task_type", ""),
                "token_policy": skill.token_policy,
            },
            "runnable": True,
        }

    def runnable_task_payloads(self, batch_id: str) -> list[dict[str, Any]]:
        tasks = read_jsonl(self.root / "data" / "state" / "runnable_tasks.jsonl")
        return [self.build_task_payload(task) for task in tasks if not batch_id or task.get("batch_id", batch_id) == batch_id]
