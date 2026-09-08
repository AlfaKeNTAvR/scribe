from __future__ import annotations

import subprocess
from pathlib import Path


def _git(cwd: str | Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def toplevel(cwd: str | Path = ".") -> Path | None:
    result = _git(cwd, "rev-parse", "--show-toplevel")
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip()).resolve()


def staged_paths(cwd: str | Path = ".") -> list[str]:
    result = _git(cwd, "diff", "--cached", "--name-only", "--diff-filter=ACMR")
    if result.returncode != 0:
        return []
    return [line.replace("\\", "/") for line in result.stdout.splitlines() if line]


def git_path(name: str, cwd: str | Path = ".") -> Path | None:
    result = _git(cwd, "rev-parse", "--git-path", name)
    if result.returncode != 0:
        return None
    path = Path(result.stdout.strip())
    if not path.is_absolute():
        path = Path(cwd).resolve() / path
    return path.resolve()


def git_path_hooks(cwd: str | Path = ".") -> Path | None:
    return git_path("hooks", cwd)
