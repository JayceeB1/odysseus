"""Read-only browser automation provider contract."""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.browser_automation.policy import BrowserAutomationPolicy, BrowserAutomationRequest
from src.prompt_security import untrusted_browser_context_message


@dataclass(frozen=True)
class BrowserObservation:
    url: str
    title: str
    text: str

    def to_trace(self) -> dict:
        return {
            "url": self.url,
            "title": self.title,
            "text_chars": len(self.text),
        }

    def to_untrusted_message(self) -> dict:
        return untrusted_browser_context_message(
            self.url,
            f"Title: {self.title}\n\n{self.text}",
        )


class BrowserAutomationProvider:
    """Policy-first provider shell.

    The provider accepts caller-supplied HTML/text for deterministic tests and
    future adapters. It does not perform network/browser IO in this PR.
    """

    def __init__(self, policy: BrowserAutomationPolicy | None = None) -> None:
        self.policy = policy or BrowserAutomationPolicy()

    async def read(self, url: str, *, html: str = "") -> BrowserObservation:
        self.policy.check(BrowserAutomationRequest(url=url, action="read", read_only=True))
        title = _extract_title(html) or url
        text = _html_to_text(html)
        return BrowserObservation(url=url, title=title, text=text)


def _extract_title(html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html or "", re.I | re.S)
    if not match:
        return ""
    return _collapse_ws(_strip_tags(match.group(1)))


def _html_to_text(html: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html or "", flags=re.I | re.S)
    text = _strip_tags(text)
    return _collapse_ws(text)


def _strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value or "")


def _collapse_ws(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()
