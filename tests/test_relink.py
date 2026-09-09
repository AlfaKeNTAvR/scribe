"""T15: `scribe relink` rebuilds implementation_links from git history (plan 5.3, F15).

Relink reads `Decision:` trailers straight from `git log`, independent of the
git hooks and scratch state that normally write them, so these tests commit
the trailers directly instead of installing hooks (that flow is T11's concern,
`tests/test_githooks.py`). This file continues T11's amend scenario (case
(d)): that test only checks the state right after `git commit --amend`, where
the stale pre-amend sha is still linked because `post-commit` only ever
appends. The missing half, that `scribe relink` drops the now-unreachable sha
and leaves exactly the reachable commits linked, belongs here.
"""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from scribe.newrecord import create_record, load_spec
from scribe.record import Record
from scribe.state import ledger_lock_path
from scribe.store import Store

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC = PROJECT_ROOT / "tests" / "fixtures" / "new_spec.json"

AMEND_LATER = {"GIT_COMMITTER_DATE": "2030-01-01T00:00:00 +0000"}


def git(repo: Path, *args: str, env: dict[str, str] | None = None, check: bool = True):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=check,
        env={**os.environ, **(env or {})},
    )


def write(repo: Path, relative: str, text: str | None = None) -> str:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if text is not None else f"{relative}\n", encoding="utf-8")
    return relative


def commit(
    repo: Path,
    message: str,
    *paths: str,
    decision: str | None = None,
    env: dict[str, str] | None = None,
) -> str:
    """Stage `paths`, commit `message` (plus a Decision trailer when given), return HEAD."""
    if paths:
        git(repo, "add", "--", *paths)
    full_message = f"{message}\n\nDecision: {decision}" if decision else message
    git(repo, "commit", "-q", "-m", full_message, env=env)
    return head(repo)


def head(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def load(repo: Path, alias: str) -> Record:
    return Record.load(repo / "docs" / "decisions" / f"{alias}.md")


def link_commits(record: Record) -> set[str]:
    return {link["commit"] for link in record.data["implementation_links"]}


def new_record(repo: Path, patterns: list[str], title: str) -> Record:
    """A proposed, unreviewed record whose `affects` matches `patterns`."""
    spec = load_spec(SPEC)
    spec["title"] = title
    spec["affects"] = [{"type": "path", "pattern": pattern} for pattern in patterns]
    path, problems = create_record(Store(repo), spec, by="tester")
    assert path is not None, problems
    return Record.load(path)


def run_relink(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "scribe", "relink"],
        cwd=str(repo),
        env=os.environ,
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.fixture
def repo_with_record(tmp_repo: Path) -> tuple[Path, Record]:
    record = new_record(tmp_repo, ["src/**"], "Relink test record")
    write(tmp_repo, ".gitignore", ".claude/scribe/\n")
    git(tmp_repo, "add", "-A")
    git(tmp_repo, "commit", "-q", "-m", "docs: Add the record")
    return tmp_repo, record


def test_relink_keeps_two_already_linked_commits(
    repo_with_record: tuple[Path, Record],
) -> None:
    repo, record = repo_with_record
    alias, ulid = record.data["alias"], record.data["id"]
    trailer = f"{alias} {ulid}"

    write(repo, "src/x.py")
    old_sha = commit(repo, "feat: Implement x", "src/x.py", decision=trailer)[:12]

    write(repo, "src/y.py")
    new_sha = commit(repo, "feat: Implement y", "src/y.py", decision=trailer)[:12]

    first = run_relink(repo)
    assert first.returncode == 0, first.stderr
    assert link_commits(load(repo, alias)) == {old_sha, new_sha}

    second = run_relink(repo)
    assert second.returncode == 0, second.stderr
    assert link_commits(load(repo, alias)) == {old_sha, new_sha}
    assert "nothing to relink" in second.stdout


def test_relink_lock_timeout_exits_nonzero_without_writing(
    repo_with_record: tuple[Path, Record],
) -> None:
    """V8: a lock held past the timeout behaves like ratify (one stderr line,
    nothing written, non-zero exit for this CLI command)."""
    repo, record = repo_with_record
    alias, ulid = record.data["alias"], record.data["id"]
    trailer = f"{alias} {ulid}"
    write(repo, "src/x.py")
    commit(repo, "feat: Implement x", "src/x.py", decision=trailer)
    before = load(repo, alias).data

    lock_path = ledger_lock_path(repo)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as holder:
        fcntl.flock(holder.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        started = time.monotonic()
        result = run_relink(repo)
        elapsed = time.monotonic() - started
        fcntl.flock(holder.fileno(), fcntl.LOCK_UN)

    assert elapsed >= 2.0
    assert result.returncode == 1
    assert "ledger lock timeout" in result.stderr
    assert load(repo, alias).data == before


def test_relink_drops_the_stale_sha_after_amend(
    repo_with_record: tuple[Path, Record],
) -> None:
    """Completes T11's case (d): the state right after amend is
    tests/test_githooks.py's concern, relink's rebuild is this file's."""
    repo, record = repo_with_record
    alias, ulid = record.data["alias"], record.data["id"]
    trailer = f"{alias} {ulid}"

    write(repo, "src/x.py")
    old_sha = commit(repo, "feat: Implement x", "src/x.py", decision=trailer)[:12]

    write(repo, "src/y.py")
    commit(repo, "feat: Implement y", "src/y.py", decision=trailer)
    assert run_relink(repo).returncode == 0
    stale_sha = load(repo, alias).data["implementation_links"][-1]["commit"]

    # A distinct committer date keeps the amended sha from colliding with the
    # original when both land in the same second with an unchanged tree.
    git(repo, "commit", "-q", "--amend", "--no-edit", env=AMEND_LATER)
    new_sha = head(repo)[:12]
    assert new_sha != stale_sha

    before = load(repo, alias)
    assert link_commits(before) == {old_sha, stale_sha}
    relinked_before = sum(
        item["event"] == "relinked" for item in before.data["history"]
    )

    result = run_relink(repo)
    assert result.returncode == 0, result.stderr

    after = load(repo, alias)
    assert link_commits(after) == {old_sha, new_sha}
    relinked_after = sum(item["event"] == "relinked" for item in after.data["history"])
    assert relinked_after - relinked_before == 1
    assert after.data["effective_state"] == "implemented"


def test_lookup_lint_and_relink_agree_on_existing_unreachable_commit(
    repo_with_record: tuple[Path, Record], run_cli, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scribe import gitutil

    repo, record = repo_with_record
    alias = record.data["alias"]
    write(repo, "src/x.py")
    old_sha = commit(repo, "feat: Implement x", "src/x.py", decision=alias)
    git(repo, "commit", "-q", "--amend", "--no-edit", env=AMEND_LATER)
    new_sha = head(repo)
    assert new_sha != old_sha
    assert gitutil.commit_exists(old_sha, repo)
    assert old_sha not in gitutil.rev_list_all(repo)
    record.data["implementation_links"] = [
        {"commit": old_sha[:7], "paths": ["src/x.py"]},
        {"commit": new_sha[:7], "paths": ["src/x.py"]},
    ]
    record.save()
    original = gitutil.rev_list_all
    scans = []

    def counted(root):
        scans.append(root)
        return original(root)

    monkeypatch.setattr(gitutil, "rev_list_all", counted)
    code, stdout, _ = run_cli(["lookup", alias], repo)
    assert code == 0
    assert f"{old_sha[:7]} src/x.py (not in this history)" in stdout
    assert f"  {new_sha[:7]} src/x.py" in stdout.splitlines()
    assert len(scans) == 1

    scans.clear()
    _, stdout, _ = run_cli(["lint", "--json"], repo)
    findings = json.loads(stdout)["findings"]
    unreachable = [item for item in findings if item["code"] == "unreachable_link"]
    assert len(unreachable) == 1
    assert old_sha[:7] in unreachable[0]["message"]
    assert len(scans) == 1

    scans.clear()
    code, stdout, _ = run_cli(["relink"], repo)
    assert code == 0, stdout
    assert link_commits(load(repo, alias)) == {new_sha[:12]}
    assert len(scans) == 1
