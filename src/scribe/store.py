from __future__ import annotations

import json
import subprocess
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .record import Record
from .schema import Problem, unhashable_enum_reason
from .state import log_hook_error

REQUIRED_ATTESTATION_KEYS = ("id", "alias", "verdict", "by", "at", "via", "body_sha256")


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
    def discover(cls, start: str | Path = ".") -> Store | None:
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
        """Every loadable record; a malformed file is skipped and logged (V17).

        One bad file must not abort the whole collection: callers such as the
        supersede gate, the index, and lint all need the other records to
        still resolve, and `scribe validate` already reports a malformed file
        on its own by loading it directly rather than through the store.

        V17 follow-up: a file that parses as valid YAML but gives `review_state`,
        `effective_state` or `supersedes` a non-string value (e.g. `[]`) is not a
        `FrontMatterError` and used to load through untouched, then crash the
        first caller that tests one of those fields for set membership or uses it
        as a dict key (`effective_edges`, `effective_authority`,
        `reconcile_supersession`, lint's `ACTIVE_STATES` check) - taking every
        other record in that same pass down with it. `unhashable_enum_reason` is
        the same type check `validate_record` runs for these fields, so this
        stays consistent with `scribe validate` about what counts as malformed.
        """
        if self._records is None or refresh:
            loaded: list[Record] = []
            for path in sorted(self.path.glob("D-*.md")):
                try:
                    record = Record.load(path)
                except (OSError, ValueError) as exc:
                    log_hook_error(self.root, f"scribe: skipped {path.name}: {exc}")
                    continue
                reason = unhashable_enum_reason(record.data)
                if reason is not None:
                    log_hook_error(self.root, f"scribe: skipped {path.name}: {reason}")
                    continue
                loaded.append(record)
            self._records = loaded
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

    def effective_authority(self, record: Record) -> bool:
        """Whether this live record is currently backed by its latest ratification."""
        latest = self.latest_attestation(record.data.get("id"))
        if (
            latest is None
            or latest.get("verdict") != "ratified"
            or latest.get("body_sha256") != record.body_sha256()
            or record.data.get("review_state") != "ratified"
            or record.data.get("effective_state") not in {"proposed", "implemented"}
        ):
            return False
        return all(
            predecessor is not record for _, predecessor in self.effective_edges()
        )


def attestation_line_problems(text: str) -> list[Problem]:
    """Structural problems in RATIFICATIONS.jsonl content (V5).

    `Store.latest_attestation` above skips a bad line so lookups stay best
    effort; this function is the one that reports every malformed or
    incomplete line, and a truncated final line, as an error instead of
    silently dropping it. `scribe check` runs it over the whole file and
    `ratify`/`reject` run it before appending, so a broken ledger is never
    written past.
    """
    problems: list[Problem] = []
    if not text:
        return problems
    truncated_tail = not text.endswith("\n")
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return problems
    last_index = len(lines) - 1
    if truncated_tail:
        problems.append(
            Problem(
                "error",
                "attestation_truncated_tail",
                f"line {last_index + 1}: the final attestation line is truncated "
                "(no trailing newline)",
            )
        )
    for index, line in enumerate(lines):
        try:
            item = json.loads(line)
        except (json.JSONDecodeError, TypeError) as exc:
            if index == last_index and truncated_tail:
                continue  # already reported as attestation_truncated_tail
            problems.append(
                Problem(
                    "error",
                    "attestation_malformed",
                    f"line {index + 1}: malformed JSON: {exc}",
                )
            )
            continue
        if not isinstance(item, dict):
            problems.append(
                Problem(
                    "error",
                    "attestation_malformed",
                    f"line {index + 1}: attestation line is not a JSON object",
                )
            )
            continue
        missing = [key for key in REQUIRED_ATTESTATION_KEYS if not item.get(key)]
        if missing:
            problems.append(
                Problem(
                    "error",
                    "attestation_incomplete",
                    f"line {index + 1}: missing {', '.join(missing)}",
                )
            )
    return problems


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
