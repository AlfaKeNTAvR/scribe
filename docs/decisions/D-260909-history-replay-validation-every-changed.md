---
id: 01M23XNCJ6AV1FGNZPSY86VBV7
alias: D-260909-history-replay-validation-every-changed
title: History replay validation (every changed mutable field must be explained by an appended history entry) is deferred until the CI check has run on real branches for a few weeks
date: '2026-09-09'
schema_version: 1
task_refs: []
review_state: unreviewed
effective_state: proposed
decided_by: agent-recommended
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
- {type: path, pattern: src/scribe/history_check.py}
- {type: path, pattern: src/scribe/schema.py}
- {type: path, pattern: src/scribe/check.py}
implementation_links: []
tags:
- validation
- history
- ci
- deferred
- codex-finding
reversibility: two-way-door
blast_radius: component
regret_when: A mutable field (effective_state, review_state, implementation_links) changes in a commit with no matching history entry and scribe check passes it, so the change is untraceable.
review: '2026-10-07'
verify:
- {id: history-check-compares-bodies, engine: grep, pattern: compare_record_versions, paths: [src/scribe/history_check.py], expect: match, severity: warning}
supersedes: null
relates_to: []
history:
- {at: '2026-09-09T20:27:31Z', event: proposed, by: claude-code, session: session_01A6tVoZuuWqu56QxEqtAjRw}
---

# History replay validation (every changed mutable field must be explained by an appended history entry) is deferred until the CI check has run on real branches for a few weeks

> In the context of the Codex validation finding V7 (history_check verifies that old history stays a prefix and that bodies are byte-identical, but never requires an appended entry to explain a changed mutable field), facing the choice between building the replay check now or deferring it, I decided to defer it and write this record so the gap is visible in INDEX.md, to achieve a v0.1.0 whose CI check is exercised on real branches before more validation logic is stacked on it, accepting that until then a hand edit of effective_state can retire a record from retrieval without a history entry.

## Question

Should scribe check require, for every commit in the checked range, that each changed mutable front-matter field of a record is explained by an appended history entry with matching field, old and new values? Codex rated the gap major (V7); the body-immutability half of V7 was fixed in Batch A (commit 96a8bd0, the rstrip removal).

## Criteria

- A decision cannot silently leave retrieval: any change to effective_state, review_state, ratified_*, implementation_links or supersedes is traceable.
- The check must not produce false failures for the writers scribe already has (post-commit, relink, ratify, lint --expire), all of which append history.
- Effort proportional to the ledger: three ratified records, every writer is scribe itself.

## Constraints and assumptions

- The body-immutability half of V7 is already fixed (Batch A, I75): compare_record_versions compares whole normalized bodies with no rstrip.
- The triage estimated the replay check at effort M and placed it in Batch C (defer with a record); the owner approved the triage order of work.
- Assumption filled in by the agent: three to four weeks of CI runs on real branches is enough to see whether hand edits of mutable fields happen at all before the check is built.
- Never edit record bodies or RATIFICATIONS.jsonl by hand remains the rule; this deferral does not relax it.

## Options considered

| Option | For | Against | Evidence | Why rejected |
|---|---|---|---|---|
| Defer: keep the prefix check and body-immutability check, record the gap here, revisit at the review date | No new validation logic before v0.1.0; the risk is a hand edit by a scribe user in a repo where every writer so far is scribe itself | A deliberate or accidental hand edit of effective_state passes CI until the check exists | docs/build/06-validation-triage.md, Batch C; the seed ledger has three records and no hand edits | chosen |
| Build the replay check now: diff each record's mutable fields between base and tip, require one appended history entry per changed field with matching old and new | Closes V7 completely; the history shape already carries field, old and new | Effort M; interacts with relink's batched history entries (one entry may cover several links) and would need its own fixture set (V23) to test without the live ledger | docs/build/04b-codex-validation.md V7; src/scribe/history_check.py | Effort and test-fixture cost not justified by a three-record ledger; deferred, not rejected |
| Forbid all mutable-field changes outside scribe's own writers by checking the commit author or a marker | Cheap | Authors are forgeable and scribe's writers run under the user's identity; no real protection | post-commit and relink commit as the user | Provides no assurance |

## Decision

scribe check keeps its current history checks (old history is a prefix, bodies byte-identical, attestations complete). The replay check is not built for v0.1.0. This record sits in the review queue so the deferral is visible; at the review date (2026-10-07) either build the check (effort M, needs the V23 fixtures first) or extend the deferral with a new record that supersedes this one.

## Consequences

- Positive: v0.1.0 ships with the CI check as exercised today; no untested validation logic added under time pressure.
- Negative: a hand edit of a mutable field passes scribe check until the replay check exists; mitigated by the deny rule on RATIFICATIONS.jsonl and by INDEX.md regeneration exposing state changes in review.
- Requires: the V23 fixture work before the check is built, so the test can use synthetic records.
- Measure: number of records whose mutable fields changed without a matching history entry, counted by hand at the review date over git log -p docs/decisions.

## Evidence

> Go ahead

- Owner (Nikita Boguslavskii) to Claude Fable 5.1, Claude Code session session_01A6tVoZuuWqu56QxEqtAjRw, 2026-09-09, approving the triage order of work in docs/build/06-validation-triage.md (Batch A now, Batch B with owner calls, Batch C deferred with a record each).
- docs/build/04b-codex-validation.md, finding V7 (Codex gpt-6-astra, 2026-09-08 21:51).
- docs/build/06-validation-triage.md, section Batch C.
- docs/build/07-batch-a-report.md, the body half of V7 (commit 96a8bd0, I75).
