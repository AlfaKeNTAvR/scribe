"""V14: pathname-returning gitutil helpers must decode real filenames.

Git's default output quotes non-ASCII, tab, quote and backslash bytes in a
pathname (C-style, with the string wrapped in double quotes); the old code
treated that quoted text as plain lines and replaced every backslash with a
forward slash, corrupting exactly the filenames this file exercises. The fix
requests `-z` (NUL-terminated, unquoted) output instead, so these tests run
against a real git repository rather than mocking `_git`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from scribe.gitutil import commit_changed_paths, diff_names, staged_paths

CAFE = "src/café.py"
TAB = "src/tab\tfile.py"
QUOTE = 'src/quo"te.py'
SPECIAL_NAMES = (CAFE, TAB, QUOTE)


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
