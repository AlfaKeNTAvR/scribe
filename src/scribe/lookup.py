"""Reverse lookup between commits and decision records (plan section 4.6).

Both directions run off the `Decision: <alias> <ulid>` commit trailer: commit ->
records, and record -> the commits that name it plus its implementation links.
"""

from __future__ import annotations

from pathlib import Path

from . import gitutil
from .record import Record
from .store import Store

TRAILER_KEY = "Decision"


def trailer_tokens(values: list[str]) -> list[str]:
    """Split `Decision:` trailer values into their alias and ULID tokens."""
    tokens: list[str] = []
    for value in values:
        tokens.extend(value.split())
    return tokens


def relative_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def format_record(record: Record, store: Store) -> str:
    data = record.data
    return "{alias} {ulid} {path} ({review}, {effective})".format(
        alias=data.get("alias", "?"),
        ulid=data.get("id", "?"),
        path=relative_path(record.path, store.root),
        review=data.get("review_state", "?"),
        effective=data.get("effective_state", "?"),
    )


def describe_commit(sha: str, store: Store) -> tuple[list[str], int]:
    """Resolve one commit's Decision trailers into record lines."""
    values = gitutil.commit_trailer_values(sha, TRAILER_KEY, store.root)
    tokens = trailer_tokens(values)
    if not tokens:
        return [f"no {TRAILER_KEY} trailers on {sha}"], 0
    lines: list[str] = []
    seen: set[str] = set()
    status = 0
    for token in tokens:
        record = store.resolve(token)
        if record is None:
            lines.append(f"UNKNOWN {token}")
            status = 1
            continue
        line = format_record(record, store)
        if line not in seen:
            seen.add(line)
            lines.append(line)
    return lines, status


def commits_for_record(record: Record, store: Store) -> list[tuple[str, str]]:
    """Commits whose Decision trailers name this record; trailers are the truth."""
    identifiers = [
        value
        for value in (record.data.get("id"), record.data.get("alias"))
        if isinstance(value, str) and value
    ]
    if not identifiers:
        return []
    matches: list[tuple[str, str]] = []
    for sha, subject in gitutil.log_grep_all(identifiers, store.root):
        values = gitutil.commit_trailer_values(sha, TRAILER_KEY, store.root)
        if any(token in identifiers for token in trailer_tokens(values)):
            matches.append((sha, subject))
    return matches


def format_links(record: Record, store: Store) -> list[str]:
    lines: list[str] = []
    history = gitutil.ReachableCommits(store.root)
    for link in record.data.get("implementation_links") or []:
        if not isinstance(link, dict):
            continue
        commit = str(link.get("commit", "?"))
        paths = " ".join(str(item) for item in (link.get("paths") or []))
        reachable = history.resolve(commit) is not None
        suffix = "" if reachable else " (not in this history)"
        lines.append(f"  {commit} {paths}{suffix}".rstrip())
    return lines


def describe_record(record: Record, store: Store) -> list[str]:
    lines = [relative_path(record.path, store.root), "commits:"]
    commits = commits_for_record(record, store)
    lines.extend(f"  {sha} {subject}" for sha, subject in commits)
    if not commits:
        lines.append("  (none)")
    lines.append("implementation_links:")
    links = format_links(record, store)
    lines.extend(links)
    if not links:
        lines.append("  (none)")
    return lines


def lookup(argument: str, store: Store) -> tuple[list[str], int]:
    """Return the printable lines and the exit status for `scribe lookup`."""
    sha = gitutil.rev_parse_commit(argument, store.root)
    if sha is not None:
        return describe_commit(sha, store)
    record = store.resolve(argument)
    if record is None:
        return [f"not found: {argument}"], 1
    return describe_record(record, store), 0
