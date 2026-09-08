from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Iterable

from .record import Record


class Store:
    def __init__(self, root: str | Path):
        supplied = Path(root).resolve()
        if supplied.name == "decisions" and supplied.parent.name == "docs":
            self.root = supplied.parent.parent
            self.path = supplied
        else:
            self.root = supplied
            self.path = supplied / "docs" / "decisions"
        self._records: list[Record] | None = None

    @classmethod
    def discover(cls, start: str | Path = ".") -> "Store | None":
        candidate = Path(start).resolve()
        if candidate.is_file():
            candidate = candidate.parent
        result = subprocess.run(
            ["git", "-C", str(candidate), "rev-parse", "--show-toplevel"],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            store = cls(result.stdout.strip())
            return store if store.path.is_dir() else None
        for parent in (candidate, *candidate.parents):
            if (parent / "docs" / "decisions").is_dir():
                return cls(parent)
        return None

    def records(self, refresh: bool = False) -> list[Record]:
        if self._records is None or refresh:
            self._records = [
                Record.load(path) for path in sorted(self.path.glob("D-*.md"))
            ]
        return self._records

    def __iter__(self) -> Iterable[Record]:
        return iter(self.records())

    def iter_records(self) -> Iterable[Record]:
        return iter(self.records())

    def resolve(self, value: object) -> Record | None:
        if not isinstance(value, str):
            return None
        return next(
            (
                record
                for record in self.records()
                if value in (record.data.get("id"), record.data.get("alias"))
            ),
            None,
        )

    def effective_edges(self) -> list[tuple[Record, Record]]:
        edges = []
        for successor in self.records():
            data = successor.data
            if data.get("review_state") == "rejected" or data.get(
                "effective_state"
            ) not in {"proposed", "implemented", "superseded"}:
                continue
            predecessor = self.resolve(data.get("supersedes"))
            if predecessor is not None:
                edges.append((successor, predecessor))
        return edges

    def latest_attestation(self, record_id: object) -> dict[str, Any] | None:
        if not isinstance(record_id, str):
            return None
        path = self.path / "RATIFICATIONS.jsonl"
        if not path.exists():
            return None
        latest = None
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(item, dict) and item.get("id") == record_id:
                latest = item
        return latest


def reconcile_supersession(records: list[Record], by: str) -> list[Record]:
    """Keep predecessor state aligned with effective supersession edges."""
    by_id = {record.data.get("id"): record for record in records}
    by_alias = {record.data.get("alias"): record for record in records}
    incoming: set[int] = set()
    for successor in records:
        if successor.data.get("review_state") == "rejected" or successor.data.get(
            "effective_state"
        ) not in {"proposed", "implemented", "superseded"}:
            continue
        predecessor = by_id.get(successor.data.get("supersedes")) or by_alias.get(
            successor.data.get("supersedes")
        )
        if predecessor is not None:
            incoming.add(id(predecessor))
    changed = []
    for record in records:
        state = record.data.get("effective_state")
        if id(record) in incoming and state in {"proposed", "implemented"}:
            record.apply_change("effective_state", "superseded", "superseded", by)
            changed.append(record)
        elif id(record) not in incoming and state == "superseded":
            prior = next(
                (
                    item.get("old")
                    for item in reversed(record.data.get("history", []))
                    if item.get("event") == "superseded"
                    and item.get("field") == "effective_state"
                ),
                None,
            )
            if prior not in {"proposed", "implemented"}:
                continue
            record.apply_change("effective_state", prior, "restored", by)
            changed.append(record)
    return changed
