"""Dry-run replay support for exported trajectories."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .models import AgentEvent, AgentRun, AgentStep, TrajectoryBundle


@dataclass(slots=True)
class ReplayPolicy:
    dry_run: bool = True


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _iter_lines(source: str | Path | Iterable[str]) -> Iterable[str]:
    if isinstance(source, Path):
        yield from source.read_text(encoding="utf-8").splitlines()
    elif isinstance(source, str):
        if "\n" in source or source.strip().startswith("{"):
            yield from source.splitlines()
        else:
            yield from Path(source).read_text(encoding="utf-8").splitlines()
    else:
        yield from source


def load_jsonl(source: str | Path | Iterable[str]) -> TrajectoryBundle:
    bundle = TrajectoryBundle()
    for lineno, line in enumerate(_iter_lines(source), start=1):
        if not line.strip():
            continue
        record = json.loads(line)
        record_type = record.get("record_type")
        if record_type == "run":
            bundle.runs.append(
                AgentRun(
                    run_id=record["run_id"],
                    surface=record["surface"],
                    status=record.get("status", "running"),
                    started_at=_parse_dt(record.get("started_at")) or datetime.fromtimestamp(0),
                    ended_at=_parse_dt(record.get("ended_at")),
                    prompt_hash=record.get("prompt_hash"),
                    metadata=record.get("metadata") or {},
                )
            )
        elif record_type == "step":
            bundle.steps.append(
                AgentStep(
                    step_id=record["step_id"],
                    run_id=record["run_id"],
                    index=int(record.get("index", 0)),
                    kind=record["kind"],
                    status=record.get("status", "ok"),
                    tool=record.get("tool"),
                    input_ref=record.get("input_ref"),
                    output_ref=record.get("output_ref"),
                    duration_ms=record.get("duration_ms"),
                    metadata=record.get("metadata") or {},
                )
            )
        elif record_type == "event":
            bundle.events.append(
                AgentEvent(
                    event_id=record["event_id"],
                    run_id=record["run_id"],
                    step_id=record.get("step_id"),
                    name=record["name"],
                    created_at=_parse_dt(record.get("created_at")) or datetime.fromtimestamp(0),
                    payload=record.get("payload") or {},
                )
            )
        else:
            raise ValueError(f"Unknown trajectory record_type at line {lineno}: {record_type!r}")
    return bundle


def replay_trajectory_jsonl(
    source: str | Path | Iterable[str],
    *,
    policy: ReplayPolicy | None = None,
) -> dict[str, int | str]:
    policy = policy or ReplayPolicy()
    if not policy.dry_run:
        raise PermissionError("PR15 replay is dry-run only; side-effect replay is not implemented")
    bundle = load_jsonl(source)
    run_ids = {run.run_id for run in bundle.runs}
    missing = sorted(
        {
            item.run_id
            for item in [*bundle.steps, *bundle.events]
            if item.run_id not in run_ids
        }
    )
    if missing:
        raise ValueError(f"Trajectory references unknown run_id(s): {', '.join(missing)}")
    return {
        "mode": "dry_run",
        "runs": len(bundle.runs),
        "steps": len(bundle.steps),
        "events": len(bundle.events),
    }
