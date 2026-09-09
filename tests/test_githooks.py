"""T11: the three git hooks (plan 5.1 to 5.3, F3, F12, F13, F14).

The hooks are installed as files that call `sys.executable -m scribe git-hook
<name>` (no shim, no uv), and real `git commit` runs in the tmp repo.
"""

import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from scribe.links import implementation_paths
from scribe.newrecord import create_record, load_spec
from scribe.record import Record
from scribe.state import state_path
from scribe.store import Store

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC = PROJECT_ROOT / "tests" / "fixtures" / "new_spec.json"
HOOKS = ("prepare-commit-msg", "commit-msg", "post-commit")
SESSION = "session-t11"

# Real records: A governs src/scribe/index.py and check.py, C is unrelated to both.
RECORD_A = "D-260908-unreviewed-may-supersede-ratified"
RECORD_C = "D-260908-verbatim-quote-is-the-evidence"
ULID_C = "01M21BVB05VVF1XV54Y66AWV6E"

RunCli = Callable[..., tuple[int, str, str]]

HOOK_TEMPLATE = """#!{python}
import os, sys
os.execv(sys.executable, [sys.executable, "-m", "scribe", "git-hook", "{name}", *sys.argv[1:]])
"""


# --- helpers -----------------------------------------------------------------


def git(repo: Path, *args: str, env: dict[str, str] | None = None, check: bool = True):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=check,
        env={**os.environ, **(env or {})},
    )


def install_hooks(repo: Path) -> None:
    hooks_dir = Path(git(repo, "rev-parse", "--git-path", "hooks").stdout.strip())
    if not hooks_dir.is_absolute():
        hooks_dir = repo / hooks_dir
    hooks_dir.mkdir(parents=True, exist_ok=True)
    for name in HOOKS:
        hook = hooks_dir / name
        hook.write_text(
            HOOK_TEMPLATE.format(python=sys.executable, name=name), encoding="utf-8"
        )
        hook.chmod(0o755)


def write(repo: Path, relative: str, text: str | None = None) -> str:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if text is not None else f"{relative}\n", encoding="utf-8")
    return relative


def commit(
    repo: Path,
    message: str,
    *paths: str,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    if paths:
        git(repo, "add", "--", *paths)
    return git(repo, "commit", "-q", "-m", message, env=env, check=check)


AMEND_LATER = {"GIT_COMMITTER_DATE": "2030-01-01T00:00:00 +0000"}


def head(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def head_message(repo: Path) -> str:
    return git(repo, "log", "-1", "--format=%B").stdout


def trailer_lines(message: str, key: str) -> list[str]:
    return [line for line in message.splitlines() if line.startswith(f"{key}:")]


def load(repo: Path, alias: str) -> Record:
    return Record.load(repo / "docs" / "decisions" / f"{alias}.md")


def link_commits(record: Record) -> set[str]:
    return {link["commit"] for link in record.data["implementation_links"]}


def pending_ids(repo: Path) -> list[str]:
    path = state_path(repo)
    if not path.exists():
        return []
    state = json.loads(path.read_text(encoding="utf-8"))
    return [
        item
        for session in state["sessions"].values()
        for item in session.get("pending_decisions", [])
    ]


def new_pending(repo: Path, patterns: list[str], title: str) -> Record:
    """A proposed, unreviewed record registered as pending for SESSION via `scribe new`."""
    spec = load_spec(SPEC)
    spec["title"] = title
    spec["affects"] = [{"type": "path", "pattern": pattern} for pattern in patterns]
    path, problems = create_record(
        Store(repo), spec, by="tester", session=SESSION, register=True
    )
    assert path is not None, problems
    return Record.load(path)


def make_unreviewed_clone(
    repo: Path, alias: str, suffix: str, patterns: list[str]
) -> Record:
    """Clone real record A with a fresh identity and its own `affects`."""
    record = load(repo, RECORD_A)
    record.path = repo / "docs" / "decisions" / f"{alias}.md"
    base = "01M21BV91NZSW1HMJ127KZAA"
    record.data.update(
        {
            "id": base[: 26 - len(suffix)] + suffix,
            "alias": alias,
            "review_state": "unreviewed",
            "ratified_by": None,
            "ratified_at": None,
            "affects": [{"type": "path", "pattern": pattern} for pattern in patterns],
            "history": record.data["history"][:1],
        }
    )
    record.save()
    return record


@pytest.fixture
def hooked_repo(tmp_repo: Path) -> Path:
    """tmp_repo with the hooks installed and a baseline commit made with hooks skipped."""
    install_hooks(tmp_repo)
    write(tmp_repo, ".gitignore", ".claude/scribe/\n")
    git(tmp_repo, "add", "-A")
    git(
        tmp_repo,
        "commit",
        "-q",
        "-m",
        "chore: baseline",
        env={"SCRIBE_SKIP_HOOKS": "1"},
    )
    assert trailer_lines(head_message(tmp_repo), "Decision") == []
    return tmp_repo


def record_then_implement(repo: Path) -> tuple[Record, str, str]:
    """The F3 two-commit sequence: returns the record, the record-commit sha, the implementing sha."""
    record = new_pending(repo, ["src/**"], "Hook test record")
    commit(repo, "docs: Add the record", "docs/decisions")
    record_sha = head(repo)
    write(repo, "src/x.py")
    commit(repo, "feat: Implement x", "src/x.py")
    return record, record_sha, head(repo)


# --- links.implementation_paths ---------------------------------------------


def test_implementation_paths_apply_affects_and_skip_the_store(
    hooked_repo: Path,
) -> None:
    record = load(hooked_repo, RECORD_A)
    record.data["affects"] = [
        {"type": "path", "pattern": "src/**"},
        {"type": "path", "pattern": "src/generated/**", "negate": True},
    ]
    changed = ["src/a.py", "src/generated/b.py", "docs/decisions/INDEX.md", "notes.md"]

    assert implementation_paths(record, changed) == ["src/a.py"]

    record.data["affects"] = [{"type": "action", "pattern": "publish"}]
    assert implementation_paths(record, changed) == [
        "src/a.py",
        "src/generated/b.py",
        "notes.md",
    ]


# --- (a) and (b): the two-commit sequence -----------------------------------


def test_record_only_commit_gets_its_trailer_and_stays_pending(
    hooked_repo: Path,
) -> None:
    record = new_pending(hooked_repo, ["src/**"], "Hook test record")
    alias, ulid = record.data["alias"], record.data["id"]

    result = commit(hooked_repo, "docs: Add the record", "docs/decisions")

    message = head_message(hooked_repo)
    assert trailer_lines(message, "Decision") == [f"Decision: {alias} {ulid}"]
    assert trailer_lines(message, "Session") == [f"Session: {SESSION}"]
    assert "scribe: linked" not in result.stderr
    saved = load(hooked_repo, alias)
    assert saved.data["effective_state"] == "proposed"
    assert saved.data["implementation_links"] == []
    assert pending_ids(hooked_repo) == [ulid]
    assert git(hooked_repo, "status", "--porcelain").stdout == ""


def test_implementing_commit_links_from_pending_state(hooked_repo: Path) -> None:
    record = new_pending(hooked_repo, ["src/**"], "Hook test record")
    alias, ulid = record.data["alias"], record.data["id"]
    commit(hooked_repo, "docs: Add the record", "docs/decisions")

    write(hooked_repo, "src/x.py")
    result = commit(hooked_repo, "feat: Implement x", "src/x.py")

    sha = head(hooked_repo)[:12]
    assert trailer_lines(head_message(hooked_repo), "Decision") == [
        f"Decision: {alias} {ulid}"
    ]
    assert (
        f"scribe: linked 1 record(s) to {sha}; run git add docs/decisions"
        in result.stderr
    )
    saved = load(hooked_repo, alias)
    assert saved.data["effective_state"] == "implemented"
    assert saved.data["implementation_links"] == [
        {"commit": sha, "paths": ["src/x.py"]}
    ]
    events = [item["event"] for item in saved.data["history"]]
    assert events == ["proposed", "link_added", "implemented"]
    assert all(item.get("commit") == sha for item in saved.data["history"][1:])
    assert pending_ids(hooked_repo) == []
    status = git(hooked_repo, "status", "--porcelain").stdout
    assert f"docs/decisions/{alias}.md" in status
    assert "docs/decisions/INDEX.md" in status


# --- (c): unrelated staged file --------------------------------------------


def test_unrelated_staged_file_gets_no_trailer(hooked_repo: Path) -> None:
    record = new_pending(hooked_repo, ["src/**"], "Hook test record")
    commit(hooked_repo, "docs: Add the record", "docs/decisions")

    write(hooked_repo, "notes.md")
    commit(hooked_repo, "docs: Notes", "notes.md")

    assert trailer_lines(head_message(hooked_repo), "Decision") == []
    assert pending_ids(hooked_repo) == [record.data["id"]]
    assert load(hooked_repo, record.data["alias"]).data["implementation_links"] == []


# --- (d) and (d2): amend -----------------------------------------------------


def test_amend_keeps_one_trailer_and_adds_a_link_for_the_new_sha(
    hooked_repo: Path,
) -> None:
    record, _, old_sha = record_then_implement(hooked_repo)
    alias, ulid = record.data["alias"], record.data["id"]

    # A distinct committer date keeps the amended sha from colliding with the
    # original when both land in the same second with an unchanged tree.
    git(hooked_repo, "commit", "-q", "--amend", "--no-edit", env=AMEND_LATER)

    new_sha = head(hooked_repo)
    assert new_sha != old_sha
    assert trailer_lines(head_message(hooked_repo), "Decision") == [
        f"Decision: {alias} {ulid}"
    ]
    saved = load(hooked_repo, alias)
    assert link_commits(saved) == {old_sha[:12], new_sha[:12]}
    assert saved.data["effective_state"] == "implemented"
    assert [item["event"] for item in saved.data["history"]].count("implemented") == 1


def test_amend_with_a_newly_pending_decision_adds_its_trailer_and_link(
    hooked_repo: Path,
) -> None:
    first, _, old_sha = record_then_implement(hooked_repo)
    second = new_pending(hooked_repo, ["src/**"], "Second record after the fact")

    # A distinct committer date keeps the amended sha from colliding with the
    # original when both land in the same second with an unchanged tree.
    git(hooked_repo, "commit", "-q", "--amend", "--no-edit", env=AMEND_LATER)

    new_sha = head(hooked_repo)
    assert trailer_lines(head_message(hooked_repo), "Decision") == [
        f"Decision: {first.data['alias']} {first.data['id']}",
        f"Decision: {second.data['alias']} {second.data['id']}",
    ]
    assert link_commits(load(hooked_repo, first.data["alias"])) == {
        old_sha[:12],
        new_sha[:12],
    }
    saved_second = load(hooked_repo, second.data["alias"])
    assert saved_second.data["implementation_links"] == [
        {"commit": new_sha[:12], "paths": ["src/x.py"]}
    ]
    assert saved_second.data["effective_state"] == "implemented"
    assert pending_ids(hooked_repo) == []


# --- (e): Session trailer ----------------------------------------------------


def test_existing_claude_session_trailer_suppresses_session(hooked_repo: Path) -> None:
    new_pending(hooked_repo, ["src/**"], "Hook test record")
    write(hooked_repo, "notes.md")

    commit(hooked_repo, "docs: Notes\n\nClaude-Session: session_abc\n", "notes.md")

    message = head_message(hooked_repo)
    assert trailer_lines(message, "Claude-Session") == ["Claude-Session: session_abc"]
    assert trailer_lines(message, "Session") == []


# --- (f): unknown decision, warn versus enforce -----------------------------


def test_unknown_decision_warns_and_fails_only_under_enforce(
    hooked_repo: Path, set_config: Callable[..., Path]
) -> None:
    write(hooked_repo, "notes.md")
    result = commit(hooked_repo, "docs: Notes\n\nDecision: D-260101-nope\n", "notes.md")
    assert result.returncode == 0
    assert "scribe: warning: unknown decision: D-260101-nope" in result.stderr
    before = head(hooked_repo)

    set_config(hooked_repo, SCRIBE_COMMIT_MSG="enforce")
    write(hooked_repo, "more.md")
    result = commit(
        hooked_repo, "docs: More\n\nDecision: D-260101-nope\n", "more.md", check=False
    )

    assert result.returncode != 0
    assert "scribe: warning: unknown decision: D-260101-nope" in result.stderr
    assert "commit rejected" in result.stderr
    assert head(hooked_repo) == before


def test_alias_and_ulid_from_different_records_warn_mismatch(hooked_repo: Path) -> None:
    write(hooked_repo, "notes.md")

    result = commit(
        hooked_repo, f"docs: Notes\n\nDecision: {RECORD_A} {ULID_C}\n", "notes.md"
    )

    assert result.returncode == 0
    assert "scribe: warning: alias/ulid mismatch" in result.stderr


# --- (g): governed paths (F12) ----------------------------------------------


def test_unrelated_active_trailer_does_not_satisfy_a_governed_path(
    hooked_repo: Path,
) -> None:
    write(hooked_repo, "src/scribe/index.py")

    result = commit(
        hooked_repo,
        f"feat: Index\n\nDecision: {RECORD_C} {ULID_C}\n",
        "src/scribe/index.py",
    )

    assert result.returncode == 0
    assert (
        "scribe: warning: governed path src/scribe/index.py changed without a "
        f"matching decision link (candidates: {RECORD_A})"
    ) in result.stderr


def test_rejected_record_trailer_does_not_satisfy_a_governed_path(
    hooked_repo: Path, run_cli: RunCli
) -> None:
    rejected = make_unreviewed_clone(
        hooked_repo, "D-260908-rejected-index-clone", "RJ", ["src/scribe/index.py"]
    )
    code, _, _ = run_cli(
        ["reject", rejected.data["alias"], "--by", "@tester"], hooked_repo
    )
    assert code == 0
    write(hooked_repo, "src/scribe/index.py")

    result = commit(
        hooked_repo,
        f"feat: Index\n\nDecision: {rejected.data['alias']}\n",
        "src/scribe/index.py",
    )

    assert result.returncode == 0
    assert f"scribe: warning: {rejected.data['alias']} is rejected" in result.stderr
    assert (
        "scribe: warning: governed path src/scribe/index.py changed without a "
        f"matching decision link (candidates: {RECORD_A})"
    ) in result.stderr


def test_each_governed_path_gets_its_own_warning_and_never_blocks(
    hooked_repo: Path, set_config: Callable[..., Path]
) -> None:
    set_config(hooked_repo, SCRIBE_COMMIT_MSG="enforce")
    write(hooked_repo, "src/scribe/index.py")
    write(hooked_repo, "src/scribe/check.py")

    result = commit(
        hooked_repo, "feat: No trailer", "src/scribe/index.py", "src/scribe/check.py"
    )

    assert result.returncode == 0
    warnings = [line for line in result.stderr.splitlines() if "governed path" in line]
    assert len(warnings) == 2
    assert any("governed path src/scribe/check.py changed" in line for line in warnings)
    assert any("governed path src/scribe/index.py changed" in line for line in warnings)
    assert all(f"(candidates: {RECORD_A})" in line for line in warnings)


def test_matching_active_trailer_satisfies_the_governed_path(hooked_repo: Path) -> None:
    write(hooked_repo, "src/scribe/index.py")

    result = commit(
        hooked_repo, f"feat: Index\n\nDecision: {RECORD_A}\n", "src/scribe/index.py"
    )

    assert result.returncode == 0
    assert "governed path" not in result.stderr
    assert "scribe: warning" not in result.stderr
    saved = load(hooked_repo, RECORD_A)
    assert saved.data["effective_state"] == "implemented"
    assert saved.data["implementation_links"] == [
        {"commit": head(hooked_repo)[:12], "paths": ["src/scribe/index.py"]}
    ]
