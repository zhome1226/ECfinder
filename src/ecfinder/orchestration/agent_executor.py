"""Agent executor interfaces for closed-loop orchestration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class AgentExecutor(ABC):
    """Base class for a runnable closed-loop agent step."""

    name = "AgentExecutor"

    def __init__(self, root: Path) -> None:
        self.root = root

    @abstractmethod
    def can_run(self, task: dict[str, Any]) -> bool:
        """Return True when this executor can consume the task."""

    @abstractmethod
    def run(self, task: dict[str, Any]) -> dict[str, Any]:
        """Execute the task and return a result payload."""

    @abstractmethod
    def write_outputs(self, result: dict[str, Any]) -> None:
        """Persist result artifacts and state updates."""


class MetadataAgentExecutor(AgentExecutor):
    name = "MetadataAgent"

    def can_run(self, task: dict[str, Any]) -> bool:
        return task.get("task_type") == "metadata"

    def run(self, task: dict[str, Any]) -> dict[str, Any]:
        return {"task": task, "status": "skipped", "reason": "metadata stage already handled by existing batch artifacts"}

    def write_outputs(self, result: dict[str, Any]) -> None:
        return None


class ScreeningAgentExecutor(MetadataAgentExecutor):
    name = "ScreeningAgent"

    def can_run(self, task: dict[str, Any]) -> bool:
        return task.get("task_type") == "screening"


class FulltextAgentExecutor(MetadataAgentExecutor):
    name = "FulltextAgent"

    def can_run(self, task: dict[str, Any]) -> bool:
        return task.get("task_type") == "fulltext"


class ParseChunkAgentExecutor(MetadataAgentExecutor):
    name = "ParseChunkAgent"

    def can_run(self, task: dict[str, Any]) -> bool:
        return task.get("task_type") in {"parse", "chunk"}
