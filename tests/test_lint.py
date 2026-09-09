"""T13: `scribe lint`, the store-wide pass (plan 4.12).

One fixture per rule code: each test arranges the smallest store that triggers
its rule once and asserts the code comes back. The last test is the acceptance
clause from the task list: lint on this repository reports no `verify_failed`
and no `verify_error`.
"""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import textwrap
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from scribe import ulid
from scribe.frontmatter import join, split
from scribe.lint import (
    DEFAULT_VERIFY_TIMEOUT_SECONDS,
    STALE_PROPOSAL_DAYS,
    _run_pytest_verify_entry,
    _run_verify_entry,
    _verify_timeout_seconds,
    run_lint,
)
from scribe.record import Record
from scribe.state import ledger_lock_path, update_state
from scribe.store import Store

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (
    PROJECT_ROOT / "tests" / "fixtures" / "records" / "valid_minimal.md"
).read_text(encoding="utf-8")
# Fresh ULIDs, not the fixture's: the tmp repo carries the real RATIFICATIONS.jsonl,
# and reusing an attested id would make every record read as state_behind_attestation.
ULID_A = ulid.generate()
ULID_B = ulid.generate()

RunCli = Callable[..., tuple[int, str, str]]


# --- helpers -----------------------------------------------------------------


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def commit_all(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--allow-empty", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def days_ago(count: int) -> str:
    return (datetime.now(timezone.utc).date() - timedelta(days=count)).isoformat()


@pytest.fixture
def lint_repo(tmp_repo: Path) -> Path:
    """A tmp repo whose decision store is empty, so each test owns every record."""
    for path in (tmp_repo / "docs" / "decisions").glob("D-*.md"):
        path.unlink()
    return tmp_repo


def write_record(repo: Path, alias: str, record_id: str, **overrides: Any) -> Path:
    """One valid record, dated today, with the given front-matter overrides."""
    data, body = split(TEMPLATE)
    data["alias"] = alias
    data["id"] = record_id
    data["date"] = days_ago(0)
    data.update(overrides)
    path = repo / "docs" / "decisions" / f"{alias}.md"
    path.write_text(join(data, body), encoding="utf-8", newline="\n")
    return path


def lint(run_cli: RunCli, repo: Path, *args: str) -> tuple[int, list[dict[str, Any]]]:
    code, stdout, _ = run_cli(["lint", "--json", *args], repo)
    return code, json.loads(stdout)["findings"]


def codes(findings: list[dict[str, Any]]) -> list[str]:
    return [finding["code"] for finding in findings]


def find(findings: list[dict[str, Any]], code: str) -> dict[str, Any]:
    matched = [finding for finding in findings if finding["code"] == code]
    assert matched, f"expected {code} in {codes(findings)}"
    return matched[0]


# --- a clean store ------------------------------------------------------------


def test_a_clean_store_with_a_current_index_exits_zero(
    run_cli: RunCli, lint_repo: Path
) -> None:
    write_record(lint_repo, "D-260908-sound-choice", ULID_A)
    assert run_cli(["index"], lint_repo)[0] == 0

    code, findings = lint(run_cli, lint_repo)

    assert code == 0
    assert findings == []


# --- identity and validate rules ---------------------------------------------


def test_two_records_sharing_an_id_report_duplicate_alias(
    run_cli: RunCli, lint_repo: Path
) -> None:
    shared = ULID_A
    write_record(lint_repo, "D-260908-sound-choice", shared)
    write_record(lint_repo, "D-260908-second-choice", shared)

    code, findings = lint(run_cli, lint_repo)

    assert code == 1
    assert "duplicate_alias" in codes(findings)


def test_a_filename_that_does_not_match_the_alias_is_reported(
    run_cli: RunCli, lint_repo: Path
) -> None:
    path = write_record(lint_repo, "D-260908-sound-choice", ULID_A)
    path.rename(path.with_name("D-260908-other-name.md"))

    code, findings = lint(run_cli, lint_repo)

    assert code == 1
    assert "alias_filename_mismatch" in codes(findings)


def test_an_unsupported_verify_engine_is_reported(
    run_cli: RunCli, lint_repo: Path
) -> None:
    write_record(
        lint_repo,
        "D-260908-sound-choice",
        ULID_A,
        verify=[
            {
                "id": "engine",
                "engine": "jsonpath",
                "pattern": "$.x",
                "paths": ["src/x.py"],
                "expect": "match",
                "severity": "error",
            }
        ],
    )

    code, findings = lint(run_cli, lint_repo)

    assert code == 1
    assert "unsupported_engine" in codes(findings)


# --- the git base rules -------------------------------------------------------


def test_an_immutable_key_changed_since_the_base_is_reported(
    run_cli: RunCli, lint_repo: Path
) -> None:
    path = write_record(lint_repo, "D-260908-sound-choice", ULID_A)
    commit_all(lint_repo, "chore: Add the record")
    (lint_repo / "src.py").write_text("value = 1\n", encoding="utf-8")
    commit_all(lint_repo, "chore: Add unrelated code")
    data, body = split(path.read_text(encoding="utf-8"))
    data["tags"] = ["test", "rewritten"]
    path.write_text(join(data, body), encoding="utf-8", newline="\n")

    code, findings = lint(run_cli, lint_repo)

    assert code == 1
    assert "immutable_changed" in codes(findings)


def test_a_dropped_history_entry_reports_history_rewritten(
    run_cli: RunCli, lint_repo: Path
) -> None:
    path = write_record(
        lint_repo,
        "D-260908-sound-choice",
        ULID_A,
        effective_state="implemented",
        history=[
            {"at": "2026-09-08T20:37:43Z", "event": "proposed", "by": "codex"},
            {
                "at": "2026-09-09T10:02:00Z",
                "event": "implemented",
                "by": "scribe-post-commit",
                "field": "effective_state",
                "old": "proposed",
                "new": "implemented",
            },
        ],
    )
    commit_all(lint_repo, "chore: Add the record")
    (lint_repo / "src.py").write_text("value = 1\n", encoding="utf-8")
    commit_all(lint_repo, "chore: Add unrelated code")
    data, body = split(path.read_text(encoding="utf-8"))
    data["history"] = data["history"][:1]
    path.write_text(join(data, body), encoding="utf-8", newline="\n")

    code, findings = lint(run_cli, lint_repo)

    assert code == 1
    assert "history_rewritten" in codes(findings)


def test_an_unknown_base_ref_is_an_error(run_cli: RunCli, lint_repo: Path) -> None:
    write_record(lint_repo, "D-260908-sound-choice", ULID_A)

    code, findings = lint(run_cli, lint_repo, "--base", "refs/heads/nowhere")

    assert code == 1
    assert "unknown_base" in codes(findings)


# --- the index rule -----------------------------------------------------------


def test_a_stale_index_is_an_error_and_fix_index_regenerates_it(
    run_cli: RunCli, lint_repo: Path
) -> None:
    write_record(lint_repo, "D-260908-sound-choice", ULID_A)

    code, findings = lint(run_cli, lint_repo)
    assert code == 1
    assert find(findings, "index_stale")["severity"] == "error"

    fixed_code, fixed_findings = lint(run_cli, lint_repo, "--fix-index")

    assert fixed_code == 0
    assert find(fixed_findings, "index_stale")["severity"] == "info"
    assert lint(run_cli, lint_repo)[1] == []


# --- lifecycle rules ----------------------------------------------------------


def test_a_predecessor_that_ignores_its_edge_reports_effective_state_stale(
    run_cli: RunCli, lint_repo: Path
) -> None:
    write_record(lint_repo, "D-260908-sound-choice", ULID_A)
    write_record(
        lint_repo,
        "D-260908-second-choice",
        ULID_B,
        supersedes="D-260908-sound-choice",
    )

    _, findings = lint(run_cli, lint_repo)

    stale = find(findings, "effective_state_stale")
    assert stale["severity"] == "warning"
    assert stale["path"].endswith("D-260908-sound-choice.md")


def test_superseded_without_an_edge_also_reports_effective_state_stale(
    run_cli: RunCli, lint_repo: Path
) -> None:
    write_record(
        lint_repo,
        "D-260908-sound-choice",
        ULID_A,
        effective_state="superseded",
        history=[
            {"at": "2026-09-08T20:37:43Z", "event": "proposed", "by": "codex"},
            {
                "at": "2026-09-09T10:02:00Z",
                "event": "superseded",
                "by": "scribe-new",
                "field": "effective_state",
                "old": "proposed",
                "new": "superseded",
            },
        ],
    )

    _, findings = lint(run_cli, lint_repo)

    assert "effective_state_stale" in codes(findings)


def test_an_action_pattern_outside_the_denylist_reports_unknown_action(
    run_cli: RunCli, lint_repo: Path
) -> None:
    write_record(
        lint_repo,
        "D-260908-sound-choice",
        ULID_A,
        affects=[{"type": "action", "pattern": "deploy-to-mars"}],
    )

    _, findings = lint(run_cli, lint_repo)

    unknown = find(findings, "unknown_action")
    assert unknown["severity"] == "warning"
    assert "deploy-to-mars" in unknown["message"]


def test_a_rejected_record_that_is_still_implemented_is_flagged(
    run_cli: RunCli, lint_repo: Path
) -> None:
    write_record(
        lint_repo,
        "D-260908-sound-choice",
        ULID_A,
        review_state="rejected",
        effective_state="implemented",
        ratified_by="@nikita",
        ratified_at="2026-09-09T10:02:00Z",
    )

    _, findings = lint(run_cli, lint_repo)

    assert find(findings, "rejected_but_implemented")["severity"] == "warning"


def test_a_review_date_in_the_past_reports_review_overdue(
    run_cli: RunCli, lint_repo: Path
) -> None:
    write_record(
        lint_repo,
        "D-260908-sound-choice",
        ULID_A,
        review=days_ago(1),
    )

    _, findings = lint(run_cli, lint_repo)

    assert find(findings, "review_overdue")["severity"] == "warning"


def test_an_implemented_record_nobody_reviewed_is_reported_as_info(
    run_cli: RunCli, lint_repo: Path
) -> None:
    write_record(
        lint_repo,
        "D-260908-sound-choice",
        ULID_A,
        effective_state="implemented",
        history=[
            {"at": "2026-09-08T20:37:43Z", "event": "proposed", "by": "codex"},
            {
                "at": "2026-09-09T10:02:00Z",
                "event": "implemented",
                "by": "scribe-post-commit",
                "field": "effective_state",
                "old": "proposed",
                "new": "implemented",
            },
        ],
    )

    _, findings = lint(run_cli, lint_repo)

    assert find(findings, "unreviewed_implemented")["severity"] == "info"


def test_a_link_to_a_commit_outside_this_history_is_reported(
    run_cli: RunCli, lint_repo: Path
) -> None:
    write_record(
        lint_repo,
        "D-260908-sound-choice",
        ULID_A,
        implementation_links=[{"commit": "0123456789abcdef", "paths": ["src/x.py"]}],
    )

    _, findings = lint(run_cli, lint_repo)

    unreachable = find(findings, "unreachable_link")
    assert unreachable["severity"] == "warning"
    assert "scribe relink" in unreachable["message"]


# --- stale proposals and --expire ---------------------------------------------


def test_an_old_unreviewed_proposal_reports_proposal_stale(
    run_cli: RunCli, lint_repo: Path
) -> None:
    write_record(
        lint_repo,
        "D-260908-sound-choice",
        ULID_A,
        date=days_ago(STALE_PROPOSAL_DAYS + 10),
    )

    _, findings = lint(run_cli, lint_repo)

    assert find(findings, "proposal_stale")["severity"] == "warning"


def test_expire_sets_expired_with_history_and_restores_the_predecessor(
    run_cli: RunCli, lint_repo: Path
) -> None:
    predecessor = write_record(
        lint_repo,
        "D-260908-sound-choice",
        ULID_A,
        effective_state="superseded",
        history=[
            {"at": "2026-09-08T20:37:43Z", "event": "proposed", "by": "codex"},
            {
                "at": "2026-09-09T10:02:00Z",
                "event": "superseded",
                "by": "scribe-new",
                "field": "effective_state",
                "old": "proposed",
                "new": "superseded",
            },
        ],
    )
    successor = write_record(
        lint_repo,
        "D-260908-second-choice",
        ULID_B,
        date=days_ago(40),
        supersedes="D-260908-sound-choice",
    )

    _, findings = lint(run_cli, lint_repo, "--expire")

    assert "proposal_stale" in codes(findings)
    expired = Record.load(successor)
    assert expired.data["effective_state"] == "expired"
    assert expired.data["history"][-1] == {
        **expired.data["history"][-1],
        "event": "expired",
        "by": "scribe-lint",
        "field": "effective_state",
        "old": "proposed",
        "new": "expired",
    }
    restored = Record.load(predecessor)
    assert restored.data["effective_state"] == "proposed"
    assert restored.data["history"][-1]["event"] == "restored"
    assert restored.data["history"][-1]["by"] == "scribe-lint"


def test_expire_leaves_a_young_proposal_alone(run_cli: RunCli, lint_repo: Path) -> None:
    path = write_record(
        lint_repo,
        "D-260908-sound-choice",
        ULID_A,
        date=days_ago(0),
    )

    _, findings = lint(run_cli, lint_repo, "--expire")

    assert "proposal_stale" not in codes(findings)
    assert Record.load(path).data["effective_state"] == "proposed"


def test_expire_lock_timeout_reports_error_and_changes_nothing(
    run_cli: RunCli, lint_repo: Path
) -> None:
    """V8: a lock held past the timeout behaves like ratify: one stderr line,
    nothing expired, non-zero exit (an error finding among the others)."""
    path = write_record(
        lint_repo,
        "D-260908-sound-choice",
        ULID_A,
        date=days_ago(STALE_PROPOSAL_DAYS + 10),
    )
    lock_path = ledger_lock_path(lint_repo)
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with lock_path.open("a+") as holder:
        fcntl.flock(holder.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        started = time.monotonic()
        code, stdout, stderr = run_cli(["lint", "--expire", "--json"], lint_repo)
        elapsed = time.monotonic() - started
        fcntl.flock(holder.fileno(), fcntl.LOCK_UN)

    findings = json.loads(stdout)["findings"]
    assert elapsed >= 2.0
    assert code == 1
    assert "ledger lock timeout" in stderr
    assert "ledger_lock_timeout" in codes(findings)
    assert Record.load(path).data["effective_state"] == "proposed"


# --- verify entries -----------------------------------------------------------


def verify_entry(**overrides: Any) -> dict[str, Any]:
    entry = {
        "id": "code-says-so",
        "engine": "grep",
        "pattern": "SENTINEL",
        "paths": ["src/x.py"],
        "expect": "match",
        "severity": "warning",
    }
    entry.update(overrides)
    return entry


def test_a_verify_entry_whose_pattern_is_absent_reports_verify_failed(
    run_cli: RunCli, lint_repo: Path
) -> None:
    (lint_repo / "src").mkdir()
    (lint_repo / "src" / "x.py").write_text("value = 1\n", encoding="utf-8")
    write_record(
        lint_repo,
        "D-260908-sound-choice",
        ULID_A,
        verify=[verify_entry()],
    )
    assert run_cli(["index"], lint_repo)[0] == 0

    code, findings = lint(run_cli, lint_repo)

    failed = find(findings, "verify_failed")
    assert failed["severity"] == "warning"
    assert "src/x.py" in failed["message"]
    assert code == 0


def test_a_verify_entry_that_matches_reports_nothing(
    run_cli: RunCli, lint_repo: Path
) -> None:
    (lint_repo / "src").mkdir()
    (lint_repo / "src" / "x.py").write_text("SENTINEL = 1\n", encoding="utf-8")
    write_record(
        lint_repo,
        "D-260908-sound-choice",
        ULID_A,
        verify=[verify_entry()],
    )
    assert run_cli(["index"], lint_repo)[0] == 0

    code, findings = lint(run_cli, lint_repo)

    assert code == 0
    assert findings == []


def test_a_verify_entry_whose_target_is_missing_reports_verify_failed(
    run_cli: RunCli, lint_repo: Path
) -> None:
    write_record(
        lint_repo,
        "D-260908-sound-choice",
        ULID_A,
        verify=[verify_entry(severity="error")],
    )

    code, findings = lint(run_cli, lint_repo)

    assert code == 1
    assert find(findings, "verify_failed")["severity"] == "error"


def test_an_invalid_verify_regex_reports_verify_error(
    run_cli: RunCli, lint_repo: Path
) -> None:
    (lint_repo / "src").mkdir()
    (lint_repo / "src" / "x.py").write_text("value = 1\n", encoding="utf-8")
    write_record(
        lint_repo,
        "D-260908-sound-choice",
        ULID_A,
        verify=[verify_entry(pattern="[unclosed", severity="warning")],
    )

    code, findings = lint(run_cli, lint_repo)

    assert code == 1
    assert find(findings, "verify_error")["severity"] == "error"


def test_a_no_match_verify_entry_fails_when_the_pattern_is_present(
    run_cli: RunCli, lint_repo: Path
) -> None:
    (lint_repo / "src").mkdir()
    (lint_repo / "src" / "x.py").write_text("SENTINEL = 1\n", encoding="utf-8")
    write_record(
        lint_repo,
        "D-260908-sound-choice",
        ULID_A,
        verify=[verify_entry(expect="no-match")],
    )

    _, findings = lint(run_cli, lint_repo)

    assert "verify_failed" in codes(findings)


# --- verify entries: pytest engine (Q4) ---------------------------------------


def pytest_project(repo: Path) -> None:
    """A tiny pytest project inside `repo`, locked so `uv run --frozen` works."""
    (repo / "pyproject.toml").write_text(
        textwrap.dedent(
            """\
            [project]
            name = "verify-target"
            version = "0.1.0"
            requires-python = ">=3.12"
            dependencies = ["pytest"]
            """
        ),
        encoding="utf-8",
    )
    tests_dir = repo / "tests"
    tests_dir.mkdir(exist_ok=True)
    (tests_dir / "test_target.py").write_text(
        textwrap.dedent(
            """\
            import subprocess
            import time
            from pathlib import Path


            def test_ok():
                pass


            def test_broken():
                assert False


            def test_slow():
                time.sleep(5)


            def test_spawn_grandchild_and_sleep():
                child = subprocess.Popen(["sleep", "30"])
                Path("grandchild.pid").write_text(str(child.pid))
                time.sleep(30)
            """
        ),
        encoding="utf-8",
    )
    subprocess.run(["uv", "lock"], cwd=repo, check=True, capture_output=True)


def pytest_entry(**overrides: Any) -> dict[str, Any]:
    entry = {
        "id": "pytest-check",
        "engine": "pytest",
        "target": "tests/test_target.py::test_ok",
        "expect": "pass",
        "severity": "warning",
    }
    entry.update(overrides)
    return entry


def test_a_passing_pytest_verify_entry_reports_nothing(
    run_cli: RunCli, lint_repo: Path
) -> None:
    pytest_project(lint_repo)
    write_record(
        lint_repo,
        "D-260908-sound-choice",
        ULID_A,
        verify=[pytest_entry()],
    )
    assert run_cli(["index"], lint_repo)[0] == 0

    code, findings = lint(run_cli, lint_repo)

    assert code == 0
    assert findings == []


def test_a_failing_pytest_verify_entry_reports_verify_failed(
    run_cli: RunCli, lint_repo: Path
) -> None:
    pytest_project(lint_repo)
    write_record(
        lint_repo,
        "D-260908-sound-choice",
        ULID_A,
        verify=[
            pytest_entry(target="tests/test_target.py::test_broken", severity="error")
        ],
    )

    code, findings = lint(run_cli, lint_repo)

    assert code == 1
    assert find(findings, "verify_failed")["severity"] == "error"


def test_expect_fail_inverts_a_pytest_verify_entry(
    run_cli: RunCli, lint_repo: Path
) -> None:
    pytest_project(lint_repo)
    write_record(
        lint_repo,
        "D-260908-sound-choice",
        ULID_A,
        verify=[
            pytest_entry(target="tests/test_target.py::test_broken", expect="fail")
        ],
    )
    assert run_cli(["index"], lint_repo)[0] == 0

    code, findings = lint(run_cli, lint_repo)

    assert code == 0
    assert findings == []


def test_a_pytest_verify_entry_that_times_out_reports_verify_error(
    run_cli: RunCli, lint_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest_project(lint_repo)
    monkeypatch.setenv("SCRIBE_VERIFY_TIMEOUT", "1")
    write_record(
        lint_repo,
        "D-260908-sound-choice",
        ULID_A,
        verify=[pytest_entry(target="tests/test_target.py::test_slow")],
    )

    code, findings = lint(run_cli, lint_repo)

    assert code == 1
    assert find(findings, "verify_error")["severity"] == "error"


def test_a_pytest_verify_entry_without_a_pytest_project_reports_verify_error(
    run_cli: RunCli, lint_repo: Path
) -> None:
    (lint_repo / "tests").mkdir()
    (lint_repo / "tests" / "test_target.py").write_text(
        "def test_ok():\n    pass\n", encoding="utf-8"
    )
    write_record(
        lint_repo,
        "D-260908-sound-choice",
        ULID_A,
        verify=[pytest_entry()],
    )

    code, findings = lint(run_cli, lint_repo)

    assert code == 1
    assert find(findings, "verify_error")["severity"] == "error"
    assert "invalid_verify" not in codes(findings)


def _forbid_pytest_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make lint's own pytest-spawning `subprocess.Popen` call fail loudly.

    Old code did not validate `target` before spawning, so `pytest --version`
    (a real, exit-0 subprocess) ran and lint reported nothing wrong. New code
    must reject the target in `_pytest_target_problem` before it ever reaches
    `subprocess.Popen` (the verify runner spawns pytest through `Popen`, not
    `subprocess.run`, so it can kill the whole process group on a timeout).
    `subprocess` is one shared module object, and `Store.discover` (store.py)
    also calls `subprocess.run` for `git rev-parse` during the same lint run,
    so this only guards `Popen` and leaves every `subprocess.run` call (git)
    untouched.
    """
    real_popen = subprocess.Popen

    def guarded_popen(command: Any, *args: Any, **kwargs: Any) -> Any:
        if "pytest" in command:
            raise AssertionError(
                "scribe lint must not spawn pytest for a rejected target"
            )
        return real_popen(command, *args, **kwargs)

    monkeypatch.setattr("scribe.lint.subprocess.Popen", guarded_popen)


def test_a_pytest_target_with_an_option_never_runs_pytest(
    run_cli: RunCli, lint_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--version` is not a path; `schema.validate_pytest_target` rejects it
    (leading `-` is an option, not a node id), so `_validate_findings`
    already reports `invalid_verify` for this record and `_verify_findings`
    skips it, never reaching the pytest runner's own (redundant) check.
    The old runner checked only that `target` is a non-empty string, so
    `pytest --version` actually ran, exited 0, and matched `expect: pass`.
    Fails on the old code because the monkeypatch's own assertion fires:
    old code spawns pytest for this target regardless of the pre-existing
    validation error.
    """
    pytest_project(lint_repo)
    _forbid_pytest_subprocess(monkeypatch)
    write_record(
        lint_repo,
        "D-260908-sound-choice",
        ULID_A,
        verify=[pytest_entry(target="--version")],
    )

    code, findings = lint(run_cli, lint_repo)

    assert code == 1
    assert find(findings, "invalid_verify")["severity"] == "error"
    assert "verify_error" not in codes(findings)


def test_a_pytest_target_with_an_absolute_path_never_runs_pytest(
    run_cli: RunCli, lint_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An absolute path is rejected by `schema.validate_pytest_target` (must
    be relative to the repo root), so, like the option case above, the
    record is flagged `invalid_verify` by validate and its verify entry is
    skipped. The old runner had no target check at all and would have
    spawned pytest against `/etc/passwd`; fails on the old code on the
    monkeypatch's assertion, since old code calls `subprocess.Popen`/
    `subprocess.run` for it regardless of the pre-existing validation error.
    """
    pytest_project(lint_repo)
    _forbid_pytest_subprocess(monkeypatch)
    write_record(
        lint_repo,
        "D-260908-sound-choice",
        ULID_A,
        verify=[pytest_entry(target="/etc/passwd")],
    )

    code, findings = lint(run_cli, lint_repo)

    assert code == 1
    assert find(findings, "invalid_verify")["severity"] == "error"
    assert "verify_error" not in codes(findings)


def test_a_valid_pytest_target_still_runs_and_leaves_no_pytest_cache(
    run_cli: RunCli, lint_repo: Path
) -> None:
    """A target `validate_pytest_target` accepts still runs pytest for real
    (no monkeypatch here) and must pass `-p no:cacheprovider`, so linting
    leaves no `.pytest_cache` behind in the linted repository. Fails on the
    old code on the last assertion: the old command had no `-p
    no:cacheprovider`, so pytest wrote `.pytest_cache` at the repo root.
    """
    pytest_project(lint_repo)
    write_record(
        lint_repo,
        "D-260908-sound-choice",
        ULID_A,
        verify=[pytest_entry()],
    )
    assert run_cli(["index"], lint_repo)[0] == 0

    code, findings = lint(run_cli, lint_repo)

    assert code == 0
    assert findings == []
    assert not (lint_repo / ".pytest_cache").exists()


def test_lint_skips_verify_for_a_record_with_an_existing_validate_error(
    run_cli: RunCli, lint_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A record whose `verify` entry itself fails schema validation (a
    pytest target the validator rejects) must not also have that entry
    executed: `_validate_findings` already reported the problem once, and
    running the entry besides risks a second, confusing finding for the
    same root cause. Old code ran `_verify_findings` over every record
    unconditionally, so the pytest-spawning `subprocess.Popen` call
    happened anyway; the monkeypatch's own assertion catches that.
    """
    pytest_project(lint_repo)
    _forbid_pytest_subprocess(monkeypatch)
    write_record(
        lint_repo,
        "D-260908-sound-choice",
        ULID_A,
        verify=[pytest_entry(target="does/not/exist.py::test_ok")],
    )

    code, findings = lint(run_cli, lint_repo)

    assert code == 1
    assert find(findings, "invalid_verify")["severity"] == "error"
    assert "verify_error" not in codes(findings)


def test_a_verify_entry_with_a_non_string_severity_does_not_crash(
    tmp_path: Path,
) -> None:
    """`severity: []` is unhashable; the old `severity not in {...}`
    membership test in `_run_verify_entry` raised `TypeError` before it
    could report anything. New code type-checks first and falls back to
    `error`. Called directly (not through `scribe lint`): schema.py already
    rejects a non-string severity for every engine, and the record-level
    skip added above means `scribe lint` itself never reaches this
    function for such a record; the crash this guards against is still
    real for `_run_verify_entry` as a unit, and for any future caller.
    Fails on the old code with a `TypeError` instead of a clean return.
    """
    (tmp_path / "docs" / "decisions").mkdir(parents=True)
    store = Store(tmp_path)
    entry = {
        "id": "sample",
        "engine": "grep",
        "pattern": "x",
        "paths": ["missing/**"],
        "expect": "match",
        "severity": [],
    }
    findings = _run_verify_entry(store, entry, [], "docs/decisions/D-x.md")
    assert findings[0].severity == "error"
    assert findings[0].code == "verify_failed"


def test_a_pytest_verify_entry_with_a_non_string_severity_does_not_crash(
    tmp_path: Path,
) -> None:
    """The pytest engine's own `severity not in {...}` check in
    `_run_pytest_verify_entry` has the same unhashable-value crash as the
    grep engine above, and is fixed and tested the same way, directly.
    Fails on the old code with a `TypeError` instead of a clean return.
    """
    (tmp_path / "docs" / "decisions").mkdir(parents=True)
    store = Store(tmp_path)
    entry = {
        "id": "sample",
        "engine": "pytest",
        "target": "tests/does_not_exist.py::test_ok",
        "expect": "pass",
        "severity": [],
    }
    findings = _run_pytest_verify_entry(store, entry, "docs/decisions/D-x.md")
    assert findings[0].code == "verify_error"


def test_verify_timeout_env_var_rejects_nan_and_falls_back_to_the_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`nan` parses as a `float` without raising, so the old code's bare
    `except ValueError` let it through as the timeout; `subprocess.run(...,
    timeout=float("nan"))` then raises `ValueError` itself the moment it
    compares against the clock. Fails on the old code: it returns `nan`
    instead of the default.
    """
    monkeypatch.setenv("SCRIBE_VERIFY_TIMEOUT", "nan")
    assert _verify_timeout_seconds() == DEFAULT_VERIFY_TIMEOUT_SECONDS


def test_verify_timeout_env_var_rejects_infinity_and_zero_and_negative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`inf`, `0`, and a negative number all parse as valid `float`s that
    are not a usable subprocess timeout (never times out, or times out
    immediately / before starting). Fails on the old code, which returned
    each of these verbatim instead of the default.
    """
    for raw in ("inf", "-inf", "0", "-5"):
        monkeypatch.setenv("SCRIBE_VERIFY_TIMEOUT", raw)
        assert _verify_timeout_seconds() == DEFAULT_VERIFY_TIMEOUT_SECONDS, raw


def test_a_timed_out_pytest_verify_entry_leaves_no_grandchild_process(
    run_cli: RunCli, lint_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A slow pytest test that itself spawns a subprocess (`sleep 30`) must
    not leave that grandchild running after lint's own timeout fires: the
    old code's `subprocess.run(..., timeout=...)` kills only the direct
    `uv` child on `TimeoutExpired`, orphaning `sleep` (and pytest under it)
    to run out its full duration. New code starts the spawned `uv run
    pytest` in its own session (`start_new_session=True`) and kills the
    whole process group (`os.killpg`) on timeout. Fails on the old code on
    the last assertion: the grandchild `sleep` pid is still alive right
    after lint returns.
    """
    pytest_project(lint_repo)
    monkeypatch.setenv("SCRIBE_VERIFY_TIMEOUT", "8")
    write_record(
        lint_repo,
        "D-260908-sound-choice",
        ULID_A,
        verify=[
            pytest_entry(target="tests/test_target.py::test_spawn_grandchild_and_sleep")
        ],
    )

    code, findings = lint(run_cli, lint_repo)

    assert code == 1
    assert find(findings, "verify_error")["severity"] == "error"
    pid_file = lint_repo / "grandchild.pid"
    for _ in range(100):
        if pid_file.exists():
            break
        time.sleep(0.1)
    assert pid_file.exists(), "the grandchild test never started"
    grandchild_pid = int(pid_file.read_text(encoding="utf-8").strip())
    time.sleep(0.5)
    with pytest.raises(ProcessLookupError):
        os.kill(grandchild_pid, 0)


# --- scratch state ------------------------------------------------------------


def test_pending_ids_that_resolve_to_no_record_are_reported_and_pruned(
    run_cli: RunCli, lint_repo: Path
) -> None:
    write_record(lint_repo, "D-260908-sound-choice", ULID_A)
    ghost = "01M21BVB05VVF1XV54Y66AWV6Z"

    def seed(document: dict[str, Any]) -> None:
        document["sessions"] = {
            "session_test": {
                "started_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "pending_decisions": [ghost, ULID_A],
            }
        }

    update_state(lint_repo, seed)

    _, findings = lint(run_cli, lint_repo)

    pending = find(findings, "duplicate_pending")
    assert pending["severity"] == "info"
    assert ghost in pending["message"]

    state = json.loads(
        (lint_repo / ".claude" / "scribe" / "state.json").read_text(encoding="utf-8")
    )
    assert state["sessions"]["session_test"]["pending_decisions"] == [ULID_A]


# --- acceptance on this repository --------------------------------------------


def test_lint_on_this_repository_has_no_verify_failure() -> None:
    _, findings, records = run_lint(PROJECT_ROOT)

    # The live ledger grows with dogfooding; only the seed floor is fixed.
    assert records >= 3
    assert [
        finding.render()
        for finding in findings
        if finding.code in {"verify_failed", "verify_error"}
    ] == []
