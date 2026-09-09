from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .frontmatter import join, split

MUTABLE_KEYS = {
    "review_state",
    "effective_state",
    "ratified_by",
    "ratified_at",
    "implementation_links",
    "supersedes",
    "history",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Record:
    path: Path
    data: dict[str, Any]
    body: str

    @classmethod
    def load(cls, path: str | Path) -> Record:
        record_path = Path(path)
        data, body = split(record_path.read_text(encoding="utf-8"))
        return cls(record_path, data, body)

    def save(self) -> None:
        """Write through a temp file and atomically replace it (crash-safe).

        The temp file is created at 0o644 (umask still applies, same as
        `_write_record_exclusive` in newrecord.py), not the platform default
        of 0o666, so a fresh record and a rewritten one always land at the
        same mode regardless of what the process umask happens to be. Since
        every write recreates the file at 0o644, an existing record's mode
        is normalized back to 0o644 rather than literally preserved bit for
        bit; see docs/build/12-review-fix-f2.md for why that's the intended
        behaviour here.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        descriptor = os.open(temporary, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o644)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(join(self.data, self.body))
        os.replace(temporary, self.path)

    def body_sha256(self) -> str:
        normalized = self.body.replace("\r\n", "\n").replace("\r", "\n")
        return hashlib.sha256(normalized.rstrip().encode("utf-8")).hexdigest()

    def apply_change(
        self,
        field: str,
        new: Any,
        event: str,
        by: str,
        *,
        force: bool = False,
        **extra: Any,
    ) -> bool:
        """Set `field` and append one history entry; `force` records an unchanged value too.

        `force` serves the ratify and reject reversals (plan 3.8): the matrix
        promises three history entries even when the same person reverses their
        own verdict and `ratified_by` keeps its value.
        """
        if field not in MUTABLE_KEYS - {"history"}:
            raise ValueError(f"immutable field: {field}")
        old = self.data.get(field)
        if old == new and not force:
            return False
        self.data[field] = new
        entry = {
            "at": extra.pop("at", utc_now()),
            "event": event,
            "by": by,
            **extra,
            "field": field,
            "old": old,
            "new": new,
        }
        self.data.setdefault("history", []).append(entry)
        return True
