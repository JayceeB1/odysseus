"""Gateway pairing and allowlist authorization."""

from __future__ import annotations

from dataclasses import dataclass

from src.gateway.models import NormalizedMessage


class GatewayAuthError(PermissionError):
    """Raised when an inbound gateway caller is not paired or allowed."""


@dataclass(frozen=True)
class GatewayPrincipal:
    adapter: str
    caller_id: str
    scopes: frozenset[str]

    def to_trace(self) -> dict:
        return {
            "adapter": self.adapter,
            "caller_id": self.caller_id,
            "scopes": sorted(self.scopes),
        }


@dataclass(frozen=True)
class GatewayAuth:
    """Fail-closed allowlist for gateway callers."""

    allowed_callers: frozenset[tuple[str, str]] = frozenset()
    default_scopes: frozenset[str] = frozenset({"gateway:chat"})

    def authorize(self, message: NormalizedMessage) -> GatewayPrincipal:
        key = (message.adapter, message.caller_id)
        if key not in self.allowed_callers:
            raise GatewayAuthError("gateway-caller-not-allowed")
        return GatewayPrincipal(
            adapter=message.adapter,
            caller_id=message.caller_id,
            scopes=self.default_scopes,
        )
