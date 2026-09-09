"""`scribe relink`: rebuild implementation_links from git history (plan 5.3, F15).

Amend and rebase change shas; `post-commit` only ever appends, so a stale link
survives an amend until something rebuilds the list from scratch. This module
walks every commit reachable from any ref, matches `Decision:` trailers to
records the same way `post-commit` does, and rebuilds each record's
`implementation_links` as: a link whose commit is still reachable is kept
(its `paths` refreshed against the commit's actual changed paths), a link
whose commit is no longer reachable is dropped, and a reachable commit that
carries the record's trailer and touches a claimed path but was never linked
is added. There is no range option: relink always looks at the whole history.
"""

from __future__ import annotations

from pathlib import Path

from . import gitutil
from .links import implementation_paths, mark_implemented, short_sha
from .lookup import TRAILER_KEY, trailer_tokens
from .record import Record, utc_now
from .store import Store

BY = "scribe-relink"


def _commit_matches(record: Record, tokens: list[str]) -> bool:
    return record.data.get("id") in tokens or record.data.get("alias") in tokens


def _implementing_commits(
    store: Store, root: Path, history: gitutil.ReachableCommits
) -> dict[str, list[tuple[str, list[str]]]]:
    """record id -> [(full sha, paths)] for every reachable commit that implements it.

    Newest first, following `git rev-list --all`.
    """
    by_record: dict[str, list[tuple[str, list[str]]]] = {}
    for sha in history.commits:
        tokens = trailer_tokens(gitutil.commit_trailer_values(sha, TRAILER_KEY, root))
        if not tokens:
            continue
        changed = None
        for record in store.records():
            if not _commit_matches(record, tokens):
                continue
            if changed is None:
                changed = gitutil.commit_changed_paths(sha, root)
            paths = implementation_paths(record, changed)
            if paths:
                record_id = str(record.data.get("id"))
                by_record.setdefault(record_id, []).append((sha, paths))
    return by_record


def _rebuild_links(
    record: Record,
    reachable: gitutil.ReachableCommits,
    matches: list[tuple[str, list[str]]],
    root: Path,
) -> list[dict[str, object]]:
    """Kept links (refreshed) in their existing order, then new ones, oldest first."""
    old_links = [
        link
        for link in record.data.get("implementation_links") or []
        if isinstance(link, dict)
    ]
    kept: dict[str, list[str]] = {}
    for link in old_links:
        commit = str(link.get("commit") or "")
        full = reachable.resolve(commit)
        if full is None:
            continue
        paths = implementation_paths(record, gitutil.commit_changed_paths(full, root))
        if paths:
            kept[short_sha(full)] = paths
    for sha, paths in reversed(matches):
        kept.setdefault(short_sha(sha), paths)
    return [{"commit": key, "paths": paths} for key, paths in kept.items()]


def run_relink(start: str | Path = ".") -> tuple[int, list[str]]:
    """Exit code and the lines `scribe relink` prints."""
    root = gitutil.toplevel(start)
    if root is None:
        return 1, ["scribe: not inside a git repository"]
    store = Store.discover(root)
    if store is None or not store.path.is_dir():
        return 1, ["no decision store found (docs/decisions)"]

    reachable = gitutil.ReachableCommits(root)
    matches = _implementing_commits(store, root, reachable)
    now = utc_now()
    changed_records: list[Record] = []
    lines: list[str] = []

    for record in store.records():
        record_id = str(record.data.get("id"))
        old_links = list(record.data.get("implementation_links") or [])
        new_links = _rebuild_links(record, reachable, matches.get(record_id, []), root)
        if new_links == old_links:
            continue
        record.apply_change("implementation_links", new_links, "relinked", BY, at=now)
        if new_links:
            mark_implemented(record, str(new_links[-1]["commit"]), BY, now)
        changed_records.append(record)
        lines.append(f"relinked {record.data.get('alias')}: {len(new_links)} commit(s)")

    for record in changed_records:
        record.save()
    if changed_records:
        from .index import write_index

        write_index(store)
    if not lines:
        lines.append("scribe relink: nothing to relink")
    return 0, lines
