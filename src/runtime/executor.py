"""Opt-in tool executor facade with budgets, timeout and result references."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

from src.runtime.budgets import (
    ToolBudgetExceeded,
    ToolBudgetTracker,
    ToolExecutionBudget,
)
from src.runtime.result_store import InMemoryResultStore, redact_text
from src.runtime.run_events import RunEvent


ToolProvider = Callable[[], Awaitable[Tuple[str, Dict[str, Any]]]]


class ToolExecutorFacade:
    """Wrap a legacy tool provider without changing its default behavior."""

    _REFERENCE_FIELDS = ("output", "stdout", "stderr", "content", "response", "results")

    def __init__(
        self,
        *,
        budget: Optional[ToolExecutionBudget] = None,
        result_store: Optional[InMemoryResultStore] = None,
    ):
        self.tracker = ToolBudgetTracker(budget)
        self.budget = self.tracker.budget
        self.result_store = result_store or InMemoryResultStore()

    async def execute(self, *, tool_name: str, provider: ToolProvider) -> Tuple[str, Dict[str, Any]]:
        started = time.perf_counter()
        events = [self._event("tool_start", tool_name, decision="started")]
        try:
            self.tracker.reserve(tool_name)
            if self.budget.timeout_seconds is None:
                desc, result = await provider()
            else:
                desc, result = await asyncio.wait_for(
                    provider(),
                    timeout=self.budget.timeout_seconds,
                )
        except ToolBudgetExceeded as exc:
            events.append(self._event("tool_budget_exceeded", tool_name, str(exc), decision="budget_exhausted", started=started))
            return self._with_events(
                f"{tool_name}: BLOCKED",
                {"error": str(exc), "exit_code": 1, "budget_exceeded": True},
                events,
            )
        except asyncio.TimeoutError:
            detail = f"timed out after {self.budget.timeout_seconds}s"
            events.append(self._event("tool_timeout", tool_name, detail, decision="timeout", started=started))
            return self._with_events(
                f"{tool_name}: TIMEOUT",
                {"error": f"Tool '{tool_name}' {detail}.", "exit_code": 124},
                events,
            )
        except Exception as exc:
            if not self.budget.catch_provider_errors:
                raise
            detail = f"{type(exc).__name__}: {redact_text(exc)}"
            events.append(self._event("tool_error", tool_name, detail, decision="provider_error", started=started))
            return self._with_events(
                f"{tool_name}: ERROR",
                {"error": detail, "exit_code": 1},
                events,
            )

        safe_result = self._apply_redaction_and_references(tool_name, result)
        events.append(self._event("tool_finish", tool_name, decision="allowed", started=started))
        return self._with_events(desc, safe_result, events)

    def _event(
        self,
        event_type: str,
        tool_name: str,
        detail: Optional[str] = None,
        *,
        decision: Optional[str] = None,
        started: Optional[float] = None,
    ) -> RunEvent:
        duration_ms = None
        if started is not None:
            duration_ms = round((time.perf_counter() - started) * 1000, 3)
        return RunEvent.now(
            event_type,
            tool_name,
            detail,
            run_id=self.budget.run_id,
            surface=self.budget.surface,
            toolset=self.budget.toolset,
            decision=decision,
            duration_ms=duration_ms,
        )

    def _apply_redaction_and_references(self, tool_name: str, result: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(result, dict):
            output = redact_text(result) if self.budget.redact_outputs else str(result)
            return {"output": output, "exit_code": 0}

        output_limit = self.budget.max_inline_output_chars
        redact_outputs = self.budget.redact_outputs or output_limit is not None
        safe = dict(result)
        refs: Dict[str, Dict[str, Any]] = {}

        for field in self._REFERENCE_FIELDS:
            if field in safe:
                safe[field] = self._safe_value(
                    tool_name,
                    field,
                    safe[field],
                    output_limit=output_limit,
                    redact_outputs=redact_outputs,
                    refs=refs,
                )

        if redact_outputs or output_limit is not None:
            for field, value in list(safe.items()):
                if field in self._REFERENCE_FIELDS or field == "result_refs":
                    continue
                safe[field] = self._safe_value(
                    tool_name,
                    field,
                    value,
                    output_limit=output_limit,
                    redact_outputs=redact_outputs,
                    refs=refs,
                )

        if refs:
            safe["result_refs"] = refs
        return safe

    def _safe_value(
        self,
        tool_name: str,
        path: str,
        value: Any,
        *,
        output_limit: Optional[int],
        redact_outputs: bool,
        refs: Dict[str, Dict[str, Any]],
    ) -> Any:
        if isinstance(value, dict):
            return {
                key: self._safe_value(
                    tool_name,
                    f"{path}.{key}",
                    nested,
                    output_limit=output_limit,
                    redact_outputs=redact_outputs,
                    refs=refs,
                )
                for key, nested in value.items()
            }
        if isinstance(value, list):
            return [
                self._safe_value(
                    tool_name,
                    f"{path}[{index}]",
                    nested,
                    output_limit=output_limit,
                    redact_outputs=redact_outputs,
                    refs=refs,
                )
                for index, nested in enumerate(value)
            ]
        if not isinstance(value, str):
            return value

        safe_text = redact_text(value) if redact_outputs else value
        if output_limit is not None and len(safe_text) > output_limit:
            stored = self.result_store.put(tool_name=tool_name, field=path, content=safe_text)
            refs[path] = {"ref": stored.ref, "size": stored.size}
            return f"[stored as {stored.ref}; {stored.size} chars]"
        return safe_text

    def _with_events(
        self,
        desc: str,
        result: Dict[str, Any],
        events: list[RunEvent],
    ) -> Tuple[str, Dict[str, Any]]:
        if self.budget.emit_events:
            result = dict(result)
            result["run_events"] = [event.to_dict() for event in events]
        return desc, result
