"""Data contracts for subagent delegation."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4


@dataclass(frozen=True)
class SubagentBudget:
    """Delegation budget inherited from a parent turn."""

    max_tokens: int
    max_tool_calls: int
    timeout_seconds: float | None = None

    def derive(self, *, max_tokens: int, max_tool_calls: int) -> "SubagentBudget":
        return SubagentBudget(
            max_tokens=max(0, min(int(max_tokens), self.max_tokens)),
            max_tool_calls=max(0, min(int(max_tool_calls), self.max_tool_calls)),
            timeout_seconds=self.timeout_seconds,
        )


@dataclass(frozen=True)
class SubagentLineage:
    parent_run_id: str
    child_run_id: str = field(default_factory=lambda: uuid4().hex)
    depth: int = 0

    def child(self) -> "SubagentLineage":
        return SubagentLineage(
            parent_run_id=self.child_run_id,
            depth=self.depth + 1,
        )

    def to_trace(self) -> dict:
        return {
            "parent_run_id": self.parent_run_id,
            "child_run_id": self.child_run_id,
            "depth": self.depth,
        }


@dataclass(frozen=True)
class SubagentRequest:
    task: str
    parent_run_id: str
    requested_tools: frozenset[str] = frozenset()
    max_tokens: int = 5000
    max_tool_calls: int = 5
    lineage: SubagentLineage | None = None


@dataclass(frozen=True)
class SubagentResult:
    status: str
    summary: str
    lineage: SubagentLineage
    budget: SubagentBudget
    artifacts: tuple[dict, ...] = ()

    def to_artifact(self) -> dict:
        return {
            "type": "subagent_result",
            "status": self.status,
            "summary": self.summary,
            "lineage": self.lineage.to_trace(),
            "budget": {
                "max_tokens": self.budget.max_tokens,
                "max_tool_calls": self.budget.max_tool_calls,
                "timeout_seconds": self.budget.timeout_seconds,
            },
            "artifacts": list(self.artifacts),
        }
