"""Deferred behaviour, stated as skip-marked tests (plan 5.2, 5.4, 7 item 7, F13).

Each test names the behaviour that is not implemented in this run and the
condition under which it is switched on. No task may un-skip or modify another
task's test here.
"""

import json
import subprocess
from pathlib import Path

import pytest
from scribe.record import Record

VERIFY_ACTIVATION = (
    "F13: enable after 14 days of dogfood `scribe lint` with zero `verify_error`"
)


@pytest.mark.skip(reason=VERIFY_ACTIVATION)
def test_commit_msg_runs_verify_on_staged_content() -> None:
    """commit-msg runs each referenced record's `verify` entries against the staged
    content (README 10.4 "Commit validation") and warns, or fails under enforce,
    on `verify_failed`. Until then only `scribe lint` runs `verify`."""
    raise AssertionError(
        "deferred: commit-msg does not run verify on staged content yet"
    )


@pytest.mark.skip(reason=VERIFY_ACTIVATION)
def test_check_runs_verify_on_committed_content() -> None:
    """`scribe check --base <ref>` runs each changed record's `verify` entries against
    the committed content of the range and fails on `verify_failed` (plan 5.4, the
    "Not implemented (F13)" paragraph). Until then only `scribe lint` runs `verify`,
    so a branch can land code that contradicts its own record's verify entry."""
    raise AssertionError(
        "deferred: scribe check does not run verify on committed content yet"
    )


@pytest.mark.skip(
    reason="deferred: two-worktree supersede test, enable before turning any gate to enforce"
)
def test_two_worktree_supersede(tmp_repo: Path, run_cli, run_hook) -> None:
    """Plan 7 item 4: branch-local supersession, ratification and merge check."""
    worktree_a = tmp_repo
    worktree_b = tmp_repo.parent / "feat-worktree"
    governed_path = "src/two_worktree/example.py"

    def git(root: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            text=True,
            capture_output=True,
            check=True,
        )
        return result.stdout.strip()

    def cli(root: Path, *args: str) -> str:
        code, stdout, stderr = run_cli(list(args), root)
        assert code == 0, (stdout, stderr)
        return stdout

    def commit(root: Path, message: str) -> None:
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", message)

    def create(root: Path, title: str, predecessor: str | None = None) -> Record:
        spec = json.loads(
            (Path(__file__).parent / "fixtures" / "new_spec.json").read_text(
                encoding="utf-8"
            )
        )
        spec["title"] = title
        spec["affects"] = [{"type": "path", "pattern": governed_path}]
        if predecessor is not None:
            spec["supersedes"] = predecessor
        spec_path = tmp_repo.parent / "worktree-spec.json"
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        store = root / "docs" / "decisions"
        before = set(store.glob("D-*.md"))
        cli(root, "new", "--spec", str(spec_path))
        created = set(store.glob("D-*.md")) - before
        assert len(created) == 1
        return Record.load(created.pop())

    def injected_aliases(root: Path) -> set[str]:
        result = run_hook(
            "pre-tool-use-edit",
            {
                "hook_event_name": "PreToolUse",
                "session_id": f"two-worktree-{root.name}",
                "cwd": str(root),
                "tool_name": "Edit",
                "tool_input": {"file_path": str(root / governed_path)},
            },
            root,
        )
        assert result.returncode == 0, result.stderr
        context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
        assert "These are retrieval candidates" in context
        # X can appear in Y's supersedes annotation, but must not be a candidate.
        return {
            line.split()[1] for line in context.splitlines() if line.startswith("- ")
        }

    git(worktree_a, "checkout", "-q", "-b", "main")
    (worktree_a / ".gitignore").write_text(".claude/scribe/\n", encoding="utf-8")
    source = worktree_a / governed_path
    source.parent.mkdir(parents=True)
    source.write_text("value = 1\n", encoding="utf-8")
    x = create(worktree_a, "Worktree X governs the example")
    x_alias = x.data["alias"]
    cli(worktree_a, "ratify", x_alias, "--by", "@tester")
    assert Record.load(x.path).data["review_state"] == "ratified"
    commit(worktree_a, "docs: Ratify X on main")
    base = git(worktree_a, "rev-parse", "HEAD")

    git(worktree_a, "worktree", "add", "-q", "-b", "feat", str(worktree_b), "main")
    y = create(worktree_b, "Worktree Y supersedes X", x.data["id"])
    y_alias = y.data["alias"]
    assert y.data["review_state"] == "unreviewed"
    assert y.data["supersedes"] == x.data["id"]
    commit(worktree_b, "docs: Propose Y on feat")

    cli(worktree_b, "index")
    index = (worktree_b / "docs" / "decisions" / "INDEX.md").read_text(
        encoding="utf-8"
    )
    queue = index.split("## Review queue", 1)[1].split("## Active decisions", 1)[0]
    assert next(line for line in queue.splitlines() if line.startswith("1. ")).startswith(
        f"1. [supersedes ratified] {y_alias} |"
    )
    retired = index.split("## Retired", 1)[1]
    assert f"{x_alias} | superseded by {y_alias}" in retired
    assert Record.load(worktree_b / "docs" / "decisions" / x.path.name).data[
        "effective_state"
    ] == "superseded"
    code, stdout, stderr = run_cli(["check", "--base", "main"], worktree_b)
    assert code == 1, (stdout, stderr)
    assert f"{y_alias} supersedes ratified {x_alias}" in stdout

    # Before the merge the same governed path retrieves a different local ledger.
    assert injected_aliases(worktree_b) == {y_alias}
    assert injected_aliases(worktree_a) == {x_alias}
    assert Record.load(x.path).data["effective_state"] == "proposed"
    assert not (worktree_a / "docs" / "decisions" / y.path.name).exists()

    cli(worktree_b, "ratify", y_alias, "--by", "@tester")
    assert Record.load(y.path).data["review_state"] == "ratified"
    commit(worktree_b, "docs: Ratify Y with attestation and index")
    assert cli(worktree_b, "check", "--base", "main").strip() == "scribe check: ok"
    git(worktree_a, "merge", "--ff-only", "feat")
    assert git(worktree_a, "rev-parse", "HEAD") == git(worktree_b, "rev-parse", "HEAD")
    # Use pre-merge main so this checks the merged range, not main...main.
    assert cli(worktree_a, "check", "--base", base).strip() == "scribe check: ok"
    assert injected_aliases(worktree_a) == {y_alias}
