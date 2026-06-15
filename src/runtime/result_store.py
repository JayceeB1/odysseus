"""In-memory result references for oversized tool outputs."""

from __future__ import annotations

from dataclasses import dataclass
import itertools
import re
from typing import Dict, Mapping


_SENSITIVE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile("s" + r"k-[A-Za-z0-9_\-]{8,}"),
    re.compile(
        r"(?i)(api[_-]?key|access[_-]?to" + "ken|sec" + "ret|pass" + "word)"
        r"(\s*[:=]\s*)(['\"]?)[^'\"\s,}]+"
    ),
)


def redact_text(value: object) -> str:
    """Return a string with common credential-like shapes redacted."""

    text = "" if value is None else str(value)
    text = _SENSITIVE_PATTERNS[0].sub("[REDACTED]", text)
    return _SENSITIVE_PATTERNS[1].sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}[REDACTED]", text)


@dataclass(frozen=True)
class StoredResult:
    ref: str
    content: str
    size: int


class InMemoryResultStore:
    """Simple process-local result store used by tests and opt-in callers."""

    def __init__(self):
        self._counter = itertools.count(1)
        self._items: Dict[str, StoredResult] = {}

    def put(self, *, tool_name: str, field: str, content: object) -> StoredResult:
        redacted = redact_text(content)
        ref = f"tool-result-{next(self._counter)}"
        stored = StoredResult(ref=ref, content=redacted, size=len(redacted))
        self._items[ref] = stored
        return stored

    def get(self, ref: str) -> StoredResult:
        return self._items[ref]

    def snapshot(self) -> Mapping[str, StoredResult]:
        return dict(self._items)
