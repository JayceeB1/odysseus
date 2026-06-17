"""Gateway core dispatch facade."""

from __future__ import annotations

import inspect
from typing import Awaitable, Callable

from src.gateway.adapters.base import GatewayAdapter
from src.gateway.auth import GatewayAuth
from src.gateway.models import GatewayReply, NormalizedMessage
from src.gateway.outbox import GatewayOutbox, OutboxItem


DispatchFn = Callable[[dict], str | Awaitable[str]]


class GatewayCore:
    """Normalize, authorize, dispatch, and enqueue gateway replies."""

    def __init__(self, *, auth: GatewayAuth, outbox: GatewayOutbox, dispatch: DispatchFn) -> None:
        self.auth = auth
        self.outbox = outbox
        self.dispatch = dispatch

    async def handle_inbound(self, adapter: GatewayAdapter, payload: dict) -> OutboxItem:
        message = adapter.normalize(payload)
        principal = self.auth.authorize(message)
        value = self.dispatch(message.to_turn(principal=principal))
        if inspect.isawaitable(value):
            value = await value
        reply = GatewayReply(
            text=str(value or ""),
            target=message.reply_to,
            idempotency_key=message.idempotency_key(),
        )
        return self.outbox.enqueue(reply)

    def deliver_due(self, adapter: GatewayAdapter, *, now: float = 0.0) -> int:
        sent = 0
        for item in self.outbox.due(now=now):
            adapter.send(item.reply())
            self.outbox.mark_sent(item.idempotency_key)
            sent += 1
        return sent


def normalize_for_trace(message: NormalizedMessage) -> dict:
    return message.to_trace()
