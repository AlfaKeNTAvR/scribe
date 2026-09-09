from pathlib import Path

import pytest

from scribe.matching import matches, matches_affects, to_repo_relative


@pytest.mark.parametrize(
    ("pattern", "path", "expected"),
    [
        ("src/**", "src/a/b.py", True),
        ("src/**", "src/a.py", True),
        ("src/*.py", "src/a.py", True),
        ("src/*.py", "src/a/b.py", False),
        ("*.sql", "db/x.sql", True),
        ("*.sql", "x.sql", True),
        ("*.sql", "db/x.SQL", False),
        ("docs/?eadme.md", "docs/readme.md", True),
        ("docs/?eadme.md", "docs/a/readme.md", False),
        ("src/[ab].py", "src/a.py", True),
        ("src/[ab].py", "src/c.py", False),
        ("src/[!a].py", "src/b.py", True),
        ("src/[!a].py", "src/a.py", False),
        ("src/[abc", "src/[abc", True),
        ("./src/**", "src/lib/x.py", True),
        ("/src/**", "/src/lib/x.py", True),
        (r"src\**\*.py", r"src\lib\x.py", True),
        ("a/**/z.py", "a/b/c/z.py", True),
        ("a/**/z.py", "a/z.py", False),
        ("**/*.py", "src/a.py", True),
        ("**/*.py", "a.py", False),
        ("file", "deep/path/file", True),
        ("file", "deep/path/other", False),
        ("src/*", "src/", True),
    ],
)
def test_matches_table(pattern: str, path: str, expected: bool) -> None:
    assert matches(pattern, path) is expected


def test_affects_require_positive_and_apply_negation() -> None:
    affects = [
        {"type": "path", "pattern": "src/**"},
        {"type": "path", "pattern": "src/generated/**", "negate": True},
        {"type": "package", "pattern": "scribe"},
    ]
    assert matches_affects(affects, "src/main.py")
    assert not matches_affects(affects, "src/generated/model.py")
    assert not matches_affects(affects, "tests/test_main.py")
    assert not matches_affects([{"type": "action", "pattern": "docker-push"}], "x")


def test_to_repo_relative_normalizes_and_rejects_outside(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    assert to_repo_relative(root, root / "src" / "main.py") == "src/main.py"
    assert to_repo_relative(root, "src/main.py") == "src/main.py"
    assert to_repo_relative(root, tmp_path / "outside.py") is None


def test_to_repo_relative_canonicalizes_symlinks_and_missing_targets(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src" / "existing.py").touch()
    checkout_link = tmp_path / "checkout-link"
    checkout_link.symlink_to(root, target_is_directory=True)
    assert (
        to_repo_relative(root, checkout_link / "src" / "existing.py")
        == "src/existing.py"
    )
    assert to_repo_relative(root, checkout_link / "src" / "new.py") == "src/new.py"

    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "escaped").symlink_to(outside, target_is_directory=True)
    assert to_repo_relative(root, root / "escaped" / "new.py") is None
    nested_outside = outside / "nested"
    nested_outside.mkdir()
    (root / "nested-escape").symlink_to(nested_outside, target_is_directory=True)
    assert to_repo_relative(root, root / "nested-escape" / ".." / "new.py") is None


def test_to_repo_relative_treats_cross_drive_as_outside(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    root.mkdir()

    def cross_drive(_path: str, _start: str) -> str:
        raise ValueError("path is on a different drive")

    monkeypatch.setattr("scribe.matching.os.path.relpath", cross_drive)
    assert to_repo_relative(root, root / "file.py") is None


def test_windows_matching_is_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("scribe.matching.os.name", "nt")
    assert matches("SRC/**", "src/Package/File.PY")
    assert to_repo_relative("/WORK/Repo", "/work/repo/SRC/Main.PY") == "src/main.py"
