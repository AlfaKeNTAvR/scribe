"""TaskCompleted and Stop reconcile hook (plan 4.8).

`select_policy` routes TaskCompleted through `launcher.run_gate` (its deny is
a real verdict, subject to `SCRIBE_GATES`) and Stop through `run_advisory`.

TaskCompleted (F9): when the session was flagged `decision_worthy` by the
ExitPlanMode gate and no record was written since, deny and append a
`capture_missing` event to `gate-log.jsonl`; the flag is cleared either way,
so each flag is reported once. Stop: append one `stop_reconcile` event unless
`stop_hook_active` is true (re-entry guard). No stub record is written in this
run.

Stdin fields read: `session_id`, `cwd`, `hook_event_name`, `task_id`,
`task_subject`, `stop_hook_active`, `last_assistant_message` (plan 4.1 item 3).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scribe.hooks.launcher import (
    POLICY_ADVISORY,
    POLICY_GATE,
    Verdict,
    append_gate_log,
    repo_root,
    store_for,
)
from scribe.record import utc_now
from scribe.state import load_state, parse_timestamp, session_entry, update_state

TASK_COMPLETED = "TaskCompleted"
STOP = "Stop"

CAPTURE_MISSING_REASON = "scribe: task '{subject}' flagged decision-worthy ({areas}) but no record was written"


def select_policy(payload: dict[str, Any]) -> str:
    if payload.get("hook_event_name") == TASK_COMPLETED:
        return POLICY_GATE
    return POLICY_ADVISORY


def _is_newer_or_equal(candidate: Any, reference: Any) -> bool:
    """`candidate >= reference` on scratch-state timestamps; unparsable is False."""
    left = parse_timestamp(candidate)
    right = parse_timestamp(reference)
    if left is None or right is None:
        return False
    return left >= right


def record_written_since(session: dict[str, Any], flagged_at: Any) -> bool:
    entries = session.get("records_written")
    if not isinstance(entries, list):
        return False
    return any(
        isinstance(entry, dict) and _is_newer_or_equal(entry.get("at"), flagged_at)
        for entry in entries
    )


def task_completed(root: Path, payload: dict[str, Any]) -> Verdict | None:
    """Report an unfulfilled decision-worthy flag once, then clear it."""
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return None
    now = utc_now()
    captured: dict[str, Any] = {}

    def mutate(state: dict[str, Any]) -> None:
        session = session_entry(state, session_id, now)
        flag = session.get("decision_worthy")
        if isinstance(flag, dict):
            captured["flag"] = flag
            captured["satisfied"] = record_written_since(session, flag.get("set_at"))
        session["decision_worthy"] = None

    update_state(root, mutate, now)
    flag = captured.get("flag")
    if flag is None:
        return None
    areas = flag.get("areas") if isinstance(flag.get("areas"), list) else []
    task_id = payload.get("task_id")
    task_subject = payload.get("task_subject")
    event = {
        "event": "gate_verdict",
        "tool": TASK_COMPLETED,
        "task_id": task_id,
        "task_subject": task_subject,
        "areas": areas,
    }
    if captured.get("satisfied"):
        return Verdict(True, "", event)
    append_gate_log(
        root,
        {
            "at": now,
            "event": "capture_missing",
            "session_id": session_id,
            "task_id": task_id,
            "task_subject": task_subject,
            "areas": areas,
            "flagged_at": flag.get("set_at"),
        },
    )
    reason = CAPTURE_MISSING_REASON.format(
        subject=task_subject if isinstance(task_subject, str) else "",
        areas=", ".join(str(area) for area in areas),
    )
    return Verdict(False, reason, event)


def stop(root: Path, payload: dict[str, Any]) -> None:
    """Log one `stop_reconcile` event per turn end; a re-entered Stop is ignored."""
    if payload.get("stop_hook_active") is True:
        return
    session_id = payload.get("session_id")
    pending: list[Any] = []
    if isinstance(session_id, str) and session_id:
        session = load_state(root).get("sessions", {}).get(session_id)
        if isinstance(session, dict) and isinstance(
            session.get("pending_decisions"), list
        ):
            pending = list(session["pending_decisions"])
    last_message = payload.get("last_assistant_message")
    append_gate_log(
        root,
        {
            "at": utc_now(),
            "event": "stop_reconcile",
            "session_id": session_id,
            "pending_decisions": pending,
            "has_last_message": isinstance(last_message, str) and bool(last_message),
        },
    )


def handle(payload: dict[str, Any]) -> Verdict | None:
    root = repo_root(payload)
    if root is None or store_for(root) is None:
        return None
    event_name = payload.get("hook_event_name")
    if event_name == TASK_COMPLETED:
        return task_completed(root, payload)
    if event_name == STOP:
        stop(root, payload)
    return None
