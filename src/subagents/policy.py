"""Fail-closed policy for subagent delegation."""

from __future__ import annotations

from dataclasses import dataclass

from src.subagents.models import SubagentBudget, SubagentLineage, SubagentRequest


class SubagentPolicyError(PermissionError):
    """Raised when a subagent request would widen runtime authority."""


@dataclass(frozen=True)
class SubagentPolicy:
    enabled: bool = False
    max_depth: int = 1
    parent_allowed_tools: frozenset[str] = frozenset()
    parent_budget: SubagentBudget = SubagentBudget(max_tokens=0, max_tool_calls=0)

    def authorize(self, request: SubagentRequest) -> tuple[SubagentLineage, SubagentBudget]:
        if not self.enabled:
            raise SubagentPolicyError("subagents-disabled")

        lineage = request.lineage or SubagentLineage(parent_run_id=request.parent_run_id)
        if lineage.depth >= self.max_depth:
            raise SubagentPolicyError("max-depth-exceeded")

        requested_tools = frozenset(request.requested_tools)
        extra_tools = requested_tools - self.parent_allowed_tools
        if extra_tools:
            raise SubagentPolicyError("toolset-escalation:" + ",".join(sorted(extra_tools)))

        child_budget = self.parent_budget.derive(
            max_tokens=request.max_tokens,
            max_tool_calls=request.max_tool_calls,
        )
        if child_budget.max_tokens <= 0 or child_budget.max_tool_calls <= 0:
            raise SubagentPolicyError("budget-exhausted")
        return lineage.child(), child_budget
