"""Validate Stage 2.6 reusable skill architecture."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ecfinder.orchestration.token_policy import TokenPolicy
from ecfinder.skills.skill_manager import SkillManagerAgent
from ecfinder.skills.skill_registry import SkillRegistry
from ecfinder.state.common import read_jsonl, write_jsonl


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
AGENTS = [
    "SearchAgent",
    "MetadataAgent",
    "TitleAbstractScreeningAgent",
    "DownloadAgent",
    "ZoteroAgent",
    "ParseAgent",
    "ChunkAgent",
    "ExtractionAgent",
    "ReviewAgent",
    "DatabaseWriteAgent",
    "SupervisorAgent",
    "ExternalSearchAgent",
    "ExternalDownloadAgent",
    "SkillManagerAgent",
]


def run_validator(script: str) -> None:
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / script)], cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise ValueError(f"{script} failed: {result.stderr.strip() or result.stdout.strip()}")


def raw_fulltext_not_tracked() -> None:
    result = subprocess.run(
        ["git", "ls-files", "data/local_fulltext/stage2_4j/pdf", "data/local_fulltext/stage2_4j/html", "data/local_fulltext/stage2_4j/si"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    bad = [line for line in result.stdout.splitlines() if line.strip() and not line.replace("\\", "/").endswith("/.gitkeep")]
    if bad:
        raise ValueError(f"raw fulltext tracked: {bad}")


def agent_audit(registry: SkillRegistry) -> list[dict[str, Any]]:
    active_by_agent = {skill.agent_name: skill for skill in registry.active()}
    rows: list[dict[str, Any]] = []
    for agent in AGENTS:
        skill = active_by_agent.get(agent)
        exists = bool(skill) or agent in {"SearchAgent", "ChunkAgent"}
        implementation_type = "skill" if skill else ("class" if agent in {"SearchAgent", "ChunkAgent"} else "missing")
        reusable = bool(skill)
        rows.append(
            {
                "agent_name": agent,
                "exists": exists,
                "implementation_type": implementation_type,
                "is_reusable_skill": reusable,
                "has_fixed_instruction": bool(skill and (ROOT / skill.instruction_ref).exists()),
                "has_schema_contract": bool(skill and (ROOT / skill.input_schema_ref).exists() and (ROOT / skill.output_schema_ref).exists()),
                "has_input_contract": bool(skill and (ROOT / skill.input_schema_ref).exists()),
                "has_output_contract": bool(skill and (ROOT / skill.output_schema_ref).exists()),
                "uses_refs_not_long_context": bool(skill and "refs" in skill.token_policy or (skill and "only" in skill.token_policy)),
                "has_version": bool(skill and skill.version),
                "called_by_supervisor": bool(skill and ("SupervisorAgent" in skill.called_by or agent in {"SupervisorAgent", "SkillManagerAgent"})),
                "token_risk": "low" if skill else "medium",
                "migration_required": not reusable,
                "notes": "Registered active skill." if skill else "Existing code path is not yet a full reusable skill contract.",
            }
        )
    return rows


def write_agent_audit(rows: list[dict[str, Any]]) -> None:
    lines = ["# Stage 2.6 Agent Skill Audit", "", "| agent_name | implementation_type | is_reusable_skill | migration_required | token_risk | notes |", "| --- | --- | --- | --- | --- | --- |"]
    for row in rows:
        lines.append(
            f"| {row['agent_name']} | {row['implementation_type']} | {str(row['is_reusable_skill']).lower()} | {str(row['migration_required']).lower()} | {row['token_risk']} | {row['notes']} |"
        )
    REPORTS.joinpath("stage2_6_agent_skill_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def write_static_reports(skill_status: dict[str, Any], token_audit: dict[str, Any], readiness: dict[str, Any]) -> None:
    REPORTS.joinpath("stage2_6_skill_manager_design.md").write_text(
        "# Stage 2.6 Skill Manager Design\n\nSkillManagerAgent audits registry contracts, schema refs, supervisor usage, token policy, and versioned changes. It writes data/state/skill_change_log.jsonl and does not extract literature evidence.\n",
        encoding="utf-8",
        newline="\n",
    )
    REPORTS.joinpath("stage2_6_supervisor_agent_design.md").write_text(
        "# Stage 2.6 Supervisor Agent Design\n\nSupervisorAgent reads source_status_board, task_registry, artifact_index, and skill_registry. It sends task_id, skill_id, input_refs, schema_refs, and short_context only, then continues until no runnable tasks remain.\n",
        encoding="utf-8",
        newline="\n",
    )
    REPORTS.joinpath("stage2_6_token_optimization_plan.md").write_text(
        "# Stage 2.6 Token Optimization Plan\n\n1. SupervisorAgent never sends full project context.\n2. Screening uses title/abstract only.\n3. Parsing is deterministic and non-LLM.\n4. Chunk relevance precedes extraction.\n5. Review receives candidate plus evidence snippet only.\n6. DOI, title/abstract, chunk, and candidate hashes drive cache reuse.\n",
        encoding="utf-8",
        newline="\n",
    )
    token_lines = ["# Stage 2.6 Token Cost Audit", ""]
    for key, value in token_audit.items():
        token_lines.append(f"{key} = {value}")
    REPORTS.joinpath("stage2_6_token_cost_audit.md").write_text("\n".join(token_lines) + "\n", encoding="utf-8", newline="\n")
    ready_lines = ["# Stage 2.6 Readiness Summary", ""]
    for key, value in readiness.items():
        rendered = str(value).lower() if isinstance(value, bool) else str(value)
        ready_lines.append(f"{key} = {rendered}")
    REPORTS.joinpath("stage2_6_readiness_summary.md").write_text("\n".join(ready_lines) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    registry = SkillRegistry(ROOT)
    skill_status = registry.validate()
    manager_status = SkillManagerAgent(ROOT).audit()
    if not (ROOT / "data" / "state" / "skill_change_log.jsonl").exists():
        write_jsonl(ROOT / "data" / "state" / "skill_change_log.jsonl", [])
    run_validator("validate_synchronous_review.py")
    run_validator("validate_title_abstract_gate.py")
    run_validator("validate_no_duplicate_work.py")
    token_audit = TokenPolicy(ROOT).cost_audit()
    raw_fulltext_not_tracked()
    rows = agent_audit(registry)
    write_agent_audit(rows)
    agents_not_yet_skills = sum(1 for row in rows if not row["is_reusable_skill"])
    ready = {
        "active_skills": skill_status["active_skills"],
        "skills_missing_contracts": skill_status["skills_missing_contracts"],
        "agents_not_yet_skills": agents_not_yet_skills,
        "supervisor_agent_ready": registry.by_agent("SupervisorAgent") is not None,
        "skill_manager_agent_ready": manager_status["skill_manager_agent_ready"],
        "title_abstract_gate_ready": registry.by_agent("TitleAbstractScreeningAgent") is not None,
        "synchronous_review_ready": True,
        "duplicate_work_prevention_ready": True,
        "token_policy_ready": token_audit["long_context_violations"] == 0,
        "autonomous_workflow_dry_run_passed": (ROOT / "data" / "state" / "stage2_6_autonomous_workflow_dry_run.jsonl").exists(),
        "ready_for_859_title_abstract_screening": False,
        "ready_for_fulltext_extraction": False,
        "reason": "skill_architecture_ready_for_limited_title_abstract_screening_after_review",
    }
    ready["ready_for_859_title_abstract_screening"] = (
        ready["skills_missing_contracts"] == 0
        and ready["supervisor_agent_ready"]
        and ready["skill_manager_agent_ready"]
        and ready["title_abstract_gate_ready"]
        and ready["synchronous_review_ready"]
        and ready["duplicate_work_prevention_ready"]
        and ready["token_policy_ready"]
        and ready["autonomous_workflow_dry_run_passed"]
    )
    ready["ready_for_fulltext_extraction"] = ready["ready_for_859_title_abstract_screening"]
    write_static_reports(skill_status, token_audit, ready)
    print(json.dumps(ready, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
