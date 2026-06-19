"""Browser automation policy and provider contracts."""

from src.browser_automation.policy import (
    BrowserAutomationError,
    BrowserAutomationPolicy,
    BrowserAutomationRequest,
)
from src.browser_automation.provider import BrowserAutomationProvider, BrowserObservation

__all__ = [
    "BrowserAutomationError",
    "BrowserAutomationPolicy",
    "BrowserAutomationProvider",
    "BrowserAutomationRequest",
    "BrowserObservation",
]
