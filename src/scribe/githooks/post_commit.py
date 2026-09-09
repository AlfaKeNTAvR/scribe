"""`post-commit`: turn the commit's `Decision:` trailers into links (plan 5.3).

A link is written only when the commit changed a path the record claims
(`links.implementation_paths`); that is also the only moment a pending id is
consumed (F3). A record-only commit therefore leaves its id pending for the
implementing commit that follows. On amend the new sha gains its own link and
the stale one stays for `scribe relink` (F14).
"""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from scribe import gitutil
from scribe.githooks import repo_store
from scribe.index import write_index
from scribe.links import add_link, implementation_paths, mark_implemented, short_sha
from scribe.lookup import TRAILER_KEY, trailer_tokens
from scribe.record import Record, utc_now
from scribe.state import load_state, update_state
from scribe.store import Store

GUARD_ENV = "SCRIBE_IN_POST_COMMIT"
BY = "scribe-post-commit"


def referenced_records(store: Store, root: Path) -> list[Record]:
    """Records named by HEAD's Decision trailers, deduplicated, trailer order."""
    values = gitutil.commit_trailer_values("HEAD", TRAILER_KEY, root)
    records: list[Record] = []
    for token in trailer_tokens(values):
        record = store.resolve(token)
        if record is not None and all(record is not seen for seen in records):
            records.append(record)
    return records


def consume_pending(root: Path, ids: set[str]) -> None:
    """Drop the linked ids from every session's pending list; no-op when absent."""
    sessions = load_state(root).get("sessions", {})
    present = any(
        isinstance(session, dict)
        and any(item in ids for item in session.get("pending_decisions") or [])
        for session in sessions.values()
    )
    if not present:
        return

    def mutate(state: dict[str, Any]) -> None:
        for session in state.get("sessions", {}).values():
            if isinstance(session, dict):
                session["pending_decisions"] = [
                    item
                    for item in session.get("pending_decisions") or []
                    if item not in ids
                ]

    update_state(root, mutate)


def run(args: Sequence[str]) -> int:
    del args
    if os.environ.get(GUARD_ENV) == "1":
        return 0
    os.environ[GUARD_ENV] = "1"
    root, store = repo_store()
    if root is None or store is None:
        return 0
    sha = gitutil.head_sha(root)
    if sha is None:
        return 0
    changed = gitutil.commit_changed_paths("HEAD", root)
    now = utc_now()
    linked: list[Record] = []
    implemented: list[Record] = []
    changed_records: list[Record] = []
    for record in referenced_records(store, root):
        paths = implementation_paths(record, changed)
        if not paths:
            continue
        implemented.append(record)
        record_changed = False
        if add_link(record, sha, paths, BY, now):
            linked.append(record)
            record_changed = True
        if mark_implemented(record, sha, BY, now):
            record_changed = True
        if record_changed:
            changed_records.append(record)
    if not implemented:
        return 0
    for record in changed_records:
        record.save()
    write_index(store)
    consume_pending(root, {str(record.data.get("id")) for record in implemented})
    if linked:
        print(
            f"scribe: linked {len(linked)} record(s) to {short_sha(sha)}; "
            "run git add docs/decisions to include the backlinks in your next commit",
            file=sys.stderr,
        )
    return 0
