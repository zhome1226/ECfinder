"""Codex-agent task preparation layer.

These modules intentionally do not call an external LLM API. In Codex mode they
prepare bounded, auditable task packets for the current interactive Codex model
to complete and write back as JSONL.
"""

