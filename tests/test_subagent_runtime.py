"""Tests for PR-PATCH-010 subagent delegation runtime."""

import pytest

from src.subagents import (
    SubagentBudget,
    SubagentLineage,
    SubagentPolicy,
    SubagentPolicyError,
    SubagentRequest,
    SubagentRuntime,
)

pytestmark = [pytest.mark.area_unit, pytest.mark.portage, pytest.mark.pr_010]


@pytest.mark.asyncio
async def test_subagent_runtime_happy_path_returns_controlled_artifact():
    policy = SubagentPolicy(
        enabled=True,
        max_depth=2,
        parent_allowed_tools=frozenset({"search", "read_file"}),
        parent_budget=SubagentBudget(max_tokens=8000, max_tool_calls=6),
    )
    runtime = SubagentRuntime(policy, delegate=lambda request: "token=SECRET child summary")
    request = SubagentRequest(
        task="summarize module",
        parent_run_id="parent-1",
        requested_tools=frozenset({"search"}),
        max_tokens=5000,
        max_tool_calls=3,
    )

    result = await runtime.run(request)

    assert result.status == "completed"
    assert result.summary == "token=<redacted> child summary"
    assert result.budget == SubagentBudget(max_tokens=5000, max_tool_calls=3)
    artifact = result.to_artifact()
    assert artifact["type"] == "subagent_result"
    assert artifact["lineage"]["parent_run_id"] != artifact["lineage"]["child_run_id"]
    assert artifact["artifacts"] == [{"kind": "summary", "trusted": False}]


@pytest.mark.asyncio
async def test_subagent_policy_is_disabled_by_default():
    runtime = SubagentRuntime(SubagentPolicy(), delegate=lambda request: "should not run")

    with pytest.raises(SubagentPolicyError, match="subagents-disabled"):
        await runtime.run(SubagentRequest(task="x", parent_run_id="parent"))


@pytest.mark.asyncio
async def test_subagent_runtime_refuses_depth_escalation():
    policy = SubagentPolicy(
        enabled=True,
        max_depth=1,
        parent_allowed_tools=frozenset({"search"}),
        parent_budget=SubagentBudget(max_tokens=5000, max_tool_calls=2),
    )
    runtime = SubagentRuntime(policy, delegate=lambda request: "should not run")
    lineage = SubagentLineage(parent_run_id="root", child_run_id="child", depth=1)

    with pytest.raises(SubagentPolicyError, match="max-depth-exceeded"):
        await runtime.run(SubagentRequest(task="x", parent_run_id="child", lineage=lineage))


@pytest.mark.asyncio
async def test_subagent_runtime_refuses_toolset_escalation():
    policy = SubagentPolicy(
        enabled=True,
        max_depth=2,
        parent_allowed_tools=frozenset({"search"}),
        parent_budget=SubagentBudget(max_tokens=5000, max_tool_calls=2),
    )
    runtime = SubagentRuntime(policy, delegate=lambda request: "should not run")

    with pytest.raises(SubagentPolicyError, match="toolset-escalation:shell"):
        await runtime.run(
            SubagentRequest(
                task="x",
                parent_run_id="parent",
                requested_tools=frozenset({"search", "shell"}),
            )
        )


@pytest.mark.asyncio
async def test_subagent_runtime_refuses_exhausted_budget():
    policy = SubagentPolicy(
        enabled=True,
        max_depth=2,
        parent_allowed_tools=frozenset({"search"}),
        parent_budget=SubagentBudget(max_tokens=0, max_tool_calls=2),
    )
    runtime = SubagentRuntime(policy, delegate=lambda request: "should not run")

    with pytest.raises(SubagentPolicyError, match="budget-exhausted"):
        await runtime.run(
            SubagentRequest(
                task="x",
                parent_run_id="parent",
                requested_tools=frozenset({"search"}),
            )
        )
