import fcntl
import json
import os
import sys
import time
from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from scribe import newrecord as newrecord_module
from scribe.newrecord import slugify
from scribe.record import Record
from scribe.schema import validate_record
from scribe.state import ledger_lock_path, session_entry, state_path, update_state
from scribe.store import Store

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SPEC = FIXTURES / "new_spec.json"
SPEC_SUPERSEDES = FIXTURES / "new_spec_supersedes.json"
SPEC_SLUG = "scribe-new-takes-a-json-spec-file"
PREDECESSOR = "D-260908-unreviewed-may-supersede-ratified"
SKILL = Path(__file__).resolve().parents[1] / "skills" / "decide" / "SKILL.md"

RunCli = Callable[..., tuple[int, str, str]]


def today_alias(slug: str) -> str:
    stamp = datetime.now(timezone.utc).date().isoformat()[2:].replace("-", "")
    return f"D-{stamp}-{slug}"


@pytest.fixture
def session_state(tmp_repo: Path) -> Path:
    """A session carrying the task refs and prompt ids that `scribe new` inherits."""

    def mutate(state: dict) -> None:
        entry = session_entry(state, "test-session", "2026-09-08T12:00:00Z")
        entry["task_refs"] = ["LIN-7"]
        entry["prompt_ids"] = ["prompt-newest", "prompt-older"]

    update_state(tmp_repo, mutate, now="2026-09-08T12:00:00Z")
    return tmp_repo


def run_new(run_cli: RunCli, root: Path, spec: Path, *extra: str) -> tuple[int, str]:
    code, stdout, _ = run_cli(
        ["new", "--spec", str(spec), "--register", "--session", "test-session", *extra],
        root,
    )
    return code, stdout


def read_state(root: Path) -> dict:
    return json.loads(state_path(root).read_text(encoding="utf-8"))


def test_slugify_lowercases_collapses_and_trims() -> None:
    assert slugify("Scribe new takes a JSON spec file") == SPEC_SLUG
    assert slugify("  Hello,   World!!  ") == "hello-world"
    assert slugify("!!!") == "decision"
    assert len(slugify("word " * 30)) <= 40
    assert not slugify("word " * 30).endswith("-")


def test_new_writes_a_record_that_validates(
    run_cli: RunCli, session_state: Path
) -> None:
    code, stdout = run_new(run_cli, session_state, SPEC)
    alias = today_alias(SPEC_SLUG)
    path = session_state / "docs" / "decisions" / f"{alias}.md"

    assert code == 0
    assert path.exists()
    assert stdout.strip().endswith(f"docs/decisions/{alias}.md")

    record = Record.load(path)
    problems = validate_record(
        record.data, record.body, store=Store(session_state), path=path
    )
    assert [problem for problem in problems if problem.severity == "error"] == []
    assert record.data["review_state"] == "unreviewed"
    assert record.data["effective_state"] == "proposed"
    assert record.data["ratified_by"] is None
    assert record.data["implementation_links"] == []
    assert record.data["title"] in record.body


@pytest.fixture
def fixed_umask() -> Iterator[int]:
    """Force a known umask (0o002) for the duration of the test and restore it after.

    0o002 (group-writable) is chosen deliberately: it is the umask value that
    makes the platform default open mode 0o666 diverge from the 0o644 base
    this fix uses (0o666 & ~0o002 == 0o664, but 0o644 & ~0o002 == 0o644), so
    it is the value that exposes a mismatch between the two write paths.
    """
    previous = os.umask(0o002)
    try:
        yield 0o002
    finally:
        os.umask(previous)


@pytest.mark.skipif(sys.platform == "win32", reason="posix file mode bits")
def test_new_writes_a_record_with_no_execute_bit(
    run_cli: RunCli, session_state: Path, fixed_umask: int
) -> None:
    """V8's exclusive create (`os.open` with `O_CREAT`) must not fall back to
    the default mode 0o777: that lands new records as 0o775 (executable)
    instead of the 0o644 the three seed records use. Fails on the old code
    on the `mode & 0o111 == 0` assertion, since the unmasked default mode
    leaves the execute bits set.
    """
    run_new(run_cli, session_state, SPEC)
    path = session_state / "docs" / "decisions" / f"{today_alias(SPEC_SLUG)}.md"

    mode = path.stat().st_mode
    assert mode & 0o111 == 0
    assert mode & 0o777 == 0o644 & ~fixed_umask


@pytest.mark.skipif(sys.platform == "win32", reason="posix file mode bits")
def test_save_rewrite_keeps_the_record_at_0o644(
    run_cli: RunCli, session_state: Path, fixed_umask: int
) -> None:
    """A record that is loaded and re-saved (as ratify and supersession
    bookkeeping do) must land back at 0o644 minus umask, matching a fresh
    `scribe new` record, not the platform default 0o666 that `Record.save`
    used to create its temp file with. Under the 0o002 umask this fixture
    forces, the old code's 0o666 base produces 0o664 where the new-record
    path produces 0o644, so this fails on the old code on the final `mode ==
    0o644 & ~fixed_umask` assertion (0o664 != 0o644).
    """
    run_new(run_cli, session_state, SPEC)
    path = session_state / "docs" / "decisions" / f"{today_alias(SPEC_SLUG)}.md"

    record = Record.load(path)
    record.save()

    mode = path.stat().st_mode & 0o777
    assert mode == 0o644 & ~fixed_umask


def test_new_inherits_task_refs_and_prompt_ids_from_state(
    run_cli: RunCli, session_state: Path
) -> None:
    run_new(run_cli, session_state, SPEC)
    record = Record.load(
        session_state / "docs" / "decisions" / f"{today_alias(SPEC_SLUG)}.md"
    )

    assert record.data["task_refs"] == ["LIN-7"]
    assert record.data["provenance"]["prompt_ids"] == ["prompt-newest"]
    assert record.data["provenance"]["session"] == "test-session"


def test_new_preserves_explicit_empty_session_lists(
    run_cli: RunCli, session_state: Path
) -> None:
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    spec["task_refs"] = []
    spec.setdefault("provenance", {})["prompt_ids"] = []
    supplied = session_state / "empty-lists.json"
    supplied.write_text(json.dumps(spec), encoding="utf-8")
    code, stdout = run_new(run_cli, session_state, supplied)
    assert code == 0, stdout
    record = Record.load(session_state / stdout.strip())
    assert record.data["task_refs"] == []
    assert record.data["provenance"]["prompt_ids"] == []


def test_new_preserves_literal_template_tokens_in_evidence(
    run_cli: RunCli, tmp_repo: Path
) -> None:
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    quote = "Keep {{EVIDENCE_POINTERS}} and {{DECISION}} verbatim."
    spec["evidence_quote"] = quote
    spec["evidence_pointers"] = ["A separate pointer"]
    supplied = tmp_repo / "literal-tokens.json"
    supplied.write_text(json.dumps(spec), encoding="utf-8")
    code, stdout = run_new(run_cli, tmp_repo, supplied)
    assert code == 0, stdout
    body = Record.load(tmp_repo / stdout.strip()).body
    assert f"> {quote}\n" in body
    assert "- A separate pointer" in body


def test_new_writes_one_proposed_history_entry(
    run_cli: RunCli, session_state: Path
) -> None:
    run_new(run_cli, session_state, SPEC, "--by", "@tester")
    record = Record.load(
        session_state / "docs" / "decisions" / f"{today_alias(SPEC_SLUG)}.md"
    )

    assert len(record.data["history"]) == 1
    entry = record.data["history"][0]
    assert entry["event"] == "proposed"
    assert entry["by"] == "@tester"
    assert entry["session"] == "test-session"


def test_new_regenerates_the_index_with_the_alias_in_the_review_queue(
    run_cli: RunCli, session_state: Path
) -> None:
    run_new(run_cli, session_state, SPEC)
    index = (session_state / "docs" / "decisions" / "INDEX.md").read_text(
        encoding="utf-8"
    )
    queue = index.split("## Review queue")[1].split("## Active decisions")[0]

    assert today_alias(SPEC_SLUG) in queue
    assert "## Review queue (1)" in index


def test_new_registers_the_ulid_in_the_session(
    run_cli: RunCli, session_state: Path
) -> None:
    run_new(run_cli, session_state, SPEC)
    record = Record.load(
        session_state / "docs" / "decisions" / f"{today_alias(SPEC_SLUG)}.md"
    )
    session = read_state(session_state)["sessions"]["test-session"]

    assert session["pending_decisions"] == [record.data["id"]]
    assert [item["id"] for item in session["records_written"]] == [record.data["id"]]


def test_new_without_register_leaves_the_session_untouched(
    run_cli: RunCli, session_state: Path
) -> None:
    code, _, _ = run_cli(
        ["new", "--spec", str(SPEC), "--session", "test-session"], session_state
    )
    session = read_state(session_state)["sessions"]["test-session"]

    assert code == 0
    assert session["pending_decisions"] == []
    assert session["records_written"] == []


def test_new_registers_under_unknown_without_a_session(
    run_cli: RunCli, tmp_repo: Path
) -> None:
    code, _, _ = run_cli(["new", "--spec", str(SPEC), "--register"], tmp_repo)
    session = read_state(tmp_repo)["sessions"]["unknown"]

    assert code == 0
    assert len(session["pending_decisions"]) == 1


def test_new_twice_with_the_same_title_appends_a_suffix(
    run_cli: RunCli, session_state: Path
) -> None:
    run_new(run_cli, session_state, SPEC)
    code, stdout = run_new(run_cli, session_state, SPEC)
    second = session_state / "docs" / "decisions" / f"{today_alias(SPEC_SLUG)}-2.md"

    assert code == 0
    assert second.exists()
    assert Record.load(second).data["alias"] == f"{today_alias(SPEC_SLUG)}-2"
    assert stdout.strip().endswith(f"{today_alias(SPEC_SLUG)}-2.md")


def test_new_alias_race_with_a_pre_created_file_advances_to_the_next_suffix(
    run_cli: RunCli, session_state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """V8: `unique_alias` is only a best-effort guess; two callers can both see
    the same free alias. Simulate the race by pinning it to an alias whose
    file another writer has already created; exclusive create must notice the
    collision at write time and advance to `-2` instead of overwriting it.
    """
    alias = today_alias(SPEC_SLUG)
    decisions = session_state / "docs" / "decisions"
    pre_existing = decisions / f"{alias}.md"
    pre_existing.write_text("written by another racing writer\n", encoding="utf-8")
    monkeypatch.setattr(
        newrecord_module, "unique_alias", lambda store, slug, today: alias
    )

    code, stdout = run_new(run_cli, session_state, SPEC)
    second = decisions / f"{alias}-2.md"

    assert code == 0
    assert stdout.strip().endswith(f"{alias}-2.md")
    assert second.exists()
    assert Record.load(second).data["alias"] == f"{alias}-2"
    # the other writer's file was never touched
    assert (
        pre_existing.read_text(encoding="utf-8") == "written by another racing writer\n"
    )


def test_new_lock_timeout_exits_nonzero_without_writing(
    run_cli: RunCli, tmp_repo: Path
) -> None:
    lock_path = ledger_lock_path(tmp_repo)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    before = sorted(p.name for p in (tmp_repo / "docs" / "decisions").glob("D-*.md"))

    with lock_path.open("a+") as holder:
        fcntl.flock(holder.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        started = time.monotonic()
        code, stdout, stderr = run_cli(
            ["new", "--spec", str(SPEC), "--register"], tmp_repo
        )
        elapsed = time.monotonic() - started
        fcntl.flock(holder.fileno(), fcntl.LOCK_UN)

    assert elapsed >= 2.0
    assert code == 1
    assert "ledger lock timeout" in stderr
    assert "no record written" in stdout
    after = sorted(p.name for p in (tmp_repo / "docs" / "decisions").glob("D-*.md"))
    assert after == before
    assert not state_path(tmp_repo).exists()


def test_new_with_supersedes_retires_the_predecessor(
    run_cli: RunCli, session_state: Path
) -> None:
    code, _ = run_new(run_cli, session_state, SPEC_SUPERSEDES)
    predecessor = Record.load(
        session_state / "docs" / "decisions" / f"{PREDECESSOR}.md"
    )
    superseded = [
        entry
        for entry in predecessor.data["history"]
        if entry.get("event") == "superseded"
    ]

    assert code == 0
    assert predecessor.data["effective_state"] == "superseded"
    assert len(superseded) == 1
    assert superseded[0]["by"] == "scribe-new"
    assert superseded[0]["field"] == "effective_state"
    assert superseded[0]["old"] == "proposed"


def test_new_with_supersedes_puts_the_record_first_in_the_review_queue(
    run_cli: RunCli, session_state: Path
) -> None:
    run_new(run_cli, session_state, SPEC_SUPERSEDES)
    index = (session_state / "docs" / "decisions" / "INDEX.md").read_text(
        encoding="utf-8"
    )
    first = [line for line in index.splitlines() if line.startswith("1. ")][0]

    assert "[supersedes ratified]" in first
    assert f"supersedes {PREDECESSOR}" in first
    assert f"{PREDECESSOR} | superseded by " in index


def test_new_writes_nothing_when_the_record_does_not_validate(
    run_cli: RunCli, tmp_repo: Path, tmp_path: Path
) -> None:
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    spec["options"] = spec["options"][:1]
    spec["tags"] = ["Not A Tag"]
    bad = tmp_path / "bad_spec.json"
    bad.write_text(json.dumps(spec), encoding="utf-8")

    code, stdout, _ = run_cli(["new", "--spec", str(bad), "--register"], tmp_repo)

    assert code == 1
    assert "invalid_tag" in stdout
    assert "no record written" in stdout
    assert not list((tmp_repo / "docs" / "decisions").glob(f"*{SPEC_SLUG}*"))
    assert not state_path(tmp_repo).exists()


def test_new_reports_an_unreadable_spec(run_cli: RunCli, tmp_repo: Path) -> None:
    code, stdout, _ = run_cli(["new", "--spec", "does-not-exist.json"], tmp_repo)

    assert code == 1
    assert "cannot read spec" in stdout


def test_decide_skill_passes_the_session_and_stays_model_invocable() -> None:
    text = SKILL.read_text(encoding="utf-8")

    assert "disable-model-invocation" not in text
    assert text.count("${CLAUDE_SESSION_ID}") >= 1
    assert "${CLAUDE_PLUGIN_ROOT}" in text
    assert "one-way-door" in text
