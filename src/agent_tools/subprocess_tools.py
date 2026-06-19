import asyncio
import sys
import time
import collections
from typing import Optional, Callable, Awaitable, Tuple, Dict
from src.constants import MAX_OUTPUT_CHARS

DEFAULT_BASH_TIMEOUT = 60 * 60     # 1 hour
DEFAULT_PYTHON_TIMEOUT = 60 * 60

PROGRESS_INTERVAL_S = 2.0
PROGRESS_TAIL_LINES = 12

async def _run_subprocess_streaming(
    proc: asyncio.subprocess.Process,
    *,
    timeout: float,
    progress_cb: Optional[Callable[[Dict], Awaitable[None]]] = None,
) -> Tuple[str, str, Optional[int], bool]:
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
            if label == "err":
                tail.append(f"! {decoded}")
            else:
                tail.append(decoded)

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
        for t in (rd_out, rd_err):
            t.cancel()
        if prog_task is not None:
            prog_task.cancel()
        raise
    finally:
        if prog_task is not None and not prog_task.done():
            prog_task.cancel()
            try:
                await prog_task
            except (asyncio.CancelledError, Exception):
                pass
        for t in (rd_out, rd_err):
            try:
                await asyncio.wait_for(t, timeout=1)
            except Exception:
                pass

    return (
        "\n".join(stdout_full),
        "\n".join(stderr_full),
        proc.returncode,
        timed_out,
    )

class BashTool:
    async def execute(self, content: str, ctx: dict) -> dict:
        from src.tool_execution import agent_cwd, _truncate
        from src.terminal_backends import TerminalCommand, backend_from_context
        progress_cb = ctx.get("progress_cb")
        _subproc_env = ctx.get("subproc_env")
        backend = backend_from_context(ctx)
        result = await backend.run(TerminalCommand(
            command=content,
            cwd=agent_cwd(),
            env=_subproc_env,
            timeout=DEFAULT_BASH_TIMEOUT,
            progress_cb=progress_cb,
        ))
        if result.timed_out:
            return {"error": f"bash: timed out after {DEFAULT_BASH_TIMEOUT}s — process killed", "exit_code": 124, "stdout": _truncate(result.stdout, MAX_OUTPUT_CHARS), "stderr": _truncate(result.stderr, MAX_OUTPUT_CHARS)}
        output = result.combined_output()
        output = _truncate(output, MAX_OUTPUT_CHARS)
        return {"output": output or "(no output)", "exit_code": result.exit_code}

class PythonTool:
    async def execute(self, content: str, ctx: dict) -> dict:
        from src.tool_execution import agent_cwd, _truncate
        from src.terminal_backends import TerminalCommand, backend_from_context
        progress_cb = ctx.get("progress_cb")
        _subproc_env = ctx.get("subproc_env")
        backend = backend_from_context(ctx)
        result = await backend.run(TerminalCommand(
            argv=(sys.executable or "python", "-I", "-c", content),
            cwd=agent_cwd(),
            env=_subproc_env,
            timeout=DEFAULT_PYTHON_TIMEOUT,
            progress_cb=progress_cb,
        ))
        if result.timed_out:
            return {"error": f"python: timed out after {DEFAULT_PYTHON_TIMEOUT}s — process killed", "exit_code": 124, "stdout": _truncate(result.stdout, MAX_OUTPUT_CHARS), "stderr": _truncate(result.stderr, MAX_OUTPUT_CHARS)}
        output = result.combined_output()
        output = _truncate(output, MAX_OUTPUT_CHARS)
        return {"output": output or "(no output)", "exit_code": result.exit_code}
