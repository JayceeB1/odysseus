"""Idempotent in-memory gateway outbox."""

from __future__ import annotations

from dataclasses import dataclass

from src.gateway.models import DeliveryTarget, GatewayReply


@dataclass
class OutboxItem:
    idempotency_key: str
    target: DeliveryTarget
    text: str
    status: str = "pending"
    attempts: int = 0
    next_attempt_after: float = 0.0

    def reply(self) -> GatewayReply:
        return GatewayReply(
            text=self.text,
            target=self.target,
            idempotency_key=self.idempotency_key,
        )


class GatewayOutbox:
    """Small outbox with idempotent enqueue and exponential retry metadata."""

    def __init__(self) -> None:
        self._items: dict[str, OutboxItem] = {}

    def enqueue(self, reply: GatewayReply) -> OutboxItem:
        existing = self._items.get(reply.idempotency_key)
        if existing:
            return existing
        item = OutboxItem(
            idempotency_key=reply.idempotency_key,
            target=reply.target,
            text=reply.redacted_text(),
        )
        self._items[reply.idempotency_key] = item
        return item

    def due(self, now: float = 0.0) -> list[OutboxItem]:
        return [
            item
            for item in self._items.values()
            if item.status in {"pending", "failed"} and item.next_attempt_after <= now
        ]

    def mark_sent(self, idempotency_key: str) -> None:
        self._items[idempotency_key].status = "sent"

    def mark_failed(self, idempotency_key: str, *, now: float = 0.0) -> None:
        item = self._items[idempotency_key]
        item.status = "failed"
        item.attempts += 1
        item.next_attempt_after = now + min(300.0, 2.0 ** item.attempts)

    def all_items(self) -> tuple[OutboxItem, ...]:
        return tuple(self._items.values())
