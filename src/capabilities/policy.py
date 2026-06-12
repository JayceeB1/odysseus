"""Toolset policy resolution for request surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Optional

from src.capabilities.profiles import BUILTIN_TOOLSETS, SURFACE_DEFAULT_TOOLSETS


class ToolsetPolicyError(ValueError):
    """Raised when a requested toolset profile cannot be safely resolved."""


@dataclass(frozen=True)
class ToolsetResolution:
    surface: str
    requested: Optional[tuple[str, ...]]
    active_toolsets: frozenset[str]
    allowed_tools: Optional[frozenset[str]]
    reasons: tuple[str, ...] = ()

    @property
    def restricted(self) -> bool:
        return self.allowed_tools is not None

    def to_trace(self) -> dict:
        return {
            "surface": self.surface,
            "requested": list(self.requested or ()),
            "active_toolsets": sorted(self.active_toolsets),
            "restricted": self.restricted,
            "allowed_tool_count": None if self.allowed_tools is None else len(self.allowed_tools),
            "reasons": list(self.reasons),
        }


class ToolsetPolicy:
    """Resolve surface/request profiles to an explicit allowlist."""

    def __init__(
        self,
        *,
        toolsets: Mapping[str, frozenset[str]] = BUILTIN_TOOLSETS,
        surface_defaults: Mapping[str, tuple[str, ...] | None] = SURFACE_DEFAULT_TOOLSETS,
    ) -> None:
        self._toolsets = dict(toolsets)
        self._surface_defaults = dict(surface_defaults)

    @classmethod
    def default(cls) -> "ToolsetPolicy":
        return cls()

    def resolve(
        self,
        *,
        surface: str = "web",
        user: Optional[str] = None,
        job=None,
        requested: Optional[str | Iterable[str]] = None,
        needs_admin: bool = False,
    ) -> ToolsetResolution:
        del user
        surface_key = (surface or "web").strip().lower()
        if surface_key not in self._surface_defaults:
            raise ToolsetPolicyError(f"Unknown toolset surface: {surface_key}")
        requested_profiles = _normalize_profiles(requested)
        if requested_profiles is None:
            requested_profiles = _normalize_profiles(_profile_from_job(job))

        if requested_profiles is None:
            defaults = self._surface_defaults.get(surface_key)
            if defaults is None:
                return ToolsetResolution(
                    surface=surface_key,
                    requested=None,
                    active_toolsets=frozenset(),
                    allowed_tools=None,
                    reasons=("surface-unrestricted",),
                )
            requested_profiles = tuple(defaults)

        profiles = tuple(dict.fromkeys(("minimal", *requested_profiles)))
        unknown = [name for name in profiles if name not in self._toolsets]
        if unknown:
            raise ToolsetPolicyError(f"Unknown toolset profile: {', '.join(sorted(unknown))}")

        if "admin" in profiles and not needs_admin:
            raise ToolsetPolicyError("Admin toolset requires an admin context")

        allowed: set[str] = set()
        for profile in profiles:
            allowed.update(self._toolsets[profile])

        return ToolsetResolution(
            surface=surface_key,
            requested=requested_profiles,
            active_toolsets=frozenset(profiles),
            allowed_tools=frozenset(allowed),
            reasons=(f"surface:{surface_key}",),
        )


def _normalize_profiles(value: Optional[str | Iterable[str]]) -> Optional[tuple[str, ...]]:
    if value is None:
        return None
    if isinstance(value, str):
        raw = [part.strip().lower() for part in value.replace(",", " ").split()]
    else:
        raw = [str(part).strip().lower() for part in value]
    profiles = tuple(part for part in raw if part and part != "default")
    return profiles or None


def _profile_from_job(job) -> Optional[str | Iterable[str]]:
    if job is None:
        return None
    for attr in ("toolset_profile", "toolset_profiles", "toolset", "tool_profile"):
        value = getattr(job, attr, None)
        if value:
            return value
    return None
