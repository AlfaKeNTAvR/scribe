---
id: 01M23XNDAT9HD7N1XW60GR28B0
alias: D-260909-post-commit-skips-its-backlink-write-whi
title: post-commit skips its backlink write while a rebase is in progress and leaves the relink to post-rewrite, so replayed commits do not dirty docs/decisions mid-rebase
date: '2026-09-09'
schema_version: 1
task_refs: []
review_state: unreviewed
effective_state: proposed
decided_by: agent
recommended_by: claude-code
ratified_by: null
ratified_at: null
provenance:
  authored_by: agent-drafted
  agent: claude-code
  model: null
  session: session_01A6tVoZuuWqu56QxEqtAjRw
  prompt_ids: []
  trigger: self-initiated
  source_messages: []
affects:
- {type: path, pattern: src/scribe/githooks/post_commit.py}
- {type: path, pattern: src/scribe/githooks/post_rewrite.py}
- {type: path, pattern: src/scribe/templates/githook_shim.py}
implementation_links: []
tags:
- git-hooks
- rebase
- post-commit
- post-rewrite
- proposed
reversibility: two-way-door
blast_radius: component
regret_when: A rebase replaying a commit that cites a record stops on a docs/decisions conflict the user did not cause, or a replayed commit never reaches implementation_links.
review: '2026-12-08'
verify:
- {id: post-rewrite-hook-exists, engine: grep, pattern: post-rewrite, paths: [src/scribe/githooks/__init__.py], expect: match, severity: warning}
supersedes: null
relates_to: []
history:
- {at: '2026-09-09T20:27:32Z', event: proposed, by: claude-code, session: session_01A6tVoZuuWqu56QxEqtAjRw}
---

# post-commit skips its backlink write while a rebase is in progress and leaves the relink to post-rewrite, so replayed commits do not dirty docs/decisions mid-rebase

> In the context of the Q3 post-rewrite hook work, where the implementer found (I127) that git already fires post-commit for every replayed commit of a non-conflicting rebase, so scribe writes backlinks into docs/decisions in the middle of the replay and a later commit in the same range that touches the same record file then conflicts, facing the choice between leaving the behaviour, guarding post-commit during a rebase, or making post-commit's write idempotent against the replay, I propose that post-commit detect an in-progress rebase (.git/rebase-merge or .git/rebase-apply present) and skip its write, to achieve a clean replay with one relink at the end by post-rewrite, accepting that implementation_links lag until the rebase finishes, which is why the post-rewrite hook must stay installed wherever post-commit is.

## Question

During a rebase, git runs post-commit for each replayed commit (observed in this git version during Q3, I127). scribe's post-commit then edits record files to add backlinks, which can conflict with a later replayed commit touching docs/decisions. What should post-commit do while a rebase is in progress? This is a proposal recorded before any code change; nothing is implemented yet.

## Criteria

- A non-conflicting rebase must stay non-conflicting when scribe is installed.
- Every replayed commit that cites a record ends up in that record's implementation_links once the rebase finishes.
- No new state files; detection uses what git already leaves on disk.

## Constraints and assumptions

- post-rewrite (commit b7f4528) already relinks the whole history after amend and rebase, so skipping post-commit during a rebase loses nothing once the rebase completes.
- post-commit writes backlinks in the working tree after the commit, which is why a dirty tree mid-rebase is possible at all (handoff note from 2026-09-08).
- Assumption filled in by the agent: .git/rebase-merge and .git/rebase-apply are the reliable in-progress markers for interactive and non-interactive rebases across the git versions in use; worktrees keep them under the worktree's own git dir, which gitutil resolves.
- Assumption: an aborted rebase leaves no backlink edits behind under this proposal, which is better than today, where aborted replays can leave a dirty docs/decisions.

## Options considered

| Option | For | Against | Evidence | Why rejected |
|---|---|---|---|---|
| post-commit detects an in-progress rebase and skips its write; post-rewrite relinks once at the end | Clean replay; one write instead of N; uses git's own markers; no new state | Links lag until the rebase ends; if post-rewrite is missing (older init) the replayed commits are only linked by a manual scribe relink | I127 in AUTONOMOUS_DECISIONS_09_08_2026.md; docs/build/10-q3-post-rewrite.md | chosen |
| Leave as is: post-commit writes per replayed commit, post-rewrite relinks again at the end | No change | Mid-rebase edits to docs/decisions can conflict with a later replayed commit in the same range; the user sees a conflict they did not cause | I127 finding | The conflict is real and confusing; the fix is small |
| Make post-commit's backlink write commute with the replay by committing the backlink into the replayed commit itself (amend during rebase) | Links land inside the history | Amending inside a rebase changes shas git is still replaying and is fragile; also changes the recorded commit id the link points at | reasoning | Fragile and changes commit identity |

## Decision

Proposed, not yet implemented: post_commit.run returns early with no write when the repository's git dir contains rebase-merge or rebase-apply. post-rewrite keeps relinking the whole history after the rebase. scribe init already installs both hooks (four shims). A test rebases two commits citing the same record and asserts docs/decisions stays clean until post-rewrite runs, then holds both links.

## Consequences

- Positive: rebases with scribe installed do not produce self-inflicted conflicts in docs/decisions.
- Negative: implementation_links are stale for the duration of the rebase; a repo initialised before Q3 (three shims) needs scribe init --force to get post-rewrite, or a manual scribe relink.
- Requires: ratification before the code change; the init preflight or README should tell three-shim repos to re-run init.
- Measure: zero rebase conflicts in docs/decisions caused by backlink edits, checked during the playground exercises and the next month of dogfooding.

## Evidence

> (no user turn; self-initiated)

- AUTONOMOUS_DECISIONS_09_08_2026.md, line I127 (Sonnet 5 worktree agent for Q3, 2026-09-09).
- docs/build/10-q3-post-rewrite.md, the Remaining section.
- docs/build/05-handoff.md, the note that post-commit writes backlinks after the commit and leaves the tree dirty.
