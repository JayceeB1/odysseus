"""Gateway adapter protocol."""

from __future__ import annotations

from typing import Protocol

from src.gateway.models import GatewayReply, NormalizedMessage


class GatewayAdapter(Protocol):
    name: str

    def normalize(self, payload: dict) -> NormalizedMessage:
        ...

    def send(self, reply: GatewayReply) -> None:
        ...
