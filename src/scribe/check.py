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
    DECISIONS_DIR,
    check_attestations_append_only,
    check_records_against_base,
)
from .index import check_index
from .links import implementation_paths
from .record import Record
from .schema import validate_record
from .store import Store, attestation_line_problems

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
    base_tip: str,
    changed_paths: list[str],
    commits: list[str],
) -> list[str]:
    """Rule 1: an unreviewed record overriding a ratified one, introduced or depended on.

    `base_tip` is the base ref exactly as given (V3): the predecessor-was-ratified
    question is asked against the target branch's current tip, not the merge base,
    so a ratification landed on the target branch after this branch forked is still
    honoured. `changed_paths` and `commits`, by contrast, are the merge-base range
    (computed by the caller): only this branch's own deltas count as "introduces or
    depends on", not unrelated commits the target picked up after the fork.
    """
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
        ) != "ratified" and not _was_ratified_at_base(store, predecessor, base_tip):
            continue
        alias = str(record.data.get("alias") or "")
        introduced = _relative_to_root(store, record.path) in changed
        depended_on = bool(implementation_paths(record, changed_paths))
        trailered = alias in trailer_tokens or record.data.get("id") in trailer_tokens
        if introduced or depended_on or trailered:
            reasons.append(
                f"{alias} supersedes ratified {predecessor.data.get('alias')} "
                "and this branch introduces or depends on it"
            )
    return reasons


def _validate_all_records(store: Store) -> list[str]:
    """Rule 2: every current record still validates, attestations included.

    Validated by path (not `store.records()`), so a malformed file still
    surfaces its own `parse_error` instead of being silently skipped from the
    collection (V17 makes `store.records()` resilient for the *other*
    consumers of the store; the CI gate needs the opposite). Every record is
    checked, not only the ones the range's diff touched: an append to
    RATIFICATIONS.jsonl can make an otherwise-unchanged record's review state
    contradict its latest attestation, and that must still fail the check (V5).
    """
    reasons: list[str] = []
    for target in sorted(store.path.glob("D-*.md")):
        relative = _relative_to_root(store, target)
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


def _attestation_integrity(store: Store) -> list[str]:
    """Rule 4b: the current ledger has no malformed, incomplete or truncated line (V5)."""
    path = store.path / "RATIFICATIONS.jsonl"
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    return [
        f"{ATTESTATIONS_PATH}: {problem.code}: {problem.message}"
        for problem in attestation_line_problems(text)
    ]


def _alias_at(root: Path, rev: str, path: str) -> str:
    """The alias a deleted record carried at `rev`, falling back to its filename stem."""
    text = gitutil.show_blob(rev, path, root)
    if text is not None:
        try:
            data, _ = split(text)
        except ValueError:
            data = {}
        alias = data.get("alias")
        if isinstance(alias, str) and alias:
            return alias
    return Path(path).stem


def _deleted_record_paths(
    base_paths: set[str], head_paths: set[str], range_deleted: list[str]
) -> set[str]:
    """Every record path missing at HEAD that existed somewhere in the range (V6).

    Base-vs-HEAD alone misses a record that was both added and deleted
    inside the same range: neither endpoint carries it, so a plain
    `base_paths - head_paths` set difference never sees it. Union in every
    path any commit in `base..head` deleted (`range_deleted`, one `git log
    --diff-filter=D --name-only -z` call for the whole range, not a tree or
    diff per commit) before subtracting what HEAD still has. A record deleted
    and then restored within the range is not reported: it is present at
    HEAD, so it drops out of the final subtraction regardless of which
    source saw the deletion.
    """
    deleted = {
        path
        for path in range_deleted
        if path.endswith(".md") and path.rsplit("/", 1)[-1].startswith("D-")
    }
    return (base_paths | deleted) - head_paths


def _deleted_record_reasons(
    root: Path,
    base: str,
    base_paths: set[str],
    head_paths: set[str],
    range_deleted: list[str],
) -> list[str]:
    """Rule 6: a record deleted anywhere in the range must not merge (V6).

    Retirement goes through `expired` or `backtracked`; deleting the file
    bypasses the ledger's immutability, so the owner's call is that this
    always fails, with no `--allow-delete` escape (supersedes I45). Covers
    both a record present at the base and gone at the tip, and one added
    after the base and deleted again before the tip (`_deleted_record_paths`).
    The three inputs are precomputed by the caller with the strict git
    helpers (V3(b)): a git failure while listing either tree or the range's
    deletions must fail the check, not be read as "no records here".
    """
    return [
        f"{path}: record_deleted: {_alias_at(root, base, path)} was deleted inside "
        "this range and is missing at HEAD; retire it with expired or backtracked "
        "instead of deleting the file"
        for path in sorted(_deleted_record_paths(base_paths, head_paths, range_deleted))
    ]


def check_range(store: Store, base: str) -> list[str]:
    """Every reason this range must not merge, in plan 5.4 rule order.

    Changed paths and commits come from the merge-base range (`fork_point`):
    they describe this branch's own delta, not whatever the target branch did
    on its own after the fork. The predecessor-was-ratified question inside
    the supersede gate is the one exception (V3): it is asked against `base`
    itself, the target ref's current tip, so a ratification landed there
    after the fork is honoured rather than lost.

    Every git call that builds the range uses the strict form (V3(b)): a bad
    ref, a missing object, or a broken repository raises `gitutil.GitError`
    instead of silently emptying the range, and is turned here into one
    explicit reason the check fails, rather than letting the historical rules
    below see an empty range and pass vacuously.
    """
    root = store.root
    try:
        fork_point = gitutil.merge_base(base, "HEAD", root, strict=True)
        changed_paths = gitutil.diff_names(fork_point, "HEAD", root, strict=True)
        commits = gitutil.rev_list_range(fork_point, "HEAD", root, strict=True)
        base_record_paths = set(
            gitutil.tree_record_paths(fork_point, DECISIONS_DIR, root, strict=True)
        )
        head_record_paths = set(
            gitutil.tree_record_paths("HEAD", DECISIONS_DIR, root, strict=True)
        )
        range_deleted = gitutil.deleted_paths_in_range(
            fork_point, "HEAD", DECISIONS_DIR, root, strict=True
        )
    except gitutil.GitError as exc:
        return [str(exc)]

    reasons = _supersede_gate(store, base, changed_paths, commits)
    reasons.extend(_validate_all_records(store))
    reasons.extend(_index_stale(store))
    reasons.extend(_attestation_integrity(store))
    reasons.extend(
        f"{ATTESTATIONS_PATH}: {problem.code}: {problem.message}"
        for problem in check_attestations_append_only(fork_point, root)
    )
    reasons.extend(
        f"{path}: {problem.code}: {problem.message}"
        for path, problem in check_records_against_base(
            fork_point, root, paths=sorted(base_record_paths)
        )
    )
    reasons.extend(
        _deleted_record_reasons(
            root, fork_point, base_record_paths, head_record_paths, range_deleted
        )
    )
    return reasons


def run_check(
    base: str, start: str | Path = ".", allow_dirty: bool = False
) -> tuple[int, list[str]]:
    """Exit code and the lines `scribe check` prints.

    A dirty ledger is refused by default (V3's cheap interim): this check
    reads records, attestations and the index off disk, so an uncommitted
    change under `docs/decisions` could mask or fake a result the committed
    range does not actually contain. `--allow-dirty` (surfaced by the caller)
    skips the guard for a caller that knows what it is doing. The dirtiness
    probe itself uses the strict form (V3(b), Codex review addendum): a
    failed `git status` has empty stdout, so the tolerant form reads it as
    "clean", and this check must not proceed on that misreading.
    """
    store = Store.discover(start)
    if store is None or not store.path.is_dir():
        return 1, ["no decision store found (docs/decisions)"]
    if not allow_dirty:
        try:
            dirty = gitutil.is_dirty(DECISIONS_DIR, store.root, strict=True)
        except gitutil.GitError as exc:
            return 1, [str(exc)]
        if dirty:
            return 1, [
                f"{DECISIONS_DIR} has uncommitted changes; commit them or re-run "
                "with --allow-dirty"
            ]
    if gitutil.rev_parse_commit(base, store.root) is None:
        return 1, [f"unknown base ref: {base}"]
    reasons = check_range(store, base)
    if reasons:
        return 1, reasons
    return 0, [OK_MESSAGE]
