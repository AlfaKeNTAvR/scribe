"""PreToolUse ExitPlanMode and Bash|PowerShell gate (plan 4.7).

No-op advisory stub registered by T6; T10 replaces it with the real handler
(POLICY "gate", verdicts through `launcher.run_gate`, mode from SCRIBE_GATES).
"""

from __future__ import annotations

from typing import Any

POLICY = "advisory"


def handle(payload: dict[str, Any]) -> None:
    return None
