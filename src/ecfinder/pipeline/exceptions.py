"""Pipeline exception types."""

from __future__ import annotations


class PipelineError(Exception):
    """Base class for pipeline failures."""


class PipelineGateError(PipelineError):
    """Raised when a hard validation gate fails."""

    def __init__(self, gate_name: str, errors: list[str], gate_results: list | None = None):
        self.gate_name = gate_name
        self.errors = errors
        self.gate_results = gate_results or []
        message = f"{gate_name} failed: " + "; ".join(errors)
        super().__init__(message)
