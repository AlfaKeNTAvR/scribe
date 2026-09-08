"""PreToolUse Edit|Write injection hook (plan 4.4).

No-op advisory stub registered by T6; T7 replaces it with the real handler.
"""

from __future__ import annotations

from typing import Any

POLICY = "advisory"


def handle(payload: dict[str, Any]) -> None:
    return None
