"""INDEX.md generator: the human-facing view of the decision store (section 3.5).

Read only. The indexer trusts effective supersession edges (section 3.8), never a
predecessor's own `effective_state`; disagreement between the two is a lint
warning, not something this module repairs.
"""

from __future__ import annotations

from pathlib import Path

from .record import Record
from .state import ledger_lock_path, locked
from .store import Store

HEADING = "# Decision index"
QUEUE_NOTE = (
    "Ordered: records that supersede a ratified record first, then implemented, "
    "then proposed; newest first within each group."
)
INDEX_FILENAME = "INDEX.md"


def _sort_newest_first(records: list[Record]) -> list[Record]:
    """Date descending, alias ascending within a date."""
    by_alias = sorted(records, key=lambda record: str(record.data.get("alias") or ""))
    return sorted(
        by_alias, key=lambda record: str(record.data.get("date") or ""), reverse=True
    )


def _affects_text(record: Record) -> str:
    patterns = []
    for item in record.data.get("affects") or []:
        if not isinstance(item, dict) or item.get("type") != "path":
            continue
        prefix = "!" if item.get("negate") else ""
        patterns.append(f"{prefix}{item.get('pattern')}")
    return ", ".join(patterns)


def _queue_groups(store: Store, queue: list[Record]) -> list[tuple[Record, str]]:
    """Group 1 supersedes a ratified record, group 2 is implemented, group 3 the rest."""
    supersedes_ratified: list[Record] = []
    implemented: list[Record] = []
    rest: list[Record] = []
    predecessor_alias: dict[int, str] = {}
    for record in queue:
        predecessor = store.resolve(record.data.get("supersedes"))
        if (
            predecessor is not None
            and predecessor.data.get("review_state") == "ratified"
        ):
            supersedes_ratified.append(record)
            predecessor_alias[id(record)] = str(predecessor.data.get("alias") or "")
        elif record.data.get("effective_state") == "implemented":
            implemented.append(record)
        else:
            rest.append(record)
    ordered: list[tuple[Record, str]] = []
    for group in (supersedes_ratified, implemented, rest):
        ordered.extend(
            (record, predecessor_alias.get(id(record), ""))
            for record in _sort_newest_first(group)
        )
    return ordered


def _record_fields(record: Record) -> list[str]:
    """Standard bullet fields shared by every section: state, by, review, title,
    affects (omitted when there are none), regret (omitted when empty)."""
    fields = [
        f"state: {record.data.get('effective_state') or ''}, "
        f"{record.data.get('review_state') or ''}",
        f"by: {record.data.get('decided_by') or ''}",
        f"review: {record.data.get('review') or ''}",
        f"title: {str(record.data.get('title') or '').strip()}",
    ]
    affects = _affects_text(record)
    if affects:
        fields.append(f"affects: {affects}")
    regret = record.data.get("regret_when")
    if regret:
        fields.append(f"regret: {str(regret).strip()}")
    return fields


def _record_block(heading: str, fields: list[str]) -> str:
    lines = [heading]
    lines.extend(f"- {field}" for field in fields)
    return "\n".join(lines)


def _queue_block(position: int, record: Record, predecessor: str) -> str:
    alias = str(record.data.get("alias") or "")
    marker = " [supersedes ratified]" if predecessor else ""
    fields = _record_fields(record)
    if predecessor:
        fields.insert(0, f"supersedes: {predecessor}")
    return _record_block(f"### {position}. {alias}{marker}", fields)


def _active_block(record: Record) -> str:
    alias = str(record.data.get("alias") or "")
    return _record_block(f"### {alias}", _record_fields(record))


def _retired_block(record: Record, state: str) -> str:
    alias = str(record.data.get("alias") or "")
    fields = _record_fields(record)
    fields.insert(0, f"retired: {state}")
    return _record_block(f"### {alias}", fields)


def _retired_state(record: Record, successor_alias: str) -> str | None:
    if successor_alias:
        return f"superseded by {successor_alias}"
    if record.data.get("review_state") == "rejected":
        return "rejected"
    effective = record.data.get("effective_state")
    if effective == "expired":
        return "expired"
    if effective == "backtracked":
        return "backtracked"
    if effective == "superseded":
        return "superseded (stale)"
    return None


def _successor_aliases(store: Store) -> dict[int, str]:
    """Effective incoming edge per predecessor, newest successor wins on a tie."""
    successors: dict[int, list[Record]] = {}
    for successor, predecessor in store.effective_edges():
        successors.setdefault(id(predecessor), []).append(successor)
    return {
        key: str(_sort_newest_first(group)[0].data.get("alias") or "")
        for key, group in successors.items()
    }


def render_index(store: Store) -> str:
    records = store.records()
    incoming = _successor_aliases(store)

    queue = [
        record for record in records if record.data.get("review_state") == "unreviewed"
    ]
    queue_blocks = [
        _queue_block(position, record, predecessor)
        for position, (record, predecessor) in enumerate(_queue_groups(store, queue), 1)
    ]

    active_blocks = []
    retired_blocks = []
    for record in _sort_newest_first(records):
        successor_alias = incoming.get(id(record), "")
        state = _retired_state(record, successor_alias)
        if state is not None:
            retired_blocks.append(_retired_block(record, state))
        elif store.effective_authority(record):
            active_blocks.append(_active_block(record))

    blocks = [
        HEADING,
        f"Generated by `scribe index` from {len(records)} records. Do not edit by hand.",
        f"## Review queue ({len(queue_blocks)})",
        QUEUE_NOTE,
    ]
    if queue_blocks:
        blocks.append("\n\n".join(queue_blocks))
    blocks.append(f"## Active decisions ({len(active_blocks)})")
    if active_blocks:
        blocks.append("\n\n".join(active_blocks))
    blocks.append(f"## Retired ({len(retired_blocks)})")
    if retired_blocks:
        blocks.append("\n\n".join(retired_blocks))
    return "\n\n".join(blocks) + "\n"


def index_path(store: Store) -> Path:
    return store.path / INDEX_FILENAME


def write_index(store: Store) -> tuple[Path, bool]:
    """Write INDEX.md; the flag says whether the file on disk changed."""
    target = index_path(store)
    text = render_index(store)
    changed = not target.exists() or target.read_text(encoding="utf-8") != text
    if changed:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    return target, changed


def check_index(store: Store) -> tuple[Path, bool]:
    """Compare INDEX.md on disk with the generated text without writing."""
    target = index_path(store)
    if not target.exists():
        return target, False
    return target, target.read_text(encoding="utf-8") == render_index(store)


# --- lock-guarded entry points (V8) ------------------------------------------
#
# `scribe index` and `scribe lint`'s index rule are the only two callers that
# read or write INDEX.md from outside a lock some other writer (new,
# post-commit, relink, lint --expire, ratify/reject) already holds; without
# this they can render from a stale in-memory record list, or a `--fix-index`
# write can race a concurrent ratify and overwrite it. Both wrappers take the
# same ledger lock those writers use, reload records from disk only after the
# lock is held, then delegate to the plain function above. On a lock timeout
# `acquired` is False and the other two values are meaningless; the caller
# must not act on them and must write nothing.


def locked_check_index(store: Store) -> tuple[Path, bool, bool]:
    with locked(ledger_lock_path(store.root)) as acquired:
        if not acquired:
            return index_path(store), False, False
        store.records(refresh=True)
        target, up_to_date = check_index(store)
        return target, up_to_date, True


def locked_write_index(store: Store) -> tuple[Path, bool, bool]:
    with locked(ledger_lock_path(store.root)) as acquired:
        if not acquired:
            return index_path(store), False, False
        store.records(refresh=True)
        target, changed = write_index(store)
        return target, changed, True
