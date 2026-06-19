"""Terminal backend contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional, Protocol


ProgressCallback = Callable[[dict], Awaitable[None]]


class TerminalBackendError(RuntimeError):
    """Raised when a backend refuses a requested operation."""


@dataclass(frozen=True)
class TerminalCommand:
    command: str | None = None
    argv: tuple[str, ...] | None = None
    cwd: str | None = None
    env: dict[str, str] | None = None
    timeout: float = 3600.0
    input_text: str | None = None
    progress_cb: Optional[ProgressCallback] = None
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class TerminalResult:
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    timed_out: bool = False
    backend: str = "host"

    def combined_output(self) -> str:
        output = self.stdout.rstrip()
        err = self.stderr.rstrip()
        if err:
            return (output + "\nSTDERR: " + err).strip() if output else "STDERR: " + err
        return output

    def to_trace(self) -> dict:
        return {
            "backend": self.backend,
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "stdout_bytes": len(self.stdout.encode("utf-8", errors="replace")),
            "stderr_bytes": len(self.stderr.encode("utf-8", errors="replace")),
        }


class TerminalBackend(Protocol):
    name: str

    async def run(self, command: TerminalCommand) -> TerminalResult:
        ...

    async def read_text(
        self,
        path: str,
        *,
        offset: int = 0,
        limit: int = 0,
        max_chars: int,
    ) -> str:
        ...

    async def write_text(self, path: str, content: str) -> str:
        ...

    async def patch_text(
        self,
        path: str,
        old: str,
        new: str,
        *,
        replace_all: bool = False,
    ) -> tuple[str, str | None, str]:
        ...
