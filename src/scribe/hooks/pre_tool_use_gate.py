"""PreToolUse ExitPlanMode and Bash|PowerShell gate (plan 4.7).

Runs through `launcher.run_gate`. The mode comes from `SCRIBE_GATES` in
`<root>/.claude/scribe/config.json` (`config.gates_mode`): `shadow` (default)
logs every verdict to `gate-log.jsonl` and exits 0, `enforce` exits 2 on a
deny. This module only decides; the launcher applies the mode.

Stdin fields read: `session_id`, `prompt_id`, `cwd`, `tool_name`,
`tool_input.command` (Bash, PowerShell), `tool_input.plan` (ExitPlanMode)
(plan 4.1 item 3). A payload for any other tool, or for a cwd without a
`docs/decisions/` store, yields no verdict and therefore no log line.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scribe import policy
from scribe.hooks.launcher import POLICY_GATE, Verdict, repo_root, store_for
from scribe.record import utc_now
from scribe.state import session_entry, update_state
from scribe.store import Store

POLICY = POLICY_GATE

COMMAND_TOOLS = ("Bash", "PowerShell")
PLAN_TOOL = "ExitPlanMode"
COMMAND_HEAD_CHARS = 80

DENYLIST_REASON = (
    "scribe: '{name}' is on the irreversible-action denylist; record it with "
    "/scribe:decide (reversibility: one-way-door) and get it ratified before running it"
)
PLAN_REASON = (
    "scribe: plan touches {areas}; run /scribe:decide before leaving plan mode"
)


def action_is_ratified(store: Store, rule_name: str) -> bool:
    """True when a ratified one-way-door record claims the action (plan 4.7 item 2, F2)."""
    for record in store.records():
        data = record.data
        if data.get("reversibility") != "one-way-door" or not store.effective_authority(record):
            continue
        affects = data.get("affects")
        if not isinstance(affects, list):
            continue
        for item in affects:
            if (
                isinstance(item, dict)
                and item.get("type") == "action"
                and item.get("pattern") == rule_name
            ):
                return True
    return False


def command_verdict(store: Store, tool: str, command: str) -> Verdict:
    """Deny a denylisted command unless a ratified one-way-door record allows it."""
    matched_rules = policy.matching_rules(command)
    uncovered_rules = [
        rule_name
        for rule_name in matched_rules
        if not action_is_ratified(store, rule_name)
    ]
    event = {
        "event": "gate_verdict",
        "tool": tool,
        "command_head": command[:COMMAND_HEAD_CHARS],
        "matched_rules": matched_rules,
        "uncovered_rules": uncovered_rules,
    }
    if not uncovered_rules:
        return Verdict(True, "", event)
    return Verdict(False, DENYLIST_REASON.format(name=uncovered_rules[0]), event)


def plan_verdict(
    root: Path, session_id: str | None, prompt_id: str | None, plan: str
) -> Verdict:
    """Flag a decision-worthy plan in scratch state; deny when nothing is pending (F9)."""
    areas = policy.decision_worthy_areas(plan)
    event = {"event": "gate_verdict", "tool": PLAN_TOOL, "areas": areas}
    if not areas:
        return Verdict(True, "", event)
    pending: list[Any] = []
    if session_id:
        now = utc_now()

        def mutate(state: dict[str, Any]) -> None:
            session = session_entry(state, session_id, now)
            recent_prompts = session.get("prompt_ids") or []
            session["decision_worthy"] = {
                "set_at": now,
                "areas": areas,
                "prompt_id": prompt_id
                or (recent_prompts[0] if recent_prompts else None),
            }
            pending.extend(session.get("pending_decisions") or [])

        # `update_state` returns the on-disk state even when its lock timed
        # out and the mutation was dropped.  Read pending decisions from that
        # returned snapshot, rather than relying on the callback having run.
        state = update_state(root, mutate, now)
        session = state.get("sessions", {}).get(session_id)
        if isinstance(session, dict):
            pending = list(session.get("pending_decisions") or [])
    if pending:
        return Verdict(True, "", event)
    return Verdict(False, PLAN_REASON.format(areas=", ".join(areas)), event)


def _optional_text(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) and value else None


def handle(payload: dict[str, Any]) -> Verdict | None:
    root = repo_root(payload)
    store = store_for(root)
    if root is None or store is None:
        return None
    tool = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    if tool in COMMAND_TOOLS:
        command = tool_input.get("command")
        return command_verdict(store, tool, command if isinstance(command, str) else "")
    if tool == PLAN_TOOL:
        plan = tool_input.get("plan")
        return plan_verdict(
            root,
            _optional_text(payload, "session_id"),
            _optional_text(payload, "prompt_id"),
            plan if isinstance(plan, str) else "",
        )
    return None
