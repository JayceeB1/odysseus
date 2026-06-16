"""Opt-in provider recovery policy."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Set

from .error_classifier import ProviderErrorCategory, ProviderErrorInfo


class ProviderRecoveryAction(str, Enum):
    ABORT = "abort"
    RETRY = "retry"
    FALLBACK = "fallback"
    COMPRESS = "compress"
    DENY = "deny"


@dataclass(frozen=True)
class ProviderRecoveryDecision:
    action: ProviderRecoveryAction
    reason: str


@dataclass(frozen=True)
class ProviderRoutingPolicy:
    """Explicit recovery policy.

    Disabled policies preserve the legacy behavior: no retry, no fallback and no
    new exception wrapping.
    """

    enabled: bool = False
    allowed_surfaces: Set[str] = field(default_factory=lambda: {"web", "api", "cron", "gateway", "admin"})
    retry_categories: Set[ProviderErrorCategory] = field(
        default_factory=lambda: {ProviderErrorCategory.RATE_LIMIT, ProviderErrorCategory.TRANSIENT}
    )
    fallback_categories: Set[ProviderErrorCategory] = field(
        default_factory=lambda: {ProviderErrorCategory.RATE_LIMIT, ProviderErrorCategory.TRANSIENT}
    )
    compress_categories: Set[ProviderErrorCategory] = field(
        default_factory=lambda: {ProviderErrorCategory.CONTEXT}
    )
    max_attempts_per_provider: int = 1
    max_fallbacks: int = 1
    compression_available: bool = False

    def decide(
        self,
        info: ProviderErrorInfo,
        *,
        surface: str,
        fallback_index: int,
        has_next_provider: bool,
        attempt: int = 1,
    ) -> ProviderRecoveryDecision:
        if not self.enabled:
            return ProviderRecoveryDecision(ProviderRecoveryAction.ABORT, "provider recovery disabled")
        if surface not in self.allowed_surfaces:
            return ProviderRecoveryDecision(ProviderRecoveryAction.DENY, "surface is not allowed to recover providers")
        if info.category in self.compress_categories and self.compression_available:
            return ProviderRecoveryDecision(ProviderRecoveryAction.COMPRESS, "context compression required")
        if attempt < self.max_attempts_per_provider and info.category in self.retry_categories:
            return ProviderRecoveryDecision(ProviderRecoveryAction.RETRY, "retry allowed by category")
        if (
            has_next_provider
            and fallback_index < self.max_fallbacks
            and info.category in self.fallback_categories
        ):
            return ProviderRecoveryDecision(ProviderRecoveryAction.FALLBACK, "fallback allowed by category")
        return ProviderRecoveryDecision(ProviderRecoveryAction.ABORT, "category is not recoverable")

    @classmethod
    def for_surfaces(cls, surfaces: Iterable[str], **kwargs) -> "ProviderRoutingPolicy":
        return cls(allowed_surfaces=set(surfaces), **kwargs)
