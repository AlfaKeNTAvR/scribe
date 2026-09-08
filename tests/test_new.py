import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import pytest
from scribe.newrecord import slugify
from scribe.record import Record
from scribe.schema import validate_record
from scribe.state import session_entry, state_path, update_state
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
