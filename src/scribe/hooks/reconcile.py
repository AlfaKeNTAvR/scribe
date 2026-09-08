"""TaskCompleted and Stop reconcile hook (plan 4.8).

No-op advisory stub registered by T6; T10 replaces it. The real handler
selects the policy per payload (`select_policy`): TaskCompleted runs through
`run_gate`, Stop through `run_advisory`.
"""

from __future__ import annotations

from typing import Any

POLICY = "advisory"


def handle(payload: dict[str, Any]) -> None:
    return None
