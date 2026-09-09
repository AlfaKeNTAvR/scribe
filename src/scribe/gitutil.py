from __future__ import annotations

import os
import subprocess
from pathlib import Path


class GitError(RuntimeError):
    """A `strict=True` git helper's underlying command failed (V3(b)).

    Every message reads `git failed while computing <what>: <stderr first
    line>`, so a caller that wants one explicit reason line can just
    `str(exc)` it.
    """

    def __init__(
        self,
        what: str,
        result: subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes],
    ) -> None:
        stderr = result.stderr or ""
        if isinstance(stderr, bytes):
            # The `-z` pathname helpers run in binary mode (V14).
            stderr = stderr.decode("utf-8", errors="replace")
        lines = stderr.strip().splitlines()
        detail = lines[0] if lines else f"git exited {result.returncode}"
        self.what = what
        self.detail = detail
        super().__init__(f"git failed while computing {what}: {detail}")


def _git(cwd: str | Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def _git_bytes(cwd: str | Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    """Like `_git`, but with `text=False` for the `-z` pathname commands.

    `text=True` runs stdout through universal-newline translation and decodes it
    as UTF-8 with strict errors; a filename containing a raw carriage return or a
    non-UTF-8 byte sequence is legal on Linux and either gets corrupted by the
    newline translation or raises `UnicodeDecodeError`, which a hook cannot
    afford (the fail-open supervisor swallows the whole hook). `_paths_from_z`
    below decodes each NUL-separated field itself, with `os.fsdecode`.
    """
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        text=False,
        capture_output=True,
        check=False,
    )


def _paths_from_z(result: subprocess.CompletedProcess[bytes]) -> list[str]:
    """Decode `-z` (NUL-terminated) pathname output (V14).

    `-z` disables git's default C-style quoting of non-ASCII, tab, quote and
    backslash bytes in a pathname, so every field here is the real filename
    and is returned as is: a literal backslash in a name is not a Windows
    separator and must not be rewritten to `/`. The command runs through
    `_git_bytes`, so `result.stdout` is raw bytes; each NUL-separated field is
    decoded with `os.fsdecode` (surrogateescape), which round-trips any byte
    sequence, valid UTF-8 or not, to a `str` that still compares equal to
    `os.fsdecode`d filesystem paths for the same bytes.
    """
    if result.returncode != 0:
        return []
    return [os.fsdecode(field) for field in result.stdout.split(b"\0") if field]


def toplevel(cwd: str | Path = ".") -> Path | None:
    result = _git(cwd, "rev-parse", "--show-toplevel")
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip()).resolve()


def staged_paths(cwd: str | Path = ".") -> list[str]:
    result = _git_bytes(
        cwd, "diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR"
    )
    return _paths_from_z(result)


def is_dirty(pathspec: str, cwd: str | Path = ".", *, strict: bool = False) -> bool:
    """True when `git status --porcelain -- <pathspec>` reports anything at all.

    A failed `git status` has empty stdout, so the tolerant form reads it as
    "clean" (V3(b), Codex review addendum): `strict=True` raises `GitError`
    instead, for a caller (`scribe check`) that must not treat "git itself
    failed" as "the ledger is clean" and proceed.
    """
    result = _git(cwd, "status", "--porcelain", "--", pathspec)
    if strict and result.returncode != 0:
        raise GitError(f"the status of {pathspec}", result)
    return bool(result.stdout.strip())


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
    result = _git_bytes(
        cwd, "diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR", base
    )
    return _paths_from_z(result)


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
        result = _git_bytes(cwd, "show", "--name-only", "-z", "--format=", rev)
    else:
        result = _git_bytes(
            cwd, "diff-tree", "--no-commit-id", "--name-only", "-z", "-r", rev
        )
    return _paths_from_z(result)


def merge_base(
    first: str, second: str = "HEAD", cwd: str | Path = ".", *, strict: bool = False
) -> str | None:
    """The commit where `second` forked from `first`, the base of `first...second`.

    `strict=True` raises `GitError` instead of returning `None` on failure, for
    a caller (`scribe check`) that must not fall back to `first` when the merge
    base itself cannot be computed (V3(b)): a bad ref, a missing object, or a
    broken repository must fail the check, not pass it vacuously.
    """
    result = _git(cwd, "merge-base", first, second)
    if result.returncode != 0:
        if strict:
            raise GitError(f"the merge base of {first} and {second}", result)
        return None
    sha = result.stdout.strip()
    return sha or None


def diff_names(
    base: str, head: str = "HEAD", cwd: str | Path = ".", *, strict: bool = False
) -> list[str]:
    """Repository-relative paths changed by `base...head`.

    `strict=True` raises `GitError` instead of returning `[]` on failure (see
    `merge_base`'s docstring); the git hooks keep calling this tolerant, so
    their fail-open behaviour is unchanged.
    """
    result = _git_bytes(cwd, "diff", "--name-only", "-z", f"{base}...{head}")
    if strict and result.returncode != 0:
        raise GitError(f"the changed paths between {base} and {head}", result)
    return _paths_from_z(result)


def rev_list_range(
    base: str, head: str = "HEAD", cwd: str | Path = ".", *, strict: bool = False
) -> list[str]:
    """Commits in `base..head`, newest first.

    `strict=True` raises `GitError` instead of returning `[]` on failure (see
    `merge_base`'s docstring).
    """
    result = _git(cwd, "rev-list", f"{base}..{head}")
    if result.returncode != 0:
        if strict:
            raise GitError(f"the commit range {base}..{head}", result)
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
    *,
    strict: bool = False,
) -> list[str]:
    """Decision record paths present at `rev` under `subdir`.

    `strict=True` raises `GitError` instead of returning `[]` on failure (see
    `merge_base`'s docstring): `scribe lint` and `history_check` keep calling
    this tolerant, so an unrelated caller never sees a `[]` that meant
    "git failed" masquerading as "no records here".
    """
    result = _git_bytes(cwd, "ls-tree", "-r", "--name-only", "-z", rev, "--", subdir)
    if strict and result.returncode != 0:
        raise GitError(f"the decision record paths at {rev}", result)
    paths = _paths_from_z(result)
    return [
        path
        for path in paths
        if path.endswith(".md") and path.rsplit("/", 1)[-1].startswith("D-")
    ]
