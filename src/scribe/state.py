"""Scratch state at <root>/.claude/scribe/state.json (plan 4.2).

Every writer goes through `update_state`, which takes the lock, reads the file,
applies one mutation, prunes stale sessions and writes back atomically. Corrupt
JSON is treated as empty state and logged, never raised. The lock adapter keeps
the platform branch in one place so the Windows path can be unit-tested with a
fake `msvcrt` module in `sys.modules`.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import IO, Any

from .record import utc_now

STATE_VERSION = 1
STATE_DIR = Path(".claude") / "scribe"
STATE_FILE = "state.json"
LOCK_FILE = "state.json.lock"
# V8: the one worktree-local lock every ledger-file writer takes, not just
# ratify/reject. Kept as a separate lock file from LOCK_FILE above: that one
# guards scratch state.json, this one guards docs/decisions/*.md and
# RATIFICATIONS.jsonl. `ratify.py` re-exports this as `ratify.LOCK_FILE` for
# callers and tests that reach into it by that name.
LEDGER_LOCK_FILE = "ratify.lock"
ERROR_LOG_FILE = "hook-errors.log"
ERROR_LOG_MAX_BYTES = 200 * 1024

PROMPT_IDS_CAP = 20
TASK_REFS_CAP = 10
RECORDS_WRITTEN_CAP = 20
SESSION_MAX_AGE = timedelta(days=7)

LOCK_RETRY_INTERVAL_S = 0.05
LOCK_TIMEOUT_S = 2.0
# "nt" selects the msvcrt branch of the lock adapter; tests patch this instead of os.name.
LOCK_PLATFORM = os.name

TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def state_dir(root: str | Path) -> Path:
    return Path(root) / STATE_DIR


def state_path(root: str | Path) -> Path:
    return state_dir(root) / STATE_FILE


def error_log_path(root: str | Path) -> Path:
    return state_dir(root) / ERROR_LOG_FILE


def ledger_lock_path(root: str | Path) -> Path:
    """The single lock every ledger-file writer (new, ratify, post-commit,
    relink, lint --expire) takes before touching docs/decisions (V8)."""
    return state_dir(root) / LEDGER_LOCK_FILE


def log_hook_error(root: str | Path | None, message: str) -> None:
    """Append one line to hook-errors.log; every failure inside is dropped."""
    if root is None:
        return
    try:
        path = error_log_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        _truncate_error_log(path)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{utc_now()} {message}\n")
    except BaseException:
        pass


def _truncate_error_log(path: Path) -> None:
    """Keep the newest half of the log once it grows past ERROR_LOG_MAX_BYTES."""
    try:
        if path.stat().st_size <= ERROR_LOG_MAX_BYTES:
            return
        content = path.read_bytes()
        tail = content[len(content) // 2 :]
        newline = tail.find(b"\n")
        if newline >= 0:
            tail = tail[newline + 1 :]
        path.write_bytes(tail)
    except OSError:
        pass


# --- lock adapter -----------------------------------------------------------


def _try_lock(handle: IO[str]) -> None:
    """Take a non-blocking exclusive lock or raise OSError / BlockingIOError.

    UNVERIFIED: the Windows branch (`msvcrt.locking` on one byte at offset 0 of
    an empty file) is plan register item U3; it is exercised only through a fake
    `msvcrt` module in tests.
    """
    if LOCK_PLATFORM == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(handle: IO[str]) -> None:
    if LOCK_PLATFORM == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def locked(lock_path: str | Path) -> Iterator[bool]:
    """Hold the state lock for the block; yield False when the lock timed out.

    Retries every LOCK_RETRY_INTERVAL_S for LOCK_TIMEOUT_S, then yields False
    and logs `state lock timeout` next to the lock file. Callers must not write
    when the lock was not acquired.
    """
    path = Path(lock_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        deadline = time.monotonic() + LOCK_TIMEOUT_S
        acquired = False
        while True:
            try:
                _try_lock(handle)
                acquired = True
                break
            except OSError:
                if time.monotonic() >= deadline:
                    break
                time.sleep(LOCK_RETRY_INTERVAL_S)
        if not acquired:
            log_hook_error(path.parent.parent.parent, "scribe: state lock timeout")
        try:
            yield acquired
        finally:
            if acquired:
                try:
                    _unlock(handle)
                except OSError:
                    pass


# --- state document ---------------------------------------------------------


def empty_state() -> dict[str, Any]:
    return {"version": STATE_VERSION, "sessions": {}}


def load_state(root: str | Path) -> dict[str, Any]:
    """Read state.json; missing or corrupt content yields empty state."""
    path = state_path(root)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return empty_state()
    try:
        loaded = json.loads(text)
    except ValueError as exc:
        log_hook_error(root, f"scribe: corrupt state.json ignored: {exc}")
        return empty_state()
    if not isinstance(loaded, dict) or not isinstance(loaded.get("sessions"), dict):
        log_hook_error(root, "scribe: corrupt state.json ignored: unexpected shape")
        return empty_state()
    loaded["version"] = STATE_VERSION
    return loaded


def _write_state(root: str | Path, state: dict[str, Any]) -> None:
    path = state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def update_state(
    root: str | Path,
    mutate: Callable[[dict[str, Any]], None],
    now: str | None = None,
) -> dict[str, Any]:
    """Locked read-modify-write; on lock timeout, drop the update."""
    with locked(state_dir(root) / LOCK_FILE) as acquired:
        if not acquired:
            return load_state(root)
        state = load_state(root)
        mutate(state)
        prune_sessions(state, now or utc_now())
        _write_state(root, state)
    return state


def session_entry(
    state: dict[str, Any], session_id: str, now: str | None = None
) -> dict[str, Any]:
    """Return the session's mapping, creating it with `started_at` when new."""
    sessions = state.setdefault("sessions", {})
    session = sessions.get(session_id)
    if not isinstance(session, dict):
        session = {"started_at": now or utc_now()}
        sessions[session_id] = session
    session.setdefault("started_at", now or utc_now())
    session.setdefault("last_prompt_at", None)
    session.setdefault("prompt_ids", [])
    session.setdefault("task_refs", [])
    session.setdefault("pending_decisions", [])
    session.setdefault("decision_worthy", None)
    session.setdefault("records_written", [])
    return session


def push_recent(items: list[Any], new_items: list[Any], cap: int | None) -> list[Any]:
    """Most recent first, deduplicated, `new_items` keep their order.

    `cap` truncates the result; `None` keeps every item (plan 4.9, V19: no cap
    on `pending_decisions`, ids stay until a commit consumes them or the
    session is pruned by `prune_sessions`'s existing expiry).
    """
    result: list[Any] = []
    for item in [*new_items, *items]:
        if item not in result:
            result.append(item)
    return result if cap is None else result[:cap]


def parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def prune_sessions(state: dict[str, Any], now: str) -> list[str]:
    """Drop sessions whose latest activity is older than SESSION_MAX_AGE."""
    reference = parse_timestamp(now)
    sessions = state.get("sessions")
    if reference is None or not isinstance(sessions, dict):
        return []
    dropped = []
    for session_id, session in list(sessions.items()):
        if not isinstance(session, dict):
            dropped.append(session_id)
            continue
        stamps = [
            stamp
            for stamp in (
                parse_timestamp(session.get("last_prompt_at")),
                parse_timestamp(session.get("started_at")),
            )
            if stamp is not None
        ]
        if stamps and reference - max(stamps) > SESSION_MAX_AGE:
            dropped.append(session_id)
    for session_id in dropped:
        del sessions[session_id]
    return dropped
