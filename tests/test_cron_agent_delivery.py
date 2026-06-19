"""Tests for PR-PATCH-012 cron agent delivery contracts."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from src.scheduler.agent_job import AgentJobSpec, build_cron_run_trace
from src.scheduler.delivery import (
    CronDeliveryError,
    dispatch_cron_delivery,
    parse_gateway_output_target,
)
from src.task_scheduler import TaskScheduler


pytestmark = [pytest.mark.area_unit, pytest.mark.portage, pytest.mark.pr_012]


def test_agent_job_spec_builds_cron_turn_context_with_toolset_profile():
    task = SimpleNamespace(
        id="task-1",
        name="Nightly summary",
        prompt="Summarize token=SECRET",
        owner="alice",
        session_id="sess-1",
        output_target="gateway:fake:dm-alice",
        tool_profile="research",
    )

    job = AgentJobSpec.from_task(task, run_id="run-1")
    turn = job.to_turn_context()
    trace = job.to_trace()

    assert turn.surface == "cron"
    assert turn.user == "alice"
    assert turn.toolset == frozenset({"research"})
    assert turn.last_user_text() == "Summarize token=SECRET"
    assert trace["prompt_preview"] == "Summarize token=<redacted>"
    assert trace["delivery_target"] == "gateway:fake:dm-alice"


def test_cron_gateway_delivery_enqueues_redacted_idempotent_outbox_item():
    holder = SimpleNamespace()
    job = AgentJobSpec(
        task_id="task-1",
        run_id="run-1",
        name="Nightly summary",
        prompt="go",
        delivery_target="gateway:fake:dm-alice",
    )

    first = dispatch_cron_delivery(holder, job, "done password=hunter2")
    second = dispatch_cron_delivery(holder, job, "changed password=hunter2")
    item = holder._gateway_outbox.all_items()[0]

    assert first.idempotency_key == second.idempotency_key
    assert item.text == "done password=<redacted>"
    assert item.target.key() == "fake|dm-alice|"

    holder._gateway_outbox.mark_failed(first.idempotency_key, now=10.0)
    retry = dispatch_cron_delivery(holder, job, "still redacted")

    assert retry.status == "failed"
    assert retry.attempts == 1
    assert holder._gateway_outbox.due(now=11.0) == []
    assert holder._gateway_outbox.due(now=12.0) == [item]


def test_invalid_gateway_delivery_target_fails_closed_without_outbox():
    holder = SimpleNamespace()
    job = AgentJobSpec(
        task_id="task-1",
        run_id="run-1",
        name="bad",
        prompt="go",
        delivery_target="gateway::dm-alice",
    )

    with pytest.raises(CronDeliveryError, match="invalid-gateway-delivery-target"):
        dispatch_cron_delivery(holder, job, "done")

    assert not hasattr(holder, "_gateway_outbox")


@pytest.mark.asyncio
async def test_scheduler_delivery_ignores_non_gateway_targets_without_outbox():
    scheduler = TaskScheduler.__new__(TaskScheduler)
    scheduler._gateway_outbox = None
    task = SimpleNamespace(
        id="task-1",
        name="Notify only",
        prompt="go",
        output_target="notification",
        owner="alice",
    )

    result = await scheduler._deliver_task_result(task, "done", db=None)

    assert result is None
    assert scheduler._gateway_outbox is None
    assert parse_gateway_output_target("session") is None


@pytest.mark.asyncio
async def test_scheduler_run_task_now_refuses_existing_execution():
    scheduler = TaskScheduler.__new__(TaskScheduler)
    scheduler._executing = {"task-1"}
    scheduler._executing_lock = asyncio.Lock()

    assert await scheduler.run_task_now("task-1") is False


def test_cron_run_trace_redacts_secrets_and_includes_delivery_metadata():
    job = AgentJobSpec(
        task_id="task-1",
        run_id="run-1",
        name="Job secret=abc",
        prompt="Use api_key=abc",
        delivery_target="gateway:fake:dm",
    )

    trace = build_cron_run_trace(
        job,
        delivery={
            "kind": "gateway",
            "status": "pending",
            "target_key": "fake|dm|",
            "idempotency_key": "cron:task-1:run-1:fake|dm|",
            "attempts": 0,
        },
    )
    encoded = json.dumps(trace, sort_keys=True)

    assert "api_key=<redacted>" in encoded
    assert "secret=<redacted>" in encoded
    assert "abc" not in encoded
    assert trace["delivery"]["status"] == "pending"
