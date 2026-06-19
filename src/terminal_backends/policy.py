"""Policy helpers for terminal backends."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping


_SECRET_ENV_RE = re.compile(r"(api[_-]?key|token|secret|password|credential)", re.I)


def filter_subprocess_env(env: Mapping[str, str] | None) -> dict[str, str]:
    """Drop likely secret-bearing environment variables before subprocess spawn."""
    out: dict[str, str] = {}
    for key, value in (env or os.environ).items():
        if _SECRET_ENV_RE.search(str(key)):
            continue
        out[str(key)] = str(value)
    return out


def path_is_under_any(path: str, roots: tuple[str, ...]) -> bool:
    try:
        resolved = os.path.realpath(path)
    except OSError:
        return False
    for root in roots:
        try:
            real_root = os.path.realpath(root)
            if os.path.commonpath([os.path.normcase(resolved), os.path.normcase(real_root)]) == os.path.normcase(real_root):
                return True
        except (OSError, ValueError):
            continue
    return False
