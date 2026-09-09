"""PreToolUse Edit|Write injection hook (plan 4.4).

Matches the edit target against the `affects` path patterns of the active
records and prints one advisory block as
`{"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": ...}}`.
Zero matches, a missing store, a target outside the repository or an expired
internal deadline all print nothing. The launcher guarantees exit 0.

Stdin fields read (plan 4.1 item 3): `cwd`, `tool_input.file_path`. Only front
matter is parsed; record bodies are never inspected here.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

# Deadline anchor: plan 4.1 item 7 fixes it at import of this module.
_START = time.monotonic()

from scribe.frontmatter import split
from scribe.hooks.launcher import payload_cwd, repo_root, store_for
from scribe.matching import matches_affects, to_repo_relative
from scribe.schema import unhashable_enum_reason
from scribe.state import log_hook_error
from scribe.store import Store

POLICY = "advisory"

DEADLINE_S = 0.7
DEADLINE_CHECK_EVERY = 20
MAX_RECORDS = 5
MAX_LINE_CHARS = 220
MAX_BLOCK_CHARS = 1600
MAX_REGRET_CHARS = 100
ELLIPSIS = "..."

ACTIVE_EFFECTIVE_STATES = ("proposed", "implemented", "backtracked")
# Successor states under which `supersedes` retires the predecessor (plan 3.8).
EDGE_EFFECTIVE_STATES = ("proposed", "implemented", "superseded")
REVIEW_ORDER = {"ratified": 0, "unreviewed": 1}
EFFECTIVE_ORDER = {"implemented": 0, "proposed": 1, "backtracked": 2}

FOOTER = (
    "These are retrieval candidates, not confirmed matches. If this edit "
    "conflicts with one, surface it and ask; do not silently comply or "
    "silently violate."
)


def deadline_passed() -> bool:
    return time.monotonic() - _START > DEADLINE_S


def target_path(payload: dict[str, Any]) -> str | None:
    """`tool_input.file_path`, resolved against the payload cwd when relative."""
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    file_path = tool_input.get("file_path")
    if not isinstance(file_path, str) or not file_path:
        return None
    path = Path(file_path)
    if not path.is_absolute():
        path = payload_cwd(payload) / path
    return str(path)


def load_front_matters(store: Store) -> list[dict[str, Any]] | None:
    """Front matter of every record; None when the deadline expires while loading.

    V17 follow-up: also skips and logs a record whose `review_state`,
    `effective_state` or `supersedes` is not a string (e.g. `effective_state: []`),
    the same check `Store.records()` and `session_start` apply. This loader's own
    downstream sets (`ACTIVE_EFFECTIVE_STATES` and friends, all tuples matched by
    equality) already tolerate such a value without crashing, but skipping it here
    too keeps every raw-front-matter loader in the codebase agreeing on what counts
    as a malformed record.
    """
    mappings: list[dict[str, Any]] = []
    for count, path in enumerate(sorted(store.path.glob("D-*.md")), start=1):
        if count % DEADLINE_CHECK_EVERY == 0 and deadline_passed():
            return None
        try:
            lines: list[bytes] = []
            with path.open("rb") as handle:
                for line in handle:
                    lines.append(line)
                    if len(lines) > 1 and line.rstrip(b"\r\n") == b"---":
                        break
            mapping, _ = split(b"".join(lines).decode("utf-8"))
        except (OSError, ValueError) as exc:
            log_hook_error(store.root, f"scribe: skipped {path.name}: {exc}")
            continue
        reason = unhashable_enum_reason(mapping)
        if reason is not None:
            log_hook_error(store.root, f"scribe: skipped {path.name}: {reason}")
            continue
        mappings.append(mapping)
    return mappings


def superseded_keys(mappings: list[dict[str, Any]]) -> set[str]:
    """Ids and aliases with an effective incoming supersession edge."""
    known = {
        key
        for mapping in mappings
        for key in (mapping.get("id"), mapping.get("alias"))
        if isinstance(key, str)
    }
    retired: set[str] = set()
    for mapping in mappings:
        if mapping.get("review_state") == "rejected":
            continue
        if mapping.get("effective_state") not in EDGE_EFFECTIVE_STATES:
            continue
        target = mapping.get("supersedes")
        if isinstance(target, str) and target in known:
            retired.add(target)
    return retired


def active_records(mappings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Plan 4.4 item 5: not rejected, active state, no effective incoming edge."""
    retired = superseded_keys(mappings)
    return [
        mapping
        for mapping in mappings
        if mapping.get("review_state") != "rejected"
        and mapping.get("effective_state") in ACTIVE_EFFECTIVE_STATES
        and mapping.get("id") not in retired
        and mapping.get("alias") not in retired
    ]


def governing_records(
    mappings: list[dict[str, Any]], relative_path: str
) -> list[dict[str, Any]]:
    """Active records whose path affects match, ordered per plan 4.4 item 7, capped."""
    matched = [
        mapping
        for mapping in active_records(mappings)
        if isinstance(mapping.get("affects"), list)
        and matches_affects(
            [item for item in mapping["affects"] if isinstance(item, dict)],
            relative_path,
        )
    ]
    matched.sort(
        key=lambda mapping: (
            REVIEW_ORDER.get(mapping.get("review_state"), len(REVIEW_ORDER)),
            EFFECTIVE_ORDER.get(mapping.get("effective_state"), len(EFFECTIVE_ORDER)),
            _descending_text_key(mapping.get("date")),
            str(mapping.get("alias")),
        )
    )
    return matched[:MAX_RECORDS]


def _descending_text_key(value: Any) -> str:
    """Sort key that orders ISO date strings newest first inside an ascending sort."""
    text = str(value) if value is not None else ""
    return "".join(chr(0x10FFFF - ord(char)) for char in text)


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    if limit <= len(ELLIPSIS):
        return ELLIPSIS[:limit]
    return text[: limit - len(ELLIPSIS)] + ELLIPSIS


def record_line(mapping: dict[str, Any], ratified_keys: set[str]) -> str:
    """One `- <alias> (<state>, <review>[, supersedes ratified X]): <title>.` line."""
    status = [str(mapping.get("effective_state"))]
    if mapping.get("review_state") == "ratified":
        status.append(f"ratified by {mapping.get('decided_by')}")
    else:
        status.append(str(mapping.get("review_state")))
    supersedes = mapping.get("supersedes")
    if isinstance(supersedes, str) and supersedes in ratified_keys:
        status.append(f"supersedes ratified {supersedes}")
    title = str(mapping.get("title", "")).rstrip(".")
    line = f"- {mapping.get('alias')} ({', '.join(status)}): {title}."
    regret = mapping.get("regret_when")
    if isinstance(regret, str) and regret.strip():
        regret_text = truncate(regret.strip().rstrip("."), MAX_REGRET_CHARS)
        line += f" Regret when: {regret_text}."
    return truncate(line, MAX_LINE_CHARS)


def format_block(
    relative_path: str,
    records: list[dict[str, Any]],
    mappings: list[dict[str, Any]],
) -> str:
    """Assemble the capped advisory block, preserving its footer and record links."""
    ratified_keys = {
        key
        for mapping in mappings
        if mapping.get("review_state") == "ratified"
        for key in (mapping.get("id"), mapping.get("alias"))
        if isinstance(key, str)
    }
    shown = list(records)
    while shown:
        record_lines = [record_line(mapping, ratified_keys) for mapping in shown]
        full_text = " ".join(f"docs/decisions/{m.get('alias')}.md" for m in shown)
        footer = f"{FOOTER} Full text: {full_text}"
        trailing = "\n".join([*record_lines, footer])
        header_fixed = len("Governing decisions for :\n")
        path_limit = MAX_BLOCK_CHARS - header_fixed - len(trailing)
        if path_limit >= 0:
            shown_path = truncate(relative_path, path_limit)
            return f"Governing decisions for {shown_path}:\n{trailing}"
        shown.pop()
    return ""


def handle(payload: dict[str, Any]) -> dict[str, Any] | None:
    target = target_path(payload)
    if target is None:
        return None
    root = repo_root(payload)
    store = store_for(root)
    if root is None or store is None:
        return None
    relative_path = to_repo_relative(root, target)
    if relative_path is None:
        return None
    mappings = load_front_matters(store)
    if mappings is None or deadline_passed():
        return None
    records = governing_records(mappings, relative_path)
    if not records:
        return None
    block = format_block(relative_path, records, mappings)
    if not block or deadline_passed():
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": block,
        }
    }
