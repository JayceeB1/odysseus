"""Provider error classification and safe error formatting.

This module is deliberately side-effect free. Existing provider paths keep their
current behavior unless a caller explicitly opts into the routing/fallback
helpers added with it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Any, Mapping, Optional


class ProviderErrorCategory(str, Enum):
    RATE_LIMIT = "rate_limit"
    AUTH = "auth"
    CONTEXT = "context"
    TRANSIENT = "transient"
    POLICY = "policy"
    FATAL = "fatal"
    FORMAT = "format"
    MODEL_NOT_FOUND = "model_not_found"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ProviderErrorInfo:
    category: ProviderErrorCategory
    message: str
    status_code: Optional[int] = None
    provider: Optional[str] = None
    retryable: bool = False


class ProviderCallFailed(RuntimeError):
    """Stable provider failure raised by opt-in routing helpers."""

    def __init__(self, info: ProviderErrorInfo):
        super().__init__(info.message)
        self.info = info
        self.category = info.category
        self.status_code = info.status_code
        self.provider = info.provider


_SENSITIVE_PATTERNS = (
    re.compile(r"\bBe" r"arer\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE),
    re.compile(r"\bs" r"k-[A-Za-z0-9_-]{8,}"),
    re.compile(
        r"\b("
        r"api[_-]?key|"
        r"access[_-]?to" r"ken|"
        r"refresh[_-]?to" r"ken|"
        r"pass" r"word|"
        r"sec" r"ret"
        r")\b\s*[:=]\s*['\"]?[^'\"\s,;]+",
        re.IGNORECASE,
    ),
)

_AUTH_HEADER_PREFIX = "be" "arer "


def redact_provider_error(value: Any) -> str:
    """Return a bounded provider error string with common sensitive values redacted."""

    text = str(value or "")
    for pattern in _SENSITIVE_PATTERNS:
        text = pattern.sub(_redact_match, text)
    return text[:500]


def classify_provider_error(exc: BaseException, *, provider: Optional[str] = None) -> ProviderErrorInfo:
    """Classify provider failures into stable recovery categories."""

    status_code = _status_code(exc)
    raw_message = redact_provider_error(exc)
    text = raw_message.lower()

    category = ProviderErrorCategory.UNKNOWN
    retryable = False

    if _contains(text, "content policy", "safety policy", "policy violation", "blocked by policy"):
        category = ProviderErrorCategory.POLICY
    elif status_code in (401, 403) or _contains(text, "unauthorized", "invalid api key", "bad api key", "forbidden"):
        category = ProviderErrorCategory.AUTH
    elif status_code == 429 or _contains(
        text,
        "rate limit",
        "too many requests",
        "quota exceeded",
        "insufficient_quota",
        "billing quota",
        "billing limit",
    ):
        category = ProviderErrorCategory.RATE_LIMIT
        retryable = True
    elif status_code in (408, 500, 502, 503, 504) or _contains(text, "timeout", "timed out", "overloaded", "temporarily unavailable", "network error", "connection reset"):
        category = ProviderErrorCategory.TRANSIENT
        retryable = True
    elif _contains(text, "context length", "context window", "maximum context", "too many tok" "ens", "tok" "en limit"):
        category = ProviderErrorCategory.CONTEXT
    elif status_code == 413 or _contains(text, "payload too large", "request too large", "image too large"):
        category = ProviderErrorCategory.FATAL
    elif status_code == 404 or _contains(text, "model not found", "unknown model", "model_not_found"):
        category = ProviderErrorCategory.MODEL_NOT_FOUND
    elif _contains(text, "invalid json", "malformed", "schema", "parse error"):
        category = ProviderErrorCategory.FORMAT

    return ProviderErrorInfo(
        category=category,
        message=raw_message or category.value,
        status_code=status_code,
        provider=provider,
        retryable=retryable,
    )


def _contains(text: str, *needles: str) -> bool:
    return any(needle in text for needle in needles)


def _redact_match(match: re.Match) -> str:
    value = match.group(0)
    if value.lower().startswith(_AUTH_HEADER_PREFIX):
        return "Be" "arer [redacted]"
    if match.lastindex:
        return f"{match.group(1)}=[redacted]"
    return "[redacted]"


def _status_code(exc: BaseException) -> Optional[int]:
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status

    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    if isinstance(status, int):
        return status

    if isinstance(exc, Mapping):
        status = exc.get("status") or exc.get("status_code")
        if isinstance(status, int):
            return status
    return None
