"""`post-rewrite`: relink `implementation_links` after amend or rebase (O5, Q3).

git calls this hook after `git commit --amend` (argv[1] == "amend") or a
non-interactive `git rebase` (argv[1] == "rebase"), piping one `<old-sha>
<new-sha>` pair per rewritten commit on stdin. `scribe relink` (relink.py)
already walks the whole history and rebuilds every record's
`implementation_links` from scratch, dropping unreachable commits and
refreshing reachable ones, so the specific sha pairs are not needed for the
rebuild itself; stdin is drained only so git never blocks on the pipe. The
actual work reuses `run_relink` rather than duplicating its logic here.

Same fail-open contract as `post_commit`: guarded against re-entry, honours
`SCRIBE_SKIP_HOOKS` (checked once, centrally, by `githooks.dispatch`), and
exits 0 on every path -- including the V8 ledger lock timeout, where
`run_relink` itself has already printed the one stderr line and written
nothing; this hook only needs to turn that non-zero exit into 0.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from typing import Any

from scribe.githooks import repo_store
from scribe.relink import run_relink

GUARD_ENV = "SCRIBE_IN_POST_REWRITE"


def read_stdin(stream: Any = None) -> str:
    """Drain git's old/new sha pairs; empty string on any read problem.

    A direct unit-test call (not a real git subprocess) may leave stdin
    unavailable (pytest's capture replaces it) or attached to a terminal;
    neither case should block or crash the hook.
    """
    target = stream or sys.stdin
    try:
        if target is None or target.isatty():
            return ""
        return target.read()
    except (OSError, ValueError, AttributeError):
        return ""


def run(args: Sequence[str]) -> int:
    if os.environ.get(GUARD_ENV) == "1":
        return 0
    os.environ[GUARD_ENV] = "1"
    kind = args[0] if args else "rewrite"
    read_stdin()
    root, store = repo_store()
    if root is None or store is None:
        return 0
    code, lines = run_relink(root)
    if code != 0:
        # Lock timeout: run_relink already printed its one stderr line and
        # wrote nothing. Fail open regardless.
        return 0
    relinked = [line for line in lines if line.startswith("relinked ")]
    if relinked:
        print(
            f"scribe: relinked {len(relinked)} record(s) after {kind}; "
            "run git add docs/decisions to include the backlinks in your "
            "next commit",
            file=sys.stderr,
        )
    return 0
