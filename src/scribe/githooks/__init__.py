"""Git hook entrypoints behind `scribe git-hook <name>` (plan section 5).

The installed hook files (shims written by `scribe init`, or the test files
that call `sys.executable -m scribe git-hook <name>`) hand their arguments to
`dispatch`. Every hook exits 0 on a crash: the failure is appended to
`.claude/scribe/hook-errors.log` (and to stderr under `SCRIBE_DEBUG=1`) and the
commit proceeds. The only non-zero exit is `commit-msg`'s deliberate 1 under
`SCRIBE_COMMIT_MSG: enforce`.
"""

from __future__ import annotations

import importlib
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from scribe import gitutil
from scribe.state import log_hook_error
from scribe.store import Store

HOOK_MODULES = {
    "prepare-commit-msg": "scribe.githooks.prepare_commit_msg",
    "commit-msg": "scribe.githooks.commit_msg",
    "post-commit": "scribe.githooks.post_commit",
    "post-rewrite": "scribe.githooks.post_rewrite",
}
SKIP_ENV = "SCRIBE_SKIP_HOOKS"


def debug_enabled() -> bool:
    return os.environ.get("SCRIBE_DEBUG") == "1"


def repo_store() -> tuple[Path | None, Store | None]:
    """Root and store for the process cwd (git runs hooks from the work tree root)."""
    root = gitutil.toplevel(Path.cwd())
    if root is None:
        return None, None
    store = Store(root)
    return root, (store if store.path.is_dir() else None)


def debug(message: str) -> None:
    if debug_enabled():
        print(f"scribe: {message}", file=sys.stderr)


def dispatch(name: str, args: Sequence[str]) -> int:
    if os.environ.get(SKIP_ENV) == "1":
        return 0
    module_name = HOOK_MODULES.get(name)
    if module_name is None:
        print(f"scribe: unknown git hook: {name}", file=sys.stderr)
        return 0
    root: Path | None = None
    try:
        root = gitutil.toplevel(Path.cwd())
        module = importlib.import_module(module_name)
        return int(module.run(list(args)) or 0)
    except BaseException as exc:  # a git hook must never fail the commit by accident
        line = f"scribe: {name} failed: {type(exc).__name__}: {exc}"
        log_hook_error(root, line)
        if debug_enabled():
            try:
                print(line, file=sys.stderr)
            except BaseException:
                pass
        return 0
