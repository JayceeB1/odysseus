"""Policy-only skills runtime resolver."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from src.prompt_security import untrusted_context_message
from src.skills.manifest import SkillManifest


@dataclass(frozen=True)
class SkillRuntimePolicy:
    """Per-turn permission boundary for skill activation."""

    allowed_permissions: frozenset[str] = frozenset()
    enabled: bool = False

    @classmethod
    def allow(cls, *permissions: str) -> "SkillRuntimePolicy":
        return cls(allowed_permissions=frozenset(permissions), enabled=True)


@dataclass(frozen=True)
class SkillResolution:
    enabled: tuple[SkillManifest, ...]
    disabled: tuple[tuple[SkillManifest, str], ...]

    def untrusted_context_messages(self) -> list[dict]:
        messages: list[dict] = []
        for manifest in self.enabled:
            context = "\n".join(
                [
                    f"Skill: {manifest.name}",
                    f"Description: {manifest.description}",
                    f"Permissions: {', '.join(sorted(manifest.permissions)) or 'none'}",
                    f"Context files: {', '.join(manifest.context_files) or 'none'}",
                ]
            )
            messages.append(untrusted_context_message(f"skill:{manifest.name}", context))
        return messages


class SkillRuntime:
    """Select skills for one turn without executing or writing them."""

    def __init__(self, policy: SkillRuntimePolicy | None = None) -> None:
        self.policy = policy or SkillRuntimePolicy()

    def resolve(self, manifests: Iterable[SkillManifest], request_text: str) -> SkillResolution:
        enabled: list[SkillManifest] = []
        disabled: list[tuple[SkillManifest, str]] = []
        for manifest in manifests:
            if not self.policy.enabled:
                disabled.append((manifest, "skills-runtime-disabled"))
                continue
            if manifest.status != "published":
                disabled.append((manifest, "skill-not-published"))
                continue
            if not manifest.matches(request_text):
                disabled.append((manifest, "trigger-not-matched"))
                continue
            missing = manifest.permissions - self.policy.allowed_permissions
            if missing:
                disabled.append((manifest, "permission-denied:" + ",".join(sorted(missing))))
                continue
            enabled.append(manifest)
        return SkillResolution(enabled=tuple(enabled), disabled=tuple(disabled))
