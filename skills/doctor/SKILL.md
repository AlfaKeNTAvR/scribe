---
name: doctor
description: Check that this scribe installation actually works: the interpreter Claude Code launches the hooks with, uv, the git hook shims, the ratification deny rule, the decision store and the index.
allowed-tools: Bash(uv run --frozen --project ${CLAUDE_PLUGIN_ROOT} scribe *)
---

# Check the installation

Every way a scribe install can break is silent. A hook whose interpreter is
missing is a single `hook error` line in the transcript; the supervisor
swallows a broken `uv` and exits 0; a git shim that is not executable is
simply never run. Nothing looks wrong, and no decision is ever recorded.

## 1. Run it

```
uv run --frozen --project ${CLAUDE_PLUGIN_ROOT} scribe doctor
```

Run it from the repository you want checked: the second half of the report is
about that repository, not about the plugin.

## 2. Report

Print every line that is not `ok`, verbatim, then the summary line. If every
check passed, say so in one line and stop. The exit code is 1 when any check
failed.

What each failure means, in the owner's terms:

- `hook interpreter`: Claude Code cannot start the scribe hooks at all, so no
  decision is injected before an edit and nothing is recorded. On Windows,
  install the Microsoft Store Python (it provides `python3.exe`) or put a
  `python3.cmd` on PATH. This is the one that makes scribe look installed
  while doing nothing.
- `supervisor smoke test`: the interpreter and `uv` both start, but scribe
  itself never answers, so every hook is failing open. The detail line carries
  the reason the supervisor gave.
- `uv`: nothing scribe does can run. Every hook and every git hook skips.
- `git hooks`: `scribe init` has not run in this repository, or another tool
  owns a hook of the same name, or a shim is not executable. Commit trailers
  and backlinks stop happening.
- `settings deny rule`: the agent's file tools are not blocked from editing
  `RATIFICATIONS.jsonl`. Re-run `scribe init`.
- `settings reach`: the deny rule exists but the file is git-ignored, so it
  protects this machine only and never reaches a teammate or another checkout.
- `index`: `INDEX.md` is behind the records; offer `scribe index`.
- `config`, `decision store`: warnings only, defaults apply.

Never offer to fix anything by editing a record or the ledger. The repairs
here are `scribe init`, `scribe index`, and installing a missing tool.
