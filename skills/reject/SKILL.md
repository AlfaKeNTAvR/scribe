---
name: reject
description: "Human only: record your verdict on a decision. The agent must never invoke this."
disable-model-invocation: true
argument-hint: <alias-or-ulid> [note]
allowed-tools: Bash(uv run --frozen --project ${CLAUDE_PLUGIN_ROOT} scribe *)
---

Verdict recorded by scribe before the model saw this text:

!`uv run --frozen --project ${CLAUDE_PLUGIN_ROOT} scribe reject --via skill $ARGUMENTS`

Report the line above to the user verbatim, then show the review queue count from docs/decisions/INDEX.md. Never run scribe ratify or scribe reject yourself.

<!-- UNVERIFIED U1 (plan section 10): this assumes $ARGUMENTS is substituted inside the inline
command above before it runs. If it is not, replace the inline command with an instruction to the
model to run the same command; nothing else changes. -->
