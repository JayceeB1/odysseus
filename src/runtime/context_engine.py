"""ContextEngine adapter for assembling one agent turn."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Protocol, Sequence

from src.prompt_security import untrusted_context_message
from src.runtime.turn_context import TurnContext, UntrustedContextBlock

logger = logging.getLogger(__name__)


class ContextProvider(Protocol):
    """Optional provider that returns untrusted context blocks for a turn."""

    def build(self, turn: TurnContext) -> Sequence[UntrustedContextBlock]:
        ...


PromptBuilder = Callable[..., tuple[list[dict[str, Any]], list[Any]]]


@dataclass(frozen=True)
class ProviderError:
    """Redacted provider failure summary for diagnostics."""

    provider: str
    error_type: str


@dataclass(frozen=True)
class ContextBuildResult:
    """Result of context preparation for one model turn."""

    messages: list[dict[str, Any]]
    mcp_schemas: list[Any]
    untrusted_block_count: int = 0
    provider_errors: tuple[ProviderError, ...] = ()


class ContextEngine:
    """Small adapter around the existing prompt builder.

    The adapter preserves current ``agent_loop`` behavior when no providers are
    configured, while giving future providers a single safe insertion point for
    retrieved context.
    """

    def __init__(
        self,
        prompt_builder: PromptBuilder,
        providers: Iterable[ContextProvider | Callable[[TurnContext], Sequence[UntrustedContextBlock]]] = (),
        *,
        log: logging.Logger | None = None,
    ) -> None:
        self._prompt_builder = prompt_builder
        self._providers = tuple(providers)
        self._logger = log or logger

    def build_turn(
        self,
        turn: TurnContext,
        *,
        model: str,
        active_document: Any,
        mcp_mgr: Any,
        disabled_tools: set[str] | None = None,
        needs_admin: bool = False,
        relevant_tools: set[str] | None = None,
        mcp_disabled_map: dict[str, set] | None = None,
        compact: bool = False,
        suppress_local_context: bool = False,
        active_email: Any = None,
    ) -> ContextBuildResult:
        """Build prompt messages and optional tool schemas for one turn."""
        messages, mcp_schemas = self._prompt_builder(
            turn.copy_messages(),
            model,
            active_document,
            mcp_mgr,
            disabled_tools,
            needs_admin=needs_admin,
            relevant_tools=relevant_tools,
            mcp_disabled_map=mcp_disabled_map,
            compact=compact,
            owner=turn.user,
            suppress_local_context=suppress_local_context,
            active_email=active_email,
        )

        blocks = list(turn.untrusted_blocks)
        provider_errors: list[ProviderError] = []
        for provider in self._providers:
            try:
                blocks.extend(self._provider_blocks(provider, turn))
            except Exception as exc:
                provider_name = provider.__class__.__name__
                provider_errors.append(ProviderError(provider_name, exc.__class__.__name__))
                self._logger.debug("context provider %s failed: %s", provider_name, exc.__class__.__name__)

        if blocks:
            messages = self._insert_untrusted_blocks(messages, blocks)

        return ContextBuildResult(
            messages=messages,
            mcp_schemas=list(mcp_schemas or []),
            untrusted_block_count=len(blocks),
            provider_errors=tuple(provider_errors),
        )

    @staticmethod
    def _provider_blocks(
        provider: ContextProvider | Callable[[TurnContext], Sequence[UntrustedContextBlock]],
        turn: TurnContext,
    ) -> Sequence[UntrustedContextBlock]:
        if hasattr(provider, "build"):
            return provider.build(turn) or ()
        return provider(turn) or ()

    @staticmethod
    def _insert_untrusted_blocks(
        messages: Sequence[dict[str, Any]],
        blocks: Sequence[UntrustedContextBlock],
    ) -> list[dict[str, Any]]:
        out = [dict(message) for message in messages]
        insert_idx = len(out)
        for index in range(len(out) - 1, -1, -1):
            if out[index].get("role") == "user":
                insert_idx = index
                break

        for block in blocks:
            out.insert(insert_idx, untrusted_context_message(block.label, block.content))
            insert_idx += 1
        return out


@dataclass(frozen=True)
class SessionSearchContextProvider:
    """Optional session-search provider for ContextEngine.

    It is intentionally not wired into the default agent loop yet. Callers must
    pass it explicitly when they want prior-session snippets included.
    """

    search: Callable[..., Sequence[Any]] | None = None
    limit: int = 3
    context_messages: int = 1
    label: str = "session search results"

    def build(self, turn: TurnContext) -> Sequence[UntrustedContextBlock]:
        query = turn.last_user_text()
        if not query:
            return ()

        search = self.search or self._default_search
        results = search(
            query,
            limit=self.limit,
            owner=turn.user,
            include_archived=False,
            context_messages=self.context_messages,
        )
        if not results:
            return ()
        return (UntrustedContextBlock(self.label, self._format_results(results)),)

    @staticmethod
    def _default_search(*args, **kwargs):
        from src.session_search import search_session_messages

        return search_session_messages(*args, **kwargs)

    @classmethod
    def _format_results(cls, results: Sequence[Any]) -> str:
        lines = ["Relevant prior-session snippets:"]
        for index, result in enumerate(results, 1):
            session_name = cls._value(result, "session_name", "Untitled")
            session_id = cls._value(result, "session_id", "")
            role = cls._value(result, "role", "")
            snippet = cls._value(result, "content_snippet", "")
            timestamp = cls._value(result, "timestamp", "")
            lines.extend([
                f"",
                f"Result {index}:",
                f"Session: {session_name} ({session_id})",
                f"Role: {role}",
                f"Timestamp: {timestamp}",
                f"Snippet: {snippet}",
            ])
            for label, items in (
                ("Before", cls._value(result, "context_before", [])),
                ("After", cls._value(result, "context_after", [])),
            ):
                for item in items or []:
                    item_role = cls._value(item, "role", "")
                    item_content = cls._value(item, "content", "")
                    lines.append(f"{label} ({item_role}): {item_content}")
        return "\n".join(lines)

    @staticmethod
    def _value(result: Any, name: str, default: Any = "") -> Any:
        if isinstance(result, dict):
            return result.get(name, default)
        return getattr(result, name, default)
