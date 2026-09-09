import fcntl
import json
import sys
import types
from pathlib import Path

import pytest
from scribe import state as state_module
from scribe.state import (
    LOCK_FILE,
    error_log_path,
    load_state,
    locked,
    prune_sessions,
    push_recent,
    session_entry,
    state_path,
    update_state,
)


def add_session(session_id: str, **fields: object):
    def mutate(state: dict) -> None:
        session = session_entry(state, session_id, "2026-09-08T12:00:00Z")
        session.update(fields)

    return mutate


def test_update_state_creates_file_with_session_shape(tmp_repo: Path) -> None:
    written = update_state(tmp_repo, add_session("s1"), now="2026-09-08T12:00:00Z")
    on_disk = json.loads(state_path(tmp_repo).read_text(encoding="utf-8"))
    assert on_disk == written
    assert on_disk["version"] == 1
    assert on_disk["sessions"]["s1"] == {
        "started_at": "2026-09-08T12:00:00Z",
        "last_prompt_at": None,
        "prompt_ids": [],
        "task_refs": [],
        "pending_decisions": [],
        "decision_worthy": None,
        "records_written": [],
    }
    assert not list((tmp_repo / ".claude" / "scribe").glob("*.tmp"))


def test_update_state_preserves_other_sessions(tmp_repo: Path) -> None:
    update_state(
        tmp_repo, add_session("s1", task_refs=["LIN-1"]), now="2026-09-08T12:00:00Z"
    )
    update_state(tmp_repo, add_session("s2"), now="2026-09-08T12:00:00Z")
    state = load_state(tmp_repo)
    assert set(state["sessions"]) == {"s1", "s2"}
    assert state["sessions"]["s1"]["task_refs"] == ["LIN-1"]


def test_corrupt_json_is_empty_state_and_logged(tmp_repo: Path) -> None:
    state_path(tmp_repo).write_text("{not json", encoding="utf-8")
    assert load_state(tmp_repo) == {"version": 1, "sessions": {}}
    assert "corrupt state.json" in error_log_path(tmp_repo).read_text(encoding="utf-8")
    state_path(tmp_repo).write_text('{"sessions": []}', encoding="utf-8")
    assert load_state(tmp_repo)["sessions"] == {}
    update_state(tmp_repo, add_session("fresh"), now="2026-09-08T12:00:00Z")
    assert "fresh" in load_state(tmp_repo)["sessions"]


def test_missing_file_is_empty_state(tmp_path: Path) -> None:
    assert load_state(tmp_path) == {"version": 1, "sessions": {}}


def test_prune_drops_sessions_older_than_seven_days() -> None:
    state = {
        "version": 1,
        "sessions": {
            "stale": {
                "started_at": "2026-08-20T00:00:00Z",
                "last_prompt_at": "2026-08-31T23:59:59Z",
            },
            "kept_by_prompt": {
                "started_at": "2026-08-01T00:00:00Z",
                "last_prompt_at": "2026-09-02T00:00:01Z",
            },
            "kept_by_start": {
                "started_at": "2026-09-07T00:00:00Z",
                "last_prompt_at": None,
            },
            "no_stamps": {"pending_decisions": ["01M21BV91NZSW1HMJ127KZAA5J"]},
            "garbage": "not a mapping",
        },
    }
    dropped = prune_sessions(state, "2026-09-08T00:00:00Z")
    assert sorted(dropped) == ["garbage", "stale"]
    assert set(state["sessions"]) == {"kept_by_prompt", "kept_by_start", "no_stamps"}


def test_prune_runs_on_every_write(tmp_repo: Path) -> None:
    update_state(
        tmp_repo,
        add_session("old", started_at="2026-08-01T00:00:00Z"),
        now="2026-08-01T00:00:00Z",
    )
    update_state(tmp_repo, add_session("new"), now="2026-09-08T12:00:00Z")
    assert set(load_state(tmp_repo)["sessions"]) == {"new"}


def test_push_recent_dedups_caps_and_keeps_new_first() -> None:
    assert push_recent(["b", "c"], ["a"], 10) == ["a", "b", "c"]
    assert push_recent(["a", "b"], ["b"], 10) == ["b", "a"]
    assert push_recent(list("cdefghijkl"), ["a", "b"], 10) == list("abcdefghij")
    assert push_recent([], ["x", "x", "y"], 10) == ["x", "y"]


# --- lock adapter ------------------------------------------------------------


class FakeMsvcrt(types.ModuleType):
    LK_NBLCK = 2
    LK_UNLCK = 0

    def __init__(self, fail_times: int = 0) -> None:
        super().__init__("msvcrt")
        self.calls: list[tuple[int, int]] = []
        self.fail_times = fail_times

    def locking(self, fd: int, mode: int, nbytes: int) -> None:
        self.calls.append((mode, nbytes))
        if mode == self.LK_NBLCK and self.fail_times > 0:
            self.fail_times -= 1
            raise OSError(36, "Resource deadlock avoided")


@pytest.fixture
def windows_lock(monkeypatch: pytest.MonkeyPatch):
    def install(fail_times: int = 0) -> FakeMsvcrt:
        fake = FakeMsvcrt(fail_times)
        monkeypatch.setitem(sys.modules, "msvcrt", fake)
        monkeypatch.setattr(state_module, "LOCK_PLATFORM", "nt")
        monkeypatch.setattr(state_module, "LOCK_RETRY_INTERVAL_S", 0.001)
        monkeypatch.setattr(state_module, "LOCK_TIMEOUT_S", 0.05)
        return fake

    return install


def test_windows_adapter_locks_one_byte_and_unlocks(
    tmp_repo: Path, windows_lock
) -> None:
    fake = windows_lock()
    lock_path = tmp_repo / ".claude" / "scribe" / LOCK_FILE
    with locked(lock_path) as acquired:
        assert acquired is True
        assert fake.calls == [(FakeMsvcrt.LK_NBLCK, 1)]
    assert fake.calls == [(FakeMsvcrt.LK_NBLCK, 1), (FakeMsvcrt.LK_UNLCK, 1)]
    assert lock_path.read_bytes() == b""


def test_windows_adapter_retries_then_acquires(tmp_repo: Path, windows_lock) -> None:
    fake = windows_lock(fail_times=3)
    with locked(tmp_repo / ".claude" / "scribe" / LOCK_FILE) as acquired:
        assert acquired is True
    lock_calls = [call for call in fake.calls if call[0] == FakeMsvcrt.LK_NBLCK]
    assert len(lock_calls) == 4


def test_windows_adapter_bounded_retry_then_reports_timeout(
    tmp_repo: Path, windows_lock
) -> None:
    fake = windows_lock(fail_times=10**6)
    with locked(tmp_repo / ".claude" / "scribe" / LOCK_FILE) as acquired:
        assert acquired is False
    assert 1 < len(fake.calls) < 1000
    assert all(mode == FakeMsvcrt.LK_NBLCK for mode, _ in fake.calls)
    assert "state lock timeout" in error_log_path(tmp_repo).read_text(encoding="utf-8")


def test_posix_contention_drops_state_update(
    tmp_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(state_module, "LOCK_RETRY_INTERVAL_S", 0.005)
    monkeypatch.setattr(state_module, "LOCK_TIMEOUT_S", 0.1)
    lock_path = tmp_repo / ".claude" / "scribe" / LOCK_FILE
    with lock_path.open("a+") as holder:
        fcntl.flock(holder.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        update_state(tmp_repo, add_session("s1"), now="2026-09-08T12:00:00Z")
        fcntl.flock(holder.fileno(), fcntl.LOCK_UN)
    assert "s1" not in load_state(tmp_repo)["sessions"]
    assert "state lock timeout" in error_log_path(tmp_repo).read_text(encoding="utf-8")


def test_posix_lock_is_released_after_block(tmp_repo: Path) -> None:
    lock_path = tmp_repo / ".claude" / "scribe" / LOCK_FILE
    with locked(lock_path) as acquired:
        assert acquired is True
        with lock_path.open("a+") as other, pytest.raises(OSError):
            fcntl.flock(other.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    with lock_path.open("a+") as other:
        fcntl.flock(other.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(other.fileno(), fcntl.LOCK_UN)
