"""Terminal backend registry."""

from __future__ import annotations

from src.terminal_backends.base import TerminalBackendError, TerminalCommand, TerminalResult
from src.terminal_backends.docker import DockerBackend
from src.terminal_backends.host import HostBackend
from src.terminal_backends.policy import filter_subprocess_env


def resolve_terminal_backend(name: str | None = None):
    backend = (name or "host").strip().lower()
    if backend in {"", "host"}:
        return HostBackend()
    if backend == "docker":
        return DockerBackend(enabled=False)
    raise TerminalBackendError(f"unknown-terminal-backend:{backend}")


def backend_from_context(ctx: dict | None):
    ctx = ctx or {}
    backend = ctx.get("terminal_backend")
    if backend is not None and any(
        hasattr(backend, attr)
        for attr in ("run", "read_text", "write_text", "patch_text")
    ):
        return backend
    return resolve_terminal_backend(ctx.get("terminal_backend_name"))


__all__ = [
    "DockerBackend",
    "HostBackend",
    "TerminalBackendError",
    "TerminalCommand",
    "TerminalResult",
    "backend_from_context",
    "filter_subprocess_env",
    "resolve_terminal_backend",
]
