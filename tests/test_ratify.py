"""T9: `scribe ratify` and `scribe reject` (plan 3.8 matrix, 4.10 order, F1/F5/F7/F8)."""

import fcntl
import json
import os
import re
import shlex
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import pytest
from scribe import ratify as ratify_module
from scribe.record import Record

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC_SUPERSEDES = PROJECT_ROOT / "tests" / "fixtures" / "new_spec_supersedes.json"
SKILLS = [PROJECT_ROOT / "skills" / name / "SKILL.md" for name in ("ratify", "reject")]

# Real record A (ratified, affects src/scribe/index.py) and its future successor B.
RATIFIED_A = "D-260908-unreviewed-may-supersede-ratified"
SUCCESSOR_SLUG = "scribe-new-reconciles-supersession"
STAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
VERDICT_FIELDS = ["review_state", "ratified_by", "ratified_at"]

RunCli = Callable[..., tuple[int, str, str]]
RunHook = Callable[..., subprocess.CompletedProcess[str]]


# --- helpers -----------------------------------------------------------------


def decisions(root: Path) -> Path:
    return root / "docs" / "decisions"


def record_path(root: Path, alias: str) -> Path:
    return decisions(root) / f"{alias}.md"


def load(root: Path, alias: str) -> Record:
    return Record.load(record_path(root, alias))


def attestation_lines(root: Path) -> list[dict]:
    text = (decisions(root) / "RATIFICATIONS.jsonl").read_text(encoding="utf-8")
    assert text.endswith("\n")
    return [json.loads(line) for line in text.splitlines()]


def entries(record: Record, event: str) -> list[dict]:
    return [item for item in record.data["history"] if item.get("event") == event]


def make_unreviewed(root: Path, alias: str, suffix: str) -> Path:
    """Clone real record A as an unreviewed record with a fresh ULID and alias."""
    record = Record.load(record_path(root, RATIFIED_A))
    record.path = record_path(root, alias)
    base = "01M21BV91NZSW1HMJ127KZAA"
    record.data.update(
        {
            "id": base[: 26 - len(suffix)] + suffix,
            "alias": alias,
            "review_state": "unreviewed",
            "ratified_by": None,
            "ratified_at": None,
            "history": record.data["history"][:1],
        }
    )
    record.save()
    return record.path


def validate(run_cli: RunCli, root: Path) -> tuple[int, str]:
    code, stdout, _ = run_cli(["validate", str(decisions(root))], root)
    return code, stdout


def today_alias(slug: str) -> str:
    stamp = datetime.now(timezone.utc).date().isoformat()[2:].replace("-", "")
    return f"D-{stamp}-{slug}"


def edit_payload(root: Path, relative: str) -> dict:
    return {
        "session_id": "session_ratify_test",
        "cwd": str(root),
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(root / relative),
            "old_string": "a",
            "new_string": "b",
        },
    }


@pytest.fixture
def unreviewed(tmp_repo: Path) -> str:
    alias = "D-260908-unreviewed-fixture"
    make_unreviewed(tmp_repo, alias, "NR01")
    return alias


# --- matrix rows ---------------------------------------------------------------


def test_ratify_sets_state_three_entries_and_one_cli_line(
    run_cli: RunCli, tmp_repo: Path, unreviewed: str
) -> None:
    before = len(attestation_lines(tmp_repo))
    code, stdout, _ = run_cli(
        ["ratify", unreviewed, "--by", "@tester", "--note", "t"], tmp_repo
    )
    record = load(tmp_repo, unreviewed)
    ratified = entries(record, "ratified")
    lines = attestation_lines(tmp_repo)

    assert code == 0
    assert stdout.strip() == f"ratified {unreviewed} by @tester (via cli)"
    assert record.data["review_state"] == "ratified"
    assert record.data["ratified_by"] == "@tester"
    assert STAMP_RE.fullmatch(record.data["ratified_at"])
    assert [item["field"] for item in ratified] == VERDICT_FIELDS
    assert {item["by"] for item in ratified} == {"@tester"}
    assert len(lines) == before + 1
    last = lines[-1]
    assert last["id"] == record.data["id"]
    assert last["alias"] == unreviewed
    assert (last["verdict"], last["by"], last["via"], last["note"]) == (
        "ratified",
        "@tester",
        "cli",
        "t",
    )
    assert last["body_sha256"] == record.body_sha256()
    assert last["at"] == record.data["ratified_at"]
    assert validate(run_cli, tmp_repo) == (0, "4 records, 0 errors, 0 warnings\n")


def test_ratify_again_is_idempotent(
    run_cli: RunCli, tmp_repo: Path, unreviewed: str
) -> None:
    run_cli(["ratify", unreviewed, "--by", "@tester", "--note", "t"], tmp_repo)
    lines_before = attestation_lines(tmp_repo)
    history_before = load(tmp_repo, unreviewed).data["history"]

    code, stdout, _ = run_cli(
        ["ratify", unreviewed, "--by", "@tester", "--note", "t"], tmp_repo
    )

    assert code == 0
    assert stdout.startswith("already ratified by @tester at 20")
    assert attestation_lines(tmp_repo) == lines_before
    assert load(tmp_repo, unreviewed).data["history"] == history_before


def test_reject_then_ratify_each_append_a_line_and_three_entries(
    run_cli: RunCli, tmp_repo: Path
) -> None:
    before = len(attestation_lines(tmp_repo))

    code, stdout, _ = run_cli(["reject", RATIFIED_A, "--by", "@tester"], tmp_repo)
    rejected = load(tmp_repo, RATIFIED_A)
    reject_entries = entries(rejected, "rejected")
    assert code == 0
    assert stdout.strip() == f"rejected {RATIFIED_A} by @tester (via cli)"
    assert rejected.data["review_state"] == "rejected"
    assert rejected.data["effective_state"] == "proposed"
    assert [item["field"] for item in reject_entries] == VERDICT_FIELDS
    assert [item["old"] for item in reject_entries[:2]] == ["ratified", "@nikita"]
    assert len(attestation_lines(tmp_repo)) == before + 1
    assert attestation_lines(tmp_repo)[-1]["verdict"] == "rejected"
    assert validate(run_cli, tmp_repo)[0] == 0

    code, _, _ = run_cli(["ratify", RATIFIED_A, "--by", "@tester"], tmp_repo)
    reratified = load(tmp_repo, RATIFIED_A)
    ratify_entries = entries(reratified, "ratified")
    assert code == 0
    assert reratified.data["review_state"] == "ratified"
    # Three from the hand-written history, three from this reversal (same @tester both times).
    assert len(ratify_entries) == 6
    assert [item["old"] for item in ratify_entries[3:5]] == ["rejected", "@tester"]
    assert len(attestation_lines(tmp_repo)) == before + 2
    assert attestation_lines(tmp_repo)[-1]["verdict"] == "ratified"
    assert validate(run_cli, tmp_repo)[0] == 0


def test_reject_twice_prints_already_rejected(run_cli: RunCli, tmp_repo: Path) -> None:
    run_cli(["reject", RATIFIED_A, "--by", "@tester"], tmp_repo)
    count = len(attestation_lines(tmp_repo))
    code, stdout, _ = run_cli(["reject", RATIFIED_A, "--by", "@tester"], tmp_repo)
    assert code == 0
    assert stdout.startswith("already rejected by @tester at ")
    assert len(attestation_lines(tmp_repo)) == count


def test_unknown_record_exits_one_and_writes_nothing(
    run_cli: RunCli, tmp_repo: Path
) -> None:
    lines = attestation_lines(tmp_repo)
    code, stdout, _ = run_cli(["ratify", "D-000000-nope", "--by", "@tester"], tmp_repo)
    assert code == 1
    assert "unknown record: D-000000-nope" in stdout
    assert attestation_lines(tmp_repo) == lines


def test_by_defaults_to_git_user_name_and_is_normalized(
    run_cli: RunCli, tmp_repo: Path, unreviewed: str
) -> None:
    other = "D-260908-unreviewed-second"
    make_unreviewed(tmp_repo, other, "NR02")

    run_cli(["ratify", unreviewed, "--via", "skill", "free", "text", "note"], tmp_repo)
    run_cli(["ratify", other, "--by", "Nikita Boguslavskii"], tmp_repo)
    first, second = attestation_lines(tmp_repo)[-2:]

    assert load(tmp_repo, unreviewed).data["ratified_by"] == "@scribe"
    assert (first["by"], first["via"], first["note"]) == (
        "@scribe",
        "skill",
        "free text note",
    )
    assert second["by"] == "@nikita"


# --- validator rule 6 ------------------------------------------------------------


def test_hand_edited_ratified_state_is_unattested(
    run_cli: RunCli, tmp_repo: Path, unreviewed: str
) -> None:
    record = load(tmp_repo, unreviewed)
    record.data.update(
        {
            "review_state": "ratified",
            "ratified_by": "@forger",
            "ratified_at": "2026-09-08T21:00:00Z",
        }
    )
    record.save()
    code, stdout = validate(run_cli, tmp_repo)
    assert code == 1
    assert "unattested_review_state" in stdout


@pytest.mark.parametrize("verb", ["ratify", "reject"])
def test_state_behind_diagnostic_command_parses_and_heals(
    run_cli: RunCli, tmp_repo: Path, unreviewed: str, verb: str
) -> None:
    path = record_path(tmp_repo, unreviewed)
    original = path.read_text(encoding="utf-8")
    run_cli([verb, unreviewed, "--by", "@tester"], tmp_repo)
    count = len(attestation_lines(tmp_repo))
    path.write_text(original, encoding="utf-8")

    code, stdout = validate(run_cli, tmp_repo)
    assert code == 1
    match = re.search(
        rf"state_behind_attestation: run (scribe \w+ {re.escape(unreviewed)}) again",
        stdout,
    )
    assert match is not None

    suggested = shlex.split(match.group(1))
    code, stdout, _ = run_cli([*suggested[1:], "--by", "@tester"], tmp_repo)
    assert code == 0
    assert stdout.startswith(f"{ratify_module.VERDICTS[verb]} {unreviewed} by @tester")
    assert len(attestation_lines(tmp_repo)) == count
    assert (
        load(tmp_repo, unreviewed).data["review_state"] == ratify_module.VERDICTS[verb]
    )
    assert validate(run_cli, tmp_repo)[0] == 0


def test_recovery_uses_actor_and_timestamp_from_attestation(
    run_cli: RunCli, tmp_repo: Path, unreviewed: str
) -> None:
    original = record_path(tmp_repo, unreviewed).read_text(encoding="utf-8")
    attested_at = "2026-09-08T21:00:00Z"
    run_cli(["ratify", unreviewed, "--by", "@alice", "--at", attested_at], tmp_repo)
    count = len(attestation_lines(tmp_repo))
    record_path(tmp_repo, unreviewed).write_text(original, encoding="utf-8")

    code, stdout, _ = run_cli(
        [
            "ratify",
            unreviewed,
            "--by",
            "@bob",
            "--at",
            "2026-09-09T01:00:00Z",
        ],
        tmp_repo,
    )
    recovered = load(tmp_repo, unreviewed)

    assert code == 0
    assert stdout.startswith(f"ratified {unreviewed} by @alice")
    assert len(attestation_lines(tmp_repo)) == count
    assert recovered.data["ratified_by"] == "@alice"
    assert recovered.data["ratified_at"] == attested_at
    assert entries(recovered, "ratified")[-1]["at"] == "2026-09-09T01:00:00Z"


def test_matching_record_with_contradictory_latest_attestation_is_repaired(
    run_cli: RunCli, tmp_repo: Path, unreviewed: str
) -> None:
    run_cli(
        [
            "ratify",
            unreviewed,
            "--by",
            "@alice",
            "--at",
            "2026-09-08T21:00:00Z",
        ],
        tmp_repo,
    )
    record = load(tmp_repo, unreviewed)
    contradictory = {
        "id": record.data["id"],
        "alias": unreviewed,
        "verdict": "rejected",
        "by": "@carol",
        "at": "2026-09-09T01:00:00Z",
        "body_sha256": record.body_sha256(),
        "via": "cli",
        "note": "",
    }
    ratify_module.append_attestation(ratify_module.Store(tmp_repo), contradictory)
    count = len(attestation_lines(tmp_repo))

    code, stdout, _ = run_cli(
        [
            "ratify",
            unreviewed,
            "--by",
            "@bob",
            "--at",
            "2026-09-09T02:00:00Z",
        ],
        tmp_repo,
    )

    assert code == 0
    assert stdout == f"ratified {unreviewed} by @bob (via cli)\n"
    assert len(attestation_lines(tmp_repo)) == count + 1
    assert attestation_lines(tmp_repo)[-1]["verdict"] == "ratified"
    assert load(tmp_repo, unreviewed).data["ratified_by"] == "@bob"
    assert validate(run_cli, tmp_repo)[0] == 0


# --- F1 end to end ---------------------------------------------------------------


def test_rejecting_the_successor_restores_the_predecessor(
    run_cli: RunCli, run_hook: RunHook, tmp_repo: Path
) -> None:
    code, _, _ = run_cli(["new", "--spec", str(SPEC_SUPERSEDES)], tmp_repo)
    successor = today_alias(SUCCESSOR_SLUG)
    assert code == 0
    assert load(tmp_repo, RATIFIED_A).data["effective_state"] == "superseded"
    index = (decisions(tmp_repo) / "INDEX.md").read_text(encoding="utf-8")
    assert f"{RATIFIED_A} | superseded by {successor}" in index.split("## Retired")[1]
    hook = run_hook(
        "pre-tool-use-edit", edit_payload(tmp_repo, "src/scribe/index.py"), tmp_repo
    )
    assert (hook.returncode, hook.stdout) == (0, "")

    code, stdout, _ = run_cli(["reject", successor, "--by", "@tester"], tmp_repo)
    predecessor = load(tmp_repo, RATIFIED_A)
    restored = entries(predecessor, "restored")
    index = (decisions(tmp_repo) / "INDEX.md").read_text(encoding="utf-8")
    active = index.split("## Active decisions")[1].split("## Retired")[0]
    retired = index.split("## Retired")[1]

    assert code == 0
    assert stdout.strip() == f"rejected {successor} by @tester (via cli)"
    assert predecessor.data["effective_state"] == "proposed"
    assert len(restored) == 1
    assert (restored[0]["by"], restored[0]["old"], restored[0]["new"]) == (
        "scribe-reject",
        "superseded",
        "proposed",
    )
    assert f"{RATIFIED_A} | proposed | ratified" in active
    assert f"{successor} | rejected" in retired
    assert validate(run_cli, tmp_repo) == (0, "4 records, 0 errors, 0 warnings\n")

    hook = run_hook(
        "pre-tool-use-edit", edit_payload(tmp_repo, "src/scribe/index.py"), tmp_repo
    )
    context = json.loads(hook.stdout)["hookSpecificOutput"]["additionalContext"]
    assert hook.returncode == 0
    assert RATIFIED_A in context
    assert successor not in context


# --- injected failures (F8) ------------------------------------------------------


def test_failed_record_save_leaves_state_behind_attestation(
    run_cli: RunCli, tmp_repo: Path, unreviewed: str
) -> None:
    count = len(attestation_lines(tmp_repo))

    def broken_replace(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk full at os.replace")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(os, "replace", broken_replace)
        code, stdout, _ = run_cli(["ratify", unreviewed, "--by", "@tester"], tmp_repo)
    assert code == 1
    assert "scribe ratify failed: disk full at os.replace" in stdout
    assert len(attestation_lines(tmp_repo)) == count + 1
    assert load(tmp_repo, unreviewed).data["review_state"] == "unreviewed"
    code, report = validate(run_cli, tmp_repo)
    assert code == 1
    assert "state_behind_attestation" in report

    code, stdout, _ = run_cli(["ratify", unreviewed, "--by", "@tester"], tmp_repo)
    assert code == 0
    assert stdout.startswith(f"ratified {unreviewed} by @tester")
    assert len(attestation_lines(tmp_repo)) == count + 1
    assert validate(run_cli, tmp_repo)[0] == 0


def test_failed_attestation_append_changes_nothing(
    run_cli: RunCli, tmp_repo: Path, unreviewed: str
) -> None:
    lines = attestation_lines(tmp_repo)
    original = record_path(tmp_repo, unreviewed).read_text(encoding="utf-8")

    def broken_append(*_args: object, **_kwargs: object) -> None:
        raise OSError("read-only RATIFICATIONS.jsonl")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(ratify_module, "append_attestation", broken_append)
        code, stdout, _ = run_cli(["ratify", unreviewed, "--by", "@tester"], tmp_repo)
    assert code == 1
    assert "scribe ratify failed: read-only RATIFICATIONS.jsonl" in stdout
    assert attestation_lines(tmp_repo) == lines
    assert record_path(tmp_repo, unreviewed).read_text(encoding="utf-8") == original
    assert validate(run_cli, tmp_repo)[0] == 0

    code, _, _ = run_cli(["ratify", unreviewed, "--by", "@tester"], tmp_repo)
    assert code == 0
    assert len(attestation_lines(tmp_repo)) == len(lines) + 1
    assert load(tmp_repo, unreviewed).data["review_state"] == "ratified"


def test_ratify_lock_timeout_exits_nonzero_without_ledger_writes(
    run_cli: RunCli, tmp_repo: Path, unreviewed: str
) -> None:
    lock_path = tmp_repo / ".claude" / "scribe" / ratify_module.LOCK_FILE
    before_record = record_path(tmp_repo, unreviewed).read_bytes()
    before_attestations = (decisions(tmp_repo) / "RATIFICATIONS.jsonl").read_bytes()
    index_path = decisions(tmp_repo) / "INDEX.md"
    assert not index_path.exists()

    with lock_path.open("a+") as holder:
        fcntl.flock(holder.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        started = time.monotonic()
        code, stdout, _ = run_cli(["ratify", unreviewed, "--by", "@tester"], tmp_repo)
        elapsed = time.monotonic() - started
        fcntl.flock(holder.fileno(), fcntl.LOCK_UN)

    assert elapsed >= 2.0
    assert code == 1
    assert stdout == "ratification lock timeout; retry the same command\n"
    assert record_path(tmp_repo, unreviewed).read_bytes() == before_record
    assert (
        decisions(tmp_repo) / "RATIFICATIONS.jsonl"
    ).read_bytes() == before_attestations
    assert not index_path.exists()


def test_failed_index_write_is_healed_by_a_rerun(
    run_cli: RunCli, tmp_repo: Path, unreviewed: str
) -> None:
    def broken_index(*_args: object, **_kwargs: object) -> None:
        raise OSError("cannot write INDEX.md")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(ratify_module, "write_index", broken_index)
        code, stdout, _ = run_cli(["ratify", unreviewed, "--by", "@tester"], tmp_repo)
    assert code == 1
    assert "cannot write INDEX.md" in stdout
    assert load(tmp_repo, unreviewed).data["review_state"] == "ratified"
    assert attestation_lines(tmp_repo)[-1]["alias"] == unreviewed
    assert validate(run_cli, tmp_repo)[0] == 0
    code, stdout, _ = run_cli(["index", "--check"], tmp_repo)
    assert code == 1
    assert "out of date" in stdout

    code, stdout, _ = run_cli(["ratify", unreviewed, "--by", "@tester"], tmp_repo)
    assert code == 0
    assert stdout.startswith("already ratified by @tester")
    assert run_cli(["index", "--check"], tmp_repo)[0] == 0


# --- attestation ledger integrity (V5) --------------------------------------


def test_ratify_refuses_to_append_after_a_truncated_ledger_tail(
    run_cli: RunCli, tmp_repo: Path, unreviewed: str
) -> None:
    """A truncated final line (interrupted write) blocks further appends."""
    path = decisions(tmp_repo) / "RATIFICATIONS.jsonl"
    before_attestations = path.read_bytes()
    before_record = record_path(tmp_repo, unreviewed).read_bytes()
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"id": "01M21BV91NZSW1HMJ127KZAA5J", "verdict": "ratified"')

    code, stdout, _ = run_cli(["ratify", unreviewed, "--by", "@tester"], tmp_repo)

    assert code == 1
    assert "attestation_truncated_tail" in stdout
    assert record_path(tmp_repo, unreviewed).read_bytes() == before_record
    assert path.read_bytes().startswith(before_attestations)
    assert path.read_bytes() == before_attestations + (
        b'{"id": "01M21BV91NZSW1HMJ127KZAA5J", "verdict": "ratified"'
    )


# --- concurrency (F8) -------------------------------------------------------------


def test_concurrent_ratifications_produce_two_valid_lines(
    run_cli: RunCli, tmp_repo: Path
) -> None:
    aliases = ["D-260908-concurrent-one", "D-260908-concurrent-two"]
    for alias, suffix in zip(aliases, ("CN01", "CN02")):
        make_unreviewed(tmp_repo, alias, suffix)
    count = len(attestation_lines(tmp_repo))

    processes = [
        subprocess.Popen(
            [sys.executable, "-m", "scribe", "ratify", alias, "--by", "@tester"],
            cwd=str(tmp_repo),
            env=os.environ.copy(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for alias in aliases
    ]
    results = [process.communicate(timeout=60) for process in processes]

    assert [process.returncode for process in processes] == [0, 0]
    assert sorted(stdout.strip() for stdout, _ in results) == sorted(
        f"ratified {alias} by @tester (via cli)" for alias in aliases
    )
    lines = attestation_lines(tmp_repo)
    assert len(lines) == count + 2
    assert sorted(line["alias"] for line in lines[-2:]) == aliases
    assert all(
        load(tmp_repo, alias).data["review_state"] == "ratified" for alias in aliases
    )
    assert validate(run_cli, tmp_repo) == (0, "5 records, 0 errors, 0 warnings\n")
    assert run_cli(["index", "--check"], tmp_repo)[0] == 0


# --- skills (F5) ----------------------------------------------------------------------


@pytest.mark.parametrize("skill", SKILLS, ids=[path.parent.name for path in SKILLS])
def test_skill_is_human_only_and_runs_the_cli_inline(skill: Path) -> None:
    text = skill.read_text(encoding="utf-8")
    verb = skill.parent.name
    inline = [line for line in text.splitlines() if line.startswith("!`uv run")]

    assert text.count("disable-model-invocation: true") == 1
    assert f"name: {verb}" in text
    assert len(inline) == 1
    assert f"scribe {verb} --via skill $ARGUMENTS`" in inline[0]
    assert "${CLAUDE_PLUGIN_ROOT}" in inline[0]
    assert (
        "allowed-tools: Bash(uv run --frozen --project ${CLAUDE_PLUGIN_ROOT} scribe *)"
        in text
    )
    assert "UNVERIFIED U1" in text
    assert "\u2013" not in text and "\u2014" not in text
