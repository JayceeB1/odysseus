"""Synchronous subagent delegation facade."""

from __future__ import annotations

import inspect
import re
from typing import Awaitable, Callable

from src.subagents.models import SubagentRequest, SubagentResult
from src.subagents.policy import SubagentPolicy, SubagentPolicyError


DelegateFn = Callable[[SubagentRequest], str | Awaitable[str]]
_SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[^'\"\s,;]+"
)


class SubagentRuntime:
    """Runs an authorized delegation through a caller-supplied delegate."""

    def __init__(self, policy: SubagentPolicy, delegate: DelegateFn | None = None) -> None:
        self.policy = policy
        self.delegate = delegate

    async def run(self, request: SubagentRequest) -> SubagentResult:
        lineage, budget = self.policy.authorize(request)
        if self.delegate is None:
            raise SubagentPolicyError("delegate-not-configured")

        value = self.delegate(request)
        if inspect.isawaitable(value):
            value = await value
        summary = _redact(str(value or ""))
        return SubagentResult(
            status="completed",
            summary=summary,
            lineage=lineage,
            budget=budget,
            artifacts=({"kind": "summary", "trusted": False},),
        )


def _redact(value: str) -> str:
    return _SECRET_RE.sub(lambda match: match.group(1) + "=<redacted>", value)
