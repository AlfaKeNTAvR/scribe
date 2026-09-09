---
id: 01M21BVA0X8D5FZCRZNX848569
alias: D-260908-one-way-door-defer-not-stop
title: One-way-door decisions are recorded as proposed and batched for the end of the run, never a hard stop, and the Bash denylist keeps the action denied until ratified
date: '2026-09-08'
schema_version: 1
task_refs: []
review_state: ratified
effective_state: implemented
decided_by: human
recommended_by: claude-code
ratified_by: '@nikita'
ratified_at: '2026-09-08T20:37:42Z'
provenance:
  authored_by: agent-drafted
  agent: claude-code
  model: claude-fable-5-1
  session: session_01A6tVoZuuWqu56QxEqtAjRw
  prompt_ids: []
  trigger: user-prompt
  source_messages: []
affects:
- {type: path, pattern: src/scribe/policy.py}
- {type: path, pattern: src/scribe/hooks/pre_tool_use_gate.py}
- {type: path, pattern: skills/decide/SKILL.md}
implementation_links:
- {commit: e87e31b6c3cf, paths: &id001 [skills/decide/SKILL.md]}
- {commit: ae40787ad91c, paths: &id002 [src/scribe/hooks/pre_tool_use_gate.py, src/scribe/policy.py]}
- {commit: ed6a758732d6, paths: &id005 [skills/decide/SKILL.md]}
tags:
- one-way-door
- autonomous-mode
- gate
- denylist
reversibility: two-way-door
blast_radius: component
regret_when: A deferred one-way-door question forces rework of more than one completed task, or a run defers more than 2 one-way-doors.
review: '2026-12-08'
verify:
- {id: gate-has-enforce-switch, engine: grep, pattern: SCRIBE_GATES, paths: [src/scribe/hooks/pre_tool_use_gate.py], expect: match, severity: warning}
- {id: decide-skill-batches-one-way-doors, engine: grep, pattern: one-way-door, paths: [skills/decide/SKILL.md], expect: match, severity: warning}
supersedes: null
relates_to:
- D-260908-unreviewed-may-supersede-ratified
history:
- {at: '2026-09-08T20:37:42Z', event: proposed, by: Nikita Boguslavskii, session: session_01A6tVoZuuWqu56QxEqtAjRw}
- {at: '2026-09-08T20:37:42Z', event: ratified, by: '@nikita', field: review_state, old: unreviewed, new: ratified}
- {at: '2026-09-08T20:37:42Z', event: ratified, by: '@nikita', field: ratified_by, old: null, new: '@nikita'}
- {at: '2026-09-08T20:37:42Z', event: ratified, by: '@nikita', field: ratified_at, old: null, new: '2026-09-08T20:37:42Z'}
- {at: '2026-09-09T01:26:46Z', event: relinked, by: scribe-relink, field: implementation_links, old: [], new: [{commit: e87e31b6c3cf, paths: [skills/decide/SKILL.md]}, {commit: ae40787ad91c, paths: [src/scribe/hooks/pre_tool_use_gate.py, src/scribe/policy.py]}]}
- {at: '2026-09-09T01:26:46Z', event: implemented, by: scribe-relink, commit: ae40787ad91c, field: effective_state, old: proposed, new: implemented}
- {at: '2026-09-09T01:39:07Z', event: link_added, by: scribe-post-commit, commit: ed6a758732d6, field: implementation_links, old: [&id003 {commit: e87e31b6c3cf, paths: *id001}, &id004 {commit: ae40787ad91c, paths: *id002}], new: [*id003, *id004, {commit: ed6a758732d6, paths: *id005}]}
---

# One-way-door decisions are recorded as proposed and batched for the end of the run, never a hard stop, and the Bash denylist keeps the action denied until ratified

> In the context of an autonomous agent run that meets a decision it cannot cheaply undo, facing the choice between stopping to ask and acting on its own judgment, I decided to record the decision as proposed, finish every piece of work that does not depend on it, and ask about all pending one-way-doors in one batch at the end of the run, to achieve unblocked progress without ever executing an irreversible action unratified, accepting that a deferred answer may cost some rework, which is why the agent blocks early only when the remaining work cannot proceed without the answer and the `PreToolUse` Bash denylist denies the action itself until a ratified record exists.

## Question

What does the agent do in autonomous mode when it reaches a one-way-door decision (a change that cannot be cheaply undone: migration, deploy, external API call, package publish, delete outside the worktree)?

## Criteria

- The agent never performs an irreversible action without human ratification (interview answer A1).
- The agent is not blocked by the question; the owner's autonomous-mode rule is "do not stop to ask".
- The owner sees every pending one-way-door in one place, once per run, not as a stream of interruptions.
- The rule is enforced by a mechanism, not only by the agent's self-restraint.

## Constraints and assumptions

- The owner's global autonomous-mode instruction already forbids destructive actions and has produced no blockers so far, so the expected frequency is near zero; nothing heavier than logging is justified until measured.
- The concrete denylist is fixed by A1: migrations, deploys, external API calls, package publishes, deletes outside the worktree; it is enforced at `PreToolUse` on Bash, not left to the agent's own `one-way-door` label.
- Assumption filled in by the agent: in this build run the denylist gate runs in shadow mode (computes and logs its verdict, always allows) until a two-worktree test passes; the "never act" half is therefore the owner's rule plus the skill's instructions for now.
- The README draft before this answer said one-way-door decisions stop the agent even in autonomous mode (accepted from the GPT-5.6-sol critique, D9); this record overrides that.

## Options considered

| Option | For | Against | Evidence | Why rejected |
|---|---|---|---|---|
| Hard-stop the agent at the first one-way-door and wait for the owner | Nothing irreversible can happen; simplest to reason about | Blocks all unrelated work; the owner may be away for hours; contradicts the autonomous-mode rule | README 10.3 draft (D9), owner quote below | Owner: "you can do other stuff and then ask me about those one-way-doors at the end, so you are not blocked" |
| Ask immediately every time via a question prompt | Fast answer when the owner is present | In autonomous mode the owner is often absent; each question is an interruption; no batching | Owner's autonomous-mode rule in CLAUDE.md | Same blocking problem in a different shape |
| Proceed on the agent's judgment when it believes the door is one-way but low risk | No friction at all | Violates A1; the agent's own label is exactly what cannot be trusted for irreversible actions | GPT-6-astra review, section 3 "do not leave the boundary entirely to the agent's one-way-door label" | Rejected by the owner in A1 |
| Record as proposed, finish independent work, batch all pending one-way-doors at the end of the run, block early only if the rest depends on it; the Bash denylist denies the action until a ratified record exists | Unblocked; owner answers once; the denylist makes "never act" mechanical rather than moral | Deferred answers can cost rework; needs the denylist gate to be real, which is scaffolded first | README 10.3 first paragraph after the owner's answer; 10.4 row "Irreversible action"; A13 | chosen |

## Decision

On a one-way-door decision in autonomous mode the agent writes the record with `reversibility: one-way-door`, `review_state: unreviewed`, `effective_state: proposed`, does not perform the action, continues with every task that does not depend on it, and lists all pending one-way-door records in a single question block at the end of the run. It blocks early only when the remaining work cannot proceed without the answer. The `PreToolUse` hook on Bash denies any command matching the irreversible-action denylist unless a ratified one-way-door record covers it; in this build run that gate is scaffolded in shadow mode and logs what it would have denied, so frequency can be measured before it is switched to enforce.

## Consequences

- Positive: autonomous runs finish; the owner reviews one-way-doors in one batch; the action boundary, not the merge, is where approval is checked.
- Negative: work completed before the batch may need rework if the owner answers differently than the agent assumed. Bounded by the "block early if the rest depends on it" clause.
- Requires: the `/scribe:decide` skill instructs the agent to batch; `policy.py` holds the denylist; the gate log records shadow verdicts.
- Measure: number of one-way-door records per run and number of denylist hits in `.claude/scribe/gate-log.jsonl`; the owner wants to "see how often you hit those" before adding anything heavier.

## Evidence

> what I would say is maybe instead of stopping unless the work absoultely depends on it you can do other stuff and then ask me about those one-way-doors at the end, so you are not blocked. I guess we will need to see how often you hit those, cause my autonomous mode instructions say do not do anything desctructive, kinda of one-way-doors and so far I haven;t seen any blockers

- Owner (Nikita Boguslavskii) to Claude Fable 5.1, Claude Code session `session_01A6tVoZuuWqu56QxEqtAjRw`, 2026-09-08 afternoon; message uuids not recorded.
- Interview answer A13 and A1: `~/.claude` repo, `research/decision-scribing/AUTONOMOUS_DECISIONS_09_08_2026.md`, "Interview answers" section, lines 35 and 46 (branch `nikita/docs/decision-scribing-glossary`).
- Design text applying the decision: `research/decision-scribing/README.md` section 10.3 first paragraph (one-way-door sentences) and section 10.4 row "Irreversible action".
- The rule this overrides: decisions file D9, "one-way-door decisions stop even in autonomous mode".
- Implementation pending: `src/scribe/policy.py`, `src/scribe/hooks/pre_tool_use_gate.py`, `skills/decide/SKILL.md`, per `docs/build/01-plan.md` sections 4.7 and 4.9.
