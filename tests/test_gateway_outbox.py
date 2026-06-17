"""Tests for PR-PATCH-011 gateway core and outbox."""

import pytest

from src.gateway import GatewayAuth, GatewayAuthError, GatewayCore, GatewayOutbox
from src.gateway.adapters.fake import FakeGatewayAdapter
from src.gateway.models import DeliveryTarget, GatewayReply

pytestmark = [pytest.mark.area_unit, pytest.mark.portage, pytest.mark.pr_011]


@pytest.mark.asyncio
async def test_gateway_core_fake_adapter_happy_path_enqueues_and_delivers():
    adapter = FakeGatewayAdapter()
    outbox = GatewayOutbox()
    seen_turns = []

    async def dispatch(turn):
        seen_turns.append(turn)
        return "hello token=SECRET"

    core = GatewayCore(
        auth=GatewayAuth(allowed_callers=frozenset({("fake", "alice")})),
        outbox=outbox,
        dispatch=dispatch,
    )

    item = await core.handle_inbound(
        adapter,
        {"caller_id": "alice", "channel_id": "dm-alice", "message_id": "msg-1", "text": "hi"},
    )

    assert item.text == "hello token=<redacted>"
    assert seen_turns[0]["surface"] == "gateway"
    assert seen_turns[0]["principal"]["caller_id"] == "alice"
    assert core.deliver_due(adapter) == 1
    assert adapter.sent[0].text == "hello token=<redacted>"
    assert outbox.all_items()[0].status == "sent"


@pytest.mark.asyncio
async def test_gateway_core_refuses_without_allowlist_and_does_not_dispatch():
    adapter = FakeGatewayAdapter()
    dispatched = False

    def dispatch(turn):
        nonlocal dispatched
        dispatched = True
        return "should not run"

    core = GatewayCore(auth=GatewayAuth(), outbox=GatewayOutbox(), dispatch=dispatch)

    with pytest.raises(GatewayAuthError, match="gateway-caller-not-allowed"):
        await core.handle_inbound(adapter, {"caller_id": "mallory", "text": "hi"})

    assert dispatched is False
    assert core.outbox.all_items() == ()


def test_gateway_outbox_enqueue_is_idempotent_and_retry_backoff_is_stable():
    outbox = GatewayOutbox()
    target = DeliveryTarget(adapter="fake", channel_id="dm")
    reply = GatewayReply(text="first", target=target, idempotency_key="same")

    first = outbox.enqueue(reply)
    second = outbox.enqueue(GatewayReply(text="second", target=target, idempotency_key="same"))
    outbox.mark_failed("same", now=10.0)

    assert first is second
    assert outbox.all_items()[0].text == "first"
    assert outbox.due(now=11.0) == []
    assert outbox.due(now=12.0) == [first]
    assert first.attempts == 1


@pytest.mark.asyncio
async def test_gateway_session_routing_does_not_replace_auth():
    adapter = FakeGatewayAdapter()
    core = GatewayCore(
        auth=GatewayAuth(allowed_callers=frozenset({("fake", "alice")})),
        outbox=GatewayOutbox(),
        dispatch=lambda turn: "ok",
    )

    with pytest.raises(GatewayAuthError):
        await core.handle_inbound(
            adapter,
            {
                "caller_id": "mallory",
                "session_id": "alice-session",
                "channel_id": "dm-mallory",
                "text": "route me as alice",
            },
        )

    assert core.outbox.all_items() == ()


def test_gateway_trace_redacts_inbound_message_secret():
    adapter = FakeGatewayAdapter()
    message = adapter.normalize(
        {
            "caller_id": "alice",
            "channel_id": "dm-alice",
            "message_id": "msg-secret",
            "text": "password=hunter2 please remember",
        }
    )

    assert message.to_trace()["text"] == "password=<redacted> please remember"
