"""Tests for memory provider lifecycle prefetch and write approval."""

import asyncio


def run(coro):
    return asyncio.run(coro)


def test_read_only_session_provider_cannot_write():
    from src.memory_provider import SessionSearchMemoryProvider

    provider = SessionSearchMemoryProvider(search_func=lambda **kwargs: [])
    proposal = run(provider.propose_write("remember this"))

    try:
        run(provider.commit_write(proposal, decision=None))
    except PermissionError as exc:
        assert "read-only" in str(exc)
    else:
        raise AssertionError("Expected session search provider to reject writes")


def test_durable_memory_write_requires_explicit_approval(tmp_path):
    from src.memory import MemoryManager
    from src.memory_provider import (
        MemoryLifecycleManager,
        MemoryProviderRegistry,
        MemoryWriteDecision,
        NativeMemoryProvider,
    )

    manager = MemoryManager(str(tmp_path))
    events = []
    provider = NativeMemoryProvider(manager)
    lifecycle = MemoryLifecycleManager(
        MemoryProviderRegistry([provider]),
        audit_sink=events.append,
    )

    proposal = run(
        lifecycle.propose_write(
            "native",
            "User prefers short answers",
            owner="alice",
        )
    )

    try:
        run(lifecycle.commit_write(proposal))
    except PermissionError as exc:
        assert "explicit approval" in str(exc)
    else:
        raise AssertionError("Expected unapproved memory write to be rejected")

    assert manager.load(owner="alice") == []
    record = run(
        lifecycle.commit_write(
            proposal,
            MemoryWriteDecision(
                approved=True,
                reason="user confirmed",
                approved_by="alice",
            ),
        )
    )

    assert record.text == "User prefers short answers"
    assert manager.load(owner="alice")[0]["id"] == record.id
    assert [(event.action, event.outcome) for event in events] == [
        ("propose_write", "ok"),
        ("commit_write", "denied"),
        ("commit_write", "committed"),
    ]
    assert all("User prefers short answers" not in str(event) for event in events)


def test_prefetched_memory_context_is_marked_untrusted(tmp_path):
    from src.memory import MemoryManager
    from src.memory_provider import (
        MemoryLifecycleManager,
        MemoryProviderRegistry,
        NativeMemoryProvider,
    )

    manager = MemoryManager(str(tmp_path))
    provider = NativeMemoryProvider(manager)
    run(provider.remember("Alice likes green tea", owner="alice"))
    lifecycle = MemoryLifecycleManager(MemoryProviderRegistry([provider]))

    results = run(lifecycle.prefetch("green tea", owner="alice"))
    context = run(lifecycle.prefetch_context("green tea", owner="alice"))

    assert results[0].hits[0].memory.metadata["trusted"] is False
    assert results[0].hits[0].memory.metadata["provider_id"] == "native"
    assert context == [
        {
            "memory_id": results[0].hits[0].memory.id,
            "provider_id": "native",
            "text": "Alice likes green tea",
            "score": None,
            "trusted": False,
            "source": "memory_provider",
        }
    ]


def test_unavailable_provider_does_not_break_prefetch():
    from src.memory_provider import MemoryLifecycleManager, MemoryProvider, MemoryProviderRegistry

    class BrokenProvider(MemoryProvider):
        provider_id = "broken"

        async def remember(self, text, **kwargs):
            raise AssertionError("not used")

        async def recall(self, query, **kwargs):
            raise RuntimeError("backend down")

        async def list_memories(self, **kwargs):
            return []

        async def delete(self, memory_id, **kwargs):
            return False

    events = []
    lifecycle = MemoryLifecycleManager(
        MemoryProviderRegistry([BrokenProvider()]),
        audit_sink=events.append,
    )

    results = run(lifecycle.prefetch("anything", owner="alice"))

    assert len(results) == 1
    assert results[0].provider_id == "broken"
    assert results[0].unavailable is True
    assert results[0].error == "RuntimeError"
    assert events[0].action == "prefetch"
    assert events[0].outcome == "unavailable"


def test_session_search_provider_maps_transcripts_to_memory_hits():
    from src.memory_provider import SessionSearchMemoryProvider

    captured = {}

    def fake_search(**kwargs):
        captured.update(kwargs)
        return [
            {
                "message_id": "msg-1",
                "session_id": "session-1",
                "session_name": "Planning",
                "role": "assistant",
                "content_snippet": "Relevant transcript snippet",
                "timestamp": "2026-01-01T00:00:00",
                "context_before": [],
                "context_after": [],
            }
        ]

    provider = SessionSearchMemoryProvider(search_func=fake_search, context_messages=2)

    hits = run(provider.recall("transcript", owner="alice", top_k=3))

    assert captured["query"] == "transcript"
    assert captured["limit"] == 3
    assert captured["owner"] == "alice"
    assert captured["context_messages"] == 2
    assert hits[0].provider_id == "session_search"
    assert hits[0].memory.id == "msg-1"
    assert hits[0].memory.text == "Relevant transcript snippet"
    assert hits[0].memory.category == "session"
    assert hits[0].memory.metadata["session_name"] == "Planning"
