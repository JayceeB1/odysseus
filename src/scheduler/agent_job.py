"""Agentic scheduled job contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from src.runtime.turn_context import TurnContext


_SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[^'\"\s,;]+"
)


@dataclass(frozen=True)
class AgentJobSpec:
    """Stable runtime spec for one scheduled agent execution."""

    task_id: str
    run_id: str
    name: str
    prompt: str
    owner: str | None = None
    session_id: str | None = None
    surface: str = "cron"
    toolset_profile: str | tuple[str, ...] | None = None
    delivery_target: str | None = None

    @classmethod
    def from_task(cls, task: Any, *, run_id: str, surface: str = "cron") -> "AgentJobSpec":
        return cls(
            task_id=str(getattr(task, "id", "") or ""),
            run_id=str(run_id or ""),
            name=str(getattr(task, "name", "") or ""),
            prompt=str(getattr(task, "prompt", "") or ""),
            owner=getattr(task, "owner", None),
            session_id=getattr(task, "session_id", None),
            surface=(surface or "cron").strip().lower(),
            toolset_profile=_toolset_profile_from_task(task),
            delivery_target=getattr(task, "output_target", None),
        )

    def to_turn_context(self) -> TurnContext:
        toolset = None
        if self.toolset_profile:
            if isinstance(self.toolset_profile, str):
                toolset = frozenset({self.toolset_profile})
            else:
                toolset = frozenset(self.toolset_profile)
        return TurnContext(
            messages=({"role": "user", "content": self.prompt},),
            user=self.owner,
            session_id=self.session_id,
            surface=self.surface,
            toolset=toolset,
            metadata=self.to_trace(),
        )

    def to_trace(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "run_id": self.run_id,
            "name": _redact(self.name),
            "surface": self.surface,
            "toolset_profile": _traceable_profile(self.toolset_profile),
            "delivery_target": _redact(self.delivery_target or ""),
            "prompt_preview": _redact(self.prompt)[:240],
        }


def build_cron_run_trace(
    job: AgentJobSpec,
    *,
    delivery: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    trace = {
        "kind": "cron_agent_job",
        "job": job.to_trace(),
    }
    if delivery:
        trace["delivery"] = dict(delivery)
    return trace


def _toolset_profile_from_task(task: Any) -> str | tuple[str, ...] | None:
    for attr in ("toolset_profile", "toolset_profiles", "toolset", "tool_profile"):
        value = getattr(task, attr, None)
        if value:
            return value
    return None


def _traceable_profile(value: str | tuple[str, ...] | None) -> str | list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return [str(item) for item in value]


def _redact(value: str) -> str:
    return _SECRET_RE.sub(lambda match: match.group(1) + "=<redacted>", str(value))
