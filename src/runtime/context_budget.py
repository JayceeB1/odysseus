"""Context budget contract used by runtime turn preparation."""

from __future__ import annotations

from dataclasses import dataclass

from src.context_budget import DEFAULT_BUDGET, DEFAULT_HARD_MAX


@dataclass(frozen=True)
class ContextBudget:
    """Declarative budget for a turn's input context.

    The current agent loop still performs trimming in ``src.agent_loop`` so
    existing plan/guide directives keep their exact ordering. This class is the
    stable handoff object for future context-engine-owned trimming.
    """

    soft_limit: int = DEFAULT_BUDGET
    context_length: int = 0
    explicit: bool = False
    hard_max: int = DEFAULT_HARD_MAX
    reserve: int = 512
    enabled: bool = True

    def effective_input_limit(self) -> int:
        """Return the soft input limit after context-window scaling."""
        configured = int(self.soft_limit or 0)
        context_length = int(self.context_length or 0)
        if self.explicit and configured > 0:
            return min(configured, context_length) if context_length > 0 else configured
        if context_length > 0:
            return max(1, min(int(context_length * 0.85), self.hard_max))
        return configured if configured > 0 else DEFAULT_BUDGET
