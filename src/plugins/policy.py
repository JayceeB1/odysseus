"""Policy loading for plugin hooks."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Tuple


DEFAULT_HOOK_TIMEOUT_SECONDS = 1.0
MIN_HOOK_TIMEOUT_SECONDS = 0.05
MAX_HOOK_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class PluginPolicy:
    enabled: bool = False
    allowlist: Tuple[str, ...] = ()
    hook_timeout_seconds: float = DEFAULT_HOOK_TIMEOUT_SECONDS
    fail_closed: bool = True

    def allows(self, plugin_id: str) -> bool:
        return self.enabled and bool(plugin_id) and plugin_id in self.allowlist


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _as_allowlist(value: Any) -> Tuple[str, ...]:
    if isinstance(value, str):
        raw: Iterable[Any] = value.split(",")
    elif isinstance(value, Iterable):
        raw = value
    else:
        raw = ()
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        plugin_id = str(item).strip()
        if not plugin_id or plugin_id in seen:
            continue
        seen.add(plugin_id)
        out.append(plugin_id)
    return tuple(out)


def _as_timeout(value: Any) -> float:
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        timeout = DEFAULT_HOOK_TIMEOUT_SECONDS
    if timeout < MIN_HOOK_TIMEOUT_SECONDS:
        return MIN_HOOK_TIMEOUT_SECONDS
    if timeout > MAX_HOOK_TIMEOUT_SECONDS:
        return MAX_HOOK_TIMEOUT_SECONDS
    return timeout


def load_plugin_policy(settings_reader: Callable[[str, Any], Any] | None = None) -> PluginPolicy:
    if settings_reader is None:
        from src.settings import get_setting

        settings_reader = get_setting
    env_enabled = os.environ.get("ODYSSEUS_PLUGIN_HOOKS")

    return PluginPolicy(
        enabled=_as_bool(env_enabled) if env_enabled is not None else _as_bool(
            settings_reader("plugins_enabled", False)
        ),
        allowlist=_as_allowlist(settings_reader("plugins_allowlist", [])),
        hook_timeout_seconds=_as_timeout(
            settings_reader("plugin_hook_timeout_seconds", DEFAULT_HOOK_TIMEOUT_SECONDS)
        ),
        fail_closed=True,
    )
