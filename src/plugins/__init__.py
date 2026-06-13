"""Opt-in plugin hook support for agent tool execution."""

from src.plugins.hooks import (
    dispatch_after_tool,
    dispatch_before_tool,
)
from src.plugins.manager import PluginHookManager, get_plugin_manager, set_plugin_manager
from src.plugins.models import HookAction, HookDecision, HookPoint, ToolInvocationContext
from src.plugins.policy import PluginPolicy, load_plugin_policy

__all__ = [
    "HookAction",
    "HookDecision",
    "HookPoint",
    "PluginHookManager",
    "PluginPolicy",
    "ToolInvocationContext",
    "dispatch_after_tool",
    "dispatch_before_tool",
    "get_plugin_manager",
    "load_plugin_policy",
    "set_plugin_manager",
]
