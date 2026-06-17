"""JSONL export helpers for trajectory bundles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .models import TrajectoryBundle


def iter_jsonl_records(bundle: TrajectoryBundle) -> Iterable[str]:
    for run in sorted(bundle.runs, key=lambda item: item.run_id):
        yield json.dumps(run.to_record(), sort_keys=True, separators=(",", ":"))
    for step in sorted(bundle.steps, key=lambda item: (item.run_id, item.index, item.step_id)):
        yield json.dumps(step.to_record(), sort_keys=True, separators=(",", ":"))
    for event in sorted(bundle.events, key=lambda item: (item.run_id, item.created_at, item.event_id)):
        yield json.dumps(event.to_record(), sort_keys=True, separators=(",", ":"))


def export_jsonl(bundle: TrajectoryBundle) -> str:
    return "\n".join(iter_jsonl_records(bundle))


def write_jsonl(bundle: TrajectoryBundle, path: str | Path) -> None:
    text = export_jsonl(bundle)
    Path(path).write_text(text + ("\n" if text else ""), encoding="utf-8")
