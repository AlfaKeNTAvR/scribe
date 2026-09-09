"""`commit-msg`: validate the `Decision:` trailers, warn only by default (plan 5.2).

Checks 1 (trailer resolves), 2 (record validates) and 5 (staged record claims a
verdict without an attestation) are fatal under `SCRIBE_COMMIT_MSG: enforce`;
check 3 (rejected record), check 4 (governed path without a matching link,
F12) and the supersede notice (6) always warn. Not implemented (F13): running
`verify` entries against staged content, see `tests/test_deferred.py`.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from scribe import gitutil
from scribe.config import commit_msg_mode
from scribe.githooks import repo_store
from scribe.links import STORE_PREFIX, _path_entries
from scribe.lookup import TRAILER_KEY
from scribe.matching import matches_affects
from scribe.protocol import announce_deny
from scribe.record import Record
from scribe.schema import validate_record
from scribe.store import Store


@dataclass(frozen=True)
class Finding:
    message: str
    fatal: bool = False
    level: str = "warning"


def decision_values(message_file: Path, root: Path) -> list[str]:
    text = message_file.read_text(encoding="utf-8", errors="replace")
    return [
        value
        for key, value in gitutil.parse_trailers(text, root)
        if key.lower() == TRAILER_KEY.lower()
    ]


def resolve_trailers(
    store: Store, values: list[str]
) -> tuple[list[Record], list[Finding]]:
    """Check 1: every token of every value names one record, all tokens agree."""
    records: list[Record] = []
    findings: list[Finding] = []
    for value in values:
        resolved = {}
        unknown = []
        for token in value.split():
            record = store.resolve(token)
            if record is None:
                unknown.append(token)
            else:
                resolved[id(record)] = record
        if not resolved:
            findings.append(Finding(f"unknown decision: {value}", fatal=True))
            continue
        if unknown or len(resolved) > 1:
            findings.append(
                Finding(f"alias/ulid mismatch in trailer: {value}", fatal=True)
            )
        for record in resolved.values():
            if all(record is not seen for seen in records):
                records.append(record)
    return records, findings


def validate_records(store: Store, records: list[Record]) -> list[Finding]:
    """Checks 2 and 3 on the resolved records."""
    findings: list[Finding] = []
    for record in records:
        alias = record.data.get("alias")
        problems = validate_record(
            record.data, record.body, store=store, path=record.path
        )
        for problem in problems:
            if problem.severity == "error":
                findings.append(
                    Finding(
                        f"{alias} fails validate: {problem.code}: {problem.message}",
                        fatal=True,
                    )
                )
        if record.data.get("review_state") == "rejected":
            findings.append(Finding(f"{alias} is rejected"))
    return findings


def active_records(store: Store) -> list[Record]:
    """Records with effective ratified authority, shared with the gate and index."""
    return [record for record in store.records() if store.effective_authority(record)]


def governed_paths(
    store: Store, staged: list[str], linked: list[Record]
) -> list[Finding]:
    """Check 4 (F12): each governed staged path needs an active, matching trailer."""
    findings: list[Finding] = []
    active = active_records(store)
    linked_ids = {id(record) for record in linked}
    for path in staged:
        governing = [
            record for record in active if matches_affects(_path_entries(record), path)
        ]
        if not governing:
            continue
        if any(id(record) in linked_ids for record in governing):
            continue
        aliases = ", ".join(str(record.data.get("alias")) for record in governing)
        findings.append(
            Finding(
                f"governed path {path} changed without a matching decision link "
                f"(candidates: {aliases})"
            )
        )
    return findings


def staged_records(store: Store, staged: list[str]) -> list[Record]:
    names = {Path(path).name for path in staged if path.startswith(STORE_PREFIX)}
    return [record for record in store.records() if record.path.name in names]


def review_claims(store: Store, records: list[Record]) -> list[Finding]:
    """Checks 5 and 6 on staged record files."""
    findings: list[Finding] = []
    for record in records:
        alias = record.data.get("alias")
        state = record.data.get("review_state")
        if state != "unreviewed":
            latest = store.latest_attestation(record.data.get("id"))
            attested = (
                latest is not None
                and latest.get("verdict") == state
                and latest.get("body_sha256") == record.body_sha256()
            )
            if not attested:
                findings.append(
                    Finding(
                        f"{alias} claims review_state {state} without a matching "
                        "attestation in RATIFICATIONS.jsonl",
                        fatal=True,
                    )
                )
        else:
            predecessor = store.resolve(record.data.get("supersedes"))
            if (
                predecessor is not None
                and predecessor.data.get("review_state") == "ratified"
            ):
                findings.append(
                    Finding(
                        f"{alias} supersedes ratified {predecessor.data.get('alias')}; "
                        "the CI check will block merge until it is reviewed",
                        level="notice",
                    )
                )
    return findings


def run(args: Sequence[str]) -> int:
    if not args:
        return 0
    message_file = Path(args[0])
    root, store = repo_store()
    if root is None or store is None:
        return 0
    staged = gitutil.staged_paths(root)
    linked, findings = resolve_trailers(store, decision_values(message_file, root))
    findings.extend(validate_records(store, linked))
    findings.extend(governed_paths(store, staged, linked))
    findings.extend(review_claims(store, staged_records(store, staged)))
    for finding in findings:
        print(f"scribe: {finding.level}: {finding.message}", file=sys.stderr)
    if commit_msg_mode(root) == "enforce" and any(f.fatal for f in findings):
        announce_deny("scribe: commit rejected (SCRIBE_COMMIT_MSG: enforce)")
        return 1
    return 0
