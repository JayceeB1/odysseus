"""Small execution-budget primitives for tool runtime facades."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


class ToolBudgetExceeded(RuntimeError):
    """Raised when a tool execution would exceed an explicit budget."""


@dataclass
class ToolExecutionBudget:
    """Opt-in limits for a tool execution facade.

    All fields default to ``None`` so existing execution paths keep their
    current behavior unless a caller explicitly passes a budget.
    """

    max_tool_calls: Optional[int] = None
    timeout_seconds: Optional[float] = None
    max_inline_output_chars: Optional[int] = None
    redact_outputs: bool = False
    catch_provider_errors: bool = False
    emit_events: bool = False
    run_id: Optional[str] = None
    surface: Optional[str] = None
    toolset: Optional[str] = None
    used_tool_calls: int = field(default=0, init=False, repr=False)


class ToolBudgetTracker:
    """Tracks per-facade tool-call consumption."""

    def __init__(self, budget: Optional[ToolExecutionBudget] = None):
        self.budget = budget or ToolExecutionBudget()

    def reserve(self, tool_name: str) -> None:
        limit = self.budget.max_tool_calls
        if limit is not None and self.budget.used_tool_calls >= limit:
            raise ToolBudgetExceeded(
                f"Tool budget exhausted before running '{tool_name}' "
                f"(limit={limit}, used={self.budget.used_tool_calls})."
            )
        self.budget.used_tool_calls += 1
