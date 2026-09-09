"""V14: pathname-returning gitutil helpers must decode real filenames.

Git's default output quotes non-ASCII, tab, quote and backslash bytes in a
pathname (C-style, with the string wrapped in double quotes); the old code
treated that quoted text as plain lines and replaced every backslash with a
forward slash, corrupting exactly the filenames this file exercises. The fix
requests `-z` (NUL-terminated, unquoted) output instead, so these tests run
against a real git repository rather than mocking `_git`.

`text=True` on the underlying `subprocess.run` is a second, separate bug on
top of the quoting one: it runs stdout through universal-newline translation
(rewriting a raw `\r` inside a field into `\n`) and decodes it as UTF-8 with
strict errors (raising `UnicodeDecodeError` on a non-UTF-8 byte sequence,
which both bytes are legal in a Linux filename). `BINARY_UNSAFE_NAMES` below
exercises those two cases; `text=False` plus per-field `os.fsdecode` fixes
both.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from scribe.gitutil import GitError, commit_changed_paths, diff_names, staged_paths

CAFE = "src/café.py"
TAB = "src/tab\tfile.py"
QUOTE = 'src/quo"te.py'
SPECIAL_NAMES = (CAFE, TAB, QUOTE)

CARRIAGE_RETURN = "src/carriage\rreturn.py"
NON_UTF8 = os.fsdecode(b"src/non-utf8-\xff\xfe.py")
BINARY_UNSAFE_NAMES = (CARRIAGE_RETURN, NON_UTF8)


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=check,
    )


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    git_home = tmp_path / "home"
    git_home.mkdir()
    monkeypatch.setenv("HOME", str(git_home))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.name", "Scribe Tests")
    git(root, "config", "user.email", "scribe-tests@example.invalid")
    git(root, "config", "commit.gpgsign", "false")
    (root / "src").mkdir()
    return root


def _write_all(root: Path, content: str) -> None:
    for name in SPECIAL_NAMES:
        (root / name).write_text(content, encoding="utf-8")


def _write_binary_unsafe(root: Path, content: str) -> None:
    for name in BINARY_UNSAFE_NAMES:
        (root / name).write_text(content, encoding="utf-8")


def test_staged_paths_preserves_special_filenames(repo: Path) -> None:
    _write_all(repo, "one\n")
    git(repo, "add", "-A")

    assert set(staged_paths(repo)) == set(SPECIAL_NAMES)


def test_diff_names_preserves_special_filenames(repo: Path) -> None:
    _write_all(repo, "one\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "add special names")
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    _write_all(repo, "two\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "change special names")

    assert set(diff_names(base, "HEAD", repo)) == set(SPECIAL_NAMES)


def test_staged_paths_preserves_carriage_return_and_non_utf8_filenames(
    repo: Path,
) -> None:
    """A raw CR inside a name and a non-UTF-8 byte sequence must both survive.

    On the old `text=True` code, `staged_paths(repo)` never returns: universal
    newline translation rewrites the embedded `\r` in `CARRIAGE_RETURN` into
    `\n` and strict UTF-8 decoding raises `UnicodeDecodeError` on `NON_UTF8`,
    so the `set(staged_paths(repo)) == set(BINARY_UNSAFE_NAMES)` assertion is
    never reached; the call itself raises first.
    """
    if os.name == "nt":
        pytest.skip("raw CR and arbitrary bytes are not legal in Windows filenames")
    try:
        _write_binary_unsafe(repo, "one\n")
    except OSError as exc:
        pytest.skip(f"filesystem refuses a raw CR or non-UTF-8 filename: {exc}")
    git(repo, "add", "-A")

    assert set(staged_paths(repo)) == set(BINARY_UNSAFE_NAMES)


def test_diff_names_preserves_carriage_return_and_non_utf8_filenames(
    repo: Path,
) -> None:
    """Same as above, through the `base...head` diff path `diff_names` uses.

    On the old code, `diff_names(base, "HEAD", repo)` raises `UnicodeDecodeError`
    decoding `NON_UTF8`'s raw bytes before the `set(...) == set(BINARY_UNSAFE_NAMES)`
    assertion is reached (and, independently, `CARRIAGE_RETURN` comes back with
    its `\r` rewritten to `\n` by universal-newline translation).
    """
    if os.name == "nt":
        pytest.skip("raw CR and arbitrary bytes are not legal in Windows filenames")
    try:
        _write_binary_unsafe(repo, "one\n")
    except OSError as exc:
        pytest.skip(f"filesystem refuses a raw CR or non-UTF-8 filename: {exc}")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "add binary-unsafe names")
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    _write_binary_unsafe(repo, "two\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "change binary-unsafe names")

    assert set(diff_names(base, "HEAD", repo)) == set(BINARY_UNSAFE_NAMES)


def test_commit_changed_paths_preserves_special_filenames(repo: Path) -> None:
    """A non-root commit takes the `diff-tree` branch."""
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "seed commit")
    _write_all(repo, "one\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "add special names")

    assert set(commit_changed_paths("HEAD", repo)) == set(SPECIAL_NAMES)


def test_commit_changed_paths_preserves_special_filenames_on_root_commit(
    repo: Path,
) -> None:
    """The root-commit fallback (`git show --name-only`) needs the same fix."""
    _write_all(repo, "one\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "root commit with special names")

    assert set(commit_changed_paths("HEAD", repo)) == set(SPECIAL_NAMES)


# --- V3(b): the strict/tolerant split on git failure -------------------------


def test_diff_names_tolerant_form_still_returns_empty_list_on_git_failure(
    repo: Path,
) -> None:
    """The default form fails open (V3(b)): the git hooks and `scribe lint`
    call this without `strict` and must keep treating a git failure as "no
    paths", not raise.
    """
    _write_all(repo, "one\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "seed commit")

    assert diff_names("not-a-real-ref", "HEAD", repo) == []


def test_diff_names_strict_form_raises_on_git_failure(repo: Path) -> None:
    """`strict=True` is `scribe check`'s form: a git failure is an exception,
    not an empty (and indistinguishable from "no changes") list.
    """
    _write_all(repo, "one\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "seed commit")

    with pytest.raises(GitError, match="git failed while computing"):
        diff_names("not-a-real-ref", "HEAD", repo, strict=True)
