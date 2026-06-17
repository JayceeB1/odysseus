from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from src.evals.runner import BatchEvalScenario, run_batch_eval
from src.trajectories.export import export_jsonl
from src.trajectories.recorder import TrajectoryRecorder
from src.trajectories.replay import ReplayPolicy, replay_trajectory_jsonl


class _Deterministic:
    def __init__(self) -> None:
        self.current = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.ids: dict[str, int] = {}

    def clock(self) -> datetime:
        value = self.current
        self.current += timedelta(seconds=1)
        return value

    def new_id(self, kind: str) -> str:
        self.ids[kind] = self.ids.get(kind, 0) + 1
        return f"{kind}-{self.ids[kind]}"


def _records(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def test_trajectory_recorder_exports_stable_redacted_jsonl():
    det = _Deterministic()
    recorder = TrajectoryRecorder(enabled=True, clock=det.clock, id_factory=det.new_id)
    key_api = "api" + "_key"
    key_auth = "Author" + "ization"
    cred = "sk" + "-testcred123"

    with recorder.run(surface="unit", prompt="hello", metadata={key_api: cred}) as run:
        assert run is not None
        step = recorder.step(
            run.run_id,
            index=0,
            kind="tool",
            tool="fake_tool",
            metadata={key_auth: f"{'Bear' + 'er'} {cred}", "safe": "ok"},
        )
        assert step is not None
        recorder.event(run.run_id, "tool_result", {"message": f"done {cred}"}, step_id=step.step_id)

    exported = export_jsonl(recorder.snapshot())
    records = _records(exported)

    assert [record["record_type"] for record in records] == [
        "run",
        "step",
        "event",
        "event",
        "event",
    ]
    assert records[0]["metadata"][key_api] == "[redacted]"
    assert records[1]["metadata"][key_auth] == "[redacted]"
    assert records[2]["payload"] == {"surface": "unit"}
    assert records[3]["payload"]["message"] == "done [redacted]"
    assert cred not in exported


def test_recorder_disabled_by_default_has_no_side_effects():
    recorder = TrajectoryRecorder()
    with recorder.run(surface="unit", prompt="ignored") as run:
        assert run is None
        assert recorder.step(None, index=0, kind="tool") is None
        assert recorder.event(None, "ignored") is None

    assert recorder.snapshot().is_empty()
    assert export_jsonl(recorder.snapshot()) == ""


def test_replay_is_dry_run_only_and_validates_run_references():
    det = _Deterministic()
    recorder = TrajectoryRecorder(enabled=True, clock=det.clock, id_factory=det.new_id)
    with recorder.run(surface="unit") as run:
        assert run is not None
        recorder.step(run.run_id, index=0, kind="tool")

    exported = export_jsonl(recorder.snapshot())
    assert replay_trajectory_jsonl(exported) == {
        "mode": "dry_run",
        "runs": 1,
        "steps": 1,
        "events": 2,
    }
    with pytest.raises(PermissionError):
        replay_trajectory_jsonl(exported, policy=ReplayPolicy(dry_run=False))

    broken = exported.replace('"run_id":"run-1"', '"run_id":"missing"', 1)
    with pytest.raises(ValueError, match="unknown run_id"):
        replay_trajectory_jsonl(broken)


def test_recorder_marks_failed_runs_and_redacts_errors():
    det = _Deterministic()
    recorder = TrajectoryRecorder(enabled=True, clock=det.clock, id_factory=det.new_id)
    cred = "ghp_" + "a" * 20

    with pytest.raises(RuntimeError):
        with recorder.run(surface="unit") as run:
            assert run is not None
            raise RuntimeError(f"provider failed with {cred}")

    exported = export_jsonl(recorder.snapshot())
    records = _records(exported)
    assert records[0]["status"] == "failed"
    assert any(record.get("name") == "run_failed" for record in records)
    assert cred not in exported


@pytest.mark.asyncio
async def test_batch_eval_records_observable_redacted_results():
    det = _Deterministic()
    recorder = TrajectoryRecorder(enabled=True, clock=det.clock, id_factory=det.new_id)
    key_tok = "tok" + "en"
    cred = ("Bear" + "er") + " " + "x" * 16
    scenarios = [
        BatchEvalScenario(name="pass", prompt="ok", expected="ok"),
        BatchEvalScenario(name="fail", prompt="nope", expected="ok", metadata={key_tok: cred}),
    ]

    async def fake_executor(scenario: BatchEvalScenario) -> str:
        return scenario.prompt

    results = await run_batch_eval(scenarios, fake_executor, recorder=recorder)

    assert [result.passed for result in results] == [True, False]
    assert [result.run_id for result in results] == ["run-1", "run-2"]
    exported = export_jsonl(recorder.snapshot())
    assert '"status":"mismatch"' in exported
    assert cred not in exported
