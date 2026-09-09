"""The one signal the fail-open supervisor honours (Codex finding V1).

`hooks/supervise.py` maps every non-zero exit of `uv run ... scribe` to exit 0
unless stderr carries `DENY_MARKER` on a line of its own. The application
prints that line only when it deliberately refuses something: a gate in
enforce mode (exit 2) or `commit-msg` under `SCRIBE_COMMIT_MSG: enforce`
(exit 1). The supervisor duplicates the constant because it cannot import
this package; `tests/test_supervise.py` keeps them equal.
"""

from __future__ import annotations

import sys

DENY_MARKER = "[scribe-deny]"


def announce_deny(reason: str) -> None:
    """Write the marker line and the human-readable reason to stderr."""
    print(DENY_MARKER, file=sys.stderr)
    print(reason, file=sys.stderr)
    sys.stderr.flush()
