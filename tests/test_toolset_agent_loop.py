import asyncio
import json
import sys
from types import SimpleNamespace

import pytest

import src.agent_loop as al


pytestmark = pytest.mark.area_unit


def _collect(gen):
    async def _run():
        return [chunk async for chunk in gen]

    return asyncio.run(_run())


def _events(chunks):
    events = []
    for chunk in chunks:
        if chunk.startswith("data: ") and not chunk.startswith("data: [DONE]"):
            try:
                events.append(json.loads(chunk[6:]))
            except json.JSONDecodeError:
                pass
    return events


def _patch_loop_basics(monkeypatch, mcp_manager=None):
    monkeypatch.setattr(al, "get_setting", lambda key, default=None: default, raising=False)
    monkeypatch.setattr(al, "get_mcp_manager", lambda: mcp_manager, raising=False)
    monkeypatch.setattr(al, "estimate_" + "to" + "kens", lambda *args, **kwargs: 10, raising=False)


class _FakeMcpManager:
    def get_all_openai_schemas(self, disabled_map=None):
        return [{
            "type": "function",
            "function": {
                "name": "mcp__srv__write",
                "description": "write via mcp",
                "parameters": {"type": "object", "properties": {}},
            },
        }]


def test_cron_surface_filters_native_schemas_and_hides_mcp(monkeypatch):
    _patch_loop_basics(monkeypatch, mcp_manager=_FakeMcpManager())
    sent_tools = []

    async def _fake_stream(_candidates, messages, **kwargs):
        sent_tools.append(kwargs.get("tools"))
        yield 'data: {"delta": "done"}\n\n'
        yield "data: [DONE]\n\n"

    monkeypatch.setattr(al, "stream_llm_with_fallback", _fake_stream, raising=False)

    _collect(
        al.stream_agent_loop(
            "https://api.openai.com/v1",
            "gpt-test",
            [{"role": "user", "content": "search the web"}],
            max_rounds=1,
            relevant_tools={"ask_user", "bash", "python", "web_search", "mcp__srv__write"},
            toolset_surface="cron",
        )
    )

    names = {
        tool["function"]["name"]
        for tool in (sent_tools[0] or [])
    }
    assert "web_search" in names
    assert "ask_user" in names
    assert "bash" not in names
    assert "python" not in names
    assert "mcp__srv__write" not in names


def test_unknown_toolset_profile_fails_closed_before_tool_start(monkeypatch, caplog):
    _patch_loop_basics(monkeypatch)
    sent_tools = []
    executed = False

    async def _fake_stream(_candidates, messages, **kwargs):
        sent_tools.append(kwargs.get("tools"))
        yield "data: " + json.dumps({"delta": "```bash\necho should-not-run\n```"}) + "\n\n"
        yield "data: [DONE]\n\n"

    async def _fake_exec(*args, **kwargs):
        nonlocal executed
        executed = True
        return ("bash", {"output": "ran", "exit_code": 0})

    monkeypatch.setattr(al, "stream_llm_with_fallback", _fake_stream, raising=False)
    monkeypatch.setattr(al, "execute_tool_block", _fake_exec, raising=False)

    chunks = _collect(
        al.stream_agent_loop(
            "http://local.test/v1",
            "local-model",
            [{"role": "user", "content": "run bash"}],
            max_rounds=1,
            relevant_tools={"bash"},
            toolset_surface="cron",
            toolset_profile="does-not-exist",
        )
    )
    events = _events(chunks)

    assert sent_tools == [None]
    assert executed is False
    assert not any(event.get("type") == "tool_start" for event in events)
    blocked = [event for event in events if event.get("type") == "tool_output"]
    assert blocked
    assert blocked[0]["tool"] == "bash"
    assert blocked[0]["exit_code"] == 1
    assert "fail-closed" in caplog.text


def test_scheduler_run_agent_loop_forwards_toolset_arguments(monkeypatch):
    from src.task_scheduler import TaskScheduler

    captured = {}

    async def _fake_stream_agent_loop(**kwargs):
        captured.update(kwargs)
        yield 'data: {"delta": "ok"}\n\n'
        yield "data: [DONE]\n\n"

    monkeypatch.setattr(al, "stream_agent_loop", _fake_stream_agent_loop, raising=False)
    scheduler = TaskScheduler.__new__(TaskScheduler)
    task = SimpleNamespace(
        id="job1",
        name="Task",
        prompt="do research",
        owner="alice",
        endpoint_url="http://local.test/v1",
        model="local-model",
        max_steps=None,
        crew_member_id=None,
        tool_profile="research",
    )

    result = asyncio.run(
        scheduler._run_agent_loop(
            "http://local.test/v1",
            "local-model",
            task,
            "session1",
            toolset_surface="cron",
            toolset_profile="research",
        )
    )

    assert result == "ok"
    assert captured["toolset_surface"] == "cron"
    assert captured["toolset_profile"] == "research"


def test_scheduler_run_agent_loop_defaults_to_legacy_web_surface(monkeypatch):
    from src.task_scheduler import TaskScheduler

    captured = {}

    async def _fake_stream_agent_loop(**kwargs):
        captured.update(kwargs)
        yield 'data: {"delta": "ok"}\n\n'
        yield "data: [DONE]\n\n"

    monkeypatch.setattr(al, "stream_agent_loop", _fake_stream_agent_loop, raising=False)
    scheduler = TaskScheduler.__new__(TaskScheduler)
    task = SimpleNamespace(
        id="job1",
        name="Task",
        prompt="do work",
        owner="alice",
        endpoint_url="http://local.test/v1",
        model="local-model",
        max_steps=None,
        crew_member_id=None,
    )

    result = asyncio.run(
        scheduler._run_agent_loop(
            "http://local.test/v1",
            "local-model",
            task,
            "session1",
        )
    )

    assert result == "ok"
    assert captured["toolset_surface"] == "web"
    assert captured["toolset_profile"] is None


def test_teacher_escalation_preserves_toolset_policy(monkeypatch):
    _patch_loop_basics(monkeypatch)
    captured = {}

    async def _fake_stream(_candidates, messages, **kwargs):
        yield 'data: {"delta": "I do not have a tool for that."}\n\n'
        yield "data: [DONE]\n\n"

    async def _fake_teacher(**kwargs):
        captured.update(kwargs)
        yield 'data: {"type": "teacher_takeover"}\n\n'

    monkeypatch.setattr(al, "stream_llm_with_fallback", _fake_stream, raising=False)
    monkeypatch.setitem(
        sys.modules,
        "src.teacher_escalation",
        SimpleNamespace(run_teacher_inline=_fake_teacher),
    )

    _collect(
        al.stream_agent_loop(
            "http://local.test/v1",
            "local-model",
            [{"role": "user", "content": "run the scheduled check"}],
            max_rounds=1,
            relevant_tools={"ask_user", "web_search"},
            toolset_surface="cron",
            toolset_profile="research",
        )
    )

    assert captured["toolset_surface"] == "cron"
    assert captured["toolset_profile"] == "research"
    assert captured["allow_admin_toolset"] is False
