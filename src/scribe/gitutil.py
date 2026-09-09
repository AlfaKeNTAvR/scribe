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


class ReachableCommits:
    """One command's reachable history snapshot, including abbreviation resolution."""

    def __init__(self, cwd: str | Path = ".") -> None:
        self.cwd = cwd
        self.commits = rev_list_all(cwd)
        self._reachable = set(self.commits)
        self._resolved: dict[str, str | None] = {}

    def resolve(self, value: str) -> str | None:
        """Full SHA only when the commit resolves and is reachable from a ref."""
        if value in self._reachable:
            return value
        if value not in self._resolved:
            full = rev_parse_commit(value, self.cwd)
            self._resolved[value] = full if full in self._reachable else None
        return self._resolved[value]


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


# --- git hook helpers (plan 5.1 to 5.3) -------------------------------------

EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def staged_paths_against(base: str, cwd: str | Path = ".") -> list[str]:
    """Staged paths relative to `base` (a commit or the empty tree), POSIX form.

    `prepare-commit-msg` uses this on amend: the index is compared with the
    amended commit's parent so the pending filter sees the whole amended
    content, not only what was staged since the original commit (F14).
    """
    result = _git(cwd, "diff", "--cached", "--name-only", "--diff-filter=ACMR", base)
    if result.returncode != 0:
        return []
    return [line.replace("\\", "/") for line in result.stdout.splitlines() if line]


def parent_or_empty_tree(rev: str, cwd: str | Path = ".") -> str:
    """`<rev>^` when it exists, else the empty tree (rev is a root commit)."""
    parent = rev_parse_commit(f"{rev}^", cwd)
    return parent if parent is not None else EMPTY_TREE


def add_trailer_to_file(
    message_file: str | Path,
    key: str,
    value: str,
    cwd: str | Path = ".",
) -> bool:
    """`git interpret-trailers --in-place --if-exists addIfDifferent` on the file."""
    result = _git(
        cwd,
        "interpret-trailers",
        "--in-place",
        "--if-exists",
        "addIfDifferent",
        "--trailer",
        f"{key}: {value}",
        str(message_file),
    )
    return result.returncode == 0


def head_sha(cwd: str | Path = ".") -> str | None:
    return rev_parse_commit("HEAD", cwd)


def commit_changed_paths(rev: str = "HEAD", cwd: str | Path = ".") -> list[str]:
    """Paths a commit touched; a root commit falls back to `git show --name-only`."""
    if rev_parse_commit(f"{rev}^", cwd) is None:
        result = _git(cwd, "show", "--name-only", "--format=", rev)
    else:
        result = _git(cwd, "diff-tree", "--no-commit-id", "--name-only", "-r", rev)
    if result.returncode != 0:
        return []
    return [
        line.replace("\\", "/") for line in result.stdout.splitlines() if line.strip()
    ]


def merge_base(first: str, second: str = "HEAD", cwd: str | Path = ".") -> str | None:
    """The commit where `second` forked from `first`, the base of `first...second`."""
    result = _git(cwd, "merge-base", first, second)
    if result.returncode != 0:
        return None
    sha = result.stdout.strip()
    return sha or None


def diff_names(base: str, head: str = "HEAD", cwd: str | Path = ".") -> list[str]:
    """Repository-relative paths changed by `base...head`, forward slashes."""
    result = _git(cwd, "diff", "--name-only", f"{base}...{head}")
    if result.returncode != 0:
        return []
    return [line.replace("\\", "/") for line in result.stdout.splitlines() if line]


def rev_list_range(base: str, head: str = "HEAD", cwd: str | Path = ".") -> list[str]:
    """Commits in `base..head`, newest first."""
    result = _git(cwd, "rev-list", f"{base}..{head}")
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def show_blob(rev: str, path: str, cwd: str | Path = ".") -> str | None:
    """The text of one file at one revision, or None when it is not there."""
    result = _git(cwd, "show", f"{rev}:{path}")
    if result.returncode != 0:
        return None
    return result.stdout


def tree_record_paths(
    rev: str,
    subdir: str = "docs/decisions",
    cwd: str | Path = ".",
) -> list[str]:
    """Decision record paths present at `rev` under `subdir`."""
    result = _git(cwd, "ls-tree", "-r", "--name-only", rev, "--", subdir)
    if result.returncode != 0:
        return []
    paths = [line.replace("\\", "/") for line in result.stdout.splitlines() if line]
    return [
        path
        for path in paths
        if path.endswith(".md") and path.rsplit("/", 1)[-1].startswith("D-")
    ]
