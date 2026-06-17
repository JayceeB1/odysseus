"""Deterministic in-memory adapter for tests and dry runs."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.gateway.models import DeliveryTarget, GatewayReply, NormalizedMessage


@dataclass
class FakeGatewayAdapter:
    name: str = "fake"
    sent: list[GatewayReply] = field(default_factory=list)

    def normalize(self, payload: dict) -> NormalizedMessage:
        caller_id = str(payload.get("caller_id") or "").strip()
        channel_id = str(payload.get("channel_id") or "default").strip()
        return NormalizedMessage(
            adapter=self.name,
            caller_id=caller_id,
            text=str(payload.get("text") or ""),
            reply_to=DeliveryTarget(
                adapter=self.name,
                channel_id=channel_id,
                thread_id=str(payload.get("thread_id") or "") or None,
            ),
            session_id=str(payload.get("session_id") or "") or None,
            message_id=str(payload.get("message_id") or "") or None,
            metadata={"fake": True},
        )

    def send(self, reply: GatewayReply) -> None:
        self.sent.append(reply)
