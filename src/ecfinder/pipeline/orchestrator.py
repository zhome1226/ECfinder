"""Continuous clean-database pipeline orchestrator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ecfinder.pipeline import gates
from ecfinder.pipeline.contracts import clean_database_counts, read_jsonl_strict
from ecfinder.pipeline.exceptions import PipelineGateError
from ecfinder.pipeline.queues import ERROR_QUEUE_REL, clear_error_queue, append_error, ensure_queues, queue_counts
from ecfinder.pipeline.report import (
    write_contracts_report,
    write_diagnosis_report,
    write_preflight_report,
    write_runbook,
)
from ecfinder.pipeline.state import (
    load_state,
    mark_failed,
    mark_gate,
    mark_step,
    mark_success,
    save_state,
    start_run,
    update_counters,
    write_event,
)
from ecfinder.pipeline.steps import create_targeted_followup_handoff_tasks


PROFILES = {"preflight_only", "clean_validation", "targeted_followup"}


def repo_root_from_cwd() -> Path:
    cwd = Path.cwd()
    if (cwd / "pyproject.toml").exists():
        return cwd
    for parent in cwd.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return cwd


def run_pipeline(root: Path, profile: str, max_sources: int = 10) -> dict[str, Any]:
    if profile not in PROFILES:
        raise ValueError(f"Unknown pipeline profile: {profile}")
    ensure_queues(root)
    state = load_state(root)
    state["active_profile"] = profile
    state["status"] = "running"
    run_id = state.get("run_id") or "read_only_validation"
    gate_results: list[gates.GateResult] = []
    try:
        gate_results = _run_hard_gates_read_only(root)
        state["status"] = "completed"
        state["current_step"] = "read_only_validation"
        state["last_successful_step"] = "read_only_validation"
        state["gates"] = {result.name: "passed" for result in gate_results}
        state["gates"]["stage_readiness"] = "passed"
        state["counters"].update(_clean_counters(root))
        if profile == "targeted_followup":
            handoff_counts = create_targeted_followup_handoff_tasks(root, max_sources=max_sources)
            state["counters"]["records_manual_review"] = handoff_counts.get("source_records_seen", 0)
        return {"ok": True, "state": state, "gate_results": gate_results, "errors": []}
    except PipelineGateError as exc:
        state = start_run(root, profile)
        run_id = state["run_id"]
        clear_error_queue(root)
        mark_gate(root, state, exc.gate_name, "failed")
        error = append_error(
            root,
            run_id,
            exc.gate_name,
            str(exc),
            details=exc.errors,
            related_files=_gate_input_files(gate_results, exc.gate_name),
        )
        mark_failed(root, state, exc.gate_name, str(exc), ERROR_QUEUE_REL)
        state = load_state(root)
        failure_results = exc.gate_results or gate_results
        write_preflight_report(root, profile, state, failure_results, validation_ok=False, errors=exc.errors)
        write_event(
            root,
            run_id,
            exc.gate_name,
            "gate_fail",
            str(exc),
            output_files=[ERROR_QUEUE_REL, "reports/pipeline_preflight_report.md"],
            counts={"error_queue_written": 1, "error_id": error["error_id"]},
        )
        return {"ok": False, "state": state, "gate_results": failure_results, "errors": exc.errors}
    except Exception as exc:
        state = start_run(root, profile)
        run_id = state["run_id"]
        clear_error_queue(root)
        error = append_error(root, run_id, "orchestrator", str(exc), details=[type(exc).__name__])
        mark_failed(root, state, "orchestrator", str(exc), ERROR_QUEUE_REL)
        state = load_state(root)
        write_preflight_report(root, profile, state, gate_results, validation_ok=False, errors=[str(exc)])
        write_event(
            root,
            run_id,
            "orchestrator",
            "failure",
            str(exc),
            output_files=[ERROR_QUEUE_REL, "reports/pipeline_preflight_report.md"],
            counts={"error_queue_written": 1, "error_id": error["error_id"]},
        )
        return {"ok": False, "state": state, "gate_results": gate_results, "errors": [str(exc)]}


def pipeline_status(root: Path) -> dict[str, Any]:
    ensure_queues(root)
    state = load_state(root)
    counts = {}
    try:
        counts.update(clean_database_counts(root))
    except Exception as exc:
        counts["clean_database_count_error"] = str(exc)
    try:
        counts.update(queue_counts(root))
    except Exception as exc:
        counts["queue_count_error"] = str(exc)
    return {"state": state, "counts": counts}


def _run_hard_gates(root: Path, state: dict[str, Any], run_id: str) -> list[gates.GateResult]:
    gate_functions = [
        ("preflight", gates.preflight_gate),
        ("jsonl_integrity", gates.jsonl_integrity_gate),
        ("clean_database_integrity", gates.clean_database_integrity_gate),
        ("natural_environment_boundary", gates.natural_environment_boundary_gate),
        ("report_consistency", gates.report_consistency_gate),
        ("stage_readiness", gates.stage_readiness_gate),
    ]
    results: list[gates.GateResult] = []
    for gate_name, gate_function in gate_functions:
        mark_step(root, state, gate_name, "running")
        write_event(root, run_id, gate_name, "start", f"Running gate: {gate_name}")
        result = gate_function(root)
        results.append(result)
        if result.passed:
            mark_gate(root, state, result.name, "passed")
            write_event(
                root,
                run_id,
                result.name,
                "gate_pass",
                f"Gate passed: {result.name}",
                input_files=result.input_files,
                counts=result.counts,
            )
        else:
            raise PipelineGateError(result.name, result.errors, gate_results=results)
    return results


def _run_hard_gates_read_only(root: Path) -> list[gates.GateResult]:
    gate_functions = [
        gates.preflight_gate,
        gates.jsonl_integrity_gate,
        gates.clean_database_integrity_gate,
        gates.natural_environment_boundary_gate,
        gates.report_consistency_gate,
        gates.stage_readiness_gate,
    ]
    results: list[gates.GateResult] = []
    for gate_function in gate_functions:
        result = gate_function(root)
        results.append(result)
        if not result.passed:
            raise PipelineGateError(result.name, result.errors, gate_results=results)
    return results


def _clean_counters(root: Path) -> dict[str, int]:
    records = read_jsonl_strict(root / "data" / "clean" / "pfas_natural_transformation_records_v1.jsonl")
    sources = read_jsonl_strict(root / "data" / "clean" / "pfas_natural_transformation_sources_v1.jsonl")
    rejected = read_jsonl_strict(root / "data" / "clean" / "pfas_natural_transformation_rejected_v1.jsonl")
    manual = read_jsonl_strict(root / "data" / "clean" / "pfas_natural_transformation_manual_review_v1.jsonl")
    auxiliary = read_jsonl_strict(root / "data" / "clean" / "pfas_auxiliary_engineered_biological_v1.jsonl")
    return {
        "sources_discovered": len(sources),
        "sources_screened": len(sources),
        "sources_downloaded": len(sources),
        "sources_parsed": len(sources),
        "records_validated": len(records),
        "records_manual_review": len(manual),
        "records_rejected": len(rejected),
        "records_auxiliary": len(auxiliary),
    }


def _sync_state_counters(root: Path, state: dict[str, Any]) -> None:
    records = read_jsonl_strict(root / "data" / "clean" / "pfas_natural_transformation_records_v1.jsonl")
    sources = read_jsonl_strict(root / "data" / "clean" / "pfas_natural_transformation_sources_v1.jsonl")
    rejected = read_jsonl_strict(root / "data" / "clean" / "pfas_natural_transformation_rejected_v1.jsonl")
    manual = read_jsonl_strict(root / "data" / "clean" / "pfas_natural_transformation_manual_review_v1.jsonl")
    auxiliary = read_jsonl_strict(root / "data" / "clean" / "pfas_auxiliary_engineered_biological_v1.jsonl")
    update_counters(
        root,
        state,
        {
            "sources_discovered": len(sources),
            "sources_screened": len(sources),
            "sources_downloaded": len(sources),
            "sources_parsed": len(sources),
            "records_validated": len(records),
            "records_manual_review": len(manual),
            "records_rejected": len(rejected),
            "records_auxiliary": len(auxiliary),
        },
    )


def _write_diagnosis(root: Path) -> None:
    try:
        counts = clean_database_counts(root)
        clean_jsonl_ok = True
        notes = [
            f"clean_jsonl_record_count = {counts['record_count']}",
            f"clean_csv_data_rows = {counts['csv_data_rows']}",
            "Current clean JSONL passed strict parser during Stage 2.2b preflight.",
        ]
    except Exception as exc:
        counts = {}
        clean_jsonl_ok = False
        notes = [f"Current clean JSONL did not pass strict validation: {exc}"]
    write_diagnosis_report(root, clean_jsonl_ok=clean_jsonl_ok, clean_counts=counts, notes=notes)


def _safe_counts(root: Path) -> dict[str, Any]:
    try:
        return clean_database_counts(root)
    except Exception:
        return {}


def _gate_input_files(results: list[gates.GateResult], gate_name: str) -> list[str]:
    for result in results:
        if result.name == gate_name:
            return result.input_files
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ecfinder.pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--profile", required=True, choices=sorted(PROFILES))
    run.add_argument("--max-sources", type=int, default=10)
    sub.add_parser("status")
    args = parser.parse_args(argv)
    root = repo_root_from_cwd()
    if args.command == "run":
        result = run_pipeline(root, profile=args.profile, max_sources=args.max_sources)
        print(json.dumps(_printable_result(result), ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if result["ok"] else 1
    if args.command == "status":
        print(json.dumps(pipeline_status(root), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    return 1


def _printable_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": result["ok"],
        "status": (result.get("state") or {}).get("status"),
        "run_id": (result.get("state") or {}).get("run_id"),
        "errors": result.get("errors") or [],
        "gates": {
            gate.name: {
                "passed": gate.passed,
                "counts": gate.counts,
                "errors": gate.errors,
            }
            for gate in result.get("gate_results", [])
        },
    }


if __name__ == "__main__":
    raise SystemExit(main())
