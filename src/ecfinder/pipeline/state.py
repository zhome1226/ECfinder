"""Pipeline state and event persistence."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ecfinder.pipeline.contracts import PIPELINE_VERSION, append_jsonl, normalize_text_value


STATE_REL = "data/clean/pipeline_state.json"
EVENTS_REL = "data/clean/pipeline_events.jsonl"

COUNTER_KEYS = [
    "sources_discovered",
    "sources_screened",
    "sources_downloaded",
    "sources_parsed",
    "chunks_created",
    "records_extracted",
    "records_validated",
    "records_manual_review",
    "records_rejected",
    "records_auxiliary",
]

GATE_KEYS = [
    "preflight",
    "jsonl_integrity",
    "clean_database_integrity",
    "natural_environment_boundary",
    "report_consistency",
    "stage_readiness",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_run_id() -> str:
    return f"run_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"


def default_state(active_profile: str = "") -> dict[str, Any]:
    now = utc_now()
    return {
        "pipeline_version": PIPELINE_VERSION,
        "active_profile": active_profile,
        "current_step": "",
        "last_successful_step": "",
        "status": "idle",
        "started_at": "",
        "updated_at": now,
        "run_id": "",
        "counters": {key: 0 for key in COUNTER_KEYS},
        "gates": {key: "pending" for key in GATE_KEYS},
        "failure": {
            "failed_step": "",
            "reason": "",
            "error_file": "",
        },
    }


def state_path(root: Path) -> Path:
    return root / STATE_REL


def events_path(root: Path) -> Path:
    return root / EVENTS_REL


def load_state(root: Path) -> dict[str, Any]:
    path = state_path(root)
    if not path.exists():
        return default_state()
    with path.open("r", encoding="utf-8") as handle:
        state = json.load(handle)
    for key, value in default_state().items():
        state.setdefault(key, value)
    state["counters"] = {**default_state()["counters"], **(state.get("counters") or {})}
    state["gates"] = {**default_state()["gates"], **(state.get("gates") or {})}
    state["failure"] = {**default_state()["failure"], **(state.get("failure") or {})}
    return state


def save_state(root: Path, state: dict[str, Any]) -> None:
    path = state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = utc_now()
    with path.open("w", encoding="utf-8") as handle:
        json.dump(normalize_text_value(state), handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def start_run(root: Path, profile: str) -> dict[str, Any]:
    state = load_state(root)
    now = utc_now()
    state.update(
        {
            "pipeline_version": PIPELINE_VERSION,
            "active_profile": profile,
            "current_step": "start",
            "status": "running",
            "started_at": now,
            "updated_at": now,
            "run_id": new_run_id(),
            "gates": {key: "pending" for key in GATE_KEYS},
            "failure": {
                "failed_step": "",
                "reason": "",
                "error_file": "",
            },
        }
    )
    save_state(root, state)
    return state


def mark_gate(root: Path, state: dict[str, Any], gate: str, status: str) -> None:
    state.setdefault("gates", {})[gate] = status
    save_state(root, state)


def mark_step(root: Path, state: dict[str, Any], step: str, status: str = "running") -> None:
    state["current_step"] = step
    state["status"] = status
    save_state(root, state)


def mark_success(root: Path, state: dict[str, Any], step: str, status: str = "completed") -> None:
    state["current_step"] = step
    state["last_successful_step"] = step
    state["status"] = status
    save_state(root, state)


def mark_failed(root: Path, state: dict[str, Any], step: str, reason: str, error_file: str) -> None:
    state["current_step"] = step
    state["status"] = "failed"
    state["failure"] = {
        "failed_step": step,
        "reason": reason,
        "error_file": error_file,
    }
    save_state(root, state)


def update_counters(root: Path, state: dict[str, Any], counters: dict[str, int]) -> None:
    state.setdefault("counters", {})
    state["counters"].update({key: int(value) for key, value in counters.items() if key in COUNTER_KEYS})
    save_state(root, state)


def write_event(
    root: Path,
    run_id: str,
    step: str,
    event_type: str,
    message: str,
    input_files: list[str] | None = None,
    output_files: list[str] | None = None,
    counts: dict[str, Any] | None = None,
) -> None:
    append_jsonl(
        events_path(root),
        {
            "run_id": run_id,
            "step": step,
            "event_type": event_type,
            "message": message,
            "input_files": input_files or [],
            "output_files": output_files or [],
            "counts": counts or {},
            "timestamp": utc_now(),
        },
    )
