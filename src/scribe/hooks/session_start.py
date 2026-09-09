"""SessionStart hook (plan 4.3): register the session, report the review queue.

Stdin fields read: `session_id`, `cwd` (plan 4.1 item 3). Output shape:
`{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ...}}`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scribe.frontmatter import split
from scribe.hooks.launcher import payload_cwd, repo_root, store_for
from scribe.state import log_hook_error, session_entry, update_state
from scribe.store import Store

POLICY = "advisory"


def load_front_matters(store: Store) -> list[dict[str, Any]]:
    """Front matter of every record; files that fail to parse are logged and skipped."""
    mappings = []
    for path in sorted(store.path.glob("D-*.md")):
        try:
            mapping, _ = split(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            log_hook_error(store.root, f"scribe: skipped {path.name}: {exc}")
            continue
        mappings.append(mapping)
    return mappings


def subdirectory_hint(cwd: Path, root: Path) -> str | None:
    """V21: the RATIFICATIONS.jsonl deny rule only loads for a root-started session.

    Live testing showed no project settings (`.claude/settings.json` or
    `settings.local.json`, whatever the rule's path form) load when Claude
    Code starts below the repository root, so the deny rule is silently
    inactive there. This is advisory only: it cannot make the rule load.
    """
    if cwd == root:
        return None
    return (
        f"scribe: session started below the repository root ({root}); the "
        "RATIFICATIONS.jsonl deny rule from .claude/settings.json is not "
        f"active here; start Claude at {root} or add "
        "Edit(**/docs/decisions/RATIFICATIONS.jsonl) to your user settings"
    )


def review_queue_counts(mappings: list[dict[str, Any]]) -> tuple[int, int]:
    """(unreviewed records, unreviewed records that supersede a ratified one)."""
    ratified_keys = {
        key
        for mapping in mappings
        if mapping.get("review_state") == "ratified"
        for key in (mapping.get("id"), mapping.get("alias"))
        if key is not None
    }
    unreviewed = [m for m in mappings if m.get("review_state") == "unreviewed"]
    superseding = [m for m in unreviewed if m.get("supersedes") in ratified_keys]
    return len(unreviewed), len(superseding)


def handle(payload: dict[str, Any]) -> dict[str, Any] | None:
    root = repo_root(payload)
    store = store_for(root)
    if root is None or store is None:
        return None
    session_id = payload.get("session_id")
    if isinstance(session_id, str) and session_id:
        update_state(root, lambda state: session_entry(state, session_id))
    lines = []
    hint = subdirectory_hint(payload_cwd(payload), root)
    if hint is not None:
        lines.append(hint)
    unreviewed, superseding = review_queue_counts(load_front_matters(store))
    if unreviewed > 0:
        lines.append(
            f"scribe: {unreviewed} unreviewed decisions, {superseding} supersede a "
            "ratified one. Run /scribe:lint or open docs/decisions/INDEX.md."
        )
    if not lines:
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "\n".join(lines),
        }
    }
