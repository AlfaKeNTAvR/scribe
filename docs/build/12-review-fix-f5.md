# Fix F5: `scribe check` must not pass vacuously on a git failure

Fixes the gap logged in the (unmerged) `docs/build/11-fable-final-review.md`, Batch B,
V3 partial, point (b): "Codex's 'git range failures must produce explicit check
failures' is untouched: `diff_names`, `rev_list_range` and `tree_record_paths`
return `[]` on a git error and a `merge_base` failure silently falls back to
`base`, so a bad ref or a shallow CI clone can make the historical rules pass
vacuously." Extended mid-task (see I-F5-6) to a fifth helper, `gitutil.is_dirty`,
per an independent Codex review of the same commits.

## What changed

- `src/scribe/gitutil.py`: added `GitError`, and a `strict: bool = False`
  keyword-only parameter to `merge_base`, `diff_names`, `rev_list_range`,
  `tree_record_paths` and `is_dirty`. Default `strict=False` is byte-identical
  to the old behaviour (empty list / `None` / "not dirty" on a failed git
  call); `strict=True` raises `GitError("<what>", result)` instead, whose
  `str()` is already `git failed while computing <what>: <stderr first
  line>`.
- `src/scribe/check.py`, `check_range`: computes `fork_point`, `changed_paths`,
  `commits`, `base_record_paths` and `head_record_paths` inside one
  `try/except gitutil.GitError` block, all with `strict=True`. On failure it
  returns `[str(exc)]` immediately, before any of the git-independent rules
  (2, 3, 4b) run.
- `src/scribe/check.py`, `run_check`: the dirty-ledger probe
  (`gitutil.is_dirty(..., strict=True)`) is now itself wrapped in a
  `try/except gitutil.GitError`, returning `[str(exc)]` on failure instead of
  treating a failed `git status` as "clean" and proceeding.
- `src/scribe/check.py`, `_deleted_record_reasons`: signature changed from
  `(store, base)` to `(root, base, base_paths, head_paths)`, the two
  `tree_record_paths` calls it used to make internally moved up into
  `check_range`'s shared strict block (see I-F5-4).
- `README.md`: one sentence added to the `check --base` row: a git failure
  during the check is itself a failure, never a pass.

## Shape chosen and why

A `strict` parameter on the existing helpers, rather than parallel `_or_raise`
functions or a wrapper module. `relink`, `lint`, the git hooks, and
`history_check`'s own internal calls never pass `strict`, so they keep their
exact old fail-open behaviour with a zero-line diff to their call sites. One
exception type (`GitError`) whose message is built once, at the raise site,
in the exact "git failed while computing `<what>`: `<stderr first line>`"
format the gap asked for, so `check.py`'s handlers are a plain `str(exc)`
with no per-call-site message assembly. See I-F5-1 and I-F5-2.

## Decisions

- **I-F5-1**: `strict: bool = False` on the affected `gitutil` functions
  (additive, keyword-only), not new `_strict` functions or a separate strict
  module. Keeps the diff small and the tolerant contract for `relink`,
  `lint`, the git hooks and `history_check` unchanged by construction (they
  never pass the new argument).
- **I-F5-2**: One `GitError` class, not one exception per helper. Its
  `__init__` takes the already-run `CompletedProcess` and builds the final
  message immediately, so every strict call site in `check.py` just needs
  `except gitutil.GitError as exc: return [str(exc)]`.
- **I-F5-3**: `check_range` computes all five range-dependent values (fork
  point, changed paths, commits, both record-path sets) inside one
  `try/except`, and returns a single-element reason list immediately on any
  failure, rather than mixing that reason in with the git-independent rules
  (validate-all-records, index-stale, attestation-integrity). Without a valid
  range, rules 1, 5 and 6 cannot be evaluated meaningfully at all, so
  reporting them alongside a git failure would be misleading; this also
  matches the gap's own wording, "turn any failure into one explicit reason
  line."
- **I-F5-4**: `_deleted_record_reasons` no longer takes `store` and computes
  its own `tree_record_paths` calls; it takes precomputed `base_paths` /
  `head_paths` instead. This lets `check_range` compute both path sets once,
  strictly, and reuse `base_record_paths` for rule 5 too (passed through
  `check_records_against_base`'s existing `paths=` parameter) instead of that
  function re-deriving them tolerantly on its own, which would have left a
  second, unguarded `tree_record_paths` call on the check path.
- **I-F5-5**: `merge_base` also got the `strict` parameter, even though its
  `Optional[str]`-return contract already unambiguously signals failure
  (unlike the `[]`-returning helpers, where empty is ambiguous with "really
  empty"). Reason: `check.py` is `merge_base`'s only caller, and without
  `strict` there is no way to surface git's stderr in the failure message,
  which would make the merge-base failure line inconsistent in shape with
  the other four. Uniformity across all five failure messages won over
  leaving `merge_base`'s contract untouched.
- **I-F5-6** (added mid-task, from a second review pass): `gitutil.is_dirty`
  has the same vacuous-pass shape as the three named helpers, a failed `git
  status` has empty stdout, so the tolerant form reads it as "clean", and
  `run_check` used it un-guarded right before the range computation. Gave it
  the identical `strict` treatment and wrapped its one call site in
  `run_check` the same way. `is_dirty` has exactly one caller in the whole
  tree (`check.py`), so this changes no other behaviour.
- **I-F5-7** (methodology, not a design call): every new or changed
  assertion in `tests/test_check.py` was verified to fail against the
  pre-fix code, not just reasoned about, by temporarily swapping in
  `git show HEAD:src/scribe/check.py` and `git show HEAD:src/scribe/gitutil.py`
  (the commit this fix branches from), rerunning just the new tests, and
  restoring the fixed files afterward. No commits, stashes or index changes
  were made to do this; see the assertions listed below.

## Tests

`tests/test_gitutil.py` (contract tests, both pass on the fix; neither is
expected to fail on the old code since they test the *new* `strict`
parameter's existence):

- `test_diff_names_tolerant_form_still_returns_empty_list_on_git_failure`:
  the default (no `strict`) form still returns `[]` on a bad ref, confirming
  `relink`/`lint`/the git hooks keep their old fail-open behaviour.
- `test_diff_names_strict_form_raises_on_git_failure`: `strict=True` raises
  `GitError` matching `"git failed while computing"`.

`tests/test_check.py` (each verified to fail on the pre-fix `check.py` /
`gitutil.py`, per I-F5-7):

- `test_a_git_failure_computing_the_range_fails_the_check` (task item 3a): a
  fake `_git` fails only `git diff ...` (the `diff_names` call) with a
  non-zero return and `"fatal: bad object deadbeef"` on stderr, against a
  branch that also carries an otherwise-failing unreviewed-successor case.
  **Fails on old code at `assert code == 1`**, the old code got `0` because
  `diff_names` swallowed the failure into `[]`, so `_supersede_gate` saw no
  changed paths and passed.
- `test_a_merge_base_failure_fails_the_check_instead_of_falling_back_to_base`
  (task item 3b): a fake `_git` fails only `git merge-base ...`. **Fails on
  old code at the `stdout.strip() ==` assertion**, the old code's `or base`
  fallback silently substituted `base` for the fork point, so the check
  still ran (and still failed, but on the unrelated supersede-gate reason,
  not on the merge-base failure) instead of reporting the git failure.
- `test_a_dirty_check_failure_fails_the_check_instead_of_reading_clean`
  (I-F5-6's test): a fake `_git` fails only `git status ...`. **Fails on old
  code at `assert code == 1`**, the old code got `0` because a failed `git
  status` has empty stdout, which `is_dirty`'s `bool(result.stdout.strip())`
  read as "not dirty".
- Happy path (task item 3c): no new test added, already covered by the
  existing `test_a_plain_unreviewed_record_passes` and
  `test_ratifying_the_successor_makes_the_check_pass`, both still passing
  unchanged, plus the manual `scribe check --base 3a5b1d2` run below.

## Verification

- `uv run --frozen pytest -q tests/test_check.py tests/test_gitutil.py -p no:cacheprovider`:
  35 passed.
- `uv run --frozen pytest -q -p no:cacheprovider` (full suite): **429 passed,
  3 skipped in 130.77s**.
- `git diff --check`: clean.
- The em and en dash scan over src, tests and README: no matches.
- `uv run --frozen scribe check --base 3a5b1d2` in this worktree: prints
  `scribe check: ok` (unchanged).

## Proposed commit

```
fix: Make scribe check fail explicitly on any git failure

`scribe check` returned `scribe check: ok` when `merge_base`, `diff_names`,
`rev_list_range`, `tree_record_paths` or `is_dirty` hit a git error, because
each read the failure as an empty range or a clean ledger instead of an
error. Give each helper a `strict` form that raises `GitError` instead, and
have `check.py` turn that into one explicit failure reason; the git hooks
and `scribe lint` keep calling the tolerant (default) form unchanged.
```
