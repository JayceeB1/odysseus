"""Gateway adapters."""

from src.gateway.adapters.base import GatewayAdapter
from src.gateway.adapters.fake import FakeGatewayAdapter

__all__ = ["FakeGatewayAdapter", "GatewayAdapter"]
