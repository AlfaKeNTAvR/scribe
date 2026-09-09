"""INDEX.md generator: the human-facing view of the decision store (section 3.5).

Read only. The indexer trusts effective supersession edges (section 3.8), never a
predecessor's own `effective_state`; disagreement between the two is a lint
warning, not something this module repairs.
"""

from __future__ import annotations

from pathlib import Path

from .record import Record
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
    return " ".join(patterns)


def _title_text(record: Record, with_tail: bool = True) -> str:
    segments = [str(record.data.get("title") or "").strip()]
    if with_tail:
        regret = record.data.get("regret_when")
        if regret:
            segments.append(f"Regret: {str(regret).strip()}")
        review = record.data.get("review")
        if review:
            segments.append(f"Review {review}")
    return ". ".join(segment.rstrip(".") for segment in segments if segment) + "."


def _join_fields(fields: list[str]) -> str:
    return " | ".join(field for field in fields if field)


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


def _queue_line(position: int, record: Record, predecessor: str) -> str:
    marker = "[supersedes ratified] " if predecessor else ""
    fields = [
        str(record.data.get("alias") or ""),
        str(record.data.get("effective_state") or ""),
        str(record.data.get("review_state") or ""),
        str(record.data.get("decided_by") or ""),
    ]
    if predecessor:
        fields.append(f"supersedes {predecessor}")
    fields.append(_affects_text(record))
    fields.append(_title_text(record))
    return f"{position}. {marker}{_join_fields(fields)}"


def _active_line(record: Record) -> str:
    return _join_fields(
        [
            str(record.data.get("alias") or ""),
            str(record.data.get("effective_state") or ""),
            str(record.data.get("review_state") or ""),
            str(record.data.get("decided_by") or ""),
            _affects_text(record),
            _title_text(record),
        ]
    )


def _retired_line(record: Record, state: str) -> str:
    return _join_fields(
        [
            str(record.data.get("alias") or ""),
            state,
            str(record.data.get("review_state") or ""),
            str(record.data.get("decided_by") or ""),
            _title_text(record, with_tail=False),
        ]
    )


def _retired_state(record: Record, successor_alias: str) -> str | None:
    if successor_alias:
        return f"superseded by {successor_alias}"
    if record.data.get("review_state") == "rejected":
        return "rejected"
    effective = record.data.get("effective_state")
    if effective == "expired":
        return "expired"
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
    queue_lines = [
        _queue_line(position, record, predecessor)
        for position, (record, predecessor) in enumerate(_queue_groups(store, queue), 1)
    ]

    active_lines = []
    retired_lines = []
    for record in _sort_newest_first(records):
        successor_alias = incoming.get(id(record), "")
        state = _retired_state(record, successor_alias)
        if state is not None:
            retired_lines.append(_retired_line(record, state))
        elif store.effective_authority(record):
            active_lines.append(_active_line(record))

    blocks = [
        HEADING,
        f"Generated by `scribe index` from {len(records)} records. Do not edit by hand.",
        f"## Review queue ({len(queue_lines)})",
        QUEUE_NOTE,
    ]
    if queue_lines:
        blocks.append("\n".join(queue_lines))
    blocks.append(f"## Active decisions ({len(active_lines)})")
    if active_lines:
        blocks.append("\n".join(active_lines))
    blocks.append(f"## Retired ({len(retired_lines)})")
    if retired_lines:
        blocks.append("\n".join(retired_lines))
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
