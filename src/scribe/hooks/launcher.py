"""The two hook dispatcher policies (plan 4.1 item 5).

`run_advisory` never fails a tool call: any exception in the handler is logged
to `.claude/scribe/hook-errors.log` and the exit code is 0. `run_gate` exits 2
only for a deliberate deny in enforce mode, announced with the
`scribe.protocol` marker so `hooks/supervise.py` lets that exit through; a
crash exits 0 in both modes.

Hook stdin fields read here are the ones plan 4.1 item 3 lists (`cwd`,
`hook_event_name`); every read is `payload.get(...)`.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

from scribe import gitutil
from scribe.config import gates_mode
from scribe.protocol import announce_deny
from scribe.record import utc_now
from scribe.state import log_hook_error, state_dir
from scribe.store import Store

GATE_LOG_FILE = "gate-log.jsonl"
POLICY_ADVISORY = "advisory"
POLICY_GATE = "gate"

# event name on the command line -> handler module. Each module exposes
# `handle(payload)` and either `POLICY` or `select_policy(payload)`.
HOOK_MODULES = {
    "session-start": "scribe.hooks.session_start",
    "user-prompt-submit": "scribe.hooks.user_prompt_submit",
    "pre-tool-use-edit": "scribe.hooks.pre_tool_use_edit",
    "gate": "scribe.hooks.pre_tool_use_gate",
    "reconcile": "scribe.hooks.reconcile",
}


@dataclass
class Verdict:
    allow: bool
    reason: str = ""
    event: dict[str, Any] = field(default_factory=dict)


Handler = Callable[[dict[str, Any]], Any]
GateHandler = Callable[[dict[str, Any]], Verdict]


def debug_enabled() -> bool:
    return os.environ.get("SCRIBE_DEBUG") == "1"


def read_payload(stream: Any = None) -> dict[str, Any] | None:
    """Parse the JSON payload on stdin; None for empty or invalid input."""
    try:
        text = (stream or sys.stdin).read()
    except (OSError, ValueError):
        return None
    if not text or not text.strip():
        return None
    try:
        payload = json.loads(text)
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def payload_cwd(payload: dict[str, Any]) -> Path:
    """The payload's `cwd`, resolved against the process cwd when relative."""
    value = payload.get("cwd")
    if isinstance(value, str) and value:
        return (Path.cwd() / value).resolve()
    return Path.cwd()


def repo_root(payload: dict[str, Any]) -> Path | None:
    """Repository root for the payload's cwd (a linked worktree is its own root)."""
    cwd = payload_cwd(payload)
    if not cwd.is_dir():
        return None
    return gitutil.toplevel(cwd)


def store_for(root: Path | None) -> Store | None:
    if root is None:
        return None
    store = Store(root)
    return store if store.path.is_dir() else None


def emit(result: Any) -> None:
    """Print a handler's return value: a mapping as JSON, a string as is."""
    if result is None:
        return
    if isinstance(result, (dict, list)):
        print(json.dumps(result))
    else:
        print(str(result))
    sys.stdout.flush()


def _report_failure(
    root: Path | None, event: str, exc: BaseException, loud: bool
) -> None:
    line = f"scribe: {event} failed: {type(exc).__name__}: {exc}"
    try:
        log_hook_error(root, line)
    except BaseException:
        pass
    if loud or debug_enabled():
        try:
            print(line, file=sys.stderr)
            sys.stderr.flush()
        except BaseException:
            pass


def run_advisory(
    fn: Handler,
    payload: dict[str, Any] | None = None,
    event: str = "hook",
) -> int:
    """Run an advisory handler: print its result if any, exit 0 on every path."""
    root: Path | None = None
    try:
        if payload is None:
            payload = read_payload()
        if payload is None:
            return 0
        root = repo_root(payload)
        emit(fn(payload))
    except BaseException as exc:
        _report_failure(root, event, exc, loud=False)
    return 0


def append_gate_log(root: Path | None, entry: dict[str, Any]) -> None:
    if root is None:
        return
    path = state_dir(root) / GATE_LOG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")


def run_gate(
    fn: GateHandler,
    mode: str,
    payload: dict[str, Any] | None = None,
    event: str = "gate",
) -> int:
    """Run a gate handler: shadow logs the verdict and exits 0, enforce exits 2 on deny."""
    root: Path | None = None
    try:
        if payload is None:
            payload = read_payload()
        if payload is None:
            return 0
        root = repo_root(payload)
        verdict = fn(payload)
        if not isinstance(verdict, Verdict):
            return 0
        entry = {"at": utc_now(), **verdict.event}
        entry.setdefault("verdict", "allow" if verdict.allow else "deny")
        entry.setdefault("reason", verdict.reason)
        try:
            append_gate_log(root, entry)
        except OSError as exc:
            _report_failure(root, event, exc, loud=True)
        if mode == "enforce" and not verdict.allow:
            announce_deny(verdict.reason)
            return 2
    except BaseException as exc:
        _report_failure(root, event, exc, loud=True)
    return 0


def _select_policy(module: ModuleType, payload: dict[str, Any]) -> str:
    selector = getattr(module, "select_policy", None)
    if callable(selector):
        return selector(payload)
    return getattr(module, "POLICY", POLICY_ADVISORY)


def dispatch(event: str) -> int:
    """`scribe hook <event>`: pick the handler module and its policy, run it."""
    try:
        module_name = HOOK_MODULES.get(event)
        if module_name is None:
            print(f"scribe: unknown hook event {event!r}", file=sys.stderr)
            return 0
        payload = read_payload()
        if payload is None:
            return 0
        module = importlib.import_module(module_name)
        if _select_policy(module, payload) == POLICY_GATE:
            mode = gates_mode(repo_root(payload))
            return run_gate(module.handle, mode, payload, event=event)
        return run_advisory(module.handle, payload, event=event)
    except BaseException as exc:
        _report_failure(None, event, exc, loud=True)
        return 0
