"""Data contracts for opt-in agent trajectories.

These models are intentionally storage-agnostic. PR15 does not alter the
runtime database schema or record production traffic by default.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(slots=True)
class AgentRun:
    run_id: str
    surface: str
    status: str = "running"
    started_at: datetime = field(default_factory=utc_now)
    ended_at: datetime | None = None
    prompt_hash: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        return {
            "record_type": "run",
            "run_id": self.run_id,
            "surface": self.surface,
            "status": self.status,
            "started_at": _iso(self.started_at),
            "ended_at": _iso(self.ended_at) if self.ended_at else None,
            "prompt_hash": self.prompt_hash,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class AgentStep:
    step_id: str
    run_id: str
    index: int
    kind: str
    status: str = "ok"
    tool: str | None = None
    input_ref: str | None = None
    output_ref: str | None = None
    duration_ms: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        return {
            "record_type": "step",
            "step_id": self.step_id,
            "run_id": self.run_id,
            "index": self.index,
            "kind": self.kind,
            "status": self.status,
            "tool": self.tool,
            "input_ref": self.input_ref,
            "output_ref": self.output_ref,
            "duration_ms": self.duration_ms,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class AgentEvent:
    event_id: str
    run_id: str
    name: str
    created_at: datetime = field(default_factory=utc_now)
    step_id: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        return {
            "record_type": "event",
            "event_id": self.event_id,
            "run_id": self.run_id,
            "step_id": self.step_id,
            "name": self.name,
            "created_at": _iso(self.created_at),
            "payload": dict(self.payload),
        }


@dataclass(slots=True)
class TrajectoryBundle:
    runs: list[AgentRun] = field(default_factory=list)
    steps: list[AgentStep] = field(default_factory=list)
    events: list[AgentEvent] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.runs and not self.steps and not self.events
