import asyncio
import inspect
import json
import logging
import time

import pytest

from src.agent_tools import ToolBlock
from src.plugins.manager import PluginHookManager, sanitize_for_audit, set_plugin_manager
from src.plugins.models import HookDecision, HookPoint
from src.plugins.policy import PluginPolicy, load_plugin_policy
from src.tool_execution import execute_tool_block
import src.tool_execution as tool_execution


pytestmark = pytest.mark.area_security


@pytest.fixture(autouse=True)
def _reset_plugin_manager():
    set_plugin_manager(None)
    yield
    set_plugin_manager(None)


@pytest.fixture(autouse=True)
def _allow_admin_owner(monkeypatch):
    monkeypatch.setattr(tool_execution, "owner_is_admin_or_single_user", lambda owner: True)


def _manager(*plugins, allowlist, timeout=1.0, enabled=True):
    manager = PluginHookManager(
        PluginPolicy(
            enabled=enabled,
            allowlist=tuple(allowlist),
            hook_timeout_seconds=timeout,
        )
    )
    for plugin in plugins:
        manager.register(plugin)
    set_plugin_manager(manager)
    return manager


def test_plugin_policy_reads_odysseus_plugin_hooks_env(monkeypatch):
    monkeypatch.setenv("ODYSSEUS_PLUGIN_HOOKS", "1")

    def settings_reader(key, default=None):
        values = {
            "plugins_enabled": False,
            "plugins_allowlist": ["allowed-plugin"],
            "plugin_hook_timeout_seconds": "0.2",
        }
        return values.get(key, default)

    policy = load_plugin_policy(settings_reader)

    assert policy.enabled is True
    assert policy.allowlist == ("allowed-plugin",)
    assert policy.hook_timeout_seconds == 0.2
    assert policy.fail_closed is True


def test_plugin_hooks_do_not_change_existing_tool_schema_surface():
    from src.agent_tools import TOOL_TAGS
    from src.tool_schemas import FUNCTION_TOOL_SCHEMAS

    schema_names = {schema["function"]["name"] for schema in FUNCTION_TOOL_SCHEMAS}

    assert {"bash", "read_file", "write_file", "manage_mcp"}.issubset(TOOL_TAGS)
    assert {"bash", "read_file", "write_file"}.issubset(schema_names)
    assert not any(name.startswith("plugin_") for name in TOOL_TAGS)
    assert not any(name.startswith("plugin_") for name in schema_names)

    signature = inspect.signature(execute_tool_block)
    assert list(signature.parameters)[:7] == [
        "block",
        "session_id",
        "disabled_tools",
        "owner",
        "progress_cb",
        "workspace",
        "tool_policy",
    ]
    assert {
        name: signature.parameters[name].default
        for name in ("executor_budget", "result_store", "executor_facade")
    } == {
        "executor_budget": None,
        "result_store": None,
        "executor_facade": None,
    }


def test_sanitize_for_audit_redacts_spaced_authorization_header():
    redacted = sanitize_for_audit("Authorization: Bearer shorttoken123")

    assert "shorttoken123" not in redacted
    assert redacted == "authorization=<redacted>"


async def _fake_direct_result(tool, content, progress_cb=None):
    return {"stdout": content, "exit_code": 0}


@pytest.mark.asyncio
async def test_plugin_hooks_disabled_by_default_preserves_tool_execution(monkeypatch):
    calls = []

    async def fake_direct(tool, content, progress_cb=None):
        calls.append((tool, content))
        return await _fake_direct_result(tool, content, progress_cb=progress_cb)

    class DenyAllPlugin:
        plugin_id = "deny-all"

        def handle_hook(self, hook, context):
            return HookDecision.deny("should not run")

    _manager(DenyAllPlugin(), allowlist=["deny-all"], enabled=False)
    monkeypatch.setattr(tool_execution, "get_mcp_manager", lambda: None)
    monkeypatch.setattr(tool_execution, "_direct_fallback", fake_direct)

    desc, result = await execute_tool_block(ToolBlock("bash", "echo ok"))

    assert desc == "bash: echo ok"
    assert result["exit_code"] == 0
    assert calls == [("bash", "echo ok")]


@pytest.mark.asyncio
async def test_before_tool_hook_blocks_shell_before_execution(monkeypatch):
    class BlockShellPlugin:
        plugin_id = "block-shell"

        def handle_hook(self, hook, context):
            if hook == HookPoint.BEFORE_TOOL and context.tool_name == "bash":
                return HookDecision.deny("shell blocked by plugin policy")
            return HookDecision.allow()

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("blocked shell tool must not execute")

    _manager(BlockShellPlugin(), allowlist=["block-shell"])
    monkeypatch.setattr(tool_execution, "get_mcp_manager", lambda: None)
    monkeypatch.setattr(tool_execution, "_direct_fallback", fail_if_called)

    desc, result = await execute_tool_block(ToolBlock("bash", "echo should-not-run"))

    assert desc == "bash: BLOCKED"
    assert result["exit_code"] == 1
    assert result["error_code"] == "plugin_hook_denied"
    assert "shell blocked by plugin policy" in result["error"]


@pytest.mark.asyncio
async def test_before_tool_hook_blocks_non_bash_tool_before_execution():
    class BlockAskUserPlugin:
        plugin_id = "block-ask-user"

        def handle_hook(self, hook, context):
            if hook == HookPoint.BEFORE_TOOL and context.tool_name == "ask_user":
                return HookDecision.deny("ask_user blocked by plugin policy")
            return HookDecision.allow()

    _manager(BlockAskUserPlugin(), allowlist=["block-ask-user"])
    content = json.dumps(
        {
            "question": "Continue?",
            "options": [{"label": "Yes"}, {"label": "No"}],
        }
    )

    desc, result = await execute_tool_block(ToolBlock("ask_user", content))

    assert desc == "ask_user: BLOCKED"
    assert result["exit_code"] == 1
    assert result["error_code"] == "plugin_hook_denied"


@pytest.mark.asyncio
async def test_non_admin_tool_guard_runs_before_plugin_hooks(monkeypatch):
    class RecordingPlugin:
        plugin_id = "recorder"

        def __init__(self):
            self.hook_calls = 0

        def handle_hook(self, hook, context):
            self.hook_calls += 1
            return HookDecision.allow()

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("non-admin shell tool must not execute")

    plugin = RecordingPlugin()
    manager = _manager(plugin, allowlist=["recorder"])
    monkeypatch.setattr(tool_execution, "owner_is_admin_or_single_user", lambda owner: False)
    monkeypatch.setattr(tool_execution, "get_mcp_manager", lambda: None)
    monkeypatch.setattr(tool_execution, "_direct_fallback", fail_if_called)

    desc, result = await execute_tool_block(
        ToolBlock("bash", "echo should-not-run"),
        owner="regular-user",
    )

    assert desc == "bash: BLOCKED"
    assert result["exit_code"] == 1
    assert "restricted to admin users" in result["error"]
    assert plugin.hook_calls == 0
    assert manager.audit_events == []


@pytest.mark.asyncio
async def test_before_tool_hook_timeout_fails_closed(monkeypatch):
    class SlowPlugin:
        plugin_id = "slow-plugin"

        async def handle_hook(self, hook, context):
            await asyncio.sleep(0.05)
            return HookDecision.allow()

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("timed-out hook must block tool execution")

    _manager(SlowPlugin(), allowlist=["slow-plugin"], timeout=0.01)
    monkeypatch.setattr(tool_execution, "get_mcp_manager", lambda: None)
    monkeypatch.setattr(tool_execution, "_direct_fallback", fail_if_called)

    desc, result = await execute_tool_block(ToolBlock("bash", "echo should-not-run"))

    assert desc == "bash: BLOCKED"
    assert result["exit_code"] == 1
    assert result["error_code"] == "plugin_hook_timeout"
    assert "TimeoutError" in result["error"]


@pytest.mark.asyncio
async def test_sync_before_tool_hook_timeout_fails_closed_without_blocking_tool(monkeypatch):
    class BlockingSyncPlugin:
        plugin_id = "blocking-sync"

        def handle_hook(self, hook, context):
            time.sleep(0.2)
            return HookDecision.allow()

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("timed-out sync hook must block tool execution")

    _manager(BlockingSyncPlugin(), allowlist=["blocking-sync"], timeout=0.01)
    monkeypatch.setattr(tool_execution, "get_mcp_manager", lambda: None)
    monkeypatch.setattr(tool_execution, "_direct_fallback", fail_if_called)

    started = time.perf_counter()
    desc, result = await execute_tool_block(ToolBlock("bash", "echo should-not-run"))
    elapsed = time.perf_counter() - started

    assert desc == "bash: BLOCKED"
    assert result["exit_code"] == 1
    assert result["error_code"] == "plugin_hook_timeout"
    assert elapsed < 0.15


@pytest.mark.asyncio
async def test_before_tool_hook_exception_fails_closed(monkeypatch):
    class BrokenPlugin:
        plugin_id = "broken-plugin"

        def handle_hook(self, hook, context):
            raise RuntimeError("Authorization: Bearer shorttoken123")

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("failing hook must block tool execution")

    _manager(BrokenPlugin(), allowlist=["broken-plugin"])
    monkeypatch.setattr(tool_execution, "get_mcp_manager", lambda: None)
    monkeypatch.setattr(tool_execution, "_direct_fallback", fail_if_called)

    desc, result = await execute_tool_block(ToolBlock("bash", "echo should-not-run"))

    assert desc == "bash: BLOCKED"
    assert result["exit_code"] == 1
    assert result["error_code"] == "plugin_hook_failed_closed"
    assert "shorttoken123" not in result["error"]


@pytest.mark.asyncio
async def test_invalid_hook_action_fails_closed(monkeypatch):
    class InvalidActionPlugin:
        plugin_id = "invalid-action"

        def handle_hook(self, hook, context):
            return {"action": "explode"}

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("invalid hook decision must block tool execution")

    _manager(InvalidActionPlugin(), allowlist=["invalid-action"])
    monkeypatch.setattr(tool_execution, "get_mcp_manager", lambda: None)
    monkeypatch.setattr(tool_execution, "_direct_fallback", fail_if_called)

    desc, result = await execute_tool_block(ToolBlock("bash", "echo should-not-run"))

    assert desc == "bash: BLOCKED"
    assert result["exit_code"] == 1
    assert result["error_code"] == "plugin_hook_invalid_decision"


@pytest.mark.asyncio
async def test_invalid_hook_mutation_fails_closed(monkeypatch):
    class InvalidMutationPlugin:
        plugin_id = "invalid-mutation"

        def handle_hook(self, hook, context):
            return {"action": "mutate", "content": {"not": "a string"}}

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("invalid mutation must block tool execution")

    _manager(InvalidMutationPlugin(), allowlist=["invalid-mutation"])
    monkeypatch.setattr(tool_execution, "get_mcp_manager", lambda: None)
    monkeypatch.setattr(tool_execution, "_direct_fallback", fail_if_called)

    desc, result = await execute_tool_block(ToolBlock("bash", "echo should-not-run"))

    assert desc == "bash: BLOCKED"
    assert result["exit_code"] == 1
    assert result["error_code"] == "plugin_hook_invalid_decision"


@pytest.mark.asyncio
async def test_plugin_policy_refreshes_between_dispatches(monkeypatch):
    state = {"enabled": True}
    calls = []

    class BlockShellPlugin:
        plugin_id = "block-shell"

        def handle_hook(self, hook, context):
            calls.append(context.tool_name)
            return HookDecision.deny("blocked while enabled")

    async def fake_direct(tool, content, progress_cb=None):
        return await _fake_direct_result(tool, content, progress_cb=progress_cb)

    manager = PluginHookManager(
        policy_loader=lambda: PluginPolicy(
            enabled=state["enabled"],
            allowlist=("block-shell",),
            hook_timeout_seconds=1.0,
        )
    )
    manager.register(BlockShellPlugin())
    set_plugin_manager(manager)
    monkeypatch.setattr(tool_execution, "get_mcp_manager", lambda: None)
    monkeypatch.setattr(tool_execution, "_direct_fallback", fake_direct)

    _desc, result = await execute_tool_block(ToolBlock("bash", "echo blocked"))
    assert result["error_code"] == "plugin_hook_denied"

    state["enabled"] = False
    desc, result = await execute_tool_block(ToolBlock("bash", "echo ok"))

    assert desc == "bash: echo ok"
    assert result["exit_code"] == 0
    assert calls == ["bash"]


@pytest.mark.asyncio
async def test_non_allowlisted_plugin_is_ignored(monkeypatch):
    calls = []

    class BlockShellPlugin:
        plugin_id = "block-shell"

        def __init__(self):
            self.hook_calls = 0

        def handle_hook(self, hook, context):
            self.hook_calls += 1
            return HookDecision.deny("should be ignored")

    async def fake_direct(tool, content, progress_cb=None):
        calls.append((tool, content))
        return await _fake_direct_result(tool, content, progress_cb=progress_cb)

    plugin = BlockShellPlugin()
    _manager(plugin, allowlist=["other-plugin"])
    monkeypatch.setattr(tool_execution, "get_mcp_manager", lambda: None)
    monkeypatch.setattr(tool_execution, "_direct_fallback", fake_direct)

    desc, result = await execute_tool_block(ToolBlock("bash", "echo ok"))

    assert desc == "bash: echo ok"
    assert result["exit_code"] == 0
    assert plugin.hook_calls == 0
    assert calls == [("bash", "echo ok")]


@pytest.mark.asyncio
async def test_before_tool_hook_can_mutate_tool_content_and_after_hook_audits(monkeypatch):
    calls = []

    class MutatingPlugin:
        plugin_id = "mutator"

        def __init__(self):
            self.after_result = None

        def handle_hook(self, hook, context):
            if hook == HookPoint.BEFORE_TOOL:
                return HookDecision.mutate("echo mutated", reason="normalized command")
            if hook == HookPoint.AFTER_TOOL:
                self.after_result = context.result
            return HookDecision.allow()

    async def fake_direct(tool, content, progress_cb=None):
        calls.append((tool, content))
        return await _fake_direct_result(tool, content, progress_cb=progress_cb)

    plugin = MutatingPlugin()
    manager = _manager(plugin, allowlist=["mutator"])
    monkeypatch.setattr(tool_execution, "get_mcp_manager", lambda: None)
    monkeypatch.setattr(tool_execution, "_direct_fallback", fake_direct)

    desc, result = await execute_tool_block(
        ToolBlock("bash", "echo original"),
        session_id="run-pr003",
    )

    assert desc == "bash: echo mutated"
    assert result["stdout"] == "echo mutated"
    assert calls == [("bash", "echo mutated")]
    assert plugin.after_result["exit_code"] == 0
    assert [event.action for event in manager.audit_events] == ["mutate", "allow"]
    assert all(event.tool_name == "bash" for event in manager.audit_events)
    assert all(event.run_id == "run-pr003" for event in manager.audit_events)
    assert all(event.surface == "agent" for event in manager.audit_events)
    assert all(event.toolset == "default" for event in manager.audit_events)
    assert all(isinstance(event.duration_ms, int) for event in manager.audit_events)


@pytest.mark.asyncio
async def test_after_tool_deny_is_observe_only_for_already_executed_tool(monkeypatch):
    calls = []

    class AfterDenyPlugin:
        plugin_id = "after-deny"

        def handle_hook(self, hook, context):
            if hook == HookPoint.AFTER_TOOL:
                return HookDecision.deny("post result denied")
            return HookDecision.allow()

    async def fake_direct(tool, content, progress_cb=None):
        calls.append((tool, content))
        return {"stdout": "SECRET=abc123", "exit_code": 0}

    manager = _manager(AfterDenyPlugin(), allowlist=["after-deny"])
    monkeypatch.setattr(tool_execution, "get_mcp_manager", lambda: None)
    monkeypatch.setattr(tool_execution, "_direct_fallback", fake_direct)

    desc, result = await execute_tool_block(ToolBlock("bash", "echo secret"))

    assert desc == "bash: echo secret"
    assert result == {"stdout": "SECRET=abc123", "exit_code": 0}
    assert calls == [("bash", "echo secret")]
    assert [event.action for event in manager.audit_events] == ["allow", "deny"]


@pytest.mark.asyncio
async def test_hook_denial_redacts_secret_from_error_and_audit(monkeypatch, caplog):
    secret = "SECRET_VALUE_DO_NOT_LOG_123456789"

    class SecretDenyPlugin:
        plugin_id = "secret-deny"

        def handle_hook(self, hook, context):
            return HookDecision.deny(f"api_key={secret}")

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("denied tool must not execute")

    caplog.set_level(logging.INFO, logger="src.plugins.manager")
    manager = _manager(SecretDenyPlugin(), allowlist=["secret-deny"])
    monkeypatch.setattr(tool_execution, "get_mcp_manager", lambda: None)
    monkeypatch.setattr(tool_execution, "_direct_fallback", fail_if_called)

    _desc, result = await execute_tool_block(ToolBlock("bash", "echo should-not-run"))

    assert result["exit_code"] == 1
    assert result["error_code"] == "plugin_hook_denied"
    assert secret not in result["error"]
    assert "api_key=<redacted>" in result["error"]
    assert secret not in caplog.text
    assert all(secret not in event.reason for event in manager.audit_events)
