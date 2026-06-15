"""Structured run events for tool execution facades."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class RunEvent:
    type: str
    tool: str
    timestamp: float
    detail: Optional[str] = None
    run_id: Optional[str] = None
    surface: Optional[str] = None
    toolset: Optional[str] = None
    decision: Optional[str] = None
    duration_ms: Optional[float] = None

    @classmethod
    def now(
        cls,
        event_type: str,
        tool: str,
        detail: Optional[str] = None,
        **metadata: Any,
    ) -> "RunEvent":
        return cls(type=event_type, tool=tool, timestamp=time.time(), detail=detail, **metadata)

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "type": self.type,
            "tool": self.tool,
            "timestamp": self.timestamp,
        }
        if self.detail:
            data["detail"] = self.detail
        if self.run_id:
            data["run_id"] = self.run_id
        if self.surface:
            data["surface"] = self.surface
        if self.toolset:
            data["toolset"] = self.toolset
        if self.decision:
            data["decision"] = self.decision
        if self.duration_ms is not None:
            data["duration_ms"] = self.duration_ms
        return data
