import json
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from scribe.hooks import user_prompt_submit
from scribe.hooks.session_start import review_queue_counts
from scribe.hooks.user_prompt_submit import extract_task_refs
from scribe.record import Record
from scribe.state import load_state

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "hooks"

RunHook = Callable[..., subprocess.CompletedProcess[str]]


def load_fixture(name: str, cwd: Path) -> dict:
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    payload["cwd"] = str(cwd)
    return payload


def make_unreviewed_copy(
    store: Path, alias: str, record_id: str, supersedes: str | None
) -> None:
    """Clone a real record's front matter into an unreviewed record for queue tests."""
    source = next(store.glob("D-*.md"))
    record = Record.load(source)
    record.path = store / f"{alias}.md"
    record.data.update(
        {
            "id": record_id,
            "alias": alias,
            "review_state": "unreviewed",
            "ratified_by": None,
            "ratified_at": None,
            "supersedes": supersedes,
        }
    )
    record.save()


# --- SessionStart ------------------------------------------------------------


def test_session_start_registers_session_and_is_quiet_with_empty_queue(
    run_hook: RunHook, tmp_repo: Path
) -> None:
    result = run_hook(
        "session-start", load_fixture("session_start.json", tmp_repo), tmp_repo
    )
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    session = load_state(tmp_repo)["sessions"]["session_fixture_0001"]
    assert session["started_at"]
    assert session["prompt_ids"] == []
    assert session["pending_decisions"] == []


def test_session_start_reports_review_queue(run_hook: RunHook, tmp_repo: Path) -> None:
    store = tmp_repo / "docs" / "decisions"
    make_unreviewed_copy(
        store,
        "D-260909-successor",
        "01M21BV91NZSW1HMJ127KZAA5K",
        "D-260908-verbatim-quote-is-the-evidence",
    )
    make_unreviewed_copy(store, "D-260909-plain", "01M21BV91NZSW1HMJ127KZAA5M", None)
    result = run_hook(
        "session-start", load_fixture("session_start.json", tmp_repo), tmp_repo
    )
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output == {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": (
                "scribe: 2 unreviewed decisions, 1 supersede a ratified one. "
                "Run /scribe:lint or open docs/decisions/INDEX.md."
            ),
        }
    }


def test_session_start_skips_unparseable_record(
    run_hook: RunHook, tmp_repo: Path
) -> None:
    store = tmp_repo / "docs" / "decisions"
    make_unreviewed_copy(store, "D-260909-plain", "01M21BV91NZSW1HMJ127KZAA5M", None)
    (store / "D-260909-broken.md").write_text(
        "no front matter here\n", encoding="utf-8"
    )
    result = run_hook(
        "session-start", load_fixture("session_start.json", tmp_repo), tmp_repo
    )
    assert result.returncode == 0
    assert "1 unreviewed decisions, 0 supersede" in result.stdout
    log = (tmp_repo / ".claude" / "scribe" / "hook-errors.log").read_text(
        encoding="utf-8"
    )
    assert "D-260909-broken.md" in log


def test_session_start_skips_a_record_with_non_string_supersedes(
    run_hook: RunHook, tmp_repo: Path
) -> None:
    """V17 follow-up: `supersedes: []` parses as valid YAML front matter, so the
    old loader (which only catches `FrontMatterError`/`OSError`) lets it through
    unchanged. `review_queue_counts` then does
    `mapping.get("supersedes") in ratified_keys`, a *set* membership test that
    raises `TypeError: unhashable type: 'list'` for this record - taking the
    whole review-queue count down with it. The `run_hook(...)` call below is
    what fails on the old code (a non-zero exit or the fail-open supervisor
    swallowing the hook entirely), not the assertions after it.
    """
    store = tmp_repo / "docs" / "decisions"
    make_unreviewed_copy(store, "D-260909-plain", "01M21BV91NZSW1HMJ127KZAA5M", None)
    source = next(store.glob("D-*.md"))
    record = Record.load(source)
    record.path = store / "D-260909-bad-supersedes.md"
    record.data.update(
        {
            "id": "01M21BV91NZSW1HMJ127KZAA5N",
            "alias": "D-260909-bad-supersedes",
            "review_state": "unreviewed",
            "ratified_by": None,
            "ratified_at": None,
            "supersedes": [],
        }
    )
    record.save()
    result = run_hook(
        "session-start", load_fixture("session_start.json", tmp_repo), tmp_repo
    )
    assert result.returncode == 0
    assert "1 unreviewed decisions, 0 supersede" in result.stdout
    log = (tmp_repo / ".claude" / "scribe" / "hook-errors.log").read_text(
        encoding="utf-8"
    )
    assert (
        "scribe: skipped D-260909-bad-supersedes.md: supersedes must be a "
        "string or null" in log
    )


def test_review_queue_counts_use_ulid_or_alias() -> None:
    mappings = [
        {"id": "A", "alias": "D-260901-a", "review_state": "ratified"},
        {
            "id": "B",
            "alias": "D-260902-b",
            "review_state": "unreviewed",
            "supersedes": "A",
        },
        {
            "id": "C",
            "alias": "D-260903-c",
            "review_state": "unreviewed",
            "supersedes": "D-260901-a",
        },
        {
            "id": "D",
            "alias": "D-260904-d",
            "review_state": "unreviewed",
            "supersedes": "B",
        },
        {
            "id": "E",
            "alias": "D-260905-e",
            "review_state": "rejected",
            "supersedes": "A",
        },
    ]
    assert review_queue_counts(mappings) == (3, 2)


def test_session_start_without_store_is_silent(
    run_hook: RunHook, tmp_path: Path
) -> None:
    repo = tmp_path / "plain"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    payload = load_fixture("session_start.json", repo)
    result = run_hook("session-start", payload, repo)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert not (repo / ".claude").exists()


def test_session_start_outside_git_is_silent(run_hook: RunHook, tmp_path: Path) -> None:
    payload = load_fixture("session_start.json", tmp_path)
    result = run_hook("session-start", payload, tmp_path)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert not (tmp_path / ".claude").exists()


def test_session_start_hints_when_started_below_repo_root(
    run_hook: RunHook, tmp_repo: Path
) -> None:
    """V21: the RATIFICATIONS.jsonl deny rule does not load below the repo root."""
    subdir = tmp_repo / "sub"
    subdir.mkdir()
    result = run_hook(
        "session-start", load_fixture("session_start.json", subdir), subdir
    )
    assert result.returncode == 0
    output = json.loads(result.stdout)
    context = output["hookSpecificOutput"]["additionalContext"]
    assert f"session started below the repository root ({tmp_repo})" in context
    assert (
        "RATIFICATIONS.jsonl deny rule from .claude/settings.json is not active here"
    ) in context
    assert f"start Claude at {tmp_repo}" in context
    assert (
        "Edit(**/docs/decisions/RATIFICATIONS.jsonl) to your user settings" in context
    )


def test_session_start_root_cwd_has_no_subdirectory_hint(
    run_hook: RunHook, tmp_repo: Path
) -> None:
    store = tmp_repo / "docs" / "decisions"
    make_unreviewed_copy(store, "D-260909-plain", "01M21BV91NZSW1HMJ127KZAA5M", None)
    result = run_hook(
        "session-start", load_fixture("session_start.json", tmp_repo), tmp_repo
    )
    assert result.returncode == 0
    output = json.loads(result.stdout)
    context = output["hookSpecificOutput"]["additionalContext"]
    assert "session started below" not in context


def test_session_start_without_session_id_only_reports(
    run_hook: RunHook, tmp_repo: Path
) -> None:
    payload = load_fixture("session_start.json", tmp_repo)
    del payload["session_id"]
    result = run_hook("session-start", payload, tmp_repo)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert not (tmp_repo / ".claude" / "scribe" / "state.json").exists()


# --- UserPromptSubmit --------------------------------------------------------


def test_user_prompt_submit_extracts_task_refs(
    run_hook: RunHook, tmp_repo: Path
) -> None:
    payload = load_fixture("user_prompt_with_refs.json", tmp_repo)
    result = run_hook("user-prompt-submit", payload, tmp_repo)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    session = load_state(tmp_repo)["sessions"]["session_fixture_0002"]
    assert session["task_refs"] == ["LIN-123", "#42", "octo/scribe#7"]
    assert session["prompt_ids"] == ["prompt_fixture_0002"]
    assert session["last_prompt_at"] == session["started_at"]


def test_user_prompt_submit_without_refs_still_stamps(
    run_hook: RunHook, tmp_repo: Path
) -> None:
    run_hook("session-start", load_fixture("session_start.json", tmp_repo), tmp_repo)
    result = run_hook(
        "user-prompt-submit",
        load_fixture("user_prompt_submit.json", tmp_repo),
        tmp_repo,
    )
    assert (result.returncode, result.stdout) == (0, "")
    session = load_state(tmp_repo)["sessions"]["session_fixture_0001"]
    assert session["task_refs"] == []
    assert session["prompt_ids"] == ["prompt_fixture_0001"]
    assert session["last_prompt_at"] is not None


def test_user_prompt_submit_malformed_stdin(run_hook: RunHook, tmp_repo: Path) -> None:
    raw = (FIXTURES / "malformed.txt").read_text(encoding="utf-8")
    result = run_hook("user-prompt-submit", raw, tmp_repo)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        ("fix LIN-123 please", ["LIN-123"]),
        ("see #42 and #42 again", ["#42"]),
        (
            "owner/repo#7 and other-org/my.repo#8",
            ["owner/repo#7", "other-org/my.repo#8"],
        ),
        ("D-260908-verbatim-quote-is-the-evidence is a record", []),
        ("UTF-8 text with ABC-1 and abc-2", ["UTF-8", "ABC-1"]),
        ("path/to/file#1 is not an owner/repo ref", []),
        ("hashtag#5 glued", []),
        ("no refs here", []),
        ("A-1 too short", []),
    ],
)
def test_extract_task_refs(prompt: str, expected: list[str]) -> None:
    assert extract_task_refs(prompt) == expected


def test_prompt_ids_cap_at_twenty_most_recent_first(
    tmp_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_repo)
    for number in range(23):
        user_prompt_submit.handle(
            {
                "session_id": "cap",
                "prompt_id": f"p{number:02d}",
                "cwd": str(tmp_repo),
                "prompt": f"step {number} on REF-{number}",
            }
        )
    session = load_state(tmp_repo)["sessions"]["cap"]
    assert len(session["prompt_ids"]) == 20
    assert session["prompt_ids"][0] == "p22"
    assert session["prompt_ids"][-1] == "p03"
    assert len(session["task_refs"]) == 10
    assert session["task_refs"][0] == "REF-22"
    assert session["task_refs"][-1] == "REF-13"


def test_task_refs_dedup_moves_existing_to_front(tmp_repo: Path) -> None:
    base = {"session_id": "dedup", "cwd": str(tmp_repo)}
    user_prompt_submit.handle({**base, "prompt_id": "p1", "prompt": "LIN-1 then LIN-2"})
    user_prompt_submit.handle({**base, "prompt_id": "p2", "prompt": "back to LIN-1"})
    session = load_state(tmp_repo)["sessions"]["dedup"]
    assert session["task_refs"] == ["LIN-1", "LIN-2"]
    assert session["prompt_ids"] == ["p2", "p1"]
