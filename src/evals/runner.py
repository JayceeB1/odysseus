"""Minimal deterministic batch-eval runner.

The runner accepts an injected callable instead of dialing an LLM provider.
This keeps PR15 network-free and suitable for regression tests.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping, Sequence

from src.trajectories.recorder import TrajectoryRecorder, redact_sensitive


@dataclass(slots=True)
class BatchEvalScenario:
    name: str
    prompt: str
    expected: Any = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BatchEvalResult:
    name: str
    passed: bool
    output: Any
    expected: Any
    run_id: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "output": redact_sensitive(self.output),
            "expected": redact_sensitive(self.expected),
            "run_id": self.run_id,
        }


Executor = Callable[[BatchEvalScenario], Any | Awaitable[Any]]


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def run_batch_eval(
    scenarios: Sequence[BatchEvalScenario],
    executor: Executor,
    *,
    recorder: TrajectoryRecorder | None = None,
    surface: str = "batch_eval",
) -> list[BatchEvalResult]:
    recorder = recorder or TrajectoryRecorder(enabled=False)
    results: list[BatchEvalResult] = []
    for index, scenario in enumerate(scenarios):
        with recorder.run(
            surface=surface,
            prompt=scenario.prompt,
            metadata={"scenario": scenario.name, **dict(scenario.metadata)},
        ) as run:
            run_id = run.run_id if run else None
            try:
                output = await _maybe_await(executor(scenario))
                passed = scenario.expected is None or output == scenario.expected
                status = "ok" if passed else "mismatch"
                recorder.step(
                    run_id,
                    index=index,
                    kind="scenario",
                    status=status,
                    input_ref=f"scenario:{scenario.name}",
                    output_ref=f"result:{scenario.name}",
                    metadata={"output": output, "expected": scenario.expected},
                )
            except Exception as exc:
                output = {"error": type(exc).__name__, "message": str(exc)}
                passed = False
                recorder.step(
                    run_id,
                    index=index,
                    kind="scenario",
                    status="error",
                    input_ref=f"scenario:{scenario.name}",
                    metadata=output,
                )
            results.append(
                BatchEvalResult(
                    name=scenario.name,
                    passed=passed,
                    output=redact_sensitive(output),
                    expected=redact_sensitive(scenario.expected),
                    run_id=run_id,
                )
            )
    return results
