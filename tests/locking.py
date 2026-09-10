"""POSIX advisory locking for the lock-contention tests.

`fcntl` exists only on POSIX. Importing it at the top of a test module made
the whole suite fail to collect on Windows, so a Windows user could not run
any test at all, not even the ones that never touch a lock. Importing it here
instead keeps collection working everywhere: `fcntl` is None on Windows and
the thirteen tests that hold a real lock carry `requires_flock`.

The locking behaviour under test is `scribe.state` and `scribe.index`, both of
which already branch on the platform themselves; this module only supplies the
adversary that holds the lock.
"""

from __future__ import annotations

import pytest

try:
    import fcntl
except ImportError:  # pragma: no cover - only taken on Windows
    fcntl = None  # type: ignore[assignment]

requires_flock = pytest.mark.skipif(
    fcntl is None,
    reason="fcntl advisory locks are POSIX only; the lock-contention tests "
    "cannot run on Windows",
)

__all__ = ["fcntl", "requires_flock"]
