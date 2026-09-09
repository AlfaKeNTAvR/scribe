#!{{SHEBANG}}
# scribe-managed v1  -- do not edit; re-run `scribe init --force` to refresh
import os
import subprocess
import sys

PLUGIN_ROOT = r"{{PLUGIN_ROOT}}"  # baked in by scribe init
HOOK = "{{HOOK}}"
COMMAND = [
    "uv",
    "run",
    "--frozen",
    "--project",
    PLUGIN_ROOT,
    "scribe",
    "git-hook",
    HOOK,
    *sys.argv[1:],
]

if os.environ.get("SCRIBE_SKIP_HOOKS") == "1":
    sys.exit(0)
try:
    if os.name == "nt":
        # UNVERIFIED (U3): on Windows os.execvp does not replace the process, so
        # the hook waits for uv and forwards its exit code; Git for Windows is
        # assumed to honour the `#!/usr/bin/env python` shebang and to resolve
        # `uv.exe` through PATH. Not exercised on a Windows machine.
        sys.exit(subprocess.call(COMMAND))
    os.execvp("uv", COMMAND)
except OSError as exc:
    sys.stderr.write(f"scribe: {HOOK} skipped ({exc})\n")
    sys.exit(0)
