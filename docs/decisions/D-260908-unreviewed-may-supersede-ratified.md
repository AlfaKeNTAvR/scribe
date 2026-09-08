---
id: 01M21BV91NZSW1HMJ127KZAA5J
alias: D-260908-unreviewed-may-supersede-ratified
title: An unreviewed agent record may supersede a ratified one, guarded by queue priority and a CI merge gate
date: 2026-09-08
schema_version: 1
task_refs: []
review_state: ratified
effective_state: proposed
decided_by: human
recommended_by: claude-code
ratified_by: "@nikita"
ratified_at: 2026-09-08T20:37:41Z
provenance:
  authored_by: agent-drafted
  agent: claude-code
  model: claude-fable-5-1
  session: session_01A6tVoZuuWqu56QxEqtAjRw
  prompt_ids: []
  trigger: user-prompt
  source_messages: []    # transcript message uuids unknown at writing time; the verbatim quote in Evidence is the proof (A12)
affects:
  - { type: path, pattern: "src/scribe/index.py" }
  - { type: path, pattern: "src/scribe/check.py" }
  - { type: path, pattern: "src/scribe/templates/scribe-check.yml" }
implementation_links: []
tags: [lifecycle, supersede, review-queue, ci]
reversibility: two-way-door
blast_radius: component
regret_when: "An unreviewed superseding record is merged to main without ratification, or more than 3 such records wait in the queue at once."
review: 2026-12-08
verify:
  - { id: index-marks-supersedes-ratified, engine: grep, pattern: "supersedes ratified", paths: ["src/scribe/index.py"], expect: match, severity: warning }
  - { id: check-blocks-on-supersede, engine: grep, pattern: "supersedes", paths: ["src/scribe/check.py"], expect: match, severity: warning }
supersedes: null
relates_to: [D-260908-one-way-door-defer-not-stop]
history:
  - { at: 2026-09-08T20:37:41Z, event: proposed, by: "Nikita Boguslavskii", session: session_01A6tVoZuuWqu56QxEqtAjRw }
  - { at: 2026-09-08T20:37:41Z, event: ratified, by: "@nikita", field: review_state, old: unreviewed, new: ratified }
  - { at: 2026-09-08T20:37:41Z, event: ratified, by: "@nikita", field: ratified_by, old: null, new: "@nikita" }
  - { at: 2026-09-08T20:37:41Z, event: ratified, by: "@nikita", field: ratified_at, old: null, new: 2026-09-08T20:37:41Z }
---

# An unreviewed agent record may supersede a ratified one, guarded by queue priority and a CI merge gate

> In the context of an autonomous agent session that discovers a human-ratified decision no longer fits, facing the choice between waiting for the human and overturning the decision on its own, I decided to let the agent write a superseding record immediately and keep working, to achieve uninterrupted progress, accepting that a human decision can be overturned for later sessions before anyone looks, which is why the record goes to the top of the review queue with a `supersedes ratified` marker and a CI required check blocks the merge until a human ratifies or rejects it.

## Question

When an autonomous session needs to replace a decision the owner has already ratified, may it do so before the owner sees it, and if so, what stops the replacement from reaching `main` unreviewed?

## Criteria

- Progress in autonomous mode is never blocked waiting for a human (owner's standing rule for autonomous mode).
- No superseding of a human decision reaches `main` without a human or AI-assisted human review.
- Such records are the first thing the owner sees at review time, not one line among many.
- The common path (ordinary decisions) pays nothing for the guard.

## Constraints and assumptions

- The owner works alone and reviews in batches, typically the next morning, over `INDEX.md`.
- The owner will add main-branch protection with the CI check as a required status on each repository (interview answer A11); without protection the gate has no teeth. Assumption filled in by the agent: the check is a GitHub Actions job named `scribe-check`.
- Records are markdown files; a `supersedes` edge is stored once on the new record and the indexer derives the inverse (fixed decision).
- The owner expects these cases to be rare ("I bet there won't be that many"), so frequency is not yet measured.

## Options considered

| Option | For | Against | Evidence | Why rejected |
|---|---|---|---|---|
| Block: an agent may not supersede a ratified record until a human confirms | Human decisions are never overturned silently | Stalls the run; contradicts the owner's autonomous-mode rule; mc856 forbids non-interactive ratified writes but says nothing about proposals | README 10.3, owner quote below | Owner: "I don't want to slow down the progress" |
| Allow with no guard | Simplest; zero friction | A human decision is overturned for every later session and can merge unnoticed | README 10.3 second paragraph | Owner: decisions "should not slip and get merged without a human/ai-assisted review" |
| Allow, but keep the old ratified record active until the new one is ratified | Old decision keeps governing edits meanwhile | Two contradictory active records inject at edit time; the agent that wrote the new one would be told to follow the old one | README 10.2 injection block design | Contradictory injection is worse than either record alone |
| Allow immediately; new record retires the old one at once; review queue puts it first with a `supersedes ratified` marker; CI required check fails until ratified or rejected | Progress never waits; the overturn is the first thing the owner sees; cannot merge unreviewed once branch protection is on | A human decision can be overturned for later sessions before anyone looks; needs branch protection to bite | README 10.3, 10.4 rows "Merge" and "Commit validation"; interview A10, A11 | chosen |

## Decision

An autonomous session may write a record whose `supersedes` points at a human-ratified record and keep working. The indexer retires the old record from the active index and from pre-edit injection at once. Two guards apply: the review queue in `INDEX.md` orders such records above every other unreviewed record with the literal marker `supersedes ratified`; and `scribe check`, run as a CI required check, fails while the branch introduces or modifies an unreviewed record that supersedes a ratified one, passing once that record is ratified or rejected. The local `commit-msg` hook only prints a notice for this case. Ordinary unreviewed records never block a merge.

## Consequences

- Positive: autonomous runs never wait on review; overturned human decisions cannot slip into `main` once protection is on; the common path costs nothing.
- Negative: between the agent's commit and the owner's review, later sessions on that branch follow the agent's decision, not the owner's. Accepted because the branch cannot merge.
- Requires: the owner adds branch protection with `scribe-check` required on each repository (A11); until then the gate is advisory.
- Measure: count `supersedes ratified` queue entries per week; if the count stays above 3, revisit (see `regret_when`).

## Evidence

> I think it is okay, we just need to make sure that those decisions are gonna be presented to me as top priority when the code will be up-to-review. I don't want to slow down the progress and those decisions should not slip and get merged without a human/ai-assited review. I bet there won't be that many.

- Owner (Nikita Boguslavskii) to Claude Fable 5.1, Claude Code session `session_01A6tVoZuuWqu56QxEqtAjRw`, 2026-09-08 afternoon; message uuids not recorded.
- Interview answers A10 and A11: `~/.claude` repo, `research/decision-scribing/AUTONOMOUS_DECISIONS_09_08_2026.md`, section "Interview answers", lines 43 to 44 (branch `nikita/docs/decision-scribing-glossary`).
- Design text applying the decision: `research/decision-scribing/README.md` section 10.3 second paragraph and section 10.4 rows "Commit validation" and "Merge".
- Implementation pending: `src/scribe/index.py` (queue ordering and marker), `src/scribe/check.py` (merge gate), per `docs/build/01-plan.md` sections 3.5 and 5.4.
