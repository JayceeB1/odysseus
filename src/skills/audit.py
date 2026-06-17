"""Audited skill lifecycle events."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.skills.manifest import SkillManifest


_SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[^'\"\s,;]+"
)


@dataclass(frozen=True)
class AuditEvent:
    event_type: str
    skill_name: str
    decision: str
    reasons: tuple[str, ...] = ()

    def to_trace(self) -> dict:
        return {
            "event_type": self.event_type,
            "skill_name": self.skill_name,
            "decision": self.decision,
            "reasons": [_redact(reason) for reason in self.reasons],
        }


@dataclass
class SkillAuditLog:
    """In-memory audit recorder for install/update review decisions."""

    events: list[AuditEvent] = field(default_factory=list)

    def record_install_review(
        self,
        manifest: SkillManifest,
        *,
        decision: str,
        reasons: tuple[str, ...] = (),
    ) -> AuditEvent:
        event = AuditEvent(
            event_type="skill-install-review",
            skill_name=manifest.name,
            decision=decision,
            reasons=tuple(reasons),
        )
        self.events.append(event)
        return event


def _redact(value: str) -> str:
    return _SECRET_RE.sub(lambda match: match.group(1) + "=<redacted>", str(value))
