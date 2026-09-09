import json
import subprocess
from pathlib import Path

import pytest
from scribe.gitutil import git_path_hooks, staged_paths, toplevel
from scribe.record import Record
from scribe.state import error_log_path
from scribe.store import Store, attestation_line_problems, reconcile_supersession


def make_record(
    tmp_path: Path,
    alias: str,
    record_id: str,
    *,
    review_state: str = "unreviewed",
    effective_state: str = "proposed",
    supersedes: str | None = None,
) -> Record:
    return Record(
        tmp_path / f"{alias}.md",
        {
            "id": record_id,
            "alias": alias,
            "review_state": review_state,
            "effective_state": effective_state,
            "supersedes": supersedes,
            "history": [
                {"at": "2026-09-08T00:00:00Z", "event": "proposed", "by": "test"}
            ],
        },
        "",
    )


@pytest.mark.parametrize(
    ("review_state", "effective_state", "effective"),
    [
        ("unreviewed", "proposed", True),
        ("ratified", "implemented", True),
        ("unreviewed", "superseded", True),
        ("rejected", "proposed", False),
        ("unreviewed", "expired", False),
        ("unreviewed", "backtracked", False),
    ],
)
def test_effective_edges(
    tmp_path: Path, review_state: str, effective_state: str, effective: bool
) -> None:
    predecessor = make_record(tmp_path, "D-260908-old", "01M21BV91NZSW1HMJ127KZAA5J")
    successor = make_record(
        tmp_path,
        "D-260909-new",
        "01M21BV91NZSW1HMJ127KZAA5K",
        review_state=review_state,
        effective_state=effective_state,
        supersedes=predecessor.data["alias"],
    )
    store = Store(tmp_path)
    store._records = [predecessor, successor]
    assert store.effective_edges() == ([(successor, predecessor)] if effective else [])


def test_effective_edge_resolves_ulid_and_ignores_dangling(tmp_path: Path) -> None:
    predecessor = make_record(tmp_path, "D-260908-old", "01M21BV91NZSW1HMJ127KZAA5J")
    successor = make_record(
        tmp_path,
        "D-260909-new",
        "01M21BV91NZSW1HMJ127KZAA5K",
        supersedes=predecessor.data["id"],
    )
    dangling = make_record(
        tmp_path,
        "D-260910-later",
        "01M21BV91NZSW1HMJ127KZAA5M",
        supersedes="D-260901-missing",
    )
    store = Store(tmp_path)
    store._records = [predecessor, successor, dangling]
    assert store.effective_edges() == [(successor, predecessor)]


def test_reconcile_marks_predecessor_and_appends_history(tmp_path: Path) -> None:
    predecessor = make_record(
        tmp_path,
        "D-260908-old",
        "01M21BV91NZSW1HMJ127KZAA5J",
        effective_state="implemented",
    )
    successor = make_record(
        tmp_path,
        "D-260909-new",
        "01M21BV91NZSW1HMJ127KZAA5K",
        supersedes=predecessor.data["alias"],
    )
    assert reconcile_supersession([predecessor, successor], "scribe-new") == [
        predecessor
    ]
    assert predecessor.data["effective_state"] == "superseded"
    assert predecessor.data["history"][-1] | {"at": "ignored"} == {
        "at": "ignored",
        "event": "superseded",
        "by": "scribe-new",
        "field": "effective_state",
        "old": "implemented",
        "new": "superseded",
    }


def test_reconcile_restores_latest_prior_state(tmp_path: Path) -> None:
    predecessor = make_record(
        tmp_path,
        "D-260908-old",
        "01M21BV91NZSW1HMJ127KZAA5J",
        effective_state="implemented",
    )
    successor = make_record(
        tmp_path,
        "D-260909-new",
        "01M21BV91NZSW1HMJ127KZAA5K",
        supersedes=predecessor.data["alias"],
    )
    reconcile_supersession([predecessor, successor], "scribe-new")
    successor.data["review_state"] = "rejected"
    assert reconcile_supersession([predecessor, successor], "scribe-reject") == [
        predecessor
    ]
    assert predecessor.data["effective_state"] == "implemented"
    assert predecessor.data["history"][-1]["event"] == "restored"
    assert predecessor.data["history"][-1]["old"] == "superseded"
    assert predecessor.data["history"][-1]["new"] == "implemented"


def test_reconcile_does_not_invent_restore_state(tmp_path: Path) -> None:
    stale = make_record(
        tmp_path,
        "D-260908-stale",
        "01M21BV91NZSW1HMJ127KZAA5J",
        effective_state="superseded",
    )
    assert reconcile_supersession([stale], "scribe-lint") == []
    assert stale.data["effective_state"] == "superseded"


def test_reconcile_chain_keeps_superseded_successor_effective(tmp_path: Path) -> None:
    first = make_record(tmp_path, "D-260908-first", "01M21BV91NZSW1HMJ127KZAA5J")
    second = make_record(
        tmp_path,
        "D-260909-second",
        "01M21BV91NZSW1HMJ127KZAA5K",
        supersedes=first.data["alias"],
    )
    third = make_record(
        tmp_path,
        "D-260910-third",
        "01M21BV91NZSW1HMJ127KZAA5M",
        supersedes=second.data["alias"],
    )
    reconcile_supersession([first, second, third], "test")
    assert first.data["effective_state"] == "superseded"
    assert second.data["effective_state"] == "superseded"


def test_git_utilities_normalize_git_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """V14: `-z` output is decoded as is; a literal backslash is not a separator."""
    nested = tmp_path / "repo" / "nested"
    nested.mkdir(parents=True)
    responses = {
        ("rev-parse", "--show-toplevel"): str(tmp_path / "repo") + "\n",
        ("rev-parse", "--git-path", "hooks"): "../.git/hooks\n",
    }
    byte_responses = {
        ("diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR"): (
            b"src/a.py\0dir\\b.py\0"
        ),
    }

    def fake_git(cwd: str | Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 0, responses[args], "")

    def fake_git_bytes(
        cwd: str | Path, *args: str
    ) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess([], 0, byte_responses[args], b"")

    monkeypatch.setattr("scribe.gitutil._git", fake_git)
    monkeypatch.setattr("scribe.gitutil._git_bytes", fake_git_bytes)
    assert toplevel(nested) == tmp_path / "repo"
    assert staged_paths(nested) == ["src/a.py", "dir\\b.py"]
    assert git_path_hooks(nested) == tmp_path / "repo" / ".git" / "hooks"


def test_records_skips_a_malformed_file_and_logs_instead_of_raising(
    tmp_path: Path,
) -> None:
    """V17: one bad record must not abort the whole collection."""
    decisions = tmp_path / "docs" / "decisions"
    decisions.mkdir(parents=True)
    good = make_record(decisions, "D-260908-good", "01M21BV91NZSW1HMJ127KZAA5J")
    good.save()
    (decisions / "D-260909-broken.md").write_text(
        "no front matter here\n", encoding="utf-8"
    )

    records = Store(tmp_path).records()

    assert [record.data["alias"] for record in records] == ["D-260908-good"]
    log = error_log_path(tmp_path).read_text(encoding="utf-8")
    assert "scribe: skipped D-260909-broken.md" in log


def test_records_skips_a_record_with_a_list_effective_state(tmp_path: Path) -> None:
    """V17 follow-up: `effective_state: []` parses as valid YAML, so the old
    `records()` (which only catches `FrontMatterError`/`OSError`) loads it
    unchanged. `effective_edges()` then tests `effective_state` for membership
    in a *set* (`not in {"proposed", "implemented", "superseded"}`), and an
    unhashable value there raises `TypeError` before the loop reaches any
    other record - the `store.effective_edges()` call below is what fails on
    the old code, not the two assertions after it.
    """
    decisions = tmp_path / "docs" / "decisions"
    decisions.mkdir(parents=True)
    good = make_record(decisions, "D-260908-good", "01M21BV91NZSW1HMJ127KZAA5J")
    good.save()
    bad = make_record(decisions, "D-260909-bad", "01M21BV91NZSW1HMJ127KZAA5K")
    bad.data["effective_state"] = []
    bad.save()

    store = Store(tmp_path)
    assert store.effective_edges() == []

    log = error_log_path(tmp_path).read_text(encoding="utf-8")
    assert "scribe: skipped D-260909-bad.md: effective_state must be a string" in log
    assert [record.data["alias"] for record in store.records()] == ["D-260908-good"]


def test_records_skips_a_record_with_a_non_string_supersedes(tmp_path: Path) -> None:
    """V17 follow-up: `supersedes: []` also parses as valid YAML and used to load
    through unchanged. `reconcile_supersession` uses `supersedes` as a dict key
    (`by_id.get(successor.data.get("supersedes"))`); an unhashable value there
    raises `TypeError` - the `reconcile_supersession(store.records(), ...)` call
    below is what fails on the old code, not the assertion after it.
    """
    decisions = tmp_path / "docs" / "decisions"
    decisions.mkdir(parents=True)
    good = make_record(decisions, "D-260908-good", "01M21BV91NZSW1HMJ127KZAA5J")
    good.save()
    bad = make_record(decisions, "D-260909-bad", "01M21BV91NZSW1HMJ127KZAA5K")
    bad.data["supersedes"] = []
    bad.save()

    store = Store(tmp_path)
    assert reconcile_supersession(store.records(), "scribe-lint") == []

    log = error_log_path(tmp_path).read_text(encoding="utf-8")
    assert "scribe: skipped D-260909-bad.md: supersedes must be a string or null" in log


FULL_ATTESTATION = {
    "id": "01M21BV91NZSW1HMJ127KZAA5J",
    "alias": "D-260908-old",
    "verdict": "ratified",
    "by": "@nikita",
    "at": "2026-09-08T20:37:41Z",
    "body_sha256": "a" * 64,
    "via": "cli",
}


def _line(**overrides: object) -> str:
    return json.dumps({**FULL_ATTESTATION, **overrides})


def test_attestation_line_problems_accepts_a_well_formed_ledger() -> None:
    text = _line() + "\n" + _line(id="01M21BV91NZSW1HMJ127KZAA5K") + "\n"
    assert attestation_line_problems(text) == []


def test_attestation_line_problems_reports_an_incomplete_line() -> None:
    """V5: a line missing actor, timestamp, alias or via is an error, not skipped."""
    incomplete = (
        '{"id": "01M21BV91NZSW1HMJ127KZAA5J", "verdict": "ratified", '
        f'"body_sha256": "{"a" * 64}"}}\n'
    )
    problems = attestation_line_problems(incomplete)
    assert [p.code for p in problems] == ["attestation_incomplete"]


def test_attestation_line_problems_reports_a_malformed_line() -> None:
    text = _line() + "\n{not json\n" + _line(id="01M21BV91NZSW1HMJ127KZAA5K") + "\n"
    problems = attestation_line_problems(text)
    assert [p.code for p in problems] == ["attestation_malformed"]


def test_attestation_line_problems_reports_a_truncated_tail() -> None:
    """A missing trailing newline on the last line is a truncated write, not a skip."""
    text = _line() + "\n" + _line(id="01M21BV91NZSW1HMJ127KZAA5K")
    problems = attestation_line_problems(text)
    assert [p.code for p in problems] == ["attestation_truncated_tail"]


@pytest.mark.parametrize(
    ("field", "value", "expected_substring"),
    [
        ("id", "not-a-ulid", "id must be a canonical ULID"),
        ("alias", 123, "alias must be a string"),
        ("verdict", "pending", "verdict must be one of"),
        (
            "body_sha256",
            "a" * 63,
            "body_sha256 must be a 64-character lowercase hex string",
        ),
        ("by", 123, "by must be a non-empty string"),
        ("at", "yesterday", "at must be an ISO 8601 UTC datetime"),
        ("via", ["cli"], "via must be one of"),
        ("note", 42, "note must be a string or null"),
    ],
)
def test_attestation_line_problems_reports_an_invalid_field(
    field: str, value: object, expected_substring: str
) -> None:
    """V5: a truthy but wrong-typed or out-of-range field is an error, not a pass.

    Fails on the old code: `attestation_line_problems` only checked
    `not item.get(key)` truthiness, so `by: 123`, `at: "yesterday"` and
    `via: ["cli"]` are all truthy and passed structural validation
    unreported (`[p.code for p in problems] == []` on the old code, not the
    `["attestation_invalid_field"]` asserted here). The old code also crashed
    on `via: ["cli"]` if the membership check used `in` without an isinstance
    guard first; this asserts a diagnostic, not an exception.
    """
    text = _line(**{field: value}) + "\n"
    problems = attestation_line_problems(text)
    assert [p.code for p in problems] == ["attestation_invalid_field"]
    assert expected_substring in problems[0].message


def test_attestation_line_problems_accepts_the_real_ledger() -> None:
    """The live RATIFICATIONS.jsonl must still pass every new field check."""
    ledger_path = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "decisions"
        / "RATIFICATIONS.jsonl"
    )
    text = ledger_path.read_text(encoding="utf-8")
    assert attestation_line_problems(text) == []


def test_effective_authority_requires_a_structurally_valid_latest_line(
    tmp_path: Path,
) -> None:
    """V12: a malformed latest line must not grant authority.

    The bare `{id, verdict, body_sha256}` line is the pre-V5 shape: its
    `verdict` and `body_sha256` both match the record, which is all the old
    code checked. Fails on the old code: `effective_authority` returns True
    for the malformed line there, not False.
    """
    decisions = tmp_path / "docs" / "decisions"
    decisions.mkdir(parents=True)
    record = make_record(
        decisions,
        "D-260908-old",
        "01M21BV91NZSW1HMJ127KZAA5J",
        review_state="ratified",
        effective_state="proposed",
    )
    store = Store(tmp_path)
    store._records = [record]
    ledger_path = decisions / "RATIFICATIONS.jsonl"

    malformed = {
        "id": record.data["id"],
        "verdict": "ratified",
        "body_sha256": record.body_sha256(),
    }
    ledger_path.write_text(json.dumps(malformed) + "\n", encoding="utf-8")
    assert not store.effective_authority(record)

    well_formed = {
        **malformed,
        "alias": record.data["alias"],
        "by": "@tester",
        "at": "2026-09-08T20:37:41Z",
        "via": "cli",
    }
    ledger_path.write_text(json.dumps(well_formed) + "\n", encoding="utf-8")
    assert store.effective_authority(record)
