"""`scribe ratify` and `scribe reject` (plan 3.8 transition matrix, 4.10 order).

Order per plan 4.10 (F8): take the exclusive lock, resolve the record and apply
the transition matrix, append the attestation line (the authority), save the
record through `apply_change` plus temp file and `os.replace`, reconcile the
predecessors' supersession state, regenerate INDEX.md. A crash between the
attestation append and the record save leaves `state_behind_attestation`
(validator rule 6); re-running the same command applies the recorded verdict
without a duplicate line.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .index import write_index
from .record import Record, utc_now
from .state import locked, state_dir
from .store import Store, reconcile_supersession

LOCK_FILE = "ratify.lock"
ATTESTATIONS_FILE = "RATIFICATIONS.jsonl"
VERDICTS = {"ratify": "ratified", "reject": "rejected"}
VIA_VALUES = ("skill", "cli", "hand-written")
FALLBACK_BY = "@unknown"


@dataclass(frozen=True)
class Outcome:
    code: int
    message: str


def normalize_by(value: str | None, root: str | Path) -> str:
    """`@` plus the first token lowercased; a missing value comes from git config."""
    text = (value or "").strip()
    if not text:
        result = subprocess.run(
            ["git", "-C", str(root), "config", "user.name"],
            text=True,
            capture_output=True,
            check=False,
        )
        text = result.stdout.strip() if result.returncode == 0 else ""
    if not text:
        return FALLBACK_BY
    if text.startswith("@"):
        return text
    return "@" + text.split()[0].lower()


def attestations_path(store: Store) -> Path:
    return store.path / ATTESTATIONS_FILE


def append_attestation(store: Store, line: dict[str, object]) -> None:
    """One `write` of one line ending in newline, then flush and fsync."""
    path = attestations_path(store)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _finish(store: Store, verb: str) -> None:
    """Steps 5 and 6: reconcile predecessors, then regenerate INDEX.md."""
    for changed in reconcile_supersession(
        store.records(refresh=True), f"scribe-{verb}"
    ):
        changed.save()
    write_index(store)


def apply_verdict(
    store: Store,
    token: str,
    verb: str,
    by: str,
    note: str | None = None,
    at: str | None = None,
    via: str = "cli",
) -> Outcome:
    verdict = VERDICTS[verb]
    stamp = at or utc_now()
    with locked(state_dir(store.root) / LOCK_FILE) as acquired:
        if not acquired:
            return Outcome(1, "ratification lock timeout; retry the same command")
        record = store.resolve(token)
        if record is None:
            return Outcome(1, f"unknown record: {token}")
        alias = str(record.data.get("alias"))
        latest = store.latest_attestation(record.data.get("id"))
        attestation_matches = (
            latest is not None
            and latest.get("verdict") == verdict
            and latest.get("body_sha256") == record.body_sha256()
        )
        authoritative_by = latest.get("by") if attestation_matches else by
        authoritative_at = latest.get("at") if attestation_matches else stamp
        record_matches = (
            record.data.get("review_state") == verdict
            and record.data.get("ratified_by") == authoritative_by
            and record.data.get("ratified_at") == authoritative_at
        )
        if attestation_matches and record_matches:
            _finish(store, verb)
            return Outcome(
                0,
                f"already {verdict} by {record.data.get('ratified_by')} "
                f"at {record.data.get('ratified_at')}",
            )
        if not attestation_matches:
            append_attestation(
                store,
                {
                    "id": record.data.get("id"),
                    "alias": alias,
                    "verdict": verdict,
                    "by": by,
                    "at": stamp,
                    "body_sha256": record.body_sha256(),
                    "via": via,
                    "note": note or "",
                },
            )
        for field, new in (
            ("review_state", verdict),
            ("ratified_by", authoritative_by),
            ("ratified_at", authoritative_at),
        ):
            record.apply_change(field, new, verdict, by, at=stamp, force=True)
        record.save()
        _finish(store, verb)
    return Outcome(0, f"{verdict} {alias} by {authoritative_by} (via {via})")
