"""Run deterministic JSONL batch-eval scenarios.

Input JSONL rows:
{"name": "case-1", "prompt": "hello", "expected": "hello"}

This CLI intentionally uses an echo executor. It is a smoke harness for the
trajectory/eval contracts, not a live LLM benchmark.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from src.evals.runner import BatchEvalScenario, run_batch_eval
from src.trajectories.export import write_jsonl
from src.trajectories.recorder import TrajectoryRecorder


def _load_scenarios(path: Path) -> list[BatchEvalScenario]:
    scenarios: list[BatchEvalScenario] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        scenarios.append(
            BatchEvalScenario(
                name=row["name"],
                prompt=row["prompt"],
                expected=row.get("expected"),
                metadata=row.get("metadata") or {},
            )
        )
    return scenarios


async def async_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenarios", type=Path)
    parser.add_argument("--trajectory-out", type=Path)
    args = parser.parse_args(argv)

    scenarios = _load_scenarios(args.scenarios)
    recorder = TrajectoryRecorder(enabled=bool(args.trajectory_out))

    async def echo_executor(scenario: BatchEvalScenario) -> str:
        return scenario.prompt

    results = await run_batch_eval(scenarios, echo_executor, recorder=recorder)
    print(json.dumps([result.to_dict() for result in results], sort_keys=True))
    if args.trajectory_out:
        write_jsonl(recorder.snapshot(), args.trajectory_out)
    return 0 if all(result.passed for result in results) else 1


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
