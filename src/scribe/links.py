"""Code-to-decision links: which changed paths a record claims, and adding a link.

`implementation_paths` is the one predicate shared by `prepare-commit-msg`
(pending filter), `post-commit` (link and consume), `scribe check` (F11
"depends on") and `scribe relink` (plan 5.3): a commit implements a record when
it changes at least one path outside `docs/decisions/` that the record's
`affects` claims. A record with no `type: path` entry claims every such path.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .matching import matches_affects
from .record import Record

STORE_PREFIX = "docs/decisions/"
SHORT_SHA_LENGTH = 12


def _path_entries(record: Record) -> list[dict[str, Any]]:
    return [
        item
        for item in record.data.get("affects") or []
        if isinstance(item, dict) and item.get("type") == "path"
    ]


def implementation_paths(record: Record, changed_paths: Iterable[str]) -> list[str]:
    """Changed paths outside the store that the record's `affects` claims."""
    candidates = [
        path
        for path in changed_paths
        if isinstance(path, str) and not path.startswith(STORE_PREFIX)
    ]
    entries = _path_entries(record)
    if not entries:
        return candidates
    return [path for path in candidates if matches_affects(entries, path)]


def short_sha(sha: str) -> str:
    return sha[:SHORT_SHA_LENGTH]


def has_link(record: Record, sha: str) -> bool:
    """True when a link names this commit (either sha may be abbreviated)."""
    for link in record.data.get("implementation_links") or []:
        if not isinstance(link, dict):
            continue
        commit = str(link.get("commit") or "")
        if commit and (sha.startswith(commit) or commit.startswith(sha)):
            return True
    return False


def add_link(record: Record, sha: str, paths: list[str], by: str, at: str) -> bool:
    """Append `{commit, paths}` unless a link for the commit exists; returns whether it did."""
    if not paths or has_link(record, sha):
        return False
    links = list(record.data.get("implementation_links") or [])
    links.append({"commit": short_sha(sha), "paths": list(paths)})
    record.apply_change(
        "implementation_links", links, "link_added", by, at=at, commit=short_sha(sha)
    )
    return True


def mark_implemented(record: Record, sha: str, by: str, at: str) -> bool:
    """A proposed record with a link becomes implemented; other states are kept."""
    if record.data.get("effective_state") != "proposed":
        return False
    return record.apply_change(
        "effective_state",
        "implemented",
        "implemented",
        by,
        at=at,
        commit=short_sha(sha),
    )
