"""Turn-scoped context objects for agent runtime preparation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import AbstractSet, Any, Mapping, Optional, Sequence

from src.runtime.context_budget import ContextBudget


@dataclass(frozen=True)
class UntrustedContextBlock:
    """Source text that must be shipped to the model as data, not instruction."""

    label: str
    content: Any


@dataclass(frozen=True)
class TurnContext:
    """Stable input contract for preparing one agent turn."""

    messages: Sequence[Mapping[str, Any]]
    user: Optional[str] = None
    session_id: Optional[str] = None
    surface: str = "agent"
    toolset: Optional[AbstractSet[str]] = None
    budget: ContextBudget = field(default_factory=ContextBudget)
    untrusted_blocks: Sequence[UntrustedContextBlock] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def copy_messages(self) -> list[dict[str, Any]]:
        """Return mutable message copies for prompt builders."""
        return [dict(message) for message in self.messages]

    def last_user_text(self) -> str:
        """Return the latest human/user text, flattening text blocks."""
        for message in reversed(self.messages):
            if message.get("role") != "user":
                continue
            content = message.get("content", "")
            if isinstance(content, list):
                return " ".join(
                    str(block.get("text", ""))
                    for block in content
                    if isinstance(block, dict) and block.get("type", "text") == "text"
                ).strip()
            return str(content or "").strip()
        return ""
