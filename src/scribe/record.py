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
    def load(cls, path: str | Path) -> "Record":
        record_path = Path(path)
        data, body = split(record_path.read_text(encoding="utf-8"))
        return cls(record_path, data, body)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        temporary.write_text(join(self.data, self.body), encoding="utf-8", newline="\n")
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
        **extra: Any,
    ) -> bool:
        if field not in MUTABLE_KEYS - {"history"}:
            raise ValueError(f"immutable field: {field}")
        old = self.data.get(field)
        if old == new:
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
