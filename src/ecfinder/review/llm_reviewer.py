"""LLM review response parsing."""

from __future__ import annotations

import json


def parse_review_response(response_text: str) -> dict:
    payload = json.loads(response_text)
    if not isinstance(payload, dict):
        raise ValueError("review response must be a JSON object")
    if payload.get("decision") not in {"accepted", "rejected", "needs_reextract"}:
        raise ValueError("invalid review decision")
    return payload
