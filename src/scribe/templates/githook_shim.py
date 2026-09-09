#!{{SHEBANG}}
# scribe-managed v1  -- do not edit; re-run `scribe init --force` to refresh
import os
import sys

PLUGIN_ROOT = r"{{PLUGIN_ROOT}}"  # baked in by scribe init
HOOK = "{{HOOK}}"

if os.environ.get("SCRIBE_SKIP_HOOKS") == "1":
    sys.exit(0)
# A git hook starts through a shebang, unlike the registered Claude hooks.
# Re-exec under isolated no-site mode before importing the supervisor.  Any
# failure remains fail-open below.
if not sys.flags.isolated:
    try:
        os.execv(sys.executable, [sys.executable, "-I", "-S", __file__, *sys.argv[1:]])
    except Exception:
        pass
# The supervisor runs `uv run ... scribe git-hook <name>` fail-open: a uv or
# startup failure exits 0 with one stderr line, so a broken tool never blocks
# a commit; only a deliberate refusal (commit-msg in enforce mode) exits 1.
# UNVERIFIED (U3): Git for Windows is assumed to honour the
# `#!/usr/bin/env python` shebang and to resolve `uv.exe` through PATH.
try:
    sys.path.insert(0, os.path.join(PLUGIN_ROOT, "hooks"))
    import supervise
except Exception as exc:  # noqa: BLE001 - fail open on any import problem
    sys.stderr.write("scribe: %s skipped (supervisor unavailable: %s)\n" % (HOOK, exc))
    sys.exit(0)
sys.exit(supervise.run(["git-hook", HOOK] + sys.argv[1:]))
