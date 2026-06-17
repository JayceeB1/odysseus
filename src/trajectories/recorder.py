"""Opt-in in-memory trajectory recorder.

The recorder is disabled by default and never writes to the application
database. Callers must explicitly pass ``enabled=True`` and export the records
they want to keep.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from contextlib import AbstractContextManager
from datetime import datetime
from typing import Any, Callable, Mapping

from .models import AgentEvent, AgentRun, AgentStep, TrajectoryBundle, utc_now


SENSITIVE_KEYS = (
    "api" + "_key",
    "api" + "key",
    "author" + "ization",
    "cookie",
    "pass" + "word",
    "refresh_" + "tok" + "en",
    "sec" + "ret",
    "set-cookie",
    "tok" + "en",
)

_CREDENTIAL_PATTERNS = [
    re.compile(r"Bear" + r"er\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE),
    re.compile(r"\bs" + r"k-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{16,}\b"),
    re.compile(r"\bAI" + r"za[A-Za-z0-9_-]{20,}\b"),
]


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower().replace("-", "_")
    return any(marker in lowered for marker in SENSITIVE_KEYS)


def redact_sensitive(value: Any) -> Any:
    """Return a copy of ``value`` with common credentials removed."""

    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            key_s = str(key)
            out[key_s] = "[redacted]" if _is_sensitive_key(key_s) else redact_sensitive(item)
        return out
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, str):
        redacted = value
        for pattern in _CREDENTIAL_PATTERNS:
            redacted = pattern.sub("[redacted]", redacted)
        return redacted
    return value


def prompt_hash(prompt: str | None) -> str | None:
    if prompt is None:
        return None
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


class InMemoryTrajectoryStore:
    def __init__(self) -> None:
        self.bundle = TrajectoryBundle()

    def add_run(self, run: AgentRun) -> None:
        self.bundle.runs.append(run)

    def add_step(self, step: AgentStep) -> None:
        self.bundle.steps.append(step)

    def add_event(self, event: AgentEvent) -> None:
        self.bundle.events.append(event)

    def snapshot(self) -> TrajectoryBundle:
        return TrajectoryBundle(
            runs=list(self.bundle.runs),
            steps=list(self.bundle.steps),
            events=list(self.bundle.events),
        )


class _RunContext(AbstractContextManager[AgentRun | None]):
    def __init__(
        self,
        recorder: "TrajectoryRecorder",
        surface: str,
        prompt: str | None,
        metadata: Mapping[str, Any] | None,
    ) -> None:
        self.recorder = recorder
        self.surface = surface
        self.prompt = prompt
        self.metadata = metadata or {}
        self.run: AgentRun | None = None

    def __enter__(self) -> AgentRun | None:
        if not self.recorder.enabled:
            return None
        self.run = AgentRun(
            run_id=self.recorder._new_id("run"),
            surface=self.surface,
            prompt_hash=prompt_hash(self.prompt),
            metadata=redact_sensitive(self.metadata),
            started_at=self.recorder.clock(),
        )
        self.recorder.store.add_run(self.run)
        self.recorder.event(self.run.run_id, "run_started", {"surface": self.surface})
        return self.run

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self.run is None:
            return False
        self.run.ended_at = self.recorder.clock()
        self.run.status = "failed" if exc_type else "ok"
        if exc_type:
            self.recorder.event(
                self.run.run_id,
                "run_failed",
                {"error_type": getattr(exc_type, "__name__", "Exception"), "error": str(exc)},
            )
        self.recorder.event(self.run.run_id, "run_finished", {"status": self.run.status})
        return False


class TrajectoryRecorder:
    def __init__(
        self,
        *,
        enabled: bool = False,
        store: InMemoryTrajectoryStore | None = None,
        clock: Callable[[], datetime] = utc_now,
        id_factory: Callable[[str], str] | None = None,
    ) -> None:
        self.enabled = enabled
        self.store = store or InMemoryTrajectoryStore()
        self.clock = clock
        self.id_factory = id_factory

    def _new_id(self, kind: str) -> str:
        if self.id_factory is not None:
            return self.id_factory(kind)
        return f"{kind}_{uuid.uuid4().hex}"

    def run(
        self,
        *,
        surface: str,
        prompt: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> _RunContext:
        return _RunContext(self, surface, prompt, metadata)

    def step(
        self,
        run_id: str | None,
        *,
        index: int,
        kind: str,
        status: str = "ok",
        tool: str | None = None,
        input_ref: str | None = None,
        output_ref: str | None = None,
        duration_ms: int | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> AgentStep | None:
        if not self.enabled or not run_id:
            return None
        step = AgentStep(
            step_id=self._new_id("step"),
            run_id=run_id,
            index=index,
            kind=kind,
            status=status,
            tool=tool,
            input_ref=input_ref,
            output_ref=output_ref,
            duration_ms=duration_ms,
            metadata=redact_sensitive(metadata or {}),
        )
        self.store.add_step(step)
        return step

    def event(
        self,
        run_id: str | None,
        name: str,
        payload: Mapping[str, Any] | None = None,
        *,
        step_id: str | None = None,
    ) -> AgentEvent | None:
        if not self.enabled or not run_id:
            return None
        event = AgentEvent(
            event_id=self._new_id("event"),
            run_id=run_id,
            step_id=step_id,
            name=name,
            payload=redact_sensitive(payload or {}),
            created_at=self.clock(),
        )
        self.store.add_event(event)
        return event

    def snapshot(self) -> TrajectoryBundle:
        return self.store.snapshot()
