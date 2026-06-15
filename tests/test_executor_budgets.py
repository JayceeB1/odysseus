import asyncio
from types import SimpleNamespace

import pytest

from src.runtime.budgets import ToolExecutionBudget
from src.runtime.executor import ToolExecutorFacade
from src.runtime.result_store import InMemoryResultStore
from src.tool_policy import ToolPolicy
import src.tool_execution as tool_execution
from src.tool_execution import execute_tool_block


pytestmark = [pytest.mark.portage, pytest.mark.pr_005]


def _run(coro):
    return asyncio.run(coro)


async def _ok_provider():
    return "demo: ok", {"output": "hello", "exit_code": 0}


def test_executor_facade_happy_path_preserves_result_shape():
    facade = ToolExecutorFacade()

    desc, result = _run(facade.execute(tool_name="demo", provider=_ok_provider))

    assert desc == "demo: ok"
    assert result == {"output": "hello", "exit_code": 0}


def test_executor_facade_preserves_sensitive_text_by_default():
    facade = ToolExecutorFacade()
    canary = "s" + "k-sensitivevalue123456789"

    async def provider():
        return "demo", {"output": canary, "exit_code": 0}

    _desc, result = _run(facade.execute(tool_name="demo", provider=provider))

    assert result["output"] == canary


def test_executor_budget_refuses_tool_without_provider_side_effect():
    called = False
    facade = ToolExecutorFacade(budget=ToolExecutionBudget(max_tool_calls=0))

    async def provider():
        nonlocal called
        called = True
        return "demo", {"output": "ran", "exit_code": 0}

    desc, result = _run(facade.execute(tool_name="demo", provider=provider))

    assert called is False
    assert desc == "demo: BLOCKED"
    assert result["exit_code"] == 1
    assert result["budget_exceeded"] is True


def test_executor_budget_tracks_across_facades_when_budget_is_shared():
    budget = ToolExecutionBudget(max_tool_calls=1)

    first = ToolExecutorFacade(budget=budget)
    second = ToolExecutorFacade(budget=budget)

    assert _run(first.execute(tool_name="demo", provider=_ok_provider))[1]["exit_code"] == 0
    desc, result = _run(second.execute(tool_name="demo", provider=_ok_provider))

    assert desc == "demo: BLOCKED"
    assert result["budget_exceeded"] is True
    assert budget.used_tool_calls == 1


def test_executor_timeout_returns_stable_failure():
    facade = ToolExecutorFacade(budget=ToolExecutionBudget(timeout_seconds=0.001))

    async def provider():
        await asyncio.sleep(1)
        return "demo", {"output": "late", "exit_code": 0}

    desc, result = _run(facade.execute(tool_name="demo", provider=provider))

    assert desc == "demo: TIMEOUT"
    assert result["exit_code"] == 124
    assert "timed out" in result["error"]


def test_executor_provider_error_is_opt_in_and_redacted():
    facade = ToolExecutorFacade(
        budget=ToolExecutionBudget(catch_provider_errors=True, redact_outputs=True, emit_events=True)
    )
    key_name = "api" + "_key"
    canary = "s" + "k-sensitivevalue123456789"

    async def provider():
        raise RuntimeError(f"{key_name}={canary}")

    desc, result = _run(facade.execute(tool_name="demo", provider=provider))

    assert desc == "demo: ERROR"
    assert result["exit_code"] == 1
    assert canary not in result["error"]
    assert result["run_events"][-1]["decision"] == "provider_error"
    assert canary not in str(result["run_events"])


def test_large_output_is_redacted_and_replaced_by_reference():
    store = InMemoryResultStore()
    facade = ToolExecutorFacade(
        budget=ToolExecutionBudget(max_inline_output_chars=12),
        result_store=store,
    )
    canary = "s" + "k-sensitivevalue123456789"

    async def provider():
        return "demo", {"output": f"prefix {canary} suffix", "exit_code": 0}

    desc, result = _run(facade.execute(tool_name="demo", provider=provider))

    ref = result["result_refs"]["output"]["ref"]
    assert desc == "demo"
    assert result["output"].startswith("[stored as tool-result-")
    assert canary not in result["output"]
    assert canary not in store.get(ref).content
    assert "[REDACTED]" in store.get(ref).content


def test_nested_outputs_are_redacted_and_replaced_by_reference():
    store = InMemoryResultStore()
    facade = ToolExecutorFacade(
        budget=ToolExecutionBudget(max_inline_output_chars=10),
        result_store=store,
    )
    canary = "s" + "k-sensitivevalue123456789"
    key_a = "sec" + "ret"
    key_b = "pass" + "word"

    async def provider():
        return "demo", {
            "diff": {"text": f"{key_a}={canary}\n" + "x" * 30},
            "documents": [{"content": f"{key_b}=hunter2 " + "y" * 30}],
            "exit_code": 0,
        }

    _desc, result = _run(facade.execute(tool_name="demo", provider=provider))

    diff_ref = result["result_refs"]["diff.text"]["ref"]
    doc_ref = result["result_refs"]["documents[0].content"]["ref"]
    assert result["diff"]["text"].startswith("[stored as ")
    assert result["documents"][0]["content"].startswith("[stored as ")
    assert canary not in store.get(diff_ref).content
    assert "hunter2" not in store.get(doc_ref).content


def test_run_events_are_opt_in_and_redacted():
    facade = ToolExecutorFacade(
        budget=ToolExecutionBudget(
            emit_events=True,
            run_id="run-pr005",
            surface="test",
            toolset="executor-budgets-result-store",
        )
    )

    desc, result = _run(facade.execute(tool_name="demo", provider=_ok_provider))

    assert desc == "demo: ok"
    assert [event["type"] for event in result["run_events"]] == ["tool_start", "tool_finish"]
    assert result["run_events"][-1]["run_id"] == "run-pr005"
    assert result["run_events"][-1]["surface"] == "test"
    assert result["run_events"][-1]["toolset"] == "executor-budgets-result-store"
    assert result["run_events"][-1]["decision"] == "allowed"
    assert isinstance(result["run_events"][-1]["duration_ms"], float)
    assert "hello" not in str(result["run_events"])


def test_execute_tool_block_forwards_budget_and_result_store(monkeypatch):
    store = InMemoryResultStore()

    async def fake_impl(*args, **kwargs):
        return "demo", {"output": "x" * 20, "exit_code": 0}

    monkeypatch.setattr(tool_execution, "_execute_tool_block_impl", fake_impl)

    desc, result = _run(
        execute_tool_block(
            SimpleNamespace(tool_type="demo", content=""),
            executor_budget=ToolExecutionBudget(max_inline_output_chars=8),
            result_store=store,
        )
    )

    ref = result["result_refs"]["output"]["ref"]
    assert desc == "demo"
    assert result["output"].startswith("[stored as ")
    assert store.get(ref).content == "x" * 20


def test_execute_tool_block_policy_denial_stays_fail_closed():
    block = SimpleNamespace(tool_type="bash", content="echo should-not-run")
    policy = ToolPolicy(
        disabled_tools=frozenset({"bash"}),
        reasons={"bash": "blocked by test policy"},
    )

    desc, result = _run(execute_tool_block(block, tool_policy=policy))

    assert desc == "bash: BLOCKED"
    assert result["exit_code"] == 1
    assert "tool 'bash'" in result["error"].lower()


def test_execute_tool_block_blocks_timeout_for_side_effecting_tool():
    block = SimpleNamespace(tool_type="write_file", content="path\ncontent")

    desc, result = _run(
        execute_tool_block(block, executor_budget=ToolExecutionBudget(timeout_seconds=0.001))
    )

    assert desc == "write_file: BLOCKED"
    assert result["exit_code"] == 1
    assert result["timeout_unsafe"] is True


def test_execute_tool_block_default_unknown_tool_non_regression():
    block = SimpleNamespace(tool_type="missing_tool", content="")

    desc, result = _run(execute_tool_block(block))

    assert desc == "unknown: missing_tool"
    assert result == {"error": "Unknown tool type: missing_tool", "exit_code": 1}
