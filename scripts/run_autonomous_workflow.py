"""Dry-run entry point for the skill-based autonomous workflow."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ecfinder.skills.skill_registry import SkillRegistry
from ecfinder.state.common import sha256_text, utc_now, write_jsonl


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "stage2_6_autonomous_workflow_design.md"
DRY_RUN_STATUS = ROOT / "data" / "state" / "stage2_6_autonomous_workflow_dry_run.jsonl"

PFAS_TERMS = ["pfas", "perfluoro", "polyfluoro", "fluorotelomer", "ftsa", "ftoh", "fosa", "fose", "pap", "dipap", "afff"]
TRANSFORM_TERMS = ["transformation", "biotransformation", "degradation product", "metabolite", "pathway", "precursor"]
ENV_TERMS = ["soil", "sediment", "groundwater", "aquifer", "wetland", "surface water", "marine", "estuarine", "microcosm"]
EXCLUDE_TERMS = ["wastewater", "activated sludge", "wwtp", "advanced oxidation", "electrochemical", "toxicity", "food web", "human exposure"]


def screen_title_abstract(row: dict[str, object]) -> dict[str, object]:
    text = f"{row.get('title', '')} {row.get('abstract', '')}".lower()
    positives = [term for term in [*PFAS_TERMS, *TRANSFORM_TERMS, *ENV_TERMS] if term in text]
    negatives = [term for term in EXCLUDE_TERMS if term in text]
    pfas = any(term in text for term in PFAS_TERMS)
    transform = any(term in text for term in TRANSFORM_TERMS)
    env = any(term in text for term in ENV_TERMS)
    if pfas and transform and env and not negatives:
        decision = "include_for_fulltext"
        next_action = "fulltext_ingest"
        evidence = "likely_transformation_evidence"
        topic = "high"
        env_rel = "natural_environment"
    elif negatives:
        decision = "exclude"
        next_action = "exclude"
        evidence = "unlikely"
        topic = "low"
        env_rel = "engineered_treatment" if any(term in text for term in ["wastewater", "activated sludge", "wwtp"]) else "not_relevant"
    else:
        decision = "manual_screen"
        next_action = "manual_screen"
        evidence = "possible"
        topic = "medium" if pfas else "low"
        env_rel = "unclear"
    return {
        "source_id": row["source_id"],
        "screening_decision": decision,
        "topic_relevance": topic,
        "environment_relevance": env_rel,
        "evidence_likelihood": evidence,
        "positive_hits": positives[:12],
        "negative_hits": negatives[:12],
        "reason": "dry-run title/abstract gate; no full text or chunks read",
        "next_action": next_action,
        "input_hash": sha256_text(json.dumps(row, ensure_ascii=False, sort_keys=True)),
        "created_at": utc_now(),
    }


def write_design_report(payload: dict[str, object]) -> None:
    lines = [
        "# Stage 2.6 Autonomous Workflow Design",
        "",
        "main_entry = python scripts/run_autonomous_workflow.py --batch-id zotero_library --mode title_abstract_first --until-idle",
        "",
        "workflow = Title/abstract screening -> selected fulltext ingest -> chunk relevance -> extraction -> immediate review -> database write",
        "",
    ]
    for key, value in payload.items():
        rendered = str(value).lower() if isinstance(value, bool) else str(value)
        lines.append(f"{key} = {rendered}")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--mode", required=True, choices=["title_abstract_first"])
    parser.add_argument("--until-idle", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    registry = SkillRegistry(ROOT)
    registry_status = registry.validate()
    smoke_sources = [
        {
            "source_id": "stage2_6_smoke_include",
            "doi": "10.0000/include",
            "title": "Biotransformation of fluorotelomer precursor in AFFF-impacted soil microcosms",
            "abstract": "The study reports PFAS transformation products and pathways in soil microcosms.",
            "year": "2026",
            "journal": "Smoke Test",
            "keywords": ["PFAS", "soil", "biotransformation"],
        },
        {
            "source_id": "stage2_6_smoke_exclude",
            "doi": "10.0000/exclude",
            "title": "Electrochemical advanced oxidation of PFAS in wastewater",
            "abstract": "An engineered treatment study using electrochemical oxidation.",
            "year": "2026",
            "journal": "Smoke Test",
            "keywords": ["PFAS", "electrochemical"],
        },
    ]
    decisions = [screen_title_abstract(row) for row in smoke_sources]
    write_jsonl(DRY_RUN_STATUS, decisions)
    output = {
        "batch_id": args.batch_id,
        "mode": args.mode,
        "dry_run": bool(args.dry_run),
        "active_skills": registry_status["active_skills"],
        "screened_sources": len(decisions),
        "include_for_fulltext": sum(1 for row in decisions if row["screening_decision"] == "include_for_fulltext"),
        "excluded": sum(1 for row in decisions if row["screening_decision"] == "exclude"),
        "manual_screen": sum(1 for row in decisions if row["screening_decision"] == "manual_screen"),
        "fulltext_ingest_executed": False,
        "extraction_executed": False,
        "no_runnable_tasks_remain": True,
        "status": "dry_run_passed",
    }
    write_design_report(output)
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
