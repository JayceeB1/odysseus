import pytest

from src.agent_loop import _apply_toolset_policy
from src.capabilities.models import ToolContext, ToolDefinition
from src.capabilities.policy import ToolsetPolicy, ToolsetPolicyError
from src.capabilities.registry import CapabilityRegistry


pytestmark = pytest.mark.area_unit


def _schema(name: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": f"{name} schema",
            "parameters": {"type": "object", "properties": {}},
        },
    }


class _StaticProvider:
    provider_id = "static"

    def list_tools(self, context=None):
        return [
            ToolDefinition("bash", _schema("bash"), self.provider_id),
            ToolDefinition("web_search", _schema("web_search"), self.provider_id),
            ToolDefinition("ask_user", _schema("ask_user"), self.provider_id),
        ]


def test_web_default_preserves_existing_unrestricted_behavior():
    resolution = ToolsetPolicy.default().resolve(surface="web")

    assert resolution.allowed_tools is None
    assert not resolution.restricted
    assert resolution.to_trace()["restricted"] is False


def test_cron_default_excludes_shell_tools():
    resolution = ToolsetPolicy.default().resolve(surface="cron")

    assert resolution.allowed_tools is not None
    assert "web_search" in resolution.allowed_tools
    assert "bash" not in resolution.allowed_tools
    assert "python" not in resolution.allowed_tools
    assert "minimal" in resolution.active_toolsets
    assert "cron" in resolution.active_toolsets


def test_non_admin_admin_profile_fails_closed():
    with pytest.raises(ToolsetPolicyError, match="Admin toolset requires"):
        ToolsetPolicy.default().resolve(surface="api", requested="admin", needs_admin=False)


def test_unknown_profile_fails_closed():
    with pytest.raises(ToolsetPolicyError, match="Unknown toolset profile"):
        ToolsetPolicy.default().resolve(surface="api", requested="does-not-exist")


def test_unknown_surface_fails_closed():
    with pytest.raises(ToolsetPolicyError, match="Unknown toolset surface"):
        ToolsetPolicy.default().resolve(surface="croon")


def test_registry_filters_context_allowed_and_disabled_tools():
    registry = CapabilityRegistry()
    registry.register_provider(_StaticProvider())
    context = ToolContext(
        allowed_tools=frozenset({"ask_user", "web_search"}),
        disabled_tools=frozenset({"web_search"}),
    )

    assert [tool.name for tool in registry.list_tools(context)] == ["ask_user"]


def test_agent_loop_policy_filters_relevant_tools_and_disables_others():
    disabled, relevant, resolution = _apply_toolset_policy(
        set(),
        {"bash", "web_search", "ask_user"},
        surface="cron",
        requested_profile=None,
        owner="user@example.test",
        needs_admin=False,
    )

    assert resolution.restricted
    assert relevant == {"web_search", "ask_user"}
    assert "bash" in disabled


def test_agent_loop_admin_profile_needs_explicit_auth_signal():
    with pytest.raises(ToolsetPolicyError, match="Admin toolset requires"):
        _apply_toolset_policy(
            set(),
            {"manage_mcp"},
            surface="admin",
            requested_profile="admin",
            owner="user@example.test",
            needs_admin=True,
        )

    disabled, relevant, resolution = _apply_toolset_policy(
        set(),
        {"manage_mcp"},
        surface="admin",
        requested_profile="admin",
        owner="admin@example.test",
        allow_admin_toolset=True,
    )

    assert resolution.restricted
    assert "admin" in resolution.active_toolsets
    assert relevant == {"manage_mcp"}
    assert "manage_mcp" not in disabled


def test_toolset_trace_redacts_user_and_job_details():
    resolution = ToolsetPolicy.default().resolve(
        surface="cron",
        user="redacted-user@example.test",
        job=type("Job", (), {"toolset_profile": "research", "prompt": "private prompt"})(),
    )

    trace = resolution.to_trace()

    assert "redacted-user@example.test" not in repr(trace)
    assert "private prompt" not in repr(trace)
    assert trace["allowed_tool_count"] == len(resolution.allowed_tools)
