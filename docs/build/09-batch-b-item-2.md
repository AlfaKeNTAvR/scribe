# Batch B, Item 2 (V3): dirty ledger guard and base-tip authority

Scope: this file covers only Item 2, V3, "refuse dirty ledger, base tip", implemented alone in
worktree `/home/alfakentavr/scribe-wt/v3` on branch `nikita/fix/batch-b-v3`. It does not touch
`docs/build/09-batch-b-report.md` or `AUTONOMOUS_DECISIONS_09_08_2026.md` (worktree deviation
from step10_prompt.txt); the main session folds the content below into those files itself. No
patch queue file was written; the diff in this worktree is the deliverable.

## Item 2 (V3)

Implemented the owner's cheap-interim call from 06-validation-triage.md's Batch B row for V3
(effort M), not the full revision-backed store (effort L, out of scope): `scribe check --base
<ref>` refuses to run when `docs/decisions` is dirty, unless `--allow-dirty` is given; and the
predecessor-was-ratified question in the supersede gate is now asked against the base ref's tip
exactly as given, not the merge base, while changed paths and commits for "introduces or depends
on it" still come from the merge-base range.

Files changed: `src/scribe/check.py`, `src/scribe/cli.py`, `src/scribe/gitutil.py`, `README.md`;
`tests/test_check.py`; this report.

### What was wrong (04b-codex-validation.md V3, 06-validation-triage.md Batch B row V3)

`check_range` read records, attestations and the index off the working tree, so an uncommitted
change under `docs/decisions` could mask or fake the committed range's result. Separately, an
earlier fix (I43) had substituted the merge base for the target ref itself when asking whether a
record's predecessor was ratified, which loses a ratification landed on the target branch after
the feature branch forked. Both are now fixed without building the full revision-backed store
V3 also describes as the long-term direction (deferred, effort L).

### Changes

- `gitutil.is_dirty(pathspec, cwd)`: true when `git status --porcelain -- <pathspec>` reports
  anything. New helper; nothing existing called `git status` before.
- `check.run_check` now takes `allow_dirty: bool = False` and, unless set, refuses to run
  (exit 1, one clear stderr-equivalent line naming `docs/decisions` and `--allow-dirty`) when
  `gitutil.is_dirty(DECISIONS_DIR, store.root)` is true. The guard runs before the "unknown base
  ref" check, so a dirty ledger is always reported first regardless of what `--base` names.
- `check.check_range` and `check._supersede_gate`: `changed_paths` and `commits` are now computed
  from `fork_point` (the merge base) rather than the literal `base` ref, matching "branch delta"
  semantics. The predecessor-was-ratified check inside `_supersede_gate` (renamed parameter
  `base_tip` for clarity) now receives the literal `base` ref instead of `fork_point`, so
  `_was_ratified_at_base` asks the target's current tip, not the fork point.
- `cli.py`: new `--allow-dirty` flag on the `check` subcommand (`store_true`, dest `allow_dirty`),
  threaded into `run_check`.
- `README.md`: the `check --base <ref>` CLI table row now documents `[--allow-dirty]` and the
  dirty-ledger refusal in one sentence. `scribe-check.yml` was not touched: CI checkouts are
  clean, so the flag has nothing to do there, matching the item's own instruction.

### Tests, with the assertion that fails on the old code

- `test_a_dirty_ledger_is_refused`: an untracked file under `docs/decisions` must produce exit 1
  with `docs/decisions`, `uncommitted changes` and `--allow-dirty` all in the output; the old
  code had no such guard and would have printed `scribe check: ok`.
- `test_a_dirty_ledger_is_allowed_with_the_flag`: the same dirty state with `--allow-dirty` must
  still print `scribe check: ok`; guards against over-tightening the new check.
- `test_dirty_changes_outside_docs_decisions_do_not_block_the_check`: a dirty file under `src/`
  must not trip the guard; confirms the pathspec is scoped to `docs/decisions`, not the whole
  worktree.
- `test_a_ratification_added_to_the_target_after_the_fork_is_honoured`: builds a predecessor
  record that is unreviewed at the fork point, forks `feat`, adds an unreviewed successor that
  supersedes it, then ratifies the predecessor on `main` (the target) after the fork. The check
  on `feat` against `--base main` must fail with `<successor> supersedes ratified <predecessor>`.
  Old code asked `_was_ratified_at_base` against the merge base, which predates the ratification,
  so the predecessor never looked ratified and the check passed incorrectly.

All four are new; no existing test encoded the defect, so none needed correcting.

### Suite

`uv run pytest -q` -> 393 passed, 3 skipped (389 baseline + 4 new). `uv run scribe lint`,
`uv run scribe index --check`, `uv run scribe validate docs/decisions`, and
`uv run scribe check --base 3a5b1d2` (run from this worktree, whose own `docs/decisions` is
clean) all exit 0. The em-dash and en-dash scan over the whole worktree prints nothing.
`git diff --check` is clean.

### Proposed commit message

```
fix: Refuse a dirty ledger and honor the base ref's tip in scribe check

scribe check --base now exits 1 with a clear message when docs/decisions
has uncommitted changes, unless --allow-dirty is given, so a dirty
working tree cannot mask or fake a committed result. The
predecessor-was-ratified question is now asked against the base ref's
own tip rather than the merge base, so a ratification landed on the
target branch after this branch forked is honored; changed paths and
commits for "introduces or depends on it" still come from the
merge-base range.
```

## I-lines (renumbered by the main session; kept as I-V3-N here)

- I-V3-1: Implemented the cheap interim exactly as the owner specified in 06-validation-triage.md
  (refuse-if-dirty plus `--allow-dirty`), not the revision-backed store V3 also describes. The
  triage doc marks the store "effort L" and defers it; nothing in this item's instructions asked
  for it.
- I-V3-2: The dirty guard is scoped to `docs/decisions` only (`git status --porcelain --
  docs/decisions`), not the whole working tree, so unrelated in-progress code changes elsewhere
  in the repo cannot block `scribe check`. This is the literal pathspec the item specifies and
  matches `DECISIONS_DIR` already used elsewhere in `check.py`.
- I-V3-3: The dirty-ledger guard runs before the "unknown base ref" check in `run_check`, so a
  dirty ledger is reported even when `--base` also happens to be wrong. No test exercises both
  conditions at once; this is a reasonable but arbitrary ordering choice worth flagging.
- I-V3-4: Fixing the base-tip question uncovered a second, related inconsistency: `changed_paths`
  and `commits` were already computed from the literal `base` ref, not `fork_point`, at the top of
  `check_range`. For `diff_names` this made no practical difference (its `base...head` three-dot
  call is merge-base-scoped internally regardless of which ref is passed), but `rev_list_range`'s
  two-dot `base..head` is not automatically merge-base-scoped. Per the item's own wording ("changed
  paths and commits still come from the merge-base range"), both are now explicitly passed
  `fork_point`. No test distinguishes this from passing `base` directly, since a diverged target
  with genuinely different two-dot vs. merge-base commit lists was not constructed; flagging this
  as untested-by-difference rather than claiming a regression test proves it.
- I-V3-5: Renamed `_supersede_gate`'s second parameter from `base` to `base_tip` to make the
  base-ref-vs-fork-point distinction visible at the call site rather than only in the docstring.
  Pure rename, no behavior change beyond what is described above.
- I-V3-6: Did not add or change anything in `src/scribe/templates/scribe-check.yml`, per the
  item's own instruction that CI checkouts are clean and therefore never need `--allow-dirty`.
- I-V3-7: V6 (`record_deleted` in `_deleted_record_reasons`) and V5 (whole-ledger validation in
  `_validate_all_records` and `_attestation_integrity`) were read but not modified; both still
  pass under the full suite run above.

## Remaining

Nothing remaining for this item. The full revision-backed store (reading records/attestations/
index from the git tree of the tip being checked, rather than disk) remains out of scope per the
owner's own cheap-interim call and is not implemented here.
