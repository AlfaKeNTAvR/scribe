---
id: 01M23XP6N2S6NGT9FF21M89E12
alias: D-260909-the-git-hooks-keep-reading-records-and-a
title: The git hooks keep reading records and attestations from the working tree, not from the staged index, until enforce mode ships or a false verdict is seen
date: '2026-09-09'
schema_version: 1
task_refs: []
review_state: unreviewed
effective_state: implemented
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
- {type: path, pattern: src/scribe/githooks/commit_msg.py}
- {type: path, pattern: src/scribe/githooks/prepare_commit_msg.py}
- {type: path, pattern: src/scribe/store.py}
implementation_links:
- {commit: 81a856b77e92, paths: &id001 [src/scribe/githooks/commit_msg.py]}
tags:
- git-hooks
- staging
- deferred
- codex-finding
reversibility: two-way-door
blast_radius: component
regret_when: commit-msg passes a commit because the reviewed working-tree copy vouched for an unreviewed staged copy, or enforce mode rejects a good commit for the reverse reason.
review: '2026-12-08'
verify:
- {id: commit-msg-documents-working-tree-reads, engine: grep, pattern: staged content, paths: [src/scribe/githooks/commit_msg.py], expect: match, severity: warning}
supersedes: null
relates_to: []
history:
- {at: '2026-09-09T20:27:58Z', event: proposed, by: claude-code, session: session_01A6tVoZuuWqu56QxEqtAjRw}
- {at: '2026-09-09T21:26:49Z', event: link_added, by: scribe-post-commit, commit: 81a856b77e92, field: implementation_links, old: [], new: [{commit: 81a856b77e92, paths: *id001}]}
- {at: '2026-09-09T21:26:49Z', event: implemented, by: scribe-post-commit, commit: 81a856b77e92, field: effective_state, old: proposed, new: implemented}
---

# The git hooks keep reading records and attestations from the working tree, not from the staged index, until enforce mode ships or a false verdict is seen

> In the context of the Codex validation finding V13 (commit-msg and prepare-commit-msg select records by staged filename but load their content and attestations from disk, so a reviewed working-tree version can vouch for an unreviewed staged version and an unstaged attestation can satisfy a staged-record check), facing the choice between an index-backed store now or keeping working-tree reads, I decided to keep working-tree reads and record the gap, to achieve a v0.1.0 whose hooks stay simple and warn-only, accepting that a partial staging can produce a wrong warning or, under enforce mode, a wrong rejection, which is why the CI check on the pushed range remains the real gate.

## Question

Should the git hooks build their Store from the staged index (git show :path for every staged record and for RATIFICATIONS.jsonl) instead of the working tree, so that what the hook checks is exactly what the commit will contain? Codex rated the gap major (V13) with effort L.

## Criteria

- What the hook checks should be what the commit contains.
- The hook must stay under one second on the edit path and fail open on any error.
- The CI check on the pushed range, not the local hook, is the gate that protects main.

## Constraints and assumptions

- commit-msg is warn-only by default (SCRIBE_COMMIT_MSG: warn); enforce mode is opt-in and not yet recommended in README.
- scribe check on the CI side already reads committed content, so the merge gate is unaffected by V13.
- The triage placed V13 in Batch C at effort L and suggested an optional cheap interim (warn when a staged record file differs from its working-tree copy); the interim was not built.
- Assumption filled in by the agent: partial staging of docs/decisions is rare because scribe's own writers (post-commit, relink, ratify) touch the whole record and the ledger together.

## Options considered

| Option | For | Against | Evidence | Why rejected |
|---|---|---|---|---|
| Defer: keep working-tree reads, document them in the hook module, rely on the CI check as the gate | No new store abstraction before v0.1.0; hooks stay warn-only so a wrong verdict costs one stderr line | Enforce mode could reject or pass a commit based on content that is not in it | docs/build/06-validation-triage.md Batch C; src/scribe/githooks/commit_msg.py | chosen |
| Index-backed store: read every staged path through git show :path and build the Store from those bytes | Exact: the hook sees the commit's content | Effort L; Store currently maps paths to files, so record loading, attestation reading and body hashing would all need a bytes-based entry point; doubles the test surface | docs/build/04b-codex-validation.md V13 | Effort not justified while the hook is warn-only and CI covers the pushed range; deferred, not rejected |
| Cheap interim: warn when a staged record file or the ledger differs from its working-tree copy | Small; makes the partial-staging case visible | Only a warning; adds a git diff --cached call per commit; does not fix the verdict itself | triage suggestion | Not built for v0.1.0; can be added later without a record if the deferral proves costly |

## Decision

commit-msg and prepare-commit-msg keep loading records and attestations from the working tree. The module docstring of commit_msg.py states this (V13, staged content not inspected). Enforce mode for commit-msg is not recommended in README until this is fixed or until the interim warning exists. Revisit at the review date or the first time a partial staging produces a wrong verdict.

## Consequences

- Positive: hooks stay simple, fast and warn-only for v0.1.0.
- Negative: a partially staged docs/decisions change can produce a wrong warning locally; under enforce mode a wrong rejection. Mitigated by CI reading committed content.
- Requires: README keeps commit-msg enforce mode marked as not yet recommended.
- Measure: count of wrong hook verdicts reported by users or seen in dogfooding before the review date; zero keeps the deferral.

## Evidence

> Go ahead

- Owner (Nikita Boguslavskii) to Claude Fable 5.1, Claude Code session session_01A6tVoZuuWqu56QxEqtAjRw, 2026-09-09, approving the triage order of work in docs/build/06-validation-triage.md.
- docs/build/04b-codex-validation.md, finding V13 (Codex gpt-6-astra, 2026-09-08 21:51).
- docs/build/06-validation-triage.md, section Batch C.
- src/scribe/githooks/commit_msg.py module docstring (F13 note on staged content).
