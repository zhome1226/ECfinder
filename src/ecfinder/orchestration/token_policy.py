"""Token policy checks for ECfinder skill-based workflow."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ecfinder.state.common import read_jsonl


LONG_CONTEXT_KEYS = {"text", "full_text", "chunk_text", "full_abstract", "full_chunk", "stdout", "stderr"}


class TokenPolicy:
    """Validate refs-first task payloads and basic duplicate-risk indicators."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def task_payload_violations(self) -> list[dict[str, Any]]:
        violations: list[dict[str, Any]] = []
        for path in (self.root / "data" / "tasks").glob("*.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            for key in LONG_CONTEXT_KEYS:
                if key in payload:
                    violations.append({"task_path": str(path), "violation": f"long_context_key:{key}"})
            for key, value in payload.items():
                if isinstance(value, str) and len(value) > 5000:
                    violations.append({"task_path": str(path), "violation": f"long_string:{key}"})
        return violations

    def duplicate_task_violations(self) -> list[dict[str, Any]]:
        seen: dict[tuple[str, str, str], str] = {}
        violations: list[dict[str, Any]] = []
        for row in read_jsonl(self.root / "data" / "state" / "task_registry.jsonl"):
            key = (str(row.get("source_id", "")), str(row.get("task_type", "")), str(row.get("agent", "")))
            task_id = str(row.get("task_id", ""))
            if key in seen and not task_id.startswith("stage2_4b_") and not task_id.startswith("stage2_4_"):
                violations.append({"task_id": task_id, "duplicates": seen[key], "key": "|".join(key)})
            seen[key] = task_id
        return violations

    def cost_audit(self) -> dict[str, Any]:
        stats_path = self.root / "data" / "state" / "cache_stats.json"
        stats = json.loads(stats_path.read_text(encoding="utf-8")) if stats_path.exists() else {}
        long_context = self.task_payload_violations()
        duplicate_tasks = self.duplicate_task_violations()
        estimated_saved = (
            int(stats.get("screening_cache_hits", 0)) * 1000
            + int(stats.get("extraction_cache_hits", 0)) * 2500
            + int(stats.get("review_cache_hits", 0)) * 1500
        )
        return {
            "screening_cache_hits": int(stats.get("screening_cache_hits", 0)),
            "screening_cache_misses": int(stats.get("screening_cache_misses", 0)),
            "extraction_cache_hits": int(stats.get("extraction_cache_hits", 0)),
            "extraction_cache_misses": int(stats.get("extraction_cache_misses", 0)),
            "review_cache_hits": int(stats.get("review_cache_hits", 0)),
            "review_cache_misses": int(stats.get("review_cache_misses", 0)),
            "estimated_tokens_saved": estimated_saved,
            "long_context_violations": len(long_context),
            "duplicate_task_violations": len(duplicate_tasks),
        }
