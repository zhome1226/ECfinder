"""Fault tolerance policy helpers for orchestrated PFAS source batches."""

from __future__ import annotations

from typing import Any


RETRY_POLICIES = {
    "metadata": {"max_attempts": 2, "retry_policy": "immediate"},
    "screening": {"max_attempts": 2, "retry_policy": "immediate"},
    "fulltext": {"max_attempts": 1, "retry_policy": "manual_trigger"},
    "parse": {"max_attempts": 2, "retry_policy": "after_manifest_update"},
    "chunk": {"max_attempts": 2, "retry_policy": "after_cache_refresh"},
    "extract": {"max_attempts": 1, "retry_policy": "manual_trigger"},
    "review": {"max_attempts": 1, "retry_policy": "manual_trigger"},
}


def missing_fulltext_error(source_id: str, stage: str = "fulltext") -> dict[str, Any]:
    return {
        "source_id": source_id,
        "stage": stage,
        "agent": "DownloadAgent",
        "error_type": "missing_fulltext",
        "recoverable": True,
        "retryable": False,
        "retry_after_stage": "fulltext",
        "error_message_short": "lawful full text not available in cache or Zotero lookup",
        "error_artifact_ref": "",
        "next_action": "manual_handoff",
    }


def manual_required_error(source_id: str, stage: str, agent: str, message: str) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "stage": stage,
        "agent": agent,
        "error_type": "manual_required",
        "recoverable": True,
        "retryable": False,
        "retry_after_stage": stage,
        "error_message_short": message,
        "error_artifact_ref": "",
        "next_action": "manual_handoff",
    }


def retry_record(source_id: str, stage: str, agent: str, reason: str, attempt: int = 1) -> dict[str, Any]:
    policy = RETRY_POLICIES[stage]
    return {
        "source_id": source_id,
        "stage": stage,
        "agent": agent,
        "reason": reason,
        "attempt": attempt,
        "max_attempts": policy["max_attempts"],
        "retry_policy": policy["retry_policy"],
        "status": "pending",
    }
