---
id: 01M21BVB05VVF1XV54Y66AWV6E
alias: D-260908-verbatim-quote-is-the-evidence
title: The Evidence section quotes the decisive user turn verbatim; transcript pointers are kept but never relied on
date: '2026-09-08'
schema_version: 1
task_refs: []
review_state: ratified
effective_state: implemented
decided_by: human
recommended_by: claude-code
ratified_by: '@nikita'
ratified_at: '2026-09-08T20:37:43Z'
provenance:
  authored_by: agent-drafted
  agent: claude-code
  model: claude-fable-5-1
  session: session_01A6tVoZuuWqu56QxEqtAjRw
  prompt_ids: []
  trigger: user-prompt
  source_messages: []
affects:
- {type: path, pattern: src/scribe/schema.py}
- {type: path, pattern: src/scribe/templates/record_template.md}
- {type: path, pattern: skills/decide/SKILL.md}
implementation_links:
- {commit: e7c2684a3173, paths: &id001 [src/scribe/schema.py]}
- {commit: e87e31b6c3cf, paths: &id002 [skills/decide/SKILL.md, src/scribe/templates/record_template.md]}
tags:
- schema
- evidence
- provenance
- multi-machine
reversibility: two-way-door
blast_radius: component
regret_when: A record's Evidence quote is shown to differ from a surviving transcript, or more than 1 in 5 new records has no decisive turn to quote.
review: '2026-12-08'
verify:
- {id: every-record-has-evidence-section, engine: grep, pattern: ^## Evidence$, paths: [docs/decisions/D-*.md], expect: match, severity: error}
- {id: template-has-evidence-quote-slot, engine: grep, pattern: '## Evidence', paths: [src/scribe/templates/record_template.md], expect: match, severity: warning}
supersedes: null
relates_to: []
history:
- {at: '2026-09-08T20:37:43Z', event: proposed, by: Nikita Boguslavskii, session: session_01A6tVoZuuWqu56QxEqtAjRw}
- {at: '2026-09-08T20:37:43Z', event: ratified, by: '@nikita', field: review_state, old: unreviewed, new: ratified}
- {at: '2026-09-08T20:37:43Z', event: ratified, by: '@nikita', field: ratified_by, old: null, new: '@nikita'}
- {at: '2026-09-08T20:37:43Z', event: ratified, by: '@nikita', field: ratified_at, old: null, new: '2026-09-08T20:37:43Z'}
- {at: '2026-09-09T01:26:46Z', event: relinked, by: scribe-relink, field: implementation_links, old: [], new: [{commit: e7c2684a3173, paths: *id001}, {commit: e87e31b6c3cf, paths: *id002}]}
- {at: '2026-09-09T01:26:46Z', event: implemented, by: scribe-relink, commit: e87e31b6c3cf, field: effective_state, old: proposed, new: implemented}
---

# The Evidence section quotes the decisive user turn verbatim; transcript pointers are kept but never relied on

> In the context of decision records written by an agent for an owner who works on several machines, facing the fact that Claude Code transcripts are machine-local and get lost, I decided that every record's Evidence section quotes the decisive user turn verbatim and treats session ids and message uuids as bonus pointers, to achieve proof of who said what that travels with the repository, accepting that records grow by a paragraph and that a quote can be misquoted, which is why the pointers stay in the schema for the cases where the transcript does survive.

## Question

What in a decision record proves that the human said what the record claims, given that the owner works on several machines and Claude Code transcripts do not travel between them?

## Criteria

- The proof lives in the repository, not on one machine's disk.
- Fabricated or backfilled rationale stays detectable (mc856 rule 4, kaldiflow anti-pattern).
- Pointers that do exist are not thrown away; they help when the transcript is available.
- Records stay short enough to read in a morning batch.

## Constraints and assumptions

- Claude Code stores transcripts under the user's home directory per machine; nothing syncs them, and `claude -p --resume` is not a transcript export (GPT-6-astra review, row on line 91).
- The `Claude-Session:` trailer is absent on plain local CLI commits, so a session id in a record is often the only session pointer at all, and it is still only a pointer.
- Assumption filled in by the agent: message uuids from hook payloads can be recorded when a hook is the writer; when a human or an agent writes the record by hand, the list may be empty, as it is here.
- The schema keeps `provenance.session` and `provenance.source_messages` as fields; only their role changes from proof to pointer.

## Options considered

| Option | For | Against | Evidence | Why rejected |
|---|---|---|---|---|
| Rely on transcript pointers only (`session`, message uuids, or line numbers) | Smallest record; exact | Transcripts are machine-local and get lost; line numbers shift; nothing to check against once the file is gone | Owner quote below; README 13 phase 4 entry on `Claude-Session:` | Owner: "given that I might work on different machines and eventually lose those it might not be recoverable" |
| Copy the whole relevant transcript excerpt into the record | Complete context | Bloat (compliance papers: context bloat is a measured smell); privacy of unrelated turns; unreadable in a batch review | README 12 AGENTS.md compliance row | Too much for a morning review and mostly noise |
| Drop transcript pointers from the schema entirely | Simpler schema | Loses the cheap wins when the transcript does survive on the same machine | Owner: "I wouldn't remove it, let's see how it goes" | Owner asked to keep them |
| Quote the decisive user turn verbatim in Evidence, required by the validator; keep `session` and `source_messages` as optional pointers | Proof travels with the repo; short; fabrication is detectable because a quote can be checked against memory or any surviving transcript | A quote can be misquoted; a decision without a user turn (self-initiated) has nothing to quote and must say so | README 10.2 Evidence heading comment and `source_messages` comment; A12 | chosen |

## Decision

Every record's `## Evidence` section starts with the decisive user turn quoted verbatim as a markdown blockquote; the validator requires at least one blockquote line in that section. For self-initiated decisions with no user turn the blockquote says so explicitly. `provenance.session`, `provenance.prompt_ids` and `provenance.source_messages` remain in the schema and are filled when known, but no tool or review step depends on them; they are pointers, not proof.

## Consequences

- Positive: a record read on any machine, or on GitHub, carries its own authority; misquotes are checkable; the record format needs no transcript infrastructure.
- Negative: records are one paragraph longer; the agent must find the decisive turn rather than the nearest one; a bad quote is a new failure mode that lint cannot detect without a transcript.
- Requires: `schema.py` enforces the blockquote; the `scribe new` template has the quote slot; the `/scribe:decide` skill tells the agent to quote verbatim.
- Measure: at review time the owner reads the quote first; if quotes are routinely missing or paraphrased, the skill wording changes (see `regret_when`).

## Evidence

> I don't recording the transcript would be that usefull, I wouldn't remove it, let's see how it goes, but given that I might work on different machines and eventually lose those it might not be recoverable.

- Owner (Nikita Boguslavskii) to Claude Fable 5.1, Claude Code session `session_01A6tVoZuuWqu56QxEqtAjRw`, 2026-09-08 afternoon; message uuids not recorded, which is the situation this decision is for.
- Interview answer A12: `~/.claude` repo, `research/decision-scribing/AUTONOMOUS_DECISIONS_09_08_2026.md`, "Interview answers" section, line 45 (branch `nikita/docs/decision-scribing-glossary`).
- Design text applying the decision: `research/decision-scribing/README.md` section 10.2, the `source_messages` comment and the `## Evidence` heading comment; `build-brief.md`, fixed decision "Evidence".
- Implementation pending: `src/scribe/schema.py` (Evidence blockquote rule), `src/scribe/templates/record_template.md`, `skills/decide/SKILL.md`, per `docs/build/01-plan.md` sections 3.4 and 4.9.
