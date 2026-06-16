import pytest

from src.providers import (
    ProviderCallFailed,
    ProviderCandidate,
    ProviderErrorCategory,
    ProviderRecoveryAction,
    ProviderRoutingPolicy,
    classify_provider_error,
    run_provider_fallback,
)


pytestmark = [pytest.mark.portage, pytest.mark.pr_006]


class ProviderHTTPError(RuntimeError):
    def __init__(self, message, status_code):
        super().__init__(message)
        self.status_code = status_code


@pytest.mark.unit_contract
def test_provider_classifier_maps_rate_limit_to_fallback_category():
    info = classify_provider_error(ProviderHTTPError("rate limit exceeded", 429), provider="primary")

    assert info.category == ProviderErrorCategory.RATE_LIMIT
    assert info.status_code == 429
    assert info.provider == "primary"
    assert info.retryable is True


@pytest.mark.unit_contract
def test_provider_classifier_keeps_policy_blocks_distinct_from_auth():
    info = classify_provider_error(ProviderHTTPError("blocked by policy", 403), provider="primary")

    assert info.category == ProviderErrorCategory.POLICY
    assert info.retryable is False


@pytest.mark.unit_contract
@pytest.mark.asyncio
async def test_provider_fallback_happy_path_is_explicit_and_correlated():
    calls = []
    events = []

    async def primary():
        calls.append("primary")
        raise ProviderHTTPError("HTTP 429 rate limit", 429)

    async def backup():
        calls.append("backup")
        return "ok"

    result = await run_provider_fallback(
        [ProviderCandidate("primary", primary), ProviderCandidate("backup", backup)],
        policy=ProviderRoutingPolicy(enabled=True),
        run_id="run-pr006",
        surface="api",
        toolset="chat",
        events=events,
    )

    assert result.provider == "backup"
    assert result.value == "ok"
    assert result.fallback_used is True
    assert calls == ["primary", "backup"]
    assert [event["decision"] for event in events] == ["fallback", "success"]
    assert all(event["run_id"] == "run-pr006" for event in events)
    assert all(event["surface"] == "api" for event in events)
    assert all(event["toolset"] == "chat" for event in events)


@pytest.mark.regression
@pytest.mark.asyncio
async def test_provider_recovery_disabled_preserves_legacy_exception_and_no_fallback():
    calls = []

    async def primary():
        calls.append("primary")
        raise ValueError("raw provider failure")

    async def backup():
        calls.append("backup")
        return "unexpected"

    with pytest.raises(ValueError, match="raw provider failure"):
        await run_provider_fallback(
            [ProviderCandidate("primary", primary), ProviderCandidate("backup", backup)]
        )

    assert calls == ["primary"]


@pytest.mark.security_contract
@pytest.mark.asyncio
async def test_provider_auth_error_does_not_retry_or_fallback():
    calls = []
    events = []

    async def primary():
        calls.append("primary")
        raise ProviderHTTPError("invalid api key", 401)

    async def backup():
        calls.append("backup")
        return "unexpected"

    with pytest.raises(ProviderCallFailed) as raised:
        await run_provider_fallback(
            [ProviderCandidate("primary", primary), ProviderCandidate("backup", backup)],
            policy=ProviderRoutingPolicy(enabled=True),
            events=events,
        )

    assert raised.value.category == ProviderErrorCategory.AUTH
    assert calls == ["primary"]
    assert events[-1]["decision"] == ProviderRecoveryAction.ABORT.value


@pytest.mark.security_contract
@pytest.mark.asyncio
async def test_provider_policy_denies_unapproved_surface_before_fallback():
    calls = []

    async def primary():
        calls.append("primary")
        raise ProviderHTTPError("HTTP 503 overloaded", 503)

    async def backup():
        calls.append("backup")
        return "unexpected"

    policy = ProviderRoutingPolicy.for_surfaces({"admin"}, enabled=True)

    with pytest.raises(ProviderCallFailed) as raised:
        await run_provider_fallback(
            [ProviderCandidate("primary", primary), ProviderCandidate("backup", backup)],
            policy=policy,
            surface="gateway",
        )

    assert raised.value.category == ProviderErrorCategory.TRANSIENT
    assert calls == ["primary"]


@pytest.mark.fault_injection
def test_provider_context_overflow_selects_compression_when_available():
    info = classify_provider_error(RuntimeError("maximum context length exceeded"))
    policy = ProviderRoutingPolicy(enabled=True, compression_available=True)

    decision = policy.decide(info, surface="api", fallback_index=0, has_next_provider=True)

    assert info.category == ProviderErrorCategory.CONTEXT
    assert decision.action == ProviderRecoveryAction.COMPRESS


@pytest.mark.observability
@pytest.mark.asyncio
async def test_provider_events_redact_sensitive_canary():
    events = []
    field_name = "api" + "_key"
    credential = "s" + "k-" + "sensitivecanary123456"

    async def primary():
        raise ProviderHTTPError(f"upstream failed {field_name}={credential}", 503)

    async def backup():
        return "ok"

    await run_provider_fallback(
        [ProviderCandidate("primary", primary), ProviderCandidate("backup", backup)],
        policy=ProviderRoutingPolicy(enabled=True),
        run_id="redaction-run",
        surface="cron",
        toolset="utility",
        events=events,
    )

    rendered = repr(events)
    assert credential not in rendered
    assert "[redacted]" in rendered
    assert events[0]["category"] == ProviderErrorCategory.TRANSIENT.value
    assert {"run_id", "surface", "toolset", "decision", "duration_ms"} <= set(events[0])
