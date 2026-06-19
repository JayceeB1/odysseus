"""Experimental Docker terminal backend policy shell.

The backend is intentionally fail-closed unless explicitly enabled by a caller.
It does not start containers in this PR; it records the policy boundary needed
before a real Docker implementation can safely mount paths.
"""

from __future__ import annotations

from src.terminal_backends.base import TerminalBackendError, TerminalCommand, TerminalResult
from src.terminal_backends.policy import path_is_under_any


class DockerBackend:
    name = "docker"

    def __init__(self, *, enabled: bool = False, allowed_mounts: tuple[str, ...] = ()) -> None:
        self.enabled = enabled
        self.allowed_mounts = tuple(allowed_mounts)

    async def run(self, command: TerminalCommand) -> TerminalResult:
        if not self.enabled:
            raise TerminalBackendError("docker-backend-disabled")
        if command.cwd and not path_is_under_any(command.cwd, self.allowed_mounts):
            raise TerminalBackendError("docker-backend-path-not-mounted")
        raise TerminalBackendError("docker-backend-experimental")

    async def read_text(self, path: str, **_kwargs) -> str:
        raise TerminalBackendError("docker-backend-file-io-disabled")

    async def write_text(self, path: str, content: str) -> str:
        raise TerminalBackendError("docker-backend-file-io-disabled")

    async def patch_text(self, path: str, old: str, new: str, *, replace_all: bool = False):
        raise TerminalBackendError("docker-backend-file-io-disabled")
