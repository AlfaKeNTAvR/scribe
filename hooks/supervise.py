#!/usr/bin/env python3
"""Fail-open supervisor for every `uv run ... scribe` call (Codex finding V1).

Claude Code treats exit 2 from a PreToolUse or UserPromptSubmit hook as a
denial, and git treats any non-zero hook exit as a refusal. `uv` itself exits
2 when it cannot start (missing binary, locked or read-only cache, stale
lock), which would turn an infrastructure failure into a denied tool call or a
blocked commit. This script runs uv, and:

- forwards stdout, stderr and the exit code unchanged when uv exits 0;
- forwards them unchanged when stderr carries this invocation's tokened denial
  marker, which the application prints only for a deliberate enforcement denial
  (the marker line itself is stripped);
- otherwise prints one `scribe: ... skipped` line to stderr and exits 0.

Stdlib only, Python 3.8 or newer, no imports from the scribe package: it must
work when the package itself cannot be imported. The marker is duplicated in
`src/scribe/protocol.py`; `tests/test_supervise.py` keeps the two equal.
"""

import os
import subprocess
import sys

DENY_MARKER = "[scribe-deny"
PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UV = os.environ.get("SCRIBE_UV", "uv")


def _skip(label, detail):
    sys.stderr.write("scribe: %s skipped (%s)\n" % (label, detail))
    sys.stderr.flush()
    return 0


def run(argv):
    """Run `uv run --frozen --project <plugin root> scribe <argv>` fail-open."""
    label = " ".join(argv[:2]) if argv else "scribe"
    command = [UV, "run", "--frozen", "--project", PLUGIN_ROOT, "scribe"] + list(argv)
    token = os.urandom(16).hex()
    environment = dict(os.environ)
    environment["SCRIBE_DENY_TOKEN"] = token
    try:
        completed = subprocess.run(command, capture_output=True, env=environment)
    except OSError as exc:
        return _skip(label, "uv could not start: %s" % exc)
    stderr_lines = completed.stderr.decode("utf-8", errors="replace").splitlines()
    marker = "%s %s]" % (DENY_MARKER, token)
    deliberate = marker in stderr_lines
    if completed.returncode == 0 or deliberate:
        sys.stdout.buffer.write(completed.stdout)
        sys.stdout.flush()
        for line in stderr_lines:
            if line != marker:
                sys.stderr.write(line + "\n")
        sys.stderr.flush()
        if deliberate:
            return 1 if argv[:1] == ["git-hook"] else 2
        return completed.returncode
    tail = next((line for line in reversed(stderr_lines) if line.strip()), "")
    return _skip(label, "exit %d: %s" % (completed.returncode, tail.strip()))


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
