"""Small wrappers around git for local workflow reports."""

from __future__ import annotations

import subprocess
from pathlib import Path


def run_git(root: str | Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=Path(root),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def current_branch(root: str | Path) -> str:
    result = run_git(root, "branch", "--show-current")
    return result.stdout.strip()


def has_remote(root: str | Path, name: str = "origin") -> bool:
    result = run_git(root, "remote", "get-url", name)
    return result.returncode == 0
