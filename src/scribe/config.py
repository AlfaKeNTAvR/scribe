"""Repo-local scribe configuration: <root>/.claude/scribe/config.json.

The two switches live in a git-ignored file, never in the environment, so a
value inherited from a parent shell can not flip a gate to enforce (plan 4.1
item 6). A missing file, a missing key or an unknown value means the safe
default.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONFIG_VERSION = 1
GATE_MODES = ("shadow", "enforce")
COMMIT_MSG_MODES = ("warn", "enforce")
DEFAULTS = {"SCRIBE_GATES": "shadow", "SCRIBE_COMMIT_MSG": "warn"}


def config_path(root: str | Path) -> Path:
    return Path(root) / ".claude" / "scribe" / "config.json"


def load_config(root: str | Path | None) -> dict[str, Any]:
    """Return the parsed config mapping, or an empty mapping on any problem."""
    if root is None:
        return {}
    try:
        loaded = json.loads(config_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _switch(root: str | Path | None, key: str, allowed: tuple[str, ...]) -> str:
    value = load_config(root).get(key)
    return value if isinstance(value, str) and value in allowed else DEFAULTS[key]


def gates_mode(root: str | Path | None) -> str:
    """`shadow` (default) or `enforce` for the PreToolUse and TaskCompleted gates."""
    return _switch(root, "SCRIBE_GATES", GATE_MODES)


def commit_msg_mode(root: str | Path | None) -> str:
    """`warn` (default) or `enforce` for the commit-msg git hook."""
    return _switch(root, "SCRIBE_COMMIT_MSG", COMMIT_MSG_MODES)


def write_config(root: str | Path, **switches: str) -> Path:
    """Merge the given switches into the config file, creating it if needed."""
    path = config_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    merged = {**load_config(root), **switches, "version": CONFIG_VERSION}
    ordered = {"version": CONFIG_VERSION}
    ordered.update({key: value for key, value in merged.items() if key != "version"})
    path.write_text(json.dumps(ordered, indent=2) + "\n", encoding="utf-8")
    return path
