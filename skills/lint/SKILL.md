---
name: lint
description: Check the decision store for drift (stale proposals, failed verify entries, a stale index, broken links) and walk the owner through the review queue one record at a time.
allowed-tools: Bash(uv run --frozen --project ${CLAUDE_PLUGIN_ROOT} scribe *)
---

# Lint the decision store

## 1. Run the linter

```
uv run --frozen --project ${CLAUDE_PLUGIN_ROOT} scribe lint
```

Report every `error` line to the owner. Report `warning` lines grouped by code.
`info` lines are for the owner's attention only, never for you to act on.

Codes worth a sentence of explanation when they appear:

- `index_stale`: `docs/decisions/INDEX.md` is behind the records. Offer to run
  `scribe index` (or `scribe lint --fix-index`).
- `verify_failed`, `verify_error`: the code a record claims to govern no longer
  matches its `verify` entry. Name the record, the entry id, and the file.
- `immutable_changed`, `history_rewritten`: someone edited a record body or an
  immutable key after it was committed. Surface it; do not repair it yourself.
- `proposal_stale`: a proposal nobody reviewed for more than 30 days. Offer
  `scribe lint --expire`, which sets `effective_state: expired` and restores any
  predecessor that proposal was holding down. Ask first; it changes records.
- `unreachable_link`: a linked commit is not in this history. Suggest
  `scribe relink`.

## 2. Present the review queue

```
uv run --frozen --project ${CLAUDE_PLUGIN_ROOT} scribe index --check
```

Then read the `## Review queue` section of `docs/decisions/INDEX.md` and present
it to the owner as a numbered list, in the order it appears there (records that
supersede a ratified record first). For each entry give the alias, the title,
and one line on what it changes.

Offer to walk the owner through the queue one record at a time: show the
`## Question`, `## Decision` and `## Consequences` sections of the record, then
wait. The verdict is the owner's, always.

Never run `scribe ratify` or `scribe reject` yourself, and never suggest a
verdict as if it were already given. Those commands are for the human, through
`/scribe:ratify` and `/scribe:reject`. Your job here ends with the question
"ratify, reject, or skip?".

## 3. Nothing to report

If lint exits 0 with no findings and the review queue is empty, say so in one
line and stop.
