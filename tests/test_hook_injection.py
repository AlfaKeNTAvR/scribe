import json
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

import pytest
from scribe.hooks import pre_tool_use_edit
from scribe.hooks.pre_tool_use_edit import (
    MAX_BLOCK_CHARS,
    MAX_LINE_CHARS,
    MAX_RECORDS,
    format_block,
    governing_records,
    handle,
    record_line,
    truncate,
)
from scribe.record import Record
from scribe.state import error_log_path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "hooks"
INDEX_RECORD = "D-260908-unreviewed-may-supersede-ratified"
SCHEMA_RECORD = "D-260908-verbatim-quote-is-the-evidence"
CANDIDATES_SENTENCE = "These are retrieval candidates"

RunHook = Callable[..., subprocess.CompletedProcess[str]]


@pytest.fixture(autouse=True)
def fresh_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    """The module stamps its deadline anchor at import; in-process calls restart it."""
    monkeypatch.setattr(pre_tool_use_edit, "_START", time.monotonic())


def load_fixture(name: str, cwd: Path) -> dict:
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    payload["cwd"] = str(cwd)
    return payload


def edit_payload(root: Path, file_path: Path | str) -> dict:
    payload = load_fixture("pre_tool_use_edit_match.json", root)
    payload["tool_input"]["file_path"] = str(file_path)
    return payload


def context_of(result: subprocess.CompletedProcess[str] | dict | None) -> str:
    output = result if isinstance(result, dict) else json.loads(result.stdout)
    assert set(output) == {"hookSpecificOutput"}
    inner = output["hookSpecificOutput"]
    assert inner["hookEventName"] == "PreToolUse"
    return inner["additionalContext"]


def write_variant(store: Path, alias: str, record_id: str, **overrides: object) -> Path:
    """Clone a real record with different identity and front matter values."""
    source = store / f"{INDEX_RECORD}.md"
    record = Record.load(source)
    record.path = store / f"{alias}.md"
    record.data.update({"id": record_id, "alias": alias, **overrides})
    if record.data.get("review_state") == "unreviewed":
        record.data["ratified_by"] = None
        record.data["ratified_at"] = None
    record.save()
    return record.path


def ulid_with_suffix(suffix: str) -> str:
    base = "01M21BV91NZSW1HMJ127KZAA"
    return base[: 26 - len(suffix)] + suffix


# --- fixtures through the real subprocess ------------------------------------


def test_match_fixture_injects_governing_record(
    run_hook: RunHook, tmp_repo: Path
) -> None:
    payload = edit_payload(tmp_repo, tmp_repo / "src" / "scribe" / "index.py")
    result = run_hook("pre-tool-use-edit", payload, tmp_repo)
    assert (result.returncode, result.stderr) == (0, "")
    context = context_of(result)
    assert context.startswith("Governing decisions for src/scribe/index.py:\n")
    assert INDEX_RECORD in context
    assert CANDIDATES_SENTENCE in context
    assert f"Full text: docs/decisions/{INDEX_RECORD}.md" in context
    assert SCHEMA_RECORD not in context


def test_match_fixture_accepts_relative_file_path(
    run_hook: RunHook, tmp_repo: Path
) -> None:
    payload = load_fixture("pre_tool_use_edit_match.json", tmp_repo)
    assert payload["tool_input"]["file_path"] == "src/scribe/index.py"
    result = run_hook("pre-tool-use-edit", payload, tmp_repo)
    assert result.returncode == 0
    assert INDEX_RECORD in context_of(result)


def test_nomatch_fixture_prints_nothing(run_hook: RunHook, tmp_repo: Path) -> None:
    payload = load_fixture("pre_tool_use_edit_nomatch.json", tmp_repo)
    payload["tool_input"]["file_path"] = str(tmp_repo / "README.md")
    result = run_hook("pre-tool-use-edit", payload, tmp_repo)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


def test_write_outside_repo_prints_nothing(
    run_hook: RunHook, tmp_repo: Path, tmp_path: Path
) -> None:
    payload = load_fixture("pre_tool_use_write_outside_repo.json", tmp_repo)
    payload["tool_input"]["file_path"] = str(tmp_path / "outside" / "notes.md")
    result = run_hook("pre-tool-use-edit", payload, tmp_repo)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


def test_malformed_stdin_prints_nothing(run_hook: RunHook, tmp_repo: Path) -> None:
    raw = (FIXTURES / "malformed.txt").read_text(encoding="utf-8")
    result = run_hook("pre-tool-use-edit", raw, tmp_repo)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


def test_missing_file_path_prints_nothing(run_hook: RunHook, tmp_repo: Path) -> None:
    payload = load_fixture("pre_tool_use_edit_match.json", tmp_repo)
    del payload["tool_input"]["file_path"]
    result = run_hook("pre-tool-use-edit", payload, tmp_repo)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    payload["tool_input"] = "not a mapping"
    result = run_hook("pre-tool-use-edit", payload, tmp_repo)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


def test_repo_without_store_prints_nothing(run_hook: RunHook, tmp_path: Path) -> None:
    bare = tmp_path / "plain"
    bare.mkdir()
    subprocess.run(["git", "init", "-q", str(bare)], check=True)
    payload = edit_payload(bare, bare / "src" / "scribe" / "index.py")
    result = run_hook("pre-tool-use-edit", payload, bare)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert not (bare / ".claude").exists()


# --- candidate selection (in process) -----------------------------------------


def test_negated_pattern_excludes_a_path(tmp_repo: Path) -> None:
    store = tmp_repo / "docs" / "decisions"
    write_variant(
        store,
        "D-260909-src-except-index",
        ulid_with_suffix("N1"),
        affects=[
            {"type": "path", "pattern": "src/scribe/**"},
            {"type": "path", "pattern": "src/scribe/index.py", "negate": True},
        ],
    )
    on_index = context_of(
        handle(edit_payload(tmp_repo, tmp_repo / "src/scribe/index.py"))
    )
    assert "D-260909-src-except-index" not in on_index
    on_store = context_of(
        handle(edit_payload(tmp_repo, tmp_repo / "src/scribe/store.py"))
    )
    assert "D-260909-src-except-index" in on_store
    assert INDEX_RECORD not in on_store


def test_rejected_and_retired_records_are_not_candidates(tmp_repo: Path) -> None:
    store = tmp_repo / "docs" / "decisions"
    write_variant(
        store,
        "D-260909-rejected",
        ulid_with_suffix("R1"),
        review_state="rejected",
        ratified_by="@nikita",
        ratified_at="2026-09-09T10:00:00Z",
    )
    write_variant(
        store, "D-260909-expired", ulid_with_suffix("E1"), effective_state="expired"
    )
    write_variant(
        store,
        "D-260909-successor",
        ulid_with_suffix("S1"),
        review_state="unreviewed",
        supersedes=INDEX_RECORD,
    )
    context = context_of(
        handle(edit_payload(tmp_repo, tmp_repo / "src/scribe/index.py"))
    )
    lines = context.splitlines()
    aliases = [line.split(" ")[1] for line in lines if line.startswith("- ")]
    assert aliases == ["D-260909-successor"]
    assert f"supersedes ratified {INDEX_RECORD}" in lines[1]
    assert "(proposed, unreviewed, supersedes ratified" in lines[1]


def test_rejected_successor_does_not_retire_its_predecessor(tmp_repo: Path) -> None:
    store = tmp_repo / "docs" / "decisions"
    write_variant(
        store,
        "D-260909-rejected-successor",
        ulid_with_suffix("S2"),
        review_state="rejected",
        ratified_by="@nikita",
        ratified_at="2026-09-09T10:00:00Z",
        supersedes=INDEX_RECORD,
    )
    context = context_of(
        handle(edit_payload(tmp_repo, tmp_repo / "src/scribe/index.py"))
    )
    assert INDEX_RECORD in context
    assert "D-260909-rejected-successor" not in context


def test_ordering_and_cap(tmp_repo: Path) -> None:
    store = tmp_repo / "docs" / "decisions"
    common = {"affects": [{"type": "path", "pattern": "src/scribe/index.py"}]}
    write_variant(
        store,
        "D-260910-unrev-impl",
        ulid_with_suffix("A1"),
        review_state="unreviewed",
        effective_state="implemented",
        date="2026-09-10",
        **common,
    )
    write_variant(
        store,
        "D-260911-unrev-prop-new",
        ulid_with_suffix("A2"),
        review_state="unreviewed",
        effective_state="proposed",
        date="2026-09-11",
        **common,
    )
    write_variant(
        store,
        "D-260909-unrev-prop-old",
        ulid_with_suffix("A3"),
        review_state="unreviewed",
        effective_state="proposed",
        date="2026-09-09",
        **common,
    )
    write_variant(
        store,
        "D-260910-rat-impl",
        ulid_with_suffix("A4"),
        effective_state="implemented",
        date="2026-09-10",
        **common,
    )
    write_variant(
        store,
        "D-260912-rat-prop",
        ulid_with_suffix("A5"),
        effective_state="proposed",
        date="2026-09-12",
        **common,
    )
    write_variant(
        store,
        "D-260907-unrev-back",
        ulid_with_suffix("A6"),
        review_state="unreviewed",
        effective_state="backtracked",
        date="2026-09-07",
        **common,
    )
    mappings = pre_tool_use_edit.load_front_matters(
        pre_tool_use_edit.store_for(tmp_repo)
    )
    assert mappings is not None
    ordered = [m["alias"] for m in governing_records(mappings, "src/scribe/index.py")]
    assert len(ordered) == MAX_RECORDS
    assert ordered == [
        "D-260910-rat-impl",
        "D-260912-rat-prop",
        INDEX_RECORD,
        "D-260910-unrev-impl",
        "D-260911-unrev-prop-new",
    ]


# --- block formatting -----------------------------------------------------------


def test_record_line_shape_and_caps() -> None:
    mapping = {
        "alias": "D-260908-x",
        "effective_state": "proposed",
        "review_state": "ratified",
        "decided_by": "human",
        "title": "A title.",
        "regret_when": "r" * 300,
        "supersedes": None,
    }
    line = record_line(mapping, set())
    assert line.startswith(
        "- D-260908-x (proposed, ratified by human): A title. Regret when: "
    )
    assert len(line) <= MAX_LINE_CHARS
    mapping["regret_when"] = "Short regret."
    mapping["title"] = "t" * 400
    line = record_line(mapping, set())
    assert len(line) == MAX_LINE_CHARS
    assert line.endswith("...")
    mapping["title"] = "A title"
    mapping["regret_when"] = None
    assert record_line(mapping, set()) == (
        "- D-260908-x (proposed, ratified by human): A title."
    )
    assert truncate("long", 2) == ".."


def test_block_drops_records_to_fit_cap() -> None:
    records = [
        {
            "alias": f"D-26090{i}-" + "r" * 51,
            "effective_state": "proposed",
            "review_state": "unreviewed",
            "decided_by": "agent",
            "title": "T" * 150,
            "regret_when": "R" * 100,
            "date": f"2026-09-0{i}",
        }
        for i in range(1, 6)
    ]
    for record in records:
        assert len(record_line(record, set())) == MAX_LINE_CHARS
    block = format_block("src/x.py", records, records)
    assert len(block) <= MAX_BLOCK_CHARS
    shown = [line for line in block.splitlines() if line.startswith("- ")]
    assert 1 <= len(shown) < len(records)
    assert shown[0].startswith("- D-260901-rrr")
    assert block.splitlines()[-1].startswith(CANDIDATES_SENTENCE)


def test_block_truncates_long_target_without_losing_footer_or_links() -> None:
    record = {
        "alias": "D-260908-x",
        "effective_state": "proposed",
        "review_state": "unreviewed",
        "title": "A title",
    }
    block = format_block("nested/" + "x" * 2000, [record], [record])
    assert len(block) <= MAX_BLOCK_CHARS
    assert block.splitlines()[0].endswith("...:")
    assert block.splitlines()[-1].startswith(CANDIDATES_SENTENCE)
    assert "Full text: docs/decisions/D-260908-x.md" in block


# --- robustness -------------------------------------------------------------------


def test_unparsable_record_is_skipped_and_logged(tmp_repo: Path) -> None:
    store = tmp_repo / "docs" / "decisions"
    (store / "D-260909-broken.md").write_text(
        "no front matter here\n", encoding="utf-8"
    )
    context = context_of(
        handle(edit_payload(tmp_repo, tmp_repo / "src/scribe/index.py"))
    )
    assert INDEX_RECORD in context
    log = error_log_path(tmp_repo).read_text(encoding="utf-8")
    assert "scribe: skipped D-260909-broken.md" in log


def test_large_record_body_is_not_decoded_by_injection(tmp_repo: Path) -> None:
    record_path = tmp_repo / "docs" / "decisions" / f"{INDEX_RECORD}.md"
    front_matter = record_path.read_bytes().split(b"\n---\n", 1)[0] + b"\n---\n"
    record_path.write_bytes(front_matter + b"\xff" * 1_000_000)

    context = context_of(
        handle(edit_payload(tmp_repo, tmp_repo / "src" / "scribe" / "index.py"))
    )

    assert INDEX_RECORD in context


def test_expired_deadline_prints_nothing(
    tmp_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pre_tool_use_edit, "DEADLINE_S", -1.0)
    assert handle(edit_payload(tmp_repo, tmp_repo / "src/scribe/index.py")) is None
    monkeypatch.setattr(pre_tool_use_edit, "DEADLINE_S", 60.0)
    assert handle(edit_payload(tmp_repo, tmp_repo / "src/scribe/index.py")) is not None


def test_deadline_is_checked_while_loading(
    tmp_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = tmp_repo / "docs" / "decisions"
    for i in range(pre_tool_use_edit.DEADLINE_CHECK_EVERY):
        write_variant(store, f"D-260909-filler-{i:02d}", ulid_with_suffix(f"{i:02d}"))
    checks: list[int] = []
    real = pre_tool_use_edit.deadline_passed

    def counting() -> bool:
        checks.append(1)
        return real()

    monkeypatch.setattr(pre_tool_use_edit, "deadline_passed", counting)
    assert handle(edit_payload(tmp_repo, tmp_repo / "src/scribe/index.py")) is not None
    assert len(checks) >= 2


def test_deadline_is_checked_after_matching_and_formatting(
    tmp_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_format = pre_tool_use_edit.format_block

    def expensive_format(*args: object, **kwargs: object) -> str:
        block = real_format(*args, **kwargs)
        monkeypatch.setattr(
            pre_tool_use_edit,
            "_START",
            time.monotonic() - pre_tool_use_edit.DEADLINE_S - 0.1,
        )
        return block

    monkeypatch.setattr(pre_tool_use_edit, "format_block", expensive_format)
    assert handle(edit_payload(tmp_repo, tmp_repo / "src/scribe/index.py")) is None
