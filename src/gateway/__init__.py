"""Fail-closed gateway core and outbox primitives."""

from src.gateway.auth import GatewayAuth, GatewayAuthError, GatewayPrincipal
from src.gateway.core import GatewayCore
from src.gateway.models import DeliveryTarget, GatewayReply, NormalizedMessage
from src.gateway.outbox import GatewayOutbox, OutboxItem

__all__ = [
    "DeliveryTarget",
    "GatewayAuth",
    "GatewayAuthError",
    "GatewayCore",
    "GatewayOutbox",
    "GatewayPrincipal",
    "GatewayReply",
    "NormalizedMessage",
    "OutboxItem",
]
