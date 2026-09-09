"""`scribe check --base <ref>`: the merge gate that CI runs (plan 5.4).

The check answers one question about a pull request range: does this branch
introduce or lean on an unreviewed decision that overrides a ratified one, and
is the ledger itself still intact. Ordinary unreviewed records pass; the gate is
about supersession (F11), attestations, and the append-only rules that the
single-file validator cannot see.
"""

from __future__ import annotations

from pathlib import Path

from . import gitutil
from .frontmatter import split
from .history_check import (
    ATTESTATIONS_PATH,
    check_attestations_append_only,
    check_records_against_base,
)
from .index import check_index
from .matching import matches_affects
from .record import Record
from .schema import validate_record
from .store import Store

OK_MESSAGE = "scribe check: ok"


def _relative_to_root(store: Store, path: Path) -> str:
    try:
        return path.resolve().relative_to(store.root).as_posix()
    except ValueError:
        return path.as_posix()


def _decision_trailer_tokens(commits: list[str], root: Path) -> set[str]:
    """Every whitespace token of every `Decision:` trailer in the range."""
    tokens: set[str] = set()
    for sha in commits:
        for value in gitutil.commit_trailer_values(sha, "Decision", root):
            tokens.update(value.split())
    return tokens


def _was_ratified_at_base(store: Store, record: Record, base: str) -> bool:
    path = _relative_to_root(store, record.path)
    text = gitutil.show_blob(base, path, store.root)
    if text is None:
        return False
    try:
        data, _ = split(text)
    except ValueError:
        return False
    return data.get("review_state") == "ratified"


def _supersede_gate(
    store: Store,
    base: str,
    changed_paths: list[str],
    commits: list[str],
) -> list[str]:
    """Rule 1: an unreviewed record overriding a ratified one, introduced or depended on."""
    trailer_tokens = _decision_trailer_tokens(commits, store.root)
    changed = set(changed_paths)
    reasons: list[str] = []
    for record in store.records():
        if record.data.get("review_state") != "unreviewed":
            continue
        predecessor = store.resolve(record.data.get("supersedes"))
        if predecessor is None:
            continue
        if predecessor.data.get(
            "review_state"
        ) != "ratified" and not _was_ratified_at_base(store, predecessor, base):
            continue
        alias = str(record.data.get("alias") or "")
        introduced = _relative_to_root(store, record.path) in changed
        affects = record.data.get("affects") or []
        depended_on = any(matches_affects(affects, path) for path in changed_paths)
        trailered = alias in trailer_tokens or record.data.get("id") in trailer_tokens
        if introduced or depended_on or trailered:
            reasons.append(
                f"{alias} supersedes ratified {predecessor.data.get('alias')} "
                "and this branch introduces or depends on it"
            )
    return reasons


def _changed_record_paths(store: Store, changed_paths: list[str]) -> list[str]:
    prefix = _relative_to_root(store, store.path) + "/"
    return [
        path
        for path in changed_paths
        if path.startswith(prefix)
        and path.endswith(".md")
        and path.rsplit("/", 1)[-1].startswith("D-")
    ]


def _validate_changed_records(store: Store, changed_paths: list[str]) -> list[str]:
    """Rule 2: every record the range touched still validates, attestations included."""
    reasons: list[str] = []
    for relative in _changed_record_paths(store, changed_paths):
        target = store.root / relative
        if not target.is_file():
            continue
        try:
            record = Record.load(target)
            problems = validate_record(
                record.data, record.body, store=store, path=target
            )
        except (OSError, ValueError) as exc:
            reasons.append(f"{relative}: parse_error: {exc}")
            continue
        reasons.extend(
            f"{relative}: {problem.code}: {problem.message}"
            for problem in problems
            if problem.severity == "error"
        )
    return reasons


def _index_stale(store: Store) -> list[str]:
    """Rule 3: INDEX.md matches what `scribe index` would write."""
    target, up_to_date = check_index(store)
    if up_to_date:
        return []
    return [f"{_relative_to_root(store, target)}: index_stale: run scribe index"]


def check_range(store: Store, base: str) -> list[str]:
    """Every reason this range must not merge, in plan 5.4 rule order."""
    root = store.root
    fork_point = gitutil.merge_base(base, "HEAD", root) or base
    changed_paths = gitutil.diff_names(base, "HEAD", root)
    commits = gitutil.rev_list_range(base, "HEAD", root)

    reasons = _supersede_gate(store, fork_point, changed_paths, commits)
    reasons.extend(_validate_changed_records(store, changed_paths))
    reasons.extend(_index_stale(store))
    reasons.extend(
        f"{ATTESTATIONS_PATH}: {problem.code}: {problem.message}"
        for problem in check_attestations_append_only(fork_point, root)
    )
    reasons.extend(
        f"{path}: {problem.code}: {problem.message}"
        for path, problem in check_records_against_base(fork_point, root)
    )
    return reasons


def run_check(base: str, start: str | Path = ".") -> tuple[int, list[str]]:
    """Exit code and the lines `scribe check` prints."""
    store = Store.discover(start)
    if store is None or not store.path.is_dir():
        return 1, ["no decision store found (docs/decisions)"]
    if gitutil.rev_parse_commit(base, store.root) is None:
        return 1, [f"unknown base ref: {base}"]
    reasons = check_range(store, base)
    if reasons:
        return 1, reasons
    return 0, [OK_MESSAGE]
