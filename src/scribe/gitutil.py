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


def parse_trailers(message: str, cwd: str | Path = ".") -> list[tuple[str, str]]:
    """Parse a commit message into (key, value) trailer pairs via git itself."""
    result = subprocess.run(
        ["git", "-C", str(cwd), "interpret-trailers", "--parse"],
        input=message,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    pairs: list[tuple[str, str]] = []
    for line in result.stdout.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            pairs.append((key.strip(), value.strip()))
    return pairs


def commit_trailer_values(
    rev: str,
    key: str = "Decision",
    cwd: str | Path = ".",
) -> list[str]:
    """Values of one trailer key on one commit, one entry per trailer line."""
    result = _git(
        cwd,
        "log",
        "-1",
        f"--format=%(trailers:key={key},valueonly)",
        rev,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def rev_parse_commit(value: str, cwd: str | Path = ".") -> str | None:
    """Full sha when `value` names a commit in this repository, else None."""
    result = _git(cwd, "rev-parse", "--verify", "--quiet", f"{value}^{{commit}}")
    if result.returncode != 0:
        return None
    sha = result.stdout.strip()
    return sha or None


def commit_exists(value: str, cwd: str | Path = ".") -> bool:
    return rev_parse_commit(value, cwd) is not None


def rev_list_all(cwd: str | Path = ".") -> list[str]:
    """Every commit reachable from any ref, newest first."""
    result = _git(cwd, "rev-list", "--all")
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def log_grep_all(
    patterns: list[str],
    cwd: str | Path = ".",
) -> list[tuple[str, str]]:
    """Prefilter commits across all refs whose message contains any pattern."""
    if not patterns:
        return []
    result = _git(
        cwd,
        "log",
        "--all",
        "--format=%H%x09%s",
        "--fixed-strings",
        *[f"--grep={pattern}" for pattern in patterns],
    )
    if result.returncode != 0:
        return []
    commits: list[tuple[str, str]] = []
    for line in result.stdout.splitlines():
        sha, separator, subject = line.partition("\t")
        if separator:
            commits.append((sha, subject))
    return commits
