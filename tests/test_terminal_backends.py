"""Tests for PR-PATCH-014 terminal backend abstraction."""

import json
import sys
from pathlib import Path

import pytest

from src.agent_tools.filesystem_tools import EditFileTool, ReadFileTool, WriteFileTool
from src.agent_tools.subprocess_tools import PythonTool
from src.terminal_backends import TerminalCommand, TerminalResult
from src.terminal_backends.docker import DockerBackend
from src.terminal_backends.host import HostBackend
from src.terminal_backends.policy import filter_subprocess_env


pytestmark = [pytest.mark.area_unit, pytest.mark.portage, pytest.mark.pr_014]


@pytest.mark.asyncio
async def test_host_backend_runs_python_command_happy_path(tmp_path):
    result = await HostBackend().run(
        TerminalCommand(
            argv=(sys.executable, "-c", "print('ok')"),
            cwd=str(tmp_path),
            timeout=5,
        )
    )

    assert result.exit_code == 0
    assert result.stdout.strip() == "ok"
    assert result.to_trace()["backend"] == "host"


@pytest.mark.asyncio
async def test_host_backend_filters_secret_env_before_spawn(tmp_path):
    result = await HostBackend().run(
        TerminalCommand(
            argv=(
                sys.executable,
                "-c",
                "import os; print(os.getenv('VISIBLE')); print(os.getenv('API_KEY'))",
            ),
            cwd=str(tmp_path),
            env={"VISIBLE": "ok", "API_KEY": "secret"},
            timeout=5,
        )
    )

    assert result.exit_code == 0
    assert result.stdout.splitlines() == ["ok", "None"]
    assert filter_subprocess_env({"TOKEN": "secret", "VISIBLE": "ok"}) == {"VISIBLE": "ok"}


@pytest.mark.asyncio
async def test_host_backend_timeout_kills_command(tmp_path):
    result = await HostBackend().run(
        TerminalCommand(
            argv=(sys.executable, "-c", "import time; time.sleep(10)"),
            cwd=str(tmp_path),
            timeout=0.1,
        )
    )

    assert result.timed_out is True
    assert result.exit_code == 124


@pytest.mark.asyncio
async def test_docker_backend_fails_closed_and_rejects_unmounted_paths(tmp_path):
    disabled = DockerBackend()
    with pytest.raises(RuntimeError, match="docker-backend-disabled"):
        await disabled.run(TerminalCommand(argv=("echo", "x"), cwd=str(tmp_path)))

    mounted = tmp_path / "mounted"
    mounted.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    backend = DockerBackend(enabled=True, allowed_mounts=(str(mounted),))
    with pytest.raises(RuntimeError, match="docker-backend-path-not-mounted"):
        await backend.run(TerminalCommand(argv=("echo", "x"), cwd=str(outside)))


@pytest.mark.asyncio
async def test_python_tool_routes_execution_through_terminal_backend(tmp_path):
    captured = {}

    class RecordingBackend:
        async def run(self, command):
            captured["command"] = command
            return TerminalResult(stdout="backend-ok", exit_code=0, backend="recording")

    result = await PythonTool().execute(
        "print('ignored')",
        {
            "terminal_backend": RecordingBackend(),
            "subproc_env": {"VISIBLE": "ok"},
        },
    )

    assert result == {"output": "backend-ok", "exit_code": 0}
    assert captured["command"].argv[:3] == (sys.executable or "python", "-I", "-c")
    assert Path(captured["command"].cwd).exists()


@pytest.mark.asyncio
async def test_file_tools_route_text_io_through_terminal_backend(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.settings.get_setting",
        lambda key, default=None: [str(tmp_path)] if key == "tool_path_extra_roots" else default,
    )
    file_path = tmp_path / "note.txt"
    calls = []
    storage = {}

    class RecordingFileBackend:
        async def write_text(self, path, content):
            calls.append(("write", path, content))
            old = storage.get(path, "")
            storage[path] = content
            return old

        async def read_text(self, path, *, offset=0, limit=0, max_chars=0):
            calls.append(("read", path, offset, limit, max_chars))
            return storage[path]

        async def patch_text(self, path, old, new, *, replace_all=False):
            calls.append(("patch", path, old, new, replace_all))
            original = storage[path]
            updated = original.replace(old, new, 1)
            storage[path] = updated
            return original, updated, "ok"

    ctx = {"terminal_backend": RecordingFileBackend()}

    write = await WriteFileTool().execute(f"{file_path}\nhello", ctx)
    read = await ReadFileTool().execute(str(file_path), ctx)
    edit = await EditFileTool().execute(
        json.dumps({
            "path": str(file_path),
            "old_string": "hello",
            "new_string": "hi",
        }),
        ctx,
    )

    assert write["exit_code"] == 0
    assert read["output"] == "hello"
    assert edit["exit_code"] == 0
    assert [call[0] for call in calls] == ["write", "read", "patch"]
