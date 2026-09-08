"""UserPromptSubmit hook (plan 4.3, F10): stamp the session, collect tracker ids.

Stdin fields read: `session_id`, `prompt_id`, `prompt`, `cwd` (plan 4.1 item 3).
No stdout.
"""

from __future__ import annotations

import re
from typing import Any

from scribe.hooks.launcher import repo_root, store_for
from scribe.record import utc_now
from scribe.schema import TASK_REF_RES
from scribe.state import (
    PROMPT_IDS_CAP,
    TASK_REFS_CAP,
    push_recent,
    session_entry,
    update_state,
)

POLICY = "advisory"

# Word-bounded forms of the three task_refs shapes in plan 3.2. Each hit is
# confirmed against the schema's anchored regexes before it is kept.
TASK_REF_SCAN_RES = [
    re.compile(r"(?<![\w/#-])[A-Z][A-Z0-9]{1,9}-\d+(?![\w-])"),
    re.compile(r"(?<![\w/#])#\d+(?!\w)"),
    re.compile(r"(?<![\w/.-])[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#\d+(?!\w)"),
]


def extract_task_refs(prompt: str) -> list[str]:
    """Tracker ids in order of first appearance, deduplicated."""
    found: list[tuple[int, str]] = []
    for scan in TASK_REF_SCAN_RES:
        for match in scan.finditer(prompt):
            token = match.group(0)
            if any(rule.fullmatch(token) for rule in TASK_REF_RES):
                found.append((match.start(), token))
    ordered: list[str] = []
    for _, token in sorted(found):
        if token not in ordered:
            ordered.append(token)
    return ordered


def handle(payload: dict[str, Any]) -> None:
    root = repo_root(payload)
    if root is None or store_for(root) is None:
        return
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return
    prompt_id = payload.get("prompt_id")
    prompt = payload.get("prompt")
    refs = extract_task_refs(prompt) if isinstance(prompt, str) else []
    now = utc_now()

    def mutate(state: dict[str, Any]) -> None:
        session = session_entry(state, session_id, now)
        session["last_prompt_at"] = now
        if isinstance(prompt_id, str) and prompt_id:
            session["prompt_ids"] = push_recent(
                session.get("prompt_ids") or [], [prompt_id], PROMPT_IDS_CAP
            )
        if refs:
            session["task_refs"] = push_recent(
                session.get("task_refs") or [], refs, TASK_REFS_CAP
            )

    update_state(root, mutate, now)
    return
