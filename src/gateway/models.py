"""Gateway data contracts."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.gateway.auth import GatewayPrincipal


_SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[^'\"\s,;]+"
)


@dataclass(frozen=True)
class DeliveryTarget:
    adapter: str
    channel_id: str
    thread_id: str | None = None

    def key(self) -> str:
        return "|".join([self.adapter, self.channel_id, self.thread_id or ""])


@dataclass(frozen=True)
class NormalizedMessage:
    adapter: str
    caller_id: str
    text: str
    reply_to: DeliveryTarget
    session_id: str | None = None
    message_id: str | None = None
    metadata: dict = field(default_factory=dict)

    def idempotency_key(self) -> str:
        base = self.message_id or f"{self.adapter}:{self.caller_id}:{self.text}:{self.reply_to.key()}"
        return hashlib.sha256(base.encode("utf-8")).hexdigest()

    def to_turn(self, *, principal: "GatewayPrincipal") -> dict:
        return {
            "surface": "gateway",
            "principal": principal.to_trace(),
            "session_id": self.session_id,
            "messages": [{"role": "user", "content": self.text}],
        }

    def to_trace(self) -> dict:
        return {
            "adapter": self.adapter,
            "caller_id": self.caller_id,
            "session_id": self.session_id,
            "message_id": self.message_id,
            "text": _redact(self.text),
        }


@dataclass(frozen=True)
class GatewayReply:
    text: str
    target: DeliveryTarget
    idempotency_key: str

    def redacted_text(self) -> str:
        return _redact(self.text)


def _redact(value: str) -> str:
    return _SECRET_RE.sub(lambda match: match.group(1) + "=<redacted>", str(value))
