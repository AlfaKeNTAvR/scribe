---
name: init
description: "Human only: install the scribe git hooks, config, deny rule and CI workflow into this repository. The agent must never invoke this."
disable-model-invocation: true
argument-hint: [--force] [--ci-source <spec>]
allowed-tools: Bash(uv run --frozen --project ${CLAUDE_PLUGIN_ROOT} scribe *)
---

# Set up scribe in this repository

Run exactly this command with the Bash tool and nothing else:

```
uv run --frozen --project ${CLAUDE_PLUGIN_ROOT} scribe init $ARGUMENTS
```

Then report its output to the user verbatim: every path it wrote, kept,
replaced, skipped or left unchanged, and the `next steps` block. Do not edit
any of the written files afterwards.

What the command does (plan section 5.5):

- installs `prepare-commit-msg`, `commit-msg` and `post-commit` shims into the
  repository's hooks directory (a hook it did not write is kept and reported;
  `--force` replaces it and leaves `<name>.pre-scribe`);
- appends `.claude/scribe/` to `.gitignore`;
- writes `.claude/scribe/config.json` with the safe values (`SCRIBE_GATES:
  shadow`, `SCRIBE_COMMIT_MSG: warn`) once, never overwriting it;
- with `--ci-source <path or git+https URL>` writes
  `.github/workflows/scribe-check.yml`; without it, it prints how to add the
  workflow later;
- adds the deny rule `Edit(/docs/decisions/RATIFICATIONS.jsonl)` to
  `.claude/settings.json`;
- creates `docs/decisions/` with an empty `RATIFICATIONS.jsonl` and an
  `INDEX.md` when the store does not exist yet.

If it exits 1, relay the reason: `uv` or the hook interpreter is missing from
PATH, `core.hooksPath` is set (the output shows how to chain the hooks or where
to pass `--hooks-dir`), or a foreign hook was kept.
