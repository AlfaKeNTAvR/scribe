"""T12: `scribe check --base <ref>`, the CI merge gate (plan 5.4, F11, F17)."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import pytest
from scribe.history_check import check_attestations_append_only

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SPEC_PLAIN = FIXTURES / "new_spec.json"
SPEC_SUPERSEDES = FIXTURES / "check_spec_supersedes.json"
SUCCESSOR_SLUG = "merge-gate-blocks-unreviewed-successors"
RATIFIED_A = "D-260908-unreviewed-may-supersede-ratified"

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


def today_alias(slug: str) -> str:
    stamp = datetime.now(timezone.utc).date().isoformat()[2:].replace("-", "")
    return f"D-{stamp}-{slug}"


def decisions(repo: Path) -> Path:
    return repo / "docs" / "decisions"


def write_source(repo: Path, relative: str, text: str) -> None:
    target = repo / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


@pytest.fixture
def ledger(tmp_repo: Path, run_cli: RunCli) -> Path:
    """`main` carrying the three real records, their attestations and INDEX.md."""
    git(tmp_repo, "checkout", "-q", "-b", "main")
    assert run_cli(["index"], tmp_repo)[0] == 0
    write_source(tmp_repo, "src/x.py", "value = 1\n")
    commit_all(tmp_repo, "chore: Bootstrap the ledger")
    return tmp_repo


@pytest.fixture
def successor_branch(ledger: Path, run_cli: RunCli) -> str:
    """Branch `feat` adding unreviewed B superseding ratified A, index regenerated."""
    git(ledger, "checkout", "-q", "-b", "feat")
    code, _, _ = run_cli(["new", "--spec", str(SPEC_SUPERSEDES)], ledger)
    assert code == 0
    commit_all(ledger, "feat: Supersede the ratified decision")
    return today_alias(SUCCESSOR_SLUG)


def check(run_cli: RunCli, repo: Path, base: str = "main") -> tuple[int, str]:
    code, stdout, _ = run_cli(["check", "--base", base], repo)
    return code, stdout


# --- the supersede gate (plan 5.4 rule 1) ------------------------------------


def test_unreviewed_successor_of_a_ratified_record_fails(
    run_cli: RunCli, ledger: Path, successor_branch: str
) -> None:
    code, stdout = check(run_cli, ledger)

    assert code == 1
    assert f"{successor_branch} supersedes ratified {RATIFIED_A}" in stdout
    assert "introduces or depends on it" in stdout


def test_ratifying_the_successor_makes_the_check_pass(
    run_cli: RunCli, ledger: Path, successor_branch: str
) -> None:
    """F17: the verdict, its attestation, the history and the index must be committed."""
    base = git(ledger, "rev-parse", "main")
    code, _, _ = run_cli(["ratify", successor_branch, "--by", "@tester"], ledger)
    assert code == 0
    commit_all(ledger, "chore: Ratify the successor")

    code, stdout = check(run_cli, ledger)

    assert (code, stdout.strip()) == (0, "scribe check: ok")
    assert check_attestations_append_only(base, ledger) == []


def test_a_plain_unreviewed_record_passes(run_cli: RunCli, ledger: Path) -> None:
    git(ledger, "checkout", "-q", "-b", "plain")
    assert run_cli(["new", "--spec", str(SPEC_PLAIN)], ledger)[0] == 0
    commit_all(ledger, "docs: Record an ordinary decision")

    code, stdout = check(run_cli, ledger)

    assert (code, stdout.strip()) == (0, "scribe check: ok")


def test_a_path_matching_affects_fails_when_the_successor_is_at_the_base(
    run_cli: RunCli, ledger: Path
) -> None:
    """F11: B is already on `main`; the branch only edits a file B's affects match."""
    assert run_cli(["new", "--spec", str(SPEC_SUPERSEDES)], ledger)[0] == 0
    successor = today_alias(SUCCESSOR_SLUG)
    commit_all(ledger, "feat: Supersede the ratified decision")
    git(ledger, "checkout", "-q", "-b", "code-only")
    write_source(ledger, "src/x.py", "value = 2\n")
    commit_all(ledger, "feat: Follow the unreviewed decision")

    code, stdout = check(run_cli, ledger)

    assert code == 1
    assert f"{successor} supersedes ratified {RATIFIED_A}" in stdout
    assert git(ledger, "diff", "--name-only", "main...HEAD") == "src/x.py"


def test_a_decision_trailer_in_the_range_fails(run_cli: RunCli, ledger: Path) -> None:
    """The third arm of rule 1: the range claims the unreviewed successor by trailer."""
    assert run_cli(["new", "--spec", str(SPEC_SUPERSEDES)], ledger)[0] == 0
    successor = today_alias(SUCCESSOR_SLUG)
    commit_all(ledger, "feat: Supersede the ratified decision")
    git(ledger, "checkout", "-q", "-b", "trailered")
    write_source(ledger, "notes.md", "outside every affects pattern\n")
    commit_all(ledger, f"docs: Note the choice\n\nDecision: {successor}\n")

    code, stdout = check(run_cli, ledger)

    assert code == 1
    assert f"{successor} supersedes ratified {RATIFIED_A}" in stdout


@pytest.mark.parametrize(
    "affects,changed,denied",
    [
        ([], "src/x.py", True),
        ([{"type": "action", "pattern": "npm-publish"}], "src/x.py", True),
        ([{"type": "package", "pattern": "scribe"}], "src/x.py", True),
        (
            [
                {"type": "path", "pattern": "src/**"},
                {"type": "path", "pattern": "src/x.py", "negate": True},
            ],
            "src/x.py",
            False,
        ),
        ([{"type": "path", "pattern": "docs/**"}], "docs/decisions/notes.md", False),
        ([], "docs/decisions/notes.md", False),
    ],
)
def test_dependency_gate_uses_implementation_paths(
    run_cli: RunCli, ledger: Path, affects: list, changed: str, denied: bool
) -> None:
    spec = json.loads(SPEC_SUPERSEDES.read_text(encoding="utf-8"))
    spec["affects"] = affects
    spec_path = ledger / "spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    assert run_cli(["new", "--spec", str(spec_path)], ledger)[0] == 0
    commit_all(ledger, "docs: Existing successor")
    git(ledger, "checkout", "-q", "-b", "dependency")
    write_source(ledger, changed, "changed\n")
    commit_all(ledger, "feat: Follow decision without a trailer")

    code, stdout = check(run_cli, ledger)

    assert code == int(denied), stdout
    assert ("supersedes ratified" in stdout) is denied


@pytest.mark.parametrize("suffix", ["\n", " ", "\t\n"])
def test_body_trailing_bytes_are_immutable(suffix: str) -> None:
    from scribe.history_check import compare_record_versions

    original = "---\ntitle: Body\n---\n\n# Body\n"
    problems = compare_record_versions(original, original + suffix)
    assert any(p.code == "immutable_changed" and "body" in p.message for p in problems)


# --- ledger integrity (plan 5.4 rules 4 and 5) -------------------------------


def test_deleting_an_attestation_line_fails(run_cli: RunCli, ledger: Path) -> None:
    git(ledger, "checkout", "-q", "-b", "tamper")
    path = decisions(ledger) / "RATIFICATIONS.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    path.write_text("".join(lines[:-1]), encoding="utf-8")
    commit_all(ledger, "chore: Drop an attestation")

    code, stdout = check(run_cli, ledger)

    assert code == 1
    assert "attestations_not_append_only" in stdout
    assert "RATIFICATIONS.jsonl is not append-only relative to the base" in stdout


def test_rewriting_a_record_body_fails_with_immutable_changed(
    run_cli: RunCli, ledger: Path
) -> None:
    git(ledger, "checkout", "-q", "-b", "rewrite")
    path = decisions(ledger) / f"{RATIFIED_A}.md"
    path.write_text(
        path.read_text(encoding="utf-8") + "\n### Rewritten after the fact\n",
        encoding="utf-8",
    )
    commit_all(ledger, "docs: Rewrite a record body")

    code, stdout = check(run_cli, ledger)

    assert code == 1
    assert "immutable_changed" in stdout
    assert "the record body changed since the base" in stdout


def test_rewriting_history_fails_with_history_rewritten(
    run_cli: RunCli, ledger: Path
) -> None:
    from scribe.record import Record

    git(ledger, "checkout", "-q", "-b", "history")
    path = decisions(ledger) / f"{RATIFIED_A}.md"
    record = Record.load(path)
    record.data["history"] = record.data["history"][1:]
    record.save()
    commit_all(ledger, "docs: Drop a history entry")

    code, stdout = check(run_cli, ledger)

    assert code == 1
    assert "history_rewritten" in stdout


def test_appending_a_contradictory_attestation_fails_an_unchanged_record(
    run_cli: RunCli, ledger: Path
) -> None:
    """V5: every current record is validated, not only the ones the diff touched.

    Only `RATIFICATIONS.jsonl` changes here; `RATIFIED_A`'s own file is
    untouched. The old code validated changed record files only, so this
    passed; the fix validates every current record, so the record's now
    unattested `ratified` state fails the check.
    """
    from scribe.record import Record

    git(ledger, "checkout", "-q", "-b", "contradict")
    record = Record.load(decisions(ledger) / f"{RATIFIED_A}.md")
    line = {
        "id": record.data["id"],
        "alias": RATIFIED_A,
        "verdict": "rejected",
        "by": "@tester",
        "at": "2026-09-08T21:00:00Z",
        "body_sha256": record.body_sha256(),
        "via": "cli",
    }
    path = decisions(ledger) / "RATIFICATIONS.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line) + "\n")
    commit_all(ledger, "chore: Append a contradictory rejection")

    code, stdout = check(run_cli, ledger)

    assert code == 1
    assert f"{RATIFIED_A}.md: unattested_review_state" in stdout


# --- record deletion (plan 5.4 rule 6, V6, supersedes I45) -------------------


def test_deleting_a_standalone_ratified_record_fails(
    run_cli: RunCli, ledger: Path
) -> None:
    git(ledger, "checkout", "-q", "-b", "delete-standalone")
    (decisions(ledger) / f"{RATIFIED_A}.md").unlink()
    commit_all(ledger, "chore: Delete a ratified record")

    code, stdout = check(run_cli, ledger)

    assert code == 1
    assert f"record_deleted: {RATIFIED_A}" in stdout
    assert "retire it with expired or backtracked" in stdout


def test_deleting_an_entire_supersession_chain_fails_for_each_alias(
    run_cli: RunCli, ledger: Path
) -> None:
    """Both the predecessor and its successor must fail, each by its own alias."""
    assert run_cli(["new", "--spec", str(SPEC_SUPERSEDES)], ledger)[0] == 0
    successor = today_alias(SUCCESSOR_SLUG)
    assert run_cli(["ratify", successor, "--by", "@tester"], ledger)[0] == 0
    commit_all(ledger, "feat: Establish a supersession chain")

    git(ledger, "checkout", "-q", "-b", "delete-chain")
    (decisions(ledger) / f"{RATIFIED_A}.md").unlink()
    (decisions(ledger) / f"{successor}.md").unlink()
    commit_all(ledger, "chore: Delete both records in the chain")

    code, stdout = check(run_cli, ledger, base="main")

    assert code == 1
    assert f"record_deleted: {RATIFIED_A}" in stdout
    assert f"record_deleted: {successor}" in stdout


def test_renaming_a_record_file_counts_as_deleted_plus_added(
    run_cli: RunCli, ledger: Path
) -> None:
    """A rename is a deletion of the old path; the new path is an ordinary addition.

    There is no rename detection here (tree listings, not a diff heuristic),
    and this repo's `alias` is not updated to match, so the new path also
    fails its own `alias_filename_mismatch` validation; that second failure
    is not this test's concern.
    """
    git(ledger, "checkout", "-q", "-b", "rename")
    old_path = decisions(ledger) / f"{RATIFIED_A}.md"
    new_path = decisions(ledger) / "D-260908-renamed-record.md"
    old_path.rename(new_path)
    commit_all(ledger, "chore: Rename a record file")

    code, stdout = check(run_cli, ledger)

    assert code == 1
    assert f"record_deleted: {RATIFIED_A}" in stdout


# --- dirty ledger guard, base-tip authority (plan 5.4, V3) ------------------


def test_a_dirty_ledger_is_refused(run_cli: RunCli, ledger: Path) -> None:
    (decisions(ledger) / "scratch.md").write_text("dirty\n", encoding="utf-8")

    code, stdout, _ = run_cli(["check", "--base", "main"], ledger)

    assert code == 1
    assert "docs/decisions" in stdout
    assert "uncommitted changes" in stdout
    assert "--allow-dirty" in stdout


def test_a_dirty_ledger_is_allowed_with_the_flag(run_cli: RunCli, ledger: Path) -> None:
    (decisions(ledger) / "scratch.md").write_text("dirty\n", encoding="utf-8")

    code, stdout, _ = run_cli(["check", "--base", "main", "--allow-dirty"], ledger)

    assert (code, stdout.strip()) == (0, "scribe check: ok")


def test_dirty_changes_outside_docs_decisions_do_not_block_the_check(
    run_cli: RunCli, ledger: Path
) -> None:
    write_source(ledger, "src/scratch.py", "value = 1\n")

    code, stdout, _ = run_cli(["check", "--base", "main"], ledger)

    assert (code, stdout.strip()) == (0, "scribe check: ok")


def test_a_ratification_added_to_the_target_after_the_fork_is_honoured(
    run_cli: RunCli, ledger: Path
) -> None:
    """V3: the predecessor-was-ratified question asks the base ref's tip, not
    the merge base. This predecessor is unreviewed at the fork point (where
    `feat` branches off `main`) and only ratified on `main` afterward; the old
    code substituted the merge base for that question and never saw it. The
    changed-paths/commits range for "introduces or depends on it" still comes
    from the merge base, so `feat`'s own delta is what is being asked about.
    """
    from scribe.newrecord import slugify

    predecessor_title = json.loads(SPEC_PLAIN.read_text(encoding="utf-8"))["title"]
    predecessor_alias = today_alias(slugify(predecessor_title))
    assert run_cli(["new", "--spec", str(SPEC_PLAIN)], ledger)[0] == 0
    commit_all(ledger, "docs: Record the predecessor, still unreviewed")

    git(ledger, "checkout", "-q", "-b", "feat")
    spec = json.loads(SPEC_SUPERSEDES.read_text(encoding="utf-8"))
    spec["supersedes"] = predecessor_alias
    spec_path = ledger / "successor_spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    assert run_cli(["new", "--spec", str(spec_path)], ledger)[0] == 0
    successor_alias = today_alias(SUCCESSOR_SLUG)
    commit_all(ledger, "feat: Supersede the not-yet-ratified predecessor")

    git(ledger, "checkout", "-q", "main")
    assert run_cli(["ratify", predecessor_alias, "--by", "@tester"], ledger)[0] == 0
    commit_all(ledger, "chore: Ratify the predecessor on main, after the fork")

    git(ledger, "checkout", "-q", "feat")
    code, stdout = check(run_cli, ledger)

    assert code == 1
    assert f"{successor_alias} supersedes ratified {predecessor_alias}" in stdout
    assert "introduces or depends on it" in stdout


# --- argument handling -------------------------------------------------------


def test_an_unknown_base_ref_exits_one(run_cli: RunCli, ledger: Path) -> None:
    code, stdout = check(run_cli, ledger, base="no-such-ref")

    assert code == 1
    assert stdout.strip() == "unknown base ref: no-such-ref"


# --- V3(b): git failures must never pass vacuously --------------------------


def _fake_git_that_fails_one_subcommand(
    module: object, subcommand: str, stderr: str
) -> Callable[..., subprocess.CompletedProcess[str]]:
    """A `gitutil._git` replacement that fails only `git <subcommand> ...`.

    Every other subcommand is delegated to the real `_git`, so the rest of
    `scribe check` runs against the real repository, exactly as it would when
    only one git call in the range computation hits a bad ref or a missing
    object.
    """
    original = module._git

    def fake(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
        if args[:1] == (subcommand,):
            return subprocess.CompletedProcess(
                args=["git", *args], returncode=128, stdout="", stderr=stderr
            )
        return original(cwd, *args)

    return fake


def test_a_git_failure_computing_the_range_fails_the_check(
    run_cli: RunCli,
    ledger: Path,
    successor_branch: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(a): a git failure while computing the range is an explicit check
    failure, not a vacuous pass.

    Fails on the old code: `diff_names` returned `[]` on a git error, so
    `changed_paths` was empty; `_supersede_gate` (rule 1) then saw no changed
    path, no depended-on path, and no trailer, and the unreviewed successor
    from `successor_branch` (which would otherwise fail this check, see
    `test_unreviewed_successor_of_a_ratified_record_fails`) passed with
    `scribe check: ok`.
    """
    import scribe.gitutil as gitutil_module

    monkeypatch.setattr(
        gitutil_module,
        "_git",
        _fake_git_that_fails_one_subcommand(
            gitutil_module, "diff", "fatal: bad object deadbeef\n"
        ),
    )

    code, stdout = check(run_cli, ledger)

    assert code == 1
    assert stdout.strip() == (
        "git failed while computing the changed paths between "
        f"{git(ledger, 'merge-base', 'main', 'HEAD')} and HEAD: "
        "fatal: bad object deadbeef"
    )


def test_a_merge_base_failure_fails_the_check_instead_of_falling_back_to_base(
    run_cli: RunCli,
    ledger: Path,
    successor_branch: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(b): a `merge_base` failure must fail the check, not silently fall back
    to `base` (check.py:192 before the fix).

    Fails on the old code: `gitutil.merge_base(base, "HEAD", root) or base`
    substituted `base` itself for the fork point, so `diff_names(base, "HEAD")`
    and `rev_list_range(base, "HEAD")` still computed a real (if wrong) range
    and the unreviewed successor from `successor_branch` still failed the
    check for the wrong reason; the merge-base failure itself was silent. This
    test's fake makes `merge-base` fail with a real git error, and asserts the
    check reports it rather than reaching rule 1 at all.
    """
    import scribe.gitutil as gitutil_module

    monkeypatch.setattr(
        gitutil_module,
        "_git",
        _fake_git_that_fails_one_subcommand(
            gitutil_module, "merge-base", "fatal: not a valid object name\n"
        ),
    )

    code, stdout = check(run_cli, ledger)

    assert code == 1
    assert stdout.strip() == (
        "git failed while computing the merge base of main and HEAD: "
        "fatal: not a valid object name"
    )


def test_a_dirty_check_failure_fails_the_check_instead_of_reading_clean(
    run_cli: RunCli, ledger: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed `git status` must not be read as "the ledger is clean".

    Fails on the old code: `is_dirty` returned `bool(result.stdout.strip())`
    unconditionally, and a failed `git status` has empty stdout, so
    `run_check` read the failure as "not dirty" and went on to `scribe check:
    ok` even though it never actually knew whether `docs/decisions` was
    clean.
    """
    import scribe.gitutil as gitutil_module

    monkeypatch.setattr(
        gitutil_module,
        "_git",
        _fake_git_that_fails_one_subcommand(
            gitutil_module, "status", "fatal: index file corrupt\n"
        ),
    )

    code, stdout = check(run_cli, ledger)

    assert code == 1
    assert stdout.strip() == (
        "git failed while computing the status of docs/decisions: "
        "fatal: index file corrupt"
    )
