import json
from pathlib import Path

from scribe.record import Record
from scribe.schema import validate_record
from scribe.store import Store

FIXTURES = Path(__file__).parent / "fixtures" / "records"


def codes(name: str) -> set[str]:
    record = Record.load(FIXTURES / name)
    return {problem.code for problem in validate_record(record.data, record.body)}


def test_valid_minimal_record() -> None:
    record = Record.load(FIXTURES / "valid_minimal.md")
    assert validate_record(record.data, record.body) == []


def test_targeted_invalid_fixtures() -> None:
    expected = {
        "bad_ulid.md": "invalid_ulid",
        "ulid_overflow.md": "invalid_ulid",
        "missing_evidence_quote.md": "missing_evidence_quote",
        "unknown_key.md": "unknown_key",
        "bad_task_ref.md": "invalid_task_ref",
        "jsonpath_engine.md": "unsupported_engine",
        "action_affects_bad_name.md": "invalid_action",
        "negate_on_action.md": "negate_on_non_path",
    }
    for fixture, code in expected.items():
        assert code in codes(fixture), fixture


def test_title_allows_200_characters() -> None:
    record = Record.load(FIXTURES / "valid_minimal.md")
    title = "x" * 200
    record.data["title"] = title
    record.body = record.body.replace("# A sound choice", f"# {title}")
    assert "invalid_title" not in {
        p.code for p in validate_record(record.data, record.body)
    }


def test_action_affect_is_valid() -> None:
    assert not codes("action_affects_valid.md")


def test_attestation_cross_checks(tmp_path: Path) -> None:
    decisions = tmp_path / "docs" / "decisions"
    decisions.mkdir(parents=True)
    source = Record.load(FIXTURES / "ratified_without_attestation.md")
    source.path = decisions / f"{source.data['alias']}.md"
    source.save()
    (decisions / "RATIFICATIONS.jsonl").write_text("", encoding="utf-8")
    store = Store(tmp_path)
    record = store.records()[0]
    assert "unattested_review_state" in {
        p.code for p in validate_record(record.data, record.body, store)
    }


def test_attestation_with_a_wrong_typed_field_does_not_satisfy_ratified_state(
    tmp_path: Path,
) -> None:
    """V5/V12: a matching verdict and body_sha256 are not enough on their own.

    `by: 123` is truthy, and verdict/body_sha256 both match the record, so
    the old code's shallow check treated this as a valid attestation and
    `unattested_review_state` did not fire. Fails on the old code: that code
    (not this fix) reports `codes()` without `unattested_review_state` here.
    """
    decisions = tmp_path / "docs" / "decisions"
    decisions.mkdir(parents=True)
    source = Record.load(FIXTURES / "ratified_without_attestation.md")
    source.path = decisions / f"{source.data['alias']}.md"
    source.save()
    attestation = {
        "id": source.data["id"],
        "alias": source.data["alias"],
        "verdict": "ratified",
        "by": 123,
        "at": "2026-09-08T20:37:43Z",
        "body_sha256": source.body_sha256(),
        "via": "cli",
    }
    (decisions / "RATIFICATIONS.jsonl").write_text(
        json.dumps(attestation) + "\n", encoding="utf-8"
    )
    store = Store(tmp_path)
    record = store.records()[0]
    assert "unattested_review_state" in {
        p.code for p in validate_record(record.data, record.body, store)
    }


def test_unreviewed_record_detects_existing_attestation(tmp_path: Path) -> None:
    decisions = tmp_path / "docs" / "decisions"
    decisions.mkdir(parents=True)
    record = Record.load(FIXTURES / "unreviewed_with_attestation.md")
    record.path = decisions / f"{record.data['alias']}.md"
    record.save()
    attestation = {
        "id": record.data["id"],
        "alias": record.data["alias"],
        "verdict": "ratified",
        "by": "@owner",
        "at": "2026-09-08T20:37:43Z",
        "body_sha256": record.body_sha256(),
        "via": "cli",
    }
    (decisions / "RATIFICATIONS.jsonl").write_text(
        json.dumps(attestation) + "\n", encoding="utf-8"
    )
    store = Store(tmp_path)
    loaded = store.records()[0]
    problems = validate_record(loaded.data, loaded.body, store)
    behind = [
        problem for problem in problems if problem.code == "state_behind_attestation"
    ]
    assert len(behind) == 1
    assert "run scribe ratify D-260908-sound-choice again" in behind[0].message


def test_committed_record_body_hashes_match_attestations() -> None:
    store = Store(Path(__file__).resolve().parents[1])
    reviewed = [
        record for record in store if record.data["review_state"] != "unreviewed"
    ]
    assert len(reviewed) >= 3
    for record in reviewed:
        attestation = store.latest_attestation(record.data["id"])
        assert attestation is not None
        assert record.body_sha256() == attestation["body_sha256"]


def test_wrong_type_review_state_produces_diagnostic_not_crash() -> None:
    """V17: `review_state: []` must be an invalid_enum diagnostic, not a TypeError."""
    record = Record.load(FIXTURES / "valid_minimal.md")
    record.data["review_state"] = []
    problems = validate_record(record.data, record.body)
    assert "invalid_enum" in {p.code for p in problems}


def test_max_ulid_produces_date_diagnostic_not_crash() -> None:
    """V17: the maximum ULID must be a diagnostic, not an unhandled ValueError."""
    record = Record.load(FIXTURES / "valid_minimal.md")
    record.data["id"] = "7ZZZZZZZZZZZZZZZZZZZZZZZZZ"
    problems = validate_record(record.data, record.body)
    assert "ulid_date_out_of_range" in {p.code for p in problems}
    assert "invalid_ulid" not in {p.code for p in problems}


def _record_with_verify(tmp_path: Path, verify: list[dict]) -> tuple[Store, object]:
    """A store-backed record (Q4) so `validate_pytest_target` can check paths."""
    decisions = tmp_path / "docs" / "decisions"
    decisions.mkdir(parents=True)
    record = Record.load(FIXTURES / "valid_minimal.md")
    record.data["verify"] = verify
    record.path = decisions / f"{record.data['alias']}.md"
    record.save()
    store = Store(tmp_path)
    return store, store.records()[0]


def test_pytest_verify_entry_accepts_a_valid_node_id(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_x.py").write_text("def test_ok():\n    pass\n", encoding="utf-8")
    store, record = _record_with_verify(
        tmp_path,
        [
            {
                "id": "sample",
                "engine": "pytest",
                "target": "tests/test_x.py::test_ok",
                "expect": "pass",
                "severity": "error",
            }
        ],
    )
    problems = validate_record(record.data, record.body, store)
    assert problems == []


def test_pytest_verify_entry_rejects_a_bad_node_id(tmp_path: Path) -> None:
    store, record = _record_with_verify(
        tmp_path,
        [
            {
                "id": "sample",
                "engine": "pytest",
                "target": "::test_ok",
                "expect": "pass",
                "severity": "error",
            }
        ],
    )
    problems = validate_record(record.data, record.body, store)
    assert "invalid_verify" in {p.code for p in problems}


def test_pytest_verify_entry_rejects_a_target_path_that_does_not_exist(
    tmp_path: Path,
) -> None:
    store, record = _record_with_verify(
        tmp_path,
        [
            {
                "id": "sample",
                "engine": "pytest",
                "target": "tests/does_not_exist.py::test_ok",
                "expect": "pass",
                "severity": "error",
            }
        ],
    )
    problems = validate_record(record.data, record.body, store)
    assert "invalid_verify" in {p.code for p in problems}


def test_pytest_verify_entry_rejects_a_target_starting_with_an_option_dash(
    tmp_path: Path,
) -> None:
    """A target starting with `-` reads as a pytest option, not a node id,
    even when a file by that literal name exists on disk. Fails on the old
    code: before this rule, `--help` (an existing file at the repo root)
    passed every prior check (non-empty string, no leading `/` or `~`, no
    `..`, and the path exists), so `problems` came back empty.
    """
    (tmp_path / "--help").write_text("not a test file\n", encoding="utf-8")
    store, record = _record_with_verify(
        tmp_path,
        [
            {
                "id": "sample",
                "engine": "pytest",
                "target": "--help",
                "expect": "pass",
                "severity": "error",
            }
        ],
    )
    problems = validate_record(record.data, record.body, store)
    assert "invalid_verify" in {p.code for p in problems}


def test_verify_entry_with_a_non_string_engine_is_rejected_without_crashing() -> None:
    """`engine: []` is unhashable; the old `engine not in {"grep", "pytest"}`
    membership test raised `TypeError` before `unknown_engine` could be
    reported. Fails on the old code with a `TypeError` escaping
    `validate_record` instead of a normal assertion failure.
    """
    record = Record.load(FIXTURES / "valid_minimal.md")
    record.data["verify"] = [
        {
            "id": "sample",
            "engine": [],
            "pattern": "x",
            "paths": ["src/x.py"],
            "expect": "match",
            "severity": "error",
        }
    ]
    problems = validate_record(record.data, record.body)
    assert "unknown_engine" in {p.code for p in problems}


def test_verify_entry_with_an_unknown_engine_is_rejected() -> None:
    record = Record.load(FIXTURES / "valid_minimal.md")
    record.data["verify"] = [
        {
            "id": "sample",
            "engine": "xpath",
            "pattern": "x",
            "paths": ["src/x.py"],
            "expect": "match",
            "severity": "error",
        }
    ]
    problems = validate_record(record.data, record.body)
    assert "unknown_engine" in {p.code for p in problems}


def test_record_hash_and_apply_change() -> None:
    record = Record.load(FIXTURES / "valid_minimal.md")
    original_hash = record.body_sha256()
    assert record.apply_change(
        "effective_state",
        "implemented",
        "implemented",
        "test",
        at="2026-09-09T00:00:00Z",
    )
    assert record.data["history"][-1]["old"] == "proposed"
    assert record.body_sha256() == original_hash
