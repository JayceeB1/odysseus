"""Host terminal backend.

This backend preserves existing Odysseus behavior. It is not a sandbox:
callers must rely on the existing owner, toolset, and path policies before
choosing this backend.
"""

from __future__ import annotations

import asyncio
import collections
import os
import time

from src.terminal_backends.base import TerminalCommand, TerminalResult
from src.terminal_backends.policy import filter_subprocess_env


PROGRESS_INTERVAL_S = 2.0
PROGRESS_TAIL_LINES = 12


class HostBackend:
    name = "host"

    async def run(self, command: TerminalCommand) -> TerminalResult:
        env = filter_subprocess_env(command.env)
        if command.command:
            proc = await asyncio.create_subprocess_shell(
                command.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE if command.input_text else None,
                env=env,
                cwd=command.cwd,
            )
        elif command.argv:
            proc = await asyncio.create_subprocess_exec(
                *command.argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE if command.input_text else None,
                env=env,
                cwd=command.cwd,
            )
        else:
            raise ValueError("terminal command requires command or argv")

        stdout, stderr, rc, timed_out = await _run_subprocess_streaming(
            proc,
            timeout=command.timeout,
            input_text=command.input_text,
            progress_cb=command.progress_cb,
        )
        return TerminalResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=124 if timed_out else (rc or 0),
            timed_out=timed_out,
            backend=self.name,
        )

    async def read_text(
        self,
        path: str,
        *,
        offset: int = 0,
        limit: int = 0,
        max_chars: int,
    ) -> str:
        def _read() -> str:
            if offset > 0 or limit > 0:
                start = max(offset, 1)
                out, n, budget = [], 0, max_chars
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    for i, line in enumerate(f, 1):
                        if i < start:
                            continue
                        if limit > 0 and n >= limit:
                            break
                        out.append(line)
                        n += 1
                        budget -= len(line)
                        if budget <= 0:
                            out.append(f"\n... [truncated at {max_chars} chars]")
                            break
                return "".join(out)
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return f.read(max_chars + 1)

        return await asyncio.to_thread(_read)

    async def write_text(self, path: str, content: str) -> str:
        def _write() -> str:
            old = ""
            try:
                with open(path, "r", encoding="utf-8") as f:
                    old = f.read()
            except (FileNotFoundError, IsADirectoryError, UnicodeDecodeError, OSError):
                old = ""
            directory = os.path.dirname(path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return old

        return await asyncio.to_thread(_write)

    async def patch_text(
        self,
        path: str,
        old: str,
        new: str,
        *,
        replace_all: bool = False,
    ) -> tuple[str, str | None, str]:
        def _patch() -> tuple[str, str | None, str]:
            with open(path, "r", encoding="utf-8") as f:
                original = f.read()
            count = original.count(old)
            if count == 0:
                return original, None, "not_found"
            if count > 1 and not replace_all:
                return original, None, f"not_unique:{count}"
            updated = original.replace(old, new) if replace_all else original.replace(old, new, 1)
            with open(path, "w", encoding="utf-8") as f:
                f.write(updated)
            return original, updated, "ok"

        return await asyncio.to_thread(_patch)


async def _run_subprocess_streaming(
    proc: asyncio.subprocess.Process,
    *,
    timeout: float,
    input_text: str | None = None,
    progress_cb=None,
) -> tuple[str, str, int | None, bool]:
    started = time.time()
    stdout_full: list[str] = []
    stderr_full: list[str] = []
    tail = collections.deque(maxlen=PROGRESS_TAIL_LINES)

    async def _reader(stream, full_buf, label: str):
        if stream is None:
            return
        while True:
            line = await stream.readline()
            if not line:
                break
            decoded = line.decode("utf-8", errors="replace").rstrip("\n")
            full_buf.append(decoded)
            tail.append(f"! {decoded}" if label == "err" else decoded)

    async def _writer():
        if proc.stdin is None or input_text is None:
            return
        proc.stdin.write(input_text.encode("utf-8", errors="replace"))
        await proc.stdin.drain()
        proc.stdin.close()

    async def _progress_emitter():
        await asyncio.sleep(PROGRESS_INTERVAL_S)
        while True:
            if progress_cb:
                try:
                    await progress_cb({
                        "elapsed_s": round(time.time() - started, 1),
                        "tail": "\n".join(list(tail)),
                    })
                except Exception:
                    pass
            await asyncio.sleep(PROGRESS_INTERVAL_S)

    rd_out = asyncio.create_task(_reader(proc.stdout, stdout_full, "out"))
    rd_err = asyncio.create_task(_reader(proc.stderr, stderr_full, "err"))
    writer = asyncio.create_task(_writer())
    prog_task = asyncio.create_task(_progress_emitter()) if progress_cb else None

    timed_out = False
    try:
        await asyncio.wait_for(proc.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        timed_out = True
        try:
            proc.kill()
        except Exception:
            pass
        try:
            await asyncio.wait_for(proc.wait(), timeout=2)
        except Exception:
            pass
    except asyncio.CancelledError:
        try:
            proc.kill()
        except Exception:
            pass
        try:
            await asyncio.wait_for(proc.wait(), timeout=2)
        except Exception:
            pass
        raise
    finally:
        for task in (writer, rd_out, rd_err):
            try:
                await asyncio.wait_for(task, timeout=1)
            except Exception:
                pass
        if prog_task is not None and not prog_task.done():
            prog_task.cancel()
            try:
                await prog_task
            except (asyncio.CancelledError, Exception):
                pass

    return "\n".join(stdout_full), "\n".join(stderr_full), proc.returncode, timed_out
