"""Immutability and append-only checks that need git history (plan 3.1 item 3, 5.4 rule 5).

The validator sees one version of a record at a time, so it cannot tell that a
body was rewritten or that a history entry was dropped. Everything here compares
the version of a file at the base of a commit range with the version in HEAD or
in the working tree. `scribe check` runs it over a pull request range; `scribe
lint` runs the same functions against its own base ref.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .frontmatter import FrontMatterError, split
from .gitutil import show_blob, tree_record_paths
from .record import MUTABLE_KEYS
from .schema import KEYS, Problem

IMMUTABLE_KEYS = [key for key in KEYS if key not in MUTABLE_KEYS]
DECISIONS_DIR = "docs/decisions"
ATTESTATIONS_PATH = f"{DECISIONS_DIR}/RATIFICATIONS.jsonl"


def _read_version(rev: str | None, path: str, cwd: str | Path) -> str | None:
    """The file at `rev`, or the working-tree file when `rev` is None."""
    if rev is not None:
        return show_blob(rev, path, cwd)
    target = Path(cwd) / path
    if not target.is_file():
        return None
    return target.read_text(encoding="utf-8")


def _history_of(data: dict[str, Any]) -> list[Any]:
    history = data.get("history")
    return history if isinstance(history, list) else []


def compare_record_versions(base_text: str, head_text: str) -> list[Problem]:
    """Immutable keys, the body, and the append-only history of one record."""
    try:
        base_data, base_body = split(base_text)
    except FrontMatterError as exc:
        return [
            Problem("error", "parse_error", f"the base version does not parse: {exc}")
        ]
    try:
        head_data, head_body = split(head_text)
    except FrontMatterError as exc:
        return [
            Problem(
                "error", "parse_error", f"the current version does not parse: {exc}"
            )
        ]

    problems: list[Problem] = []
    for key in IMMUTABLE_KEYS:
        if base_data.get(key) != head_data.get(key):
            problems.append(
                Problem(
                    "error",
                    "immutable_changed",
                    f"immutable key changed since the base: {key}",
                )
            )
    if base_body != head_body:
        problems.append(
            Problem(
                "error", "immutable_changed", "the record body changed since the base"
            )
        )
    base_history = _history_of(base_data)
    head_history = _history_of(head_data)
    if head_history[: len(base_history)] != base_history:
        problems.append(
            Problem(
                "error",
                "history_rewritten",
                "the history at the base is not a prefix of the current history",
            )
        )
    return problems


def check_records_against_base(
    base: str,
    cwd: str | Path = ".",
    head: str | None = None,
    paths: list[str] | None = None,
) -> list[tuple[str, Problem]]:
    """Compare every record present at `base` with its current version.

    `head` names a revision; None reads the working tree. A record that the range
    deletes is skipped: removing a record is not an immutability question and no
    rule in plan 5.4 covers it.
    """
    targets = (
        paths if paths is not None else tree_record_paths(base, DECISIONS_DIR, cwd)
    )
    findings: list[tuple[str, Problem]] = []
    for path in sorted(targets):
        base_text = show_blob(base, path, cwd)
        head_text = _read_version(head, path, cwd)
        if base_text is None or head_text is None:
            continue
        findings.extend(
            (path, problem) for problem in compare_record_versions(base_text, head_text)
        )
    return findings


def check_attestations_append_only(
    base: str,
    cwd: str | Path = ".",
    head: str | None = None,
    path: str = ATTESTATIONS_PATH,
) -> list[Problem]:
    """The attestation file at `base` must be a line-wise prefix of the current one."""
    base_text = show_blob(base, path, cwd)
    if base_text is None:
        return []
    head_text = _read_version(head, path, cwd)
    head_lines = head_text.splitlines() if head_text is not None else []
    base_lines = base_text.splitlines()
    if head_lines[: len(base_lines)] == base_lines:
        return []
    return [
        Problem(
            "error",
            "attestations_not_append_only",
            f"{path} is not append-only relative to the base",
        )
    ]
