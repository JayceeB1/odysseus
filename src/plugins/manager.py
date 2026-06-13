"""In-process plugin hook manager.

No plugin is discovered, imported, or registered automatically. Callers must
explicitly register plugin objects, and the policy allowlist must include the
plugin id before any hook is invoked.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from src.plugins.models import HookAction, HookDecision, HookPoint, ToolInvocationContext
from src.plugins.policy import PluginPolicy, load_plugin_policy

logger = logging.getLogger(__name__)

_SECRET_VALUE_RE = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|password|passwd|authorization)\b\s*[:=]\s*[^\s,;]+"
)
_AUTH_HEADER_RE = re.compile(
    r"(?i)\bauthorization\s*[:=]\s*(?:bearer|basic|token)?\s*[^\s,;]+"
)
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\b")
_LONG_SECRET_RE = re.compile(r"\b[A-Za-z0-9_\-]{24,}\b")
_CODE_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,79}$")
_MAX_AUDIT_REASON = 200


def sanitize_for_audit(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    text = _AUTH_HEADER_RE.sub("authorization=<redacted>", text)
    text = _JWT_RE.sub("<redacted>", text)
    text = _SECRET_VALUE_RE.sub(lambda match: f"{match.group(1)}=<redacted>", text)
    text = _LONG_SECRET_RE.sub("<redacted>", text)
    if len(text) > _MAX_AUDIT_REASON:
        text = text[: _MAX_AUDIT_REASON - 3] + "..."
    return text


def sanitize_code(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    return text if _CODE_RE.fullmatch(text) else ""


@dataclass(frozen=True)
class PluginAuditEvent:
    plugin_id: str
    hook: str
    tool_name: str
    action: str
    reason: str = ""
    run_id: str = ""
    surface: str = "agent"
    toolset: str = "default"
    duration_ms: int = 0


class PluginHookManager:
    def __init__(
        self,
        policy: Optional[PluginPolicy] = None,
        policy_loader: Callable[[], PluginPolicy] = load_plugin_policy,
    ):
        self._policy_loader = policy_loader
        self._refresh_policy = policy is None
        self.policy = policy if policy is not None else self._policy_loader()
        self._plugins: list[Any] = []
        self.audit_events: list[PluginAuditEvent] = []

    def register(self, plugin: Any) -> None:
        plugin_id = self._plugin_id(plugin)
        if not plugin_id:
            raise ValueError("plugin_id is required")
        self._plugins.append(plugin)

    async def dispatch(
        self,
        hook_point: HookPoint | str,
        context: ToolInvocationContext,
    ) -> HookDecision:
        policy = self._current_policy()
        try:
            hook = HookPoint(hook_point)
        except ValueError:
            return HookDecision.deny(
                "Unknown plugin hook point.",
                code="plugin_hook_invalid_decision",
            )

        if not policy.enabled or not policy.allowlist:
            return HookDecision.allow()

        final_decision = HookDecision.allow()
        current_context = context
        for plugin in list(self._plugins):
            plugin_id = self._plugin_id(plugin)
            if not policy.allows(plugin_id):
                continue
            safe_plugin_id = sanitize_for_audit(plugin_id)
            start = time.perf_counter()
            try:
                decision = await self._invoke(plugin, hook, current_context)
            except Exception as exc:
                logger.warning(
                    "Plugin hook failed closed plugin_id=%s hook=%s error_type=%s",
                    safe_plugin_id,
                    hook.value,
                    type(exc).__name__,
                )
                error_code = (
                    "plugin_hook_timeout"
                    if isinstance(exc, asyncio.TimeoutError)
                    else "plugin_hook_failed_closed"
                )
                decision = HookDecision.deny(
                    f"Plugin hook failed closed for {safe_plugin_id}: {type(exc).__name__}",
                    code=error_code,
                )
            duration_ms = int((time.perf_counter() - start) * 1000)

            decision = self._normalize_decision(decision)
            self._audit(plugin_id, hook, decision, current_context, duration_ms)

            if decision.action == HookAction.DENY:
                return decision
            if decision.action == HookAction.MUTATE:
                if not isinstance(decision.content, str):
                    invalid = HookDecision.deny(
                        "Plugin hook returned an invalid mutation.",
                        code="plugin_hook_invalid_decision",
                    )
                    self._audit(plugin_id, hook, invalid, current_context, duration_ms)
                    return invalid
                current_context = current_context.with_content(decision.content)
                final_decision = decision

        return final_decision

    def _current_policy(self) -> PluginPolicy:
        if self._refresh_policy:
            self.policy = self._policy_loader()
        return self.policy

    async def _invoke(
        self,
        plugin: Any,
        hook: HookPoint,
        context: ToolInvocationContext,
    ) -> Any:
        handler = self._handler_for(plugin, hook)
        if handler is None:
            return HookDecision.allow()
        accepts_hook = self._accepts_hook(handler)
        timeout = self.policy.hook_timeout_seconds
        if inspect.iscoroutinefunction(handler):
            raw = handler(hook, context) if accepts_hook else handler(context)
            return await asyncio.wait_for(raw, timeout=timeout)

        def call_handler() -> Any:
            return handler(hook, context) if accepts_hook else handler(context)

        raw = await asyncio.wait_for(asyncio.to_thread(call_handler), timeout=timeout)
        if inspect.isawaitable(raw):
            return await asyncio.wait_for(raw, timeout=timeout)
        return raw

    def _handler_for(self, plugin: Any, hook: HookPoint) -> Optional[Callable[..., Any]]:
        handler = getattr(plugin, "handle_hook", None)
        if callable(handler):
            return handler
        named = getattr(plugin, hook.value, None)
        if callable(named):
            return named
        return None

    def _accepts_hook(self, handler: Callable[..., Any]) -> bool:
        try:
            signature = inspect.signature(handler)
        except (TypeError, ValueError):
            return False
        positional = [
            param
            for param in signature.parameters.values()
            if param.kind
            in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD, param.VAR_POSITIONAL)
        ]
        return any(param.kind == param.VAR_POSITIONAL for param in positional) or len(positional) >= 2

    def _normalize_decision(self, raw: Any) -> HookDecision:
        if raw is None:
            return HookDecision.allow()
        if isinstance(raw, HookDecision):
            try:
                action = HookAction(raw.action)
            except ValueError:
                return HookDecision.deny(
                    "Plugin hook returned an invalid action.",
                    code="plugin_hook_invalid_decision",
                )
            return HookDecision(
                action=action,
                reason=sanitize_for_audit(raw.reason),
                content=raw.content,
                code=sanitize_code(raw.code),
            )
        if isinstance(raw, dict):
            try:
                action = HookAction(str(raw.get("action") or HookAction.ALLOW.value))
            except ValueError:
                return HookDecision.deny(
                    "Plugin hook returned an invalid action.",
                    code="plugin_hook_invalid_decision",
                )
            reason = sanitize_for_audit(raw.get("reason") or "")
            content = raw.get("content")
            code = sanitize_code(raw.get("code") or "")
            return HookDecision(action=action, reason=reason, content=content, code=code)
        if raw is False:
            return HookDecision.deny("Plugin hook denied execution.")
        if raw is True:
            return HookDecision.allow()
        return HookDecision.deny(
            "Plugin hook returned an invalid decision.",
            code="plugin_hook_invalid_decision",
        )

    def _audit(
        self,
        plugin_id: str,
        hook: HookPoint,
        decision: HookDecision,
        context: ToolInvocationContext,
        duration_ms: int,
    ) -> None:
        event = PluginAuditEvent(
            plugin_id=sanitize_for_audit(plugin_id),
            hook=hook.value,
            tool_name=sanitize_for_audit(context.tool_name),
            action=decision.action.value,
            reason=sanitize_for_audit(decision.reason),
            run_id=sanitize_for_audit(context.run_id or context.session_id or ""),
            surface=sanitize_for_audit(context.surface),
            toolset=sanitize_for_audit(context.toolset),
            duration_ms=max(0, duration_ms),
        )
        self.audit_events.append(event)
        logger.info(
            "Plugin hook audit plugin_id=%s hook=%s tool=%s action=%s run_id=%s surface=%s toolset=%s duration_ms=%s reason=%s",
            event.plugin_id,
            event.hook,
            event.tool_name,
            event.action,
            event.run_id,
            event.surface,
            event.toolset,
            event.duration_ms,
            event.reason,
        )

    def _plugin_id(self, plugin: Any) -> str:
        return str(getattr(plugin, "plugin_id", "")).strip()


_default_manager: PluginHookManager | None = None


def get_plugin_manager() -> PluginHookManager:
    global _default_manager
    if _default_manager is None:
        _default_manager = PluginHookManager()
    return _default_manager


def set_plugin_manager(manager: PluginHookManager | None) -> None:
    global _default_manager
    _default_manager = manager
