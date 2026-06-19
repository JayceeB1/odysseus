"""Fail-closed policy for browser automation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urlparse

from src.url_safety import check_outbound_url


READ_ONLY_ACTIONS = frozenset({"read", "screenshot", "extract"})
MUTATING_ACTIONS = frozenset({"click", "type", "submit"})


class BrowserAutomationError(ValueError):
    """Raised when browser automation is not allowed."""


@dataclass(frozen=True)
class BrowserAutomationRequest:
    url: str
    action: str = "read"
    read_only: bool = True
    approved: bool = False


@dataclass(frozen=True)
class BrowserAutomationPolicy:
    allowed_domains: tuple[str, ...] = ()
    allow_downloads: bool = False
    block_private: bool = True
    resolver: Callable[[str], list[str]] | None = None
    approved_actions: frozenset[str] = field(default_factory=frozenset)

    def check(self, request: BrowserAutomationRequest) -> None:
        action = (request.action or "read").strip().lower()
        if action == "download" and not self.allow_downloads:
            raise BrowserAutomationError("browser-downloads-disabled")
        if action in MUTATING_ACTIONS:
            if request.read_only or not request.approved or action not in self.approved_actions:
                raise BrowserAutomationError("browser-action-requires-approval")
        elif action not in READ_ONLY_ACTIONS and action != "download":
            raise BrowserAutomationError(f"browser-action-unknown:{action}")

        ok, reason = check_outbound_url(
            request.url,
            block_private=self.block_private,
            resolver=self.resolver,
        )
        if not ok:
            raise BrowserAutomationError(f"browser-url-blocked:{reason}")

        if self.allowed_domains:
            host = (urlparse(request.url).hostname or "").lower()
            allowed = any(
                host == domain.lower().lstrip(".")
                or host.endswith("." + domain.lower().lstrip("."))
                for domain in self.allowed_domains
            )
            if not allowed:
                raise BrowserAutomationError("browser-domain-not-allowed")

    def to_trace(self) -> dict:
        return {
            "allowed_domains": list(self.allowed_domains),
            "allow_downloads": self.allow_downloads,
            "block_private": self.block_private,
            "approved_actions": sorted(self.approved_actions),
        }
