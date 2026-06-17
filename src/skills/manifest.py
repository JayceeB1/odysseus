"""Skill manifest validation for the opt-in runtime layer."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from services.memory.skill_format import parse_frontmatter


ALLOWED_PERMISSIONS = frozenset(
    {
        "browser",
        "files",
        "gateway",
        "mcp",
        "memory",
        "network",
        "shell",
        "skills",
        "subagents",
    }
)
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")


class ManifestValidationError(ValueError):
    """Raised when a skill manifest is unsafe or malformed."""


@dataclass(frozen=True)
class SkillManifest:
    """Minimal runtime contract extracted from a SKILL.md frontmatter block."""

    name: str
    description: str = ""
    permissions: frozenset[str] = field(default_factory=frozenset)
    triggers: tuple[str, ...] = ()
    context_files: tuple[str, ...] = ()
    status: str = "draft"
    source: str = "unknown"

    @classmethod
    def from_markdown(cls, text: str) -> "SkillManifest":
        frontmatter, _body = parse_frontmatter(text or "")
        return cls.from_mapping(frontmatter)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "SkillManifest":
        name = str(raw.get("name") or "").strip()
        if not _NAME_RE.match(name):
            raise ManifestValidationError("skill manifest requires a safe lowercase name")

        permissions = frozenset(_normalize_list(raw.get("permissions") or raw.get("requires_permissions")))
        unknown = sorted(permissions - ALLOWED_PERMISSIONS)
        if unknown:
            raise ManifestValidationError(f"unknown skill permission(s): {', '.join(unknown)}")

        triggers = tuple(_normalize_list(raw.get("triggers") or raw.get("when_to_use")))
        context_files = tuple(_validate_context_files(_normalize_list(raw.get("context_files"))))
        status = str(raw.get("status") or "draft").strip().lower()
        if status not in {"draft", "published"}:
            raise ManifestValidationError("skill status must be draft or published")

        return cls(
            name=name,
            description=str(raw.get("description") or "").strip(),
            permissions=permissions,
            triggers=triggers,
            context_files=context_files,
            status=status,
            source=str(raw.get("source") or "unknown").strip() or "unknown",
        )

    def matches(self, request_text: str) -> bool:
        if not self.triggers:
            return False
        text = (request_text or "").lower()
        return any(trigger.lower() in text for trigger in self.triggers if trigger)


def _normalize_list(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        parts = [value]
    elif isinstance(value, Iterable):
        parts = list(value)
    else:
        parts = [value]
    return tuple(str(part).strip().lower() for part in parts if str(part).strip())


def _validate_context_files(paths: Iterable[str]) -> tuple[str, ...]:
    safe: list[str] = []
    for path in paths:
        normalized = path.replace("\\", "/").strip("/")
        if not normalized or normalized.startswith("../") or "/../" in normalized:
            raise ManifestValidationError("context_files must stay inside the skill directory")
        safe.append(normalized)
    return tuple(safe)
