"""Load and validate ECfinder reusable skill contracts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REQUIRED_SKILL_FILES = ["instruction_ref", "input_schema_ref", "output_schema_ref"]


@dataclass(frozen=True)
class SkillContract:
    skill_id: str
    agent_name: str
    version: str
    instruction_ref: str
    input_schema_ref: str
    output_schema_ref: str
    status: str
    owner_agent: str
    called_by: list[str]
    token_policy: str
    last_updated: str


class SkillRegistry:
    def __init__(self, root: Path, registry_ref: str = "skills/skill_registry.json") -> None:
        self.root = root
        self.registry_path = root / registry_ref

    def load(self) -> list[SkillContract]:
        payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
        return [SkillContract(**item) for item in payload.get("skills", [])]

    def active(self) -> list[SkillContract]:
        return [skill for skill in self.load() if skill.status == "active"]

    def by_agent(self, agent_name: str) -> SkillContract | None:
        for skill in self.active():
            if skill.agent_name == agent_name:
                return skill
        return None

    def by_task_type(self, task_type: str) -> SkillContract | None:
        mapping = {
            "metadata": "MetadataAgent",
            "screening": "TitleAbstractScreeningAgent",
            "download": "DownloadAgent",
            "zotero": "ZoteroAgent",
            "parse": "ParseAgent",
            "chunk": "ParseAgent",
            "extract": "ExtractionAgent",
            "review": "ReviewAgent",
            "write_database": "DatabaseWriteAgent",
            "supervisor": "SupervisorAgent",
            "skill_manager": "SkillManagerAgent",
        }
        agent = mapping.get(task_type)
        return self.by_agent(agent) if agent else None

    def validate(self) -> dict[str, Any]:
        active = self.active()
        missing: list[dict[str, str]] = []
        for skill in active:
            for field in REQUIRED_SKILL_FILES:
                ref = getattr(skill, field)
                if not ref or not (self.root / ref).exists():
                    missing.append({"skill_id": skill.skill_id, "missing": field, "ref": ref})
            skill_dir = self.root / Path(skill.instruction_ref).parent
            for name in ["skill.yaml", "examples.jsonl", "CHANGELOG.md"]:
                if not (skill_dir / name).exists():
                    missing.append({"skill_id": skill.skill_id, "missing": name, "ref": str(skill_dir / name)})
            if not skill.version:
                missing.append({"skill_id": skill.skill_id, "missing": "version", "ref": ""})
            if not skill.skill_id:
                missing.append({"skill_id": "", "missing": "skill_id", "ref": ""})
            if not skill.called_by:
                missing.append({"skill_id": skill.skill_id, "missing": "called_by", "ref": ""})
        return {
            "active_skills": len(active),
            "skills_missing_contracts": len(missing),
            "missing_contracts": missing,
        }


def load_active_skills(root: Path) -> list[SkillContract]:
    return SkillRegistry(root).active()
