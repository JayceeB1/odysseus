"""Data contracts for plugin hooks.

The contracts are deliberately small and stdlib-only. This PR establishes the
execution boundary; it does not add dynamic plugin discovery or loading.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Mapping, Optional


class HookPoint(str, Enum):
    BEFORE_TOOL = "before_tool"
    AFTER_TOOL = "after_tool"


class HookAction(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    MUTATE = "mutate"


@dataclass(frozen=True)
class ToolInvocationContext:
    """Metadata passed to hook handlers.

    ``content`` is model-controlled tool input. Hook audit code must never log it
    raw because it may contain secrets, prompts, or file contents.
    """

    tool_name: str
    content: str
    owner: Optional[str] = None
    session_id: Optional[str] = None
    run_id: Optional[str] = None
    surface: str = "agent"
    toolset: str = "default"
    workspace: Optional[str] = None
    result: Optional[Mapping[str, Any]] = None
    error_type: Optional[str] = None

    def with_content(self, content: str) -> "ToolInvocationContext":
        return replace(self, content=content)


@dataclass(frozen=True)
class HookDecision:
    action: HookAction = HookAction.ALLOW
    reason: str = ""
    content: Optional[str] = None
    code: str = ""

    @classmethod
    def allow(cls, reason: str = "", code: str = "") -> "HookDecision":
        return cls(action=HookAction.ALLOW, reason=reason, code=code)

    @classmethod
    def deny(cls, reason: str, code: str = "plugin_hook_denied") -> "HookDecision":
        return cls(action=HookAction.DENY, reason=reason, code=code)

    @classmethod
    def mutate(cls, content: str, reason: str = "", code: str = "") -> "HookDecision":
        return cls(action=HookAction.MUTATE, reason=reason, content=content, code=code)

    @property
    def denied(self) -> bool:
        return self.action == HookAction.DENY
