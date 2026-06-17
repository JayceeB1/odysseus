"""Memory provider interfaces for native and external memory systems."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional


@dataclass
class MemoryRecord:
    """Provider-neutral memory entry."""

    id: str
    text: str
    timestamp: int = 0
    category: str = "fact"
    source: str = "unknown"
    owner: Optional[str] = None
    session_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MemorySearchHit:
    """A memory returned by provider recall."""

    memory: MemoryRecord
    provider_id: str
    score: Optional[float] = None


@dataclass(frozen=True)
class MemoryPrefetchRequest:
    """Provider-neutral request for turn-time memory retrieval."""

    query: str
    owner: Optional[str] = None
    session_id: Optional[str] = None
    top_k: int = 5
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryPrefetchResult:
    """Result of a provider prefetch attempt."""

    provider_id: str
    hits: List[MemorySearchHit] = field(default_factory=list)
    unavailable: bool = False
    error: Optional[str] = None


@dataclass(frozen=True)
class MemoryWriteProposal:
    """A pending durable-memory write."""

    provider_id: str
    text: str
    owner: Optional[str] = None
    session_id: Optional[str] = None
    category: str = "fact"
    source: str = "user"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MemoryWriteDecision:
    """Explicit approval or denial for a proposed durable-memory write."""

    approved: bool
    reason: str
    approved_by: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MemoryAuditEvent:
    """Auditable lifecycle event without storing memory text or credentials."""

    action: str
    provider_id: str
    outcome: str
    reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class MemoryWriteApprovalPolicy:
    """Fail-closed policy for durable-memory writes."""

    default_denial_reason = "durable memory write requires explicit approval"

    def decide(
        self,
        proposal: MemoryWriteProposal,
        decision: Optional[MemoryWriteDecision] = None,
    ) -> MemoryWriteDecision:
        if decision and decision.approved:
            return decision
        if decision:
            return decision
        return MemoryWriteDecision(
            approved=False,
            reason=self.default_denial_reason,
        )


class MemoryProvider(ABC):
    """Base contract for Odysseus memory providers.

    The native memory provider should always be available. External providers
    can add recall/write behavior and their own tools without replacing the
    built-in local memory baseline.
    """

    provider_id = "unknown"
    display_name = "Unknown"
    enabled = True
    read_only = False

    async def initialize(self) -> None:
        """Prepare provider resources before use."""

    async def shutdown(self) -> None:
        """Release provider resources."""

    @abstractmethod
    async def remember(
        self,
        text: str,
        *,
        owner: Optional[str] = None,
        session_id: Optional[str] = None,
        category: str = "fact",
        source: str = "user",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MemoryRecord:
        """Store a memory and return the stored record."""

    @abstractmethod
    async def recall(
        self,
        query: str,
        *,
        owner: Optional[str] = None,
        top_k: int = 5,
    ) -> List[MemorySearchHit]:
        """Return provider memories relevant to the query."""

    @abstractmethod
    async def list_memories(
        self,
        *,
        owner: Optional[str] = None,
        limit: int = 100,
    ) -> List[MemoryRecord]:
        """List memories visible to the owner."""

    @abstractmethod
    async def delete(self, memory_id: str, *, owner: Optional[str] = None) -> bool:
        """Delete a memory by ID when allowed by the provider."""

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Return provider-defined tool schemas when this provider is enabled."""
        return []

    async def handle_tool_call(self, name: str, arguments: Dict[str, Any]) -> Any:
        """Handle a provider-defined tool call."""
        raise KeyError(f"Provider {self.provider_id} does not expose tool {name}")

    async def search(self, request: MemoryPrefetchRequest) -> List[MemorySearchHit]:
        """Search this provider for turn-time memory context."""
        return await self.recall(
            request.query,
            owner=request.owner,
            top_k=request.top_k,
        )

    async def prefetch(self, request: MemoryPrefetchRequest) -> MemoryPrefetchResult:
        """Prefetch memory without allowing provider failures to leak text."""
        return MemoryPrefetchResult(
            provider_id=self.provider_id,
            hits=await self.search(request),
        )

    async def propose_write(
        self,
        text: str,
        *,
        owner: Optional[str] = None,
        session_id: Optional[str] = None,
        category: str = "fact",
        source: str = "user",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MemoryWriteProposal:
        """Create a durable-memory write proposal without committing it."""
        return MemoryWriteProposal(
            provider_id=self.provider_id,
            text=text,
            owner=owner,
            session_id=session_id,
            category=category,
            source=source,
            metadata=dict(metadata or {}),
        )

    async def commit_write(
        self,
        proposal: MemoryWriteProposal,
        decision: MemoryWriteDecision,
    ) -> MemoryRecord:
        """Commit an approved durable-memory write."""
        if self.read_only:
            raise PermissionError(f"Memory provider {self.provider_id} is read-only")
        if not decision.approved:
            raise PermissionError(decision.reason or "memory write was not approved")
        return await self.remember(
            proposal.text,
            owner=proposal.owner,
            session_id=proposal.session_id,
            category=proposal.category,
            source=proposal.source,
            metadata=proposal.metadata,
        )


class NativeMemoryProvider(MemoryProvider):
    """Provider adapter for Odysseus' built-in memory manager and vector store."""

    provider_id = "native"
    display_name = "Odysseus native memory"

    _CORE_FIELDS = {
        "id",
        "text",
        "timestamp",
        "source",
        "category",
        "uses",
        "owner",
        "session_id",
        "metadata",
    }

    def __init__(self, memory_manager, memory_vector=None):
        self.memory_manager = memory_manager
        self.memory_vector = memory_vector

    def _to_record(self, entry: Dict[str, Any]) -> MemoryRecord:
        metadata = {
            key: value
            for key, value in entry.items()
            if key not in self._CORE_FIELDS
        }
        stored_metadata = entry.get("metadata")
        if isinstance(stored_metadata, dict):
            metadata.update(stored_metadata)

        return MemoryRecord(
            id=entry.get("id", ""),
            text=entry.get("text", ""),
            timestamp=entry.get("timestamp", 0),
            category=entry.get("category", "fact"),
            source=entry.get("source", "unknown"),
            owner=entry.get("owner"),
            session_id=entry.get("session_id"),
            metadata=metadata,
        )

    async def remember(
        self,
        text: str,
        *,
        owner: Optional[str] = None,
        session_id: Optional[str] = None,
        category: str = "fact",
        source: str = "user",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MemoryRecord:
        entry = self.memory_manager.add_entry(
            text,
            source=source,
            category=category,
            owner=owner,
        )
        if session_id:
            entry["session_id"] = session_id
        if metadata:
            entry["metadata"] = dict(metadata)

        memories = self.memory_manager.load_all()
        memories.append(entry)
        self.memory_manager.save(memories)

        if self._vector_available():
            self.memory_vector.add(entry["id"], entry["text"])

        return self._to_record(entry)

    async def recall(
        self,
        query: str,
        *,
        owner: Optional[str] = None,
        top_k: int = 5,
    ) -> List[MemorySearchHit]:
        memories = self.memory_manager.load(owner=owner)
        by_id = {m.get("id"): m for m in memories}

        if self._vector_available():
            hits: List[MemorySearchHit] = []
            for result in self.memory_vector.search(query, k=top_k):
                if not isinstance(result, dict):
                    continue
                memory_id = result.get("memory_id")
                entry = by_id.get(memory_id) if memory_id else result
                if not entry:
                    continue
                if owner is not None and entry.get("owner") != owner:
                    continue
                hits.append(
                    MemorySearchHit(
                        memory=self._to_record(entry),
                        provider_id=self.provider_id,
                        score=result.get("score"),
                    )
                )
            if hits:
                return hits

        fallback = self.memory_manager.get_relevant_memories(
            query,
            memories,
            max_items=top_k,
        )
        return [
            MemorySearchHit(
                memory=self._to_record(entry),
                provider_id=self.provider_id,
                score=None,
            )
            for entry in fallback
        ]

    async def list_memories(
        self,
        *,
        owner: Optional[str] = None,
        limit: int = 100,
    ) -> List[MemoryRecord]:
        return [
            self._to_record(entry)
            for entry in self.memory_manager.load(owner=owner)[:limit]
        ]

    async def delete(self, memory_id: str, *, owner: Optional[str] = None) -> bool:
        memories = self.memory_manager.load_all()
        remaining = []
        deleted_id = None

        for entry in memories:
            if entry.get("id") != memory_id:
                remaining.append(entry)
                continue
            if owner is not None and entry.get("owner") != owner:
                remaining.append(entry)
                continue
            deleted_id = entry.get("id")

        if deleted_id is None:
            return False

        self.memory_manager.save(remaining)
        if self._vector_available():
            self.memory_vector.remove(deleted_id)
        return True

    def _vector_available(self) -> bool:
        return bool(self.memory_vector and getattr(self.memory_vector, "healthy", True))


class SessionSearchMemoryProvider(MemoryProvider):
    """Read-only provider that exposes session transcript search as memory."""

    provider_id = "session_search"
    display_name = "Session transcript search"
    read_only = True

    def __init__(
        self,
        search_func: Optional[Callable[..., Any]] = None,
        *,
        enabled: bool = True,
        include_archived: bool = False,
        context_messages: int = 1,
    ):
        if search_func is None:
            from src.session_search import search_session_messages

            search_func = search_session_messages
        self.search_func = search_func
        self.enabled = enabled
        self.include_archived = include_archived
        self.context_messages = context_messages

    async def remember(
        self,
        text: str,
        *,
        owner: Optional[str] = None,
        session_id: Optional[str] = None,
        category: str = "fact",
        source: str = "user",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MemoryRecord:
        raise PermissionError(f"Memory provider {self.provider_id} is read-only")

    async def recall(
        self,
        query: str,
        *,
        owner: Optional[str] = None,
        top_k: int = 5,
    ) -> List[MemorySearchHit]:
        results = self.search_func(
            query=query,
            limit=top_k,
            owner=owner,
            include_archived=self.include_archived,
            context_messages=self.context_messages,
        )
        hits: List[MemorySearchHit] = []
        for result in results:
            data = result.to_dict() if hasattr(result, "to_dict") else dict(result)
            message_id = str(data.get("message_id") or "")
            content = str(data.get("content_snippet") or data.get("content") or "")
            session_id = data.get("session_id")
            hits.append(
                MemorySearchHit(
                    memory=MemoryRecord(
                        id=message_id,
                        text=content,
                        category="session",
                        source=self.provider_id,
                        owner=owner,
                        session_id=str(session_id) if session_id is not None else None,
                        metadata={
                            "session_name": data.get("session_name"),
                            "role": data.get("role"),
                            "timestamp": data.get("timestamp"),
                            "context_before": data.get("context_before", []),
                            "context_after": data.get("context_after", []),
                        },
                    ),
                    provider_id=self.provider_id,
                    score=None,
                )
            )
        return hits

    async def list_memories(
        self,
        *,
        owner: Optional[str] = None,
        limit: int = 100,
    ) -> List[MemoryRecord]:
        return []

    async def delete(self, memory_id: str, *, owner: Optional[str] = None) -> bool:
        raise PermissionError(f"Memory provider {self.provider_id} is read-only")


class MemoryProviderRegistry:
    """Container for native and optional external memory providers."""

    def __init__(self, providers: Optional[Iterable[MemoryProvider]] = None):
        self._providers: Dict[str, MemoryProvider] = {}
        for provider in providers or []:
            self.register(provider)

    def register(self, provider: MemoryProvider) -> None:
        if provider.provider_id in self._providers:
            raise ValueError(f"Memory provider already registered: {provider.provider_id}")
        self._providers[provider.provider_id] = provider

    def get(self, provider_id: str) -> MemoryProvider:
        return self._providers[provider_id]

    def all(self) -> List[MemoryProvider]:
        return list(self._providers.values())

    def active(self) -> List[MemoryProvider]:
        return [provider for provider in self._providers.values() if provider.enabled]

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        schemas: List[Dict[str, Any]] = []
        seen: Dict[str, str] = {}

        for provider in self.active():
            for schema in provider.get_tool_schemas():
                name = self._tool_name(schema)
                if name in seen:
                    raise ValueError(
                        f"Memory tool name conflict: {name} from "
                        f"{provider.provider_id} already exposed by {seen[name]}"
                    )
                seen[name] = provider.provider_id
                schemas.append(schema)

        return schemas

    async def handle_tool_call(self, name: str, arguments: Dict[str, Any]) -> Any:
        provider_by_tool: Dict[str, MemoryProvider] = {}
        for provider in self.active():
            for schema in provider.get_tool_schemas():
                tool_name = self._tool_name(schema)
                if tool_name in provider_by_tool:
                    raise ValueError(
                        f"Memory tool name conflict: {tool_name} from "
                        f"{provider.provider_id} already exposed by "
                        f"{provider_by_tool[tool_name].provider_id}"
                    )
                provider_by_tool[tool_name] = provider

        provider = provider_by_tool.get(name)
        if provider:
            return await provider.handle_tool_call(name, arguments)
        raise KeyError(f"No active memory provider exposes tool {name}")

    @staticmethod
    def _tool_name(schema: Dict[str, Any]) -> str:
        if not isinstance(schema, dict):
            raise ValueError("Memory provider tool schema must be a dict")
        name = schema.get("name")
        if isinstance(name, str) and name:
            return name
        function = schema.get("function")
        if isinstance(function, dict):
            function_name = function.get("name")
            if isinstance(function_name, str) and function_name:
                return function_name
        raise ValueError("Memory provider tool schema is missing a tool name")


class MemoryLifecycleManager:
    """Coordinates lifecycle memory providers for a single turn."""

    def __init__(
        self,
        registry: MemoryProviderRegistry,
        *,
        write_policy: Optional[MemoryWriteApprovalPolicy] = None,
        audit_sink: Optional[Callable[[MemoryAuditEvent], None]] = None,
    ):
        self.registry = registry
        self.write_policy = write_policy or MemoryWriteApprovalPolicy()
        self.audit_sink = audit_sink

    async def prefetch(
        self,
        query: str,
        *,
        owner: Optional[str] = None,
        session_id: Optional[str] = None,
        top_k: int = 5,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[MemoryPrefetchResult]:
        request = MemoryPrefetchRequest(
            query=query,
            owner=owner,
            session_id=session_id,
            top_k=top_k,
            metadata=dict(metadata or {}),
        )
        results: List[MemoryPrefetchResult] = []
        for provider in self.registry.active():
            try:
                result = await provider.prefetch(request)
                results.append(self._mark_untrusted(result))
                self._audit(
                    "prefetch",
                    provider.provider_id,
                    "ok",
                    metadata={"hit_count": len(result.hits)},
                )
            except Exception as exc:
                results.append(
                    MemoryPrefetchResult(
                        provider_id=provider.provider_id,
                        unavailable=True,
                        error=type(exc).__name__,
                    )
                )
                self._audit(
                    "prefetch",
                    provider.provider_id,
                    "unavailable",
                    reason=type(exc).__name__,
                )
        return results

    async def prefetch_context(self, *args: Any, **kwargs: Any) -> List[Dict[str, Any]]:
        """Return context entries explicitly marked as untrusted model input."""
        results = await self.prefetch(*args, **kwargs)
        context: List[Dict[str, Any]] = []
        for result in results:
            if result.unavailable:
                continue
            for hit in result.hits:
                context.append(
                    {
                        "memory_id": hit.memory.id,
                        "provider_id": hit.provider_id,
                        "text": hit.memory.text,
                        "score": hit.score,
                        "trusted": False,
                        "source": "memory_provider",
                    }
                )
        return context

    async def propose_write(
        self,
        provider_id: str,
        text: str,
        **kwargs: Any,
    ) -> MemoryWriteProposal:
        provider = self.registry.get(provider_id)
        proposal = await provider.propose_write(text, **kwargs)
        self._audit(
            "propose_write",
            proposal.provider_id,
            "ok",
            metadata={
                "category": proposal.category,
                "source": proposal.source,
                "text_length": len(proposal.text),
            },
        )
        return proposal

    async def commit_write(
        self,
        proposal: MemoryWriteProposal,
        decision: Optional[MemoryWriteDecision] = None,
    ) -> MemoryRecord:
        provider = self.registry.get(proposal.provider_id)
        if provider.read_only:
            self._audit("commit_write", provider.provider_id, "denied", reason="read_only")
            raise PermissionError(f"Memory provider {provider.provider_id} is read-only")

        final_decision = self.write_policy.decide(proposal, decision)
        if not final_decision.approved:
            self._audit(
                "commit_write",
                provider.provider_id,
                "denied",
                reason=final_decision.reason,
            )
            raise PermissionError(final_decision.reason)

        record = await provider.commit_write(proposal, final_decision)
        self._audit(
            "commit_write",
            provider.provider_id,
            "committed",
            metadata={
                "memory_id": record.id,
                "category": record.category,
                "source": record.source,
            },
        )
        return record

    def _mark_untrusted(self, result: MemoryPrefetchResult) -> MemoryPrefetchResult:
        marked_hits: List[MemorySearchHit] = []
        for hit in result.hits:
            metadata = dict(hit.memory.metadata)
            metadata["trusted"] = False
            metadata["provider_id"] = hit.provider_id
            marked_hits.append(
                MemorySearchHit(
                    memory=MemoryRecord(
                        id=hit.memory.id,
                        text=hit.memory.text,
                        timestamp=hit.memory.timestamp,
                        category=hit.memory.category,
                        source=hit.memory.source,
                        owner=hit.memory.owner,
                        session_id=hit.memory.session_id,
                        metadata=metadata,
                    ),
                    provider_id=hit.provider_id,
                    score=hit.score,
                )
            )
        return MemoryPrefetchResult(
            provider_id=result.provider_id,
            hits=marked_hits,
            unavailable=result.unavailable,
            error=result.error,
        )

    def _audit(
        self,
        action: str,
        provider_id: str,
        outcome: str,
        *,
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self.audit_sink:
            return
        self.audit_sink(
            MemoryAuditEvent(
                action=action,
                provider_id=provider_id,
                outcome=outcome,
                reason=reason,
                metadata=dict(metadata or {}),
            )
        )
