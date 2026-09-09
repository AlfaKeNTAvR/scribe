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
    assert "invalid_title" not in {p.code for p in validate_record(record.data, record.body)}


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
    assert "unattested_review_state" in {p.code for p in validate_record(record.data, record.body, store)}


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
    behind = [problem for problem in problems if problem.code == "state_behind_attestation"]
    assert len(behind) == 1
    assert "run scribe ratify D-260908-sound-choice again" in behind[0].message


def test_committed_record_body_hashes_match_attestations() -> None:
    store = Store(Path(__file__).resolve().parents[1])
    for record in store:
        attestation = store.latest_attestation(record.data["id"])
        assert attestation is not None
        assert record.body_sha256() == attestation["body_sha256"]


def test_record_hash_and_apply_change() -> None:
    record = Record.load(FIXTURES / "valid_minimal.md")
    original_hash = record.body_sha256()
    assert record.apply_change("effective_state", "implemented", "implemented", "test", at="2026-09-09T00:00:00Z")
    assert record.data["history"][-1]["old"] == "proposed"
    assert record.body_sha256() == original_hash
