"""`prepare-commit-msg`: add `Decision:` and `Session:` trailers (plan 5.1).

Arguments: `<msg-file> [<source> [<sha>]]`. Candidates come from two origins,
kept apart for logging and for F3: a staged record file carries its own id
(`record-carried`), and a session's `pending_decisions` contributes an id when
the staged content implements that record (`pending`). `addIfDifferent` keeps
an amend from duplicating trailers (F14).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from scribe import gitutil
from scribe.githooks import debug, repo_store
from scribe.links import STORE_PREFIX, implementation_paths
from scribe.record import Record
from scribe.state import load_state, parse_timestamp
from scribe.store import Store

SKIPPED_SOURCES = {"merge", "squash"}
DECISION_KEY = "Decision"
SESSION_KEY = "Session"
SESSION_KEYS_PRESENT = {"session", "claude-session"}


def staged_paths(root: Path, source: str | None, sha: str | None) -> list[str]:
    """Staged paths; on amend, relative to the amended commit's parent (F14)."""
    if source == "commit" and sha:
        return gitutil.staged_paths_against(
            gitutil.parent_or_empty_tree(sha, root), root
        )
    return gitutil.staged_paths(root)


def record_carried(store: Store, staged: list[str]) -> list[Record]:
    """Records whose own file is staged."""
    staged_names = {
        Path(path).name
        for path in staged
        if path.startswith(STORE_PREFIX) and Path(path).name.startswith("D-")
    }
    return [record for record in store.records() if record.path.name in staged_names]


def pending_ids(root: Path) -> list[str]:
    ids: list[str] = []
    for session in load_state(root).get("sessions", {}).values():
        if not isinstance(session, dict):
            continue
        for item in session.get("pending_decisions") or []:
            if isinstance(item, str) and item not in ids:
                ids.append(item)
    return ids


def pending_records(store: Store, root: Path, staged: list[str]) -> list[Record]:
    """Pending records that the staged content implements (plan 5.1 item 4b)."""
    matched: list[Record] = []
    for record_id in pending_ids(root):
        record = store.resolve(record_id)
        if record is not None and implementation_paths(record, staged):
            matched.append(record)
    return matched


def candidates(store: Store, root: Path, staged: list[str]) -> list[tuple[Record, str]]:
    """Deduplicated (record, origin) pairs: record-carried first, then pending."""
    seen: set[str] = set()
    ordered: list[tuple[Record, str]] = []
    for origin, records in (
        ("record-carried", record_carried(store, staged)),
        ("pending", pending_records(store, root, staged)),
    ):
        for record in records:
            record_id = str(record.data.get("id"))
            if record_id not in seen:
                seen.add(record_id)
                ordered.append((record, origin))
    return ordered


def latest_session(root: Path) -> str | None:
    """The session with the newest `last_prompt_at` (or `started_at`)."""
    best: tuple[object, str] | None = None
    for session_id, session in load_state(root).get("sessions", {}).items():
        if not isinstance(session, dict):
            continue
        stamp = parse_timestamp(session.get("last_prompt_at")) or parse_timestamp(
            session.get("started_at")
        )
        if stamp is None:
            continue
        if best is None or stamp > best[0]:
            best = (stamp, str(session_id))
    return best[1] if best else None


def has_session_trailer(message_file: Path, root: Path) -> bool:
    text = message_file.read_text(encoding="utf-8", errors="replace")
    return any(
        key.lower() in SESSION_KEYS_PRESENT
        for key, _ in gitutil.parse_trailers(text, root)
    )


def run(args: Sequence[str]) -> int:
    if not args:
        return 0
    message_file = Path(args[0])
    source = args[1] if len(args) > 1 else None
    sha = args[2] if len(args) > 2 else None
    if source in SKIPPED_SOURCES:
        return 0
    root, store = repo_store()
    if root is None or store is None:
        return 0
    staged = staged_paths(root, source, sha)
    for record, origin in candidates(store, root, staged):
        alias = record.data.get("alias")
        record_id = record.data.get("id")
        debug(f"prepare-commit-msg: {origin} {alias}")
        gitutil.add_trailer_to_file(
            message_file, DECISION_KEY, f"{alias} {record_id}", root
        )
    if not has_session_trailer(message_file, root):
        session_id = latest_session(root)
        if session_id:
            gitutil.add_trailer_to_file(message_file, SESSION_KEY, session_id, root)
    return 0
