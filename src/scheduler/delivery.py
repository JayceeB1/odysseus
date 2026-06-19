"""Delivery helpers for scheduled agent jobs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.gateway.models import DeliveryTarget, GatewayReply
from src.gateway.outbox import GatewayOutbox
from src.scheduler.agent_job import AgentJobSpec


class CronDeliveryError(ValueError):
    """Raised when a cron delivery target fails closed."""


@dataclass(frozen=True)
class CronDeliveryResult:
    kind: str
    status: str
    target_key: str
    idempotency_key: str
    attempts: int = 0

    def to_trace(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "status": self.status,
            "target_key": self.target_key,
            "idempotency_key": self.idempotency_key,
            "attempts": self.attempts,
        }


def parse_gateway_output_target(output: str | None) -> DeliveryTarget | None:
    """Parse gateway delivery targets.

    Supported format: gateway:<adapter>:<channel_id>[:thread_id].
    Non-gateway targets return None so existing delivery paths keep their
    historical behavior.
    """
    target = (output or "").strip()
    if not target.startswith("gateway:"):
        return None
    parts = target.split(":")
    if len(parts) not in {3, 4}:
        raise CronDeliveryError("invalid-gateway-delivery-target")
    _, adapter, channel_id, *rest = parts
    adapter = adapter.strip()
    channel_id = channel_id.strip()
    thread_id = rest[0].strip() if rest else None
    if not adapter or not channel_id:
        raise CronDeliveryError("invalid-gateway-delivery-target")
    return DeliveryTarget(adapter=adapter, channel_id=channel_id, thread_id=thread_id or None)


def dispatch_cron_delivery(
    holder: Any,
    job: AgentJobSpec,
    result: str,
    *,
    output_target: str | None = None,
) -> CronDeliveryResult | None:
    target = parse_gateway_output_target(output_target or job.delivery_target)
    if target is None:
        return None

    outbox = _ensure_gateway_outbox(holder)
    key = f"cron:{job.task_id}:{job.run_id}:{target.key()}"
    item = outbox.enqueue(
        GatewayReply(
            text=result or "",
            target=target,
            idempotency_key=key,
        )
    )
    return CronDeliveryResult(
        kind="gateway",
        status=item.status,
        target_key=target.key(),
        idempotency_key=item.idempotency_key,
        attempts=item.attempts,
    )


def _ensure_gateway_outbox(holder: Any) -> GatewayOutbox:
    outbox = getattr(holder, "_gateway_outbox", None)
    if outbox is None:
        outbox = GatewayOutbox()
        setattr(holder, "_gateway_outbox", outbox)
    return outbox
