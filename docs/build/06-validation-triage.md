# Triage of the Codex validation findings (V3 to V23)

Written 2026-09-09 by the main Fable 5.1 session after fixing V1 (M10) and V2. Source: `docs/build/04b-codex-validation.md`. Every finding was re-read against the code; none was re-executed. Verdicts:

- `fix now`: mechanical, clearly correct, no design change; safe to hand to an implementer as a batch.
- `owner call`: the fix changes behaviour the plan or an I-line chose deliberately; needs a decision before code moves.
- `defer`: real, but larger than its current risk in a single-user, shadow-mode tool; gets a scribe record so the deferral is visible.

Effort: S under an hour, M a few hours, L a day or more.

## Batch A: fix now (no design decision needed)

| Finding | What to do | Effort |
|---|---|---|
| V4 | `check._supersede_gate` dependency arm uses `links.implementation_paths` (the same predicate as post-commit) instead of `matches_affects`. Tests: empty affects, action-only affects, negation. | S |
| V5 | `scribe check` validates every current record, not only changed files; `latest_attestation` reports malformed or incomplete JSONL lines (missing actor, timestamp, alias, via) as errors instead of skipping them; a truncated final line is an error before any append. | M |
| V7 (body part) | `history_check` compares bodies byte for byte; drop `rstrip()`. The mutable-field replay is in Batch C. | S |
| V9 | `ratify.apply_verdict` treats a lock timeout as a retryable failure: prints one line, exits non-zero, writes nothing. Scratch-state writers keep the fail-open fallback (drop the update, never overwrite unlocked). Test: hold the lock past the 2 s timeout. | S |
| V10 | Recovery copies `ratified_by` and the verdict timestamp from the latest attestation; the idempotent branch first compares the record with the latest attestation and repairs a contradiction (ratified record, latest line rejected) before saying `already ratified`. | S |
| V11 | `command_verdict` evaluates every matched rule and denies if any lacks authorization; the event lists matched and uncovered rules. Same pass fixes the `rm -rf build /tmp/other` miss (check every target, not the first). | S |
| V14 | `gitutil` path helpers use `-z` output and decode NUL-separated fields; stop turning backslashes into slashes. Tests with `src/café.py`, a tab, a quote. | M |
| V15 | One canonicalisation for root and target in `matching.to_repo_relative`: resolve the nearest existing ancestor, then append the rest; cross-drive paths on Windows count as outside instead of raising. | S |
| V16 | `post_commit.run` tracks implemented records separately from new links; index write and pending consumption always run when anything was implemented; `mark_implemented` changes are saved. Test a failure after each persistence step. | S |
| V17 | `schema` type-checks before membership, hashing and date conversion; out-of-range ULID dates become a diagnostic; `store.records` and the injection matcher skip one malformed file with a logged line instead of aborting the collection. | M |
| V18 | Injection reads a record only up to the closing front-matter delimiter and checks the 700 ms deadline once more before emitting. Test with 1 MB bodies. | S |
| V19 (template, empty lists) | Single-pass template substitution; an explicit empty `task_refs` or `prompt_ids` in the spec stays empty. The pending cap is an owner call (below). | S |
| V20 | One shared reachable-commit check (`git rev-list --all` cached per run, abbreviations resolved) for relink, lint and lookup. Test: an amended-away commit that still exists as an object. | S |
| V22 | The attestation recovery diagnostic names `scribe ratify` / `scribe reject`; tests assert the suggested command parses and heals. | S |
| conformance | `init.check_command` quotes filesystem CI-source paths with `shlex.quote`. | S |

Estimated total: two Codex 20-minute slices or three Sonnet subagents, then the main session re-runs the suite and commits through `/commit` per group.

## Batch B: owner calls (one decision each, asked one per turn)

- V3 dirty-tree CI semantics. Proposal: `scribe check` reads records and attestations from the git tree of the tip it is checking (a revision-backed store), so local dirty state cannot mask or fake a result; and the "was the predecessor ratified on the target" question is asked against the base tip, not the merge base. Cheap interim: refuse to run (exit 1, clear message) when `docs/decisions/` has uncommitted changes, unless `--allow-dirty`. Effort M for the interim, L for the revision-backed store.
- V6 deleting a committed record. I45 allowed deletion. Proposal: `scribe check` fails when a record present at the base ref is gone at the tip (`record_deleted`), retirement goes through `expired` or `backtracked` only. Effort S. Risk: a repo that really wants to drop a bogus record needs a documented escape (`--allow-delete <alias>` or a record explaining the removal).
- V8 write serialisation. Proposal: reserve new record filenames with exclusive create (fixes the alias race, S), and take the ratify lock in `new`, `post-commit`, `relink` and `lint --expire` as well (one worktree-local ledger lock, M). The alternative is to document "one writer at a time" and do only the exclusive create.
- V12 which records may authorize a one-way-door action. Proposal: only a record whose latest attestation is `ratified` with a matching body hash, whose effective state is `proposed` or `implemented`, and which is not superseded. Retired records never authorize. Effort S once decided; reuses one shared "effective authority" predicate for gates, INDEX.md and commit-msg.
- V19 pending cap. `pending_decisions` is silently capped at 20. Proposal: no cap; prune only on session expiry. Effort S.
- V21 deny-rule anchor. The `Edit(/docs/decisions/RATIFICATIONS.jsonl)` rule is relative to the session's starting directory. Needs a live test from a subdirectory and from a linked worktree before choosing between "document: start Claude at the repo root" and a broader rule. Effort S to test, decision after.
- TaskCompleted clears its `decision_worthy` flag even after an enforce denial (conformance note). Follows the plan; revisit together with V12 before any gate goes to enforce.

## Batch C: defer, with a scribe record each

- V7 history replay: require appended history entries to explain every changed mutable field. Effort M. Deferred because the ledger is three records and every writer is scribe itself; revisit once the CI check has run for a few weeks.
- V13 staged-content checks in the git hooks (index-backed store). Effort L. Deferred with a cheap interim in Batch A's spirit if wanted: warn when a staged record file differs from its working-tree copy.
- V23 test fixtures: replace the copied live ledger with stable fixture records so dogfooding cannot break unrelated tests; isolate the timing test's bytecode purge to a temp copy. Effort M. The V1 part of V23 is done (`tests/test_supervise.py`).

## Rejected or already closed

- V1, V2: fixed (M10, commit 7172b42).
- V23's "skips are environment-dependent": accepted as a documentation note; the README Tests section already names the three deferred tests.
- Nothing else rejected.

## Order of work proposed

1. Batch A as one implementer job (Codex, two slices, main session verifies and commits per group).
2. Batch B decisions one per turn, in the order V6, V12, V3, V8, V19, V21.
3. Batch C records written with `/scribe:decide` so the deferrals are visible in `INDEX.md`.
