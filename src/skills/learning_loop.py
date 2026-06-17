"""Learning-loop proposal objects for skills."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Mapping


_SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[^'\"\s,;]+"
)


@dataclass(frozen=True)
class SkillUpdateProposal:
    target_skill: str
    summary: str
    evidence: tuple[str, ...]
    proposed_markdown: str
    requires_approval: bool = True
    committed: bool = False


def propose_skill_update(
    *,
    target_skill: str,
    run_trace: Iterable[Mapping[str, object] | str],
    summary: str,
) -> SkillUpdateProposal:
    """Create an approval-gated skill update proposal without writing files."""

    target = (target_skill or "").strip()
    if not target:
        raise ValueError("target_skill is required")
    clean_summary = _redact(summary or "").strip()
    evidence = tuple(_trace_lines(run_trace))
    body = "\n".join(
        [
            f"# Proposed update for {target}",
            "",
            clean_summary or "No summary provided.",
            "",
            "## Evidence",
            *(f"- {item}" for item in evidence),
        ]
    )
    return SkillUpdateProposal(
        target_skill=target,
        summary=clean_summary,
        evidence=evidence,
        proposed_markdown=body,
    )


def _trace_lines(run_trace: Iterable[Mapping[str, object] | str]) -> Iterable[str]:
    for raw in run_trace:
        if isinstance(raw, Mapping):
            kind = str(raw.get("type") or raw.get("event") or "trace")
            text = str(raw.get("text") or raw.get("message") or raw.get("content") or "")
            yield f"{kind}: {_redact(text)[:300]}"
            continue
        yield _redact(str(raw))[:300]


def _redact(value: str) -> str:
    return _SECRET_RE.sub(lambda match: match.group(1) + "=<redacted>", str(value))
