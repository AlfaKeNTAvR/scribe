---
id: 01M249WDNZC5XF34H0VHP09NSZ
alias: D-260910-write-index-heading-per-record
title: INDEX.md renders one heading per record with one bullet per field (state, by, review, title, affects, regret) instead of one pipe-separated line, so editors can collapse and read it
date: '2026-09-10'
schema_version: 1
task_refs: []
review_state: unreviewed
effective_state: proposed
decided_by: human
recommended_by: claude-code
ratified_by: null
ratified_at: null
provenance:
  authored_by: agent-drafted
  agent: claude-code
  model: null
  session: session_01A6tVoZuuWqu56QxEqtAjRw
  prompt_ids: []
  trigger: user-prompt
  source_messages: []
affects:
- {type: path, pattern: src/scribe/index.py}
implementation_links: []
tags:
- index
- readability
- format
reversibility: two-way-door
blast_radius: component
regret_when: The Active section grows past roughly 50 records and scrolling the index costs more than the collapsible headings save, or a tool starts parsing INDEX.md and needs a stable one-line form.
review: '2026-12-08'
verify:
- {id: index-uses-record-headings, engine: grep, pattern: '### ', paths: [docs/decisions/INDEX.md], expect: match, severity: error}
supersedes: null
relates_to: []
history:
- {at: '2026-09-10T00:01:05Z', event: proposed, by: claude-code, session: session_01A6tVoZuuWqu56QxEqtAjRw}
---

# INDEX.md renders one heading per record with one bullet per field (state, by, review, title, affects, regret) instead of one pipe-separated line, so editors can collapse and read it

> In the context of INDEX.md being the human-facing view of the ledger that no tool parses (the edit hook reads records directly, SessionStart only counts the queue, CI only checks staleness), facing one 300-character pipe-separated line per record that was unreadable in VS Code, I decided to render each record as a level-3 heading followed by one bullet per field (state, by, review, title, affects, regret, plus supersedes or retired when they apply) to achieve a file that reads and collapses like an outline, accepting about seven lines per record, which is why the section structure and ordering stay exactly as before.

## Question

What layout should the generated INDEX.md use so a human can scan the review queue and the active decisions in an editor, given that the previous one-line-per-record form was unreadable?

## Criteria

- Readable and collapsible in VS Code source and preview.
- Every field the old line carried stays visible (state, review state, decided by, review date, title, affects, regret).
- Deterministic output so scribe index --check keeps working.
- No consumer other than humans depends on the layout.

## Constraints and assumptions

- Confirmed by search that no module parses INDEX.md; only humans read it.
- The owner previewed three layouts (a table, a heading with a compact line, and a heading with a bullet per field) rendered from the real ledger (docs/build/13-index-preview-c.md) and chose the bullet form with affects and regret kept.
- Section headers, the queue ordering note and the queue numbering stay as they were.

## Options considered

| Option | For | Against | Evidence | Why rejected |
|---|---|---|---|---|
| Heading per record, one bullet per field, affects and regret kept | Collapses in VS Code; every field on its own line; regret visible where the review happens | About seven lines per record, so a large Active section is long | docs/build/13-index-preview-c.md; owner's choice | chosen |
| One markdown table per section (alias, state, by, review, title) | Densest scan; aligned columns | Long titles make rows wrap; affects and regret would be dropped from the index | the A mock shown to the owner | Owner preferred collapsible headings |
| Heading per record with fields on a compact line under it | Shorter than bullets | The compact line is still hard to scan; no per-field alignment | the B mock shown to the owner | Owner preferred one bullet per field |
| Keep the one-line form | No change | Unreadable in an editor; the reason this came up | docs/decisions/INDEX.md before 2026-09-09 night | Owner: this is not really human readable |

## Decision

render_index emits, per record, a level-3 heading (numbered in the review queue, with [supersedes ratified] appended where it applies) followed by bullets in this order: supersedes or retired when applicable, state (effective, review), by, review date, title, affects (comma-separated path patterns, omitted when empty), regret (omitted when empty). Blocks are separated by one blank line; the document header, section headers and ordering are unchanged.

## Consequences

- Positive: the review queue and active decisions read as an outline; headings collapse in editors.
- Negative: the index is about seven times longer per record; a very large ledger scrolls more.
- Requires: any future tool that wants machine-readable index data reads the records, not INDEX.md.
- Measure: whether the owner keeps reading INDEX.md in the editor rather than opening records, and the line count of the Active section over time.

## Evidence

> Yeah. I think I like this option, especially because in Versus Code, you can easily collapse, uh, headers. I think it's pretty viewable. So let's use, uh, this format.

- Owner (Nikita Boguslavskii) to Claude Fable 5.1, Claude Code session session_01A6tVoZuuWqu56QxEqtAjRw, 2026-09-09 night, voice-transcribed (Versus Code is VS Code).
- docs/build/13-index-preview-c.md, the preview the owner approved.
- docs/build/14-index-format-c.md, the implementation report.
