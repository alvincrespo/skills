"""The one place subprocesses are run (except the streaming Claude session)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Sequence

from .errors import HarnessError


def child_env() -> dict[str, str]:
    """The environment for every child: never prompt, never colour."""
    env = dict(os.environ)
    env.update(NO_COLOR="1", GIT_TERMINAL_PROMPT="0", GH_PROMPT_DISABLED="1")
    return env


def run(cmd: Sequence[str], cwd: Path | None = None, check: bool = True, timeout: int = 180) -> str:
    """Run `cmd`, return stdout. With check=True a non-zero exit raises HarnessError."""
    result = subprocess.run(
        list(cmd), cwd=cwd, env=child_env(), capture_output=True, text=True,
        stdin=subprocess.DEVNULL, timeout=timeout,
    )
    if check and result.returncode != 0:
        detail = (result.stderr.strip() or result.stdout.strip())[:600]
        raise HarnessError(f"`{' '.join(cmd)}` failed (exit {result.returncode}): {detail}")
    return result.stdout


def succeeds(cmd: Sequence[str], cwd: Path | None = None, timeout: int = 180) -> bool:
    """True if `cmd` exits 0. Never raises on a non-zero exit."""
    result = subprocess.run(
        list(cmd), cwd=cwd, env=child_env(), capture_output=True,
        stdin=subprocess.DEVNULL, timeout=timeout,
    )
    return result.returncode == 0
