"""Small opt-in provider fallback runner."""

from __future__ import annotations

from dataclasses import dataclass
import inspect
import time
from typing import Any, Callable, List, MutableSequence, Optional

from .error_classifier import (
    ProviderCallFailed,
    ProviderErrorInfo,
    classify_provider_error,
    redact_provider_error,
)
from .routing_policy import ProviderRecoveryAction, ProviderRoutingPolicy


ProviderCall = Callable[..., Any]


@dataclass(frozen=True)
class ProviderCandidate:
    name: str
    call: ProviderCall


@dataclass(frozen=True)
class ProviderFallbackResult:
    provider: str
    value: Any
    fallback_used: bool = False


async def run_provider_fallback(
    candidates: List[ProviderCandidate],
    *args,
    policy: Optional[ProviderRoutingPolicy] = None,
    run_id: str = "",
    surface: str = "api",
    toolset: str = "default",
    events: Optional[MutableSequence[dict]] = None,
    **kwargs,
) -> ProviderFallbackResult:
    """Run candidates in order under an explicit provider recovery policy."""

    if not candidates:
        info = ProviderErrorInfo(
            category=classify_provider_error(RuntimeError("No provider candidates configured")).category,
            message="No provider candidates configured",
        )
        raise ProviderCallFailed(info)

    active_policy = policy or ProviderRoutingPolicy(enabled=False)
    fallback_index = 0
    last_info: Optional[ProviderErrorInfo] = None

    for candidate_index, candidate in enumerate(candidates):
        attempt = 1
        while True:
            started = time.perf_counter()
            try:
                value = await _maybe_await(candidate.call(*args, **kwargs))
                _emit_event(
                    events,
                    run_id=run_id,
                    surface=surface,
                    toolset=toolset,
                    provider=candidate.name,
                    decision="success",
                    duration_ms=_duration_ms(started),
                )
                return ProviderFallbackResult(
                    provider=candidate.name,
                    value=value,
                    fallback_used=candidate_index > 0,
                )
            except Exception as exc:
                info = classify_provider_error(exc, provider=candidate.name)
                last_info = info
                has_next = candidate_index + 1 < len(candidates)
                decision = active_policy.decide(
                    info,
                    surface=surface,
                    fallback_index=fallback_index,
                    has_next_provider=has_next,
                    attempt=attempt,
                )
                _emit_event(
                    events,
                    run_id=run_id,
                    surface=surface,
                    toolset=toolset,
                    provider=candidate.name,
                    decision=decision.action.value,
                    category=info.category.value,
                    error=info.message,
                    duration_ms=_duration_ms(started),
                )

                if not active_policy.enabled:
                    raise
                if decision.action == ProviderRecoveryAction.RETRY:
                    attempt += 1
                    continue
                if decision.action == ProviderRecoveryAction.FALLBACK:
                    fallback_index += 1
                    break
                raise ProviderCallFailed(info)

    raise ProviderCallFailed(last_info or classify_provider_error(RuntimeError("All provider candidates failed")))


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _emit_event(events: Optional[MutableSequence[dict]], **event: Any) -> None:
    if events is None:
        return
    safe = dict(event)
    if "error" in safe:
        safe["error"] = redact_provider_error(safe["error"])
    events.append(safe)


def _duration_ms(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1000))
