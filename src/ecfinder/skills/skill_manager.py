"""SkillManagerAgent support for versioned skill audits."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ecfinder.state.common import read_jsonl, sha256_text, utc_now, write_jsonl

from .skill_registry import SkillRegistry


CHANGE_LOG = Path("data/state/skill_change_log.jsonl")


class SkillManagerAgent:
    """Audit skill contracts and maintain versioned change records."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.registry = SkillRegistry(root)

    def audit(self) -> dict[str, Any]:
        result = self.registry.validate()
        result["skill_manager_agent_ready"] = result["skills_missing_contracts"] == 0
        return result

    def record_change(
        self,
        skill_id: str,
        old_version: str,
        new_version: str,
        reason: str,
        changed_files: list[str],
    ) -> dict[str, Any]:
        record = {
            "change_id": sha256_text("|".join([skill_id, old_version, new_version, reason]))[:20],
            "skill_id": skill_id,
            "old_version": old_version,
            "new_version": new_version,
            "reason": reason,
            "changed_files": changed_files,
            "validation_required": True,
            "created_at": utc_now(),
        }
        path = self.root / CHANGE_LOG
        records = [row for row in read_jsonl(path) if row.get("change_id") != record["change_id"]]
        records.append(record)
        write_jsonl(path, records)
        return record
