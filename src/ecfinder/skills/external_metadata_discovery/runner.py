"""Runner for the ``external_metadata_discovery_v1`` skill.

This module is the public executable boundary used by external harnesses. It
keeps provider calls inside ECfinder and exchanges only durable JSON files with
the caller.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROVIDER_MODULES = {
    "crossref": "ecfinder.search.crossref_adapter",
    "openalex": "ecfinder.search.openalex_adapter",
    "semantic_scholar": "ecfinder.search.semantic_scholar_adapter",
    "pubmed": "ecfinder.search.pubmed_adapter",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m ecfinder.skills.external_metadata_discovery.runner"
    )
    parser.add_argument("--input", required=True, help="Skill request JSON path.")
    parser.add_argument("--output", required=True, help="Skill result JSON path.")
    args = parser.parse_args(argv)
    request_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    request = _read_json(request_path)
    result = run_skill(request, output_path)
    _write_json(output_path, result)
    return 0


def run_skill(request: dict[str, Any], output_path: Path) -> dict[str, Any]:
    if request.get("skill_id") not in {"", None, "external_metadata_discovery_v1"}:
        raise ValueError("skill_id must be external_metadata_discovery_v1")
    run_id = str(request.get("run_id") or "")
    query_id = str(request.get("query_id") or "")
    iteration = int(request.get("iteration") or 1)
    output_root = Path(str(request["output_root"])).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    page_root = output_root / "provider_pages"
    page_root.mkdir(parents=True, exist_ok=True)
    queries = _load_queries_ref(Path(str(request["queries_ref"])))
    query_by_provider = {
        str(row.get("provider") or row.get("source_name")): row for row in queries
    }
    providers = [str(provider) for provider in request.get("providers", [])]
    max_candidates = int(request.get("max_candidates") or request.get("max_results_per_query") or 1)
    page_size = int(request.get("page_size") or max_candidates)
    per_provider_limit = min(max_candidates, page_size * int(request.get("max_scan_depth_per_provider") or 1))
    date_from = str(request.get("date_from") or "")
    date_to = str(request.get("date_to") or "")
    document_types = [str(value) for value in request.get("document_types", [])]
    provider_page_refs: dict[str, list[str]] = {}
    provider_states: dict[str, dict[str, Any]] = {}
    source_status: dict[str, str] = {}
    next_cursor_by_provider: dict[str, str] = {}
    providers_available: list[str] = []
    candidates: list[dict[str, Any]] = []

    for provider in providers:
        state: dict[str, Any] = {
            "provider": provider,
            "date_from": date_from,
            "date_to": date_to,
            "document_types": document_types,
            "requested_limit": per_provider_limit,
        }
        row = query_by_provider.get(provider, {})
        executable_query = _provider_query(provider, row, date_from, date_to, document_types)
        state["executable_request"] = _executable_request(provider, executable_query, per_provider_limit, date_from, date_to, document_types)
        provider_page_refs[provider] = []
        if provider not in PROVIDER_MODULES:
            state["error"] = "provider not supported by external_metadata_discovery_v1"
            state["status"] = "not-run"
            source_status[provider] = "not-run"
            provider_states[provider] = state
            continue
        try:
            adapter = importlib.import_module(PROVIDER_MODULES[provider])
            result = adapter.search(executable_query, max_results=per_provider_limit)
        except Exception as exc:  # pragma: no cover - defensive executable boundary
            state["error"] = str(exc)
            state["status"] = "failed"
            source_status[provider] = "failed"
            provider_states[provider] = state
            continue
        records = list(getattr(result, "records", []) or [])
        available = bool(getattr(result, "available", False))
        error = str(getattr(result, "error", "") or "")
        status = _provider_status(available, records, error)
        state["status"] = status
        state["error"] = error
        state["record_count"] = len(records)
        state["query_text"] = executable_query
        source_status[provider] = status
        if available:
            providers_available.append(provider)
        if records:
            page_path = page_root / f"{provider}_page_0001.jsonl"
            normalized = [
                _normalize_record(
                    raw=record,
                    provider=provider,
                    rank=rank,
                    run_id=run_id,
                    query_id=query_id,
                    iteration=iteration,
                    executable_query=executable_query,
                )
                for rank, record in enumerate(records, start=1)
            ]
            _write_jsonl(page_path, normalized)
            provider_page_refs[provider].append(str(page_path))
            candidates.extend(normalized)
            next_cursor_by_provider[provider] = str(len(normalized))
        else:
            next_cursor_by_provider[provider] = ""
        provider_states[provider] = state

    candidates_ref = output_root / "candidates.jsonl"
    provider_states_ref = output_root / "provider_states.json"
    source_status_ref = output_root / "source_status.json"
    memory_usage_ref = output_root / "memory_usage.json"
    _write_jsonl(candidates_ref, candidates)
    _write_json(provider_states_ref, provider_states)
    _write_json(source_status_ref, source_status)
    _write_json(memory_usage_ref, {"runner_pid": os.getpid(), "completed_at": _now()})
    return {
        "candidates_ref": str(candidates_ref),
        "deduped_ref": "",
        "new_sources_ref": "",
        "provider_page_refs": provider_page_refs,
        "provider_states_ref": str(provider_states_ref),
        "next_cursor_by_provider": next_cursor_by_provider,
        "source_status_ref": str(source_status_ref),
        "memory_usage_ref": str(memory_usage_ref),
        "providers_attempted": providers,
        "providers_available": providers_available,
        "total_external_candidates": len(candidates),
        "execution_status": _execution_status(source_status, len(candidates)),
    }


def _provider_query(
    provider: str,
    row: dict[str, Any],
    date_from: str,
    date_to: str,
    document_types: list[str],
) -> str:
    base = str(row.get("query_text") or row.get("compiled_query") or "").strip()
    if provider == "pubmed":
        additions = []
        if date_from or date_to:
            additions.append(f'("{date_from or "1900-01-01"}"[Date - Publication] : "{date_to or "3000-12-31"}"[Date - Publication])')
        if document_types:
            additions.append("(" + " OR ".join(f'"{item}"[Publication Type]' for item in document_types) + ")")
        return " AND ".join([part for part in [base, *additions] if part])
    return base


def _executable_request(
    provider: str,
    query: str,
    limit: int,
    date_from: str,
    date_to: str,
    document_types: list[str],
) -> dict[str, Any]:
    return {
        "provider": provider,
        "query": query,
        "limit": limit,
        "date_from": date_from,
        "date_to": date_to,
        "document_types": document_types,
        "runner": "ecfinder.skills.external_metadata_discovery.runner",
    }


def _provider_status(available: bool, records: list[dict[str, Any]], error: str) -> str:
    if error:
        lowered = error.lower()
        if "429" in lowered or "rate" in lowered:
            return "rate-limited"
        return "failed" if not records else "partial"
    if not available:
        return "failed"
    return "success" if records else "no-results"


def _execution_status(source_status: dict[str, str], total: int) -> str:
    statuses = set(source_status.values())
    if statuses and statuses <= {"failed", "rate-limited", "not-run"}:
        return "failed"
    if total == 0:
        return "no_results"
    if statuses & {"failed", "rate-limited", "partial"}:
        return "partial"
    return "success"


def _normalize_record(
    *,
    raw: dict[str, Any],
    provider: str,
    rank: int,
    run_id: str,
    query_id: str,
    iteration: int,
    executable_query: str,
) -> dict[str, Any]:
    provider_record_id = str(raw.get("provider_record_id") or raw.get("doi") or raw.get("url") or f"{provider}:{rank}")
    return {
        **raw,
        "source_provider": provider,
        "source_record_id": provider_record_id,
        "provider_record_id": provider_record_id,
        "rank": rank,
        "retrieval_page": 1,
        "query_text": executable_query,
        "run_id": run_id,
        "query_id": query_id,
        "iteration": iteration,
        "retrieved_at": _now(),
        "document_type": raw.get("document_type"),
        "language": raw.get("language"),
    }


def _load_queries_ref(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    value = _read_json(path)
    if isinstance(value, list):
        return [dict(row) for row in value if isinstance(row, dict)]
    return []


def _read_json(path: Path) -> dict[str, Any] | list[Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    tmp.replace(path)


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
