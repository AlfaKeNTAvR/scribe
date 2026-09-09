# Batch F3: index backtracked defect and pytest verify target validation

Fixes two defects from the review pass (`11-fable-final-review.md` "New defects"
items 3 and 4, "Pytest verify engine" section), plus five follow-up defects
Codex found in the same lint/schema area while this fix was in flight. All
work is in the worktree `/home/alfakentavr/scribe-wt/f3`
(`nikita/fix/review-f3-index-and-verify-target`, base `c7dbf0f`); nothing is
committed.

## Defect A: a ratified `backtracked` record vanished from INDEX.md

**Files:** `src/scribe/index.py`, `tests/test_index.py`.

`_retired_state` (index.py) classifies every record as Active, Retired, or
neither. It already returned a reason for `expired` and `superseded`, but not
for `backtracked`: a record with `effective_state: backtracked` and no
successor fell through to `None` (not Retired), and separately failed
`Store.effective_authority` (which requires `effective_state` in `{proposed,
implemented}`, so it's never Active either). The record appeared in neither
section.

Fix: `_retired_state` now returns `"backtracked"` for a `backtracked` record
with no effective successor, so it lands in Retired with that reason, the
same way `expired` does. No change to `Store.effective_authority` or to the
Bash gate / injection hook that consume it: those correctly keep treating a
backtracked record as not currently authoritative.

**`scribe lint`'s own `ACTIVE_STATES`** (`src/scribe/lint.py`, a local
constant `{"proposed", "implemented", "backtracked"}`, distinct from the
index's classification) was checked and left unchanged. Its docstring says
it is deliberately state-based, not `effective_authority`-based, because the
lifecycle smells it feeds (`review_overdue`, `unreviewed_implemented`) must
still fire on records nobody has ratified yet, backtracked ones included.
That is a different question from "does this record appear in INDEX.md
Active", and the two do not contradict each other.

**Test:** `tests/test_index.py::test_backtracked_record_appears_in_retired_not_vanished`
Builds a store with one ratified, backtracked record and no successor.
Assertion that fails on the old code: `retired == ["D-260905-backtracked | backtracked | ratified | human | Title of D-260905-backtracked."]`
comes back as `retired == []` on old code (confirmed by reverting the fix and
rerunning: `AssertionError: assert [] == ['D-260905-ba...backtracked.']`).

## Defect B: `scribe lint` ran pytest verify entries the validator rejects

**Files:** `src/scribe/lint.py`, `src/scribe/schema.py`, `tests/test_lint.py`,
`tests/test_schema.py`, `README.md`.

`_run_pytest_verify_entry` (lint.py) only checked that `target` was a
non-empty string, then spawned `uv run --frozen pytest -q -x <target>`
directly. `schema._validate_pytest_target` (now public, `validate_pytest_target`)
already rejects options, `..`, and absolute paths, so a record with
`target: "--version"` made `scribe validate` report `invalid_verify` while
`scribe lint` ran `pytest --version` for real, got exit 0, and reported the
entry as passed.

### Fix (original scope)

- `validate_pytest_target` (renamed from `_validate_pytest_target`, no
  leading underscore, so `lint.py` can import and reuse it: see I-F3-1) is
  now the single place that decides what a pytest verify target may be.
- `lint.py` adds `_pytest_target_problem(target, store)`, a thin adapter that
  calls `validate_pytest_target` with a callback collecting its first
  message, and `_run_pytest_verify_entry` calls it before doing anything
  else. A rejected target returns a `verify_error` Finding and never reaches
  `subprocess.Popen`.
- The pytest command now passes `-p no:cacheprovider`, so linting leaves no
  `.pytest_cache` in the linted repository.

### Fix (Codex follow-up items folded in)

1. **Option-shaped targets** (`--help`, `--version`): `validate_pytest_target`
   now also rejects a target whose path segment starts with `-` (a leading
   dash reads as a pytest option, not a node id, even if a file by that
   literal name exists on disk). The command line also puts `--` immediately
   before `<target>`, a second, independent layer.
2. **Verify runs on already-invalid records**: `lint_store` now collects the
   relative paths of every record with an existing validate error (severity
   `error`) and passes that set into `_verify_findings`, which skips those
   records entirely (see I-F3-4 for why "skip silently" rather than "skip and
   report").
3. **Crash on non-string `engine`/`severity`**: `[]` is unhashable, so
   `engine not in {"grep", "pytest"}` (schema.py) and `severity not in
   {"error", "warning"}` (lint.py, both verify runners) raised `TypeError`
   instead of reporting a finding. Both now check `isinstance(..., str)`
   first, matching the existing `_in_str_set` pattern schema.py already uses
   elsewhere.
4. **`SCRIBE_VERIFY_TIMEOUT` accepted `nan`/`inf`/zero/negative**:
   `_verify_timeout_seconds` now falls back to the 60 second default unless
   the parsed value is finite and positive.
5. **Timeout only killed the direct child**: `_run_pytest_verify_entry` now
   uses `subprocess.Popen(..., start_new_session=True)` (POSIX only) instead
   of `subprocess.run`, so `uv run ... pytest ...` and everything it spawns
   share one process group; on `TimeoutExpired`,
   `_kill_verify_process_group` sends `SIGKILL` to that whole group via
   `os.killpg`, falling back to killing just the direct child on Windows
   (where `os.killpg` does not exist).

### Tests

- `tests/test_schema.py::test_pytest_verify_entry_rejects_a_target_starting_with_an_option_dash`
  Fails on old code: a file literally named `--help` at the repo root passed
  every prior check, so `problems` came back `set()` instead of containing
  `invalid_verify`.
- `tests/test_schema.py::test_verify_entry_with_a_non_string_engine_is_rejected_without_crashing`
  Fails on old code with `TypeError: unhashable type: 'list'` raised out of
  `validate_record`, instead of a clean `unknown_engine` finding.
- `tests/test_lint.py::test_a_pytest_target_with_an_option_never_runs_pytest`
  and `test_a_pytest_target_with_an_absolute_path_never_runs_pytest`
  Fail on old code on the monkeypatched `subprocess.Popen` guard's own
  assertion (`"scribe lint must not spawn pytest for a rejected target"`):
  old code spawns pytest for these targets regardless of the pre-existing
  `invalid_verify` from validate.
- `tests/test_lint.py::test_a_valid_pytest_target_still_runs_and_leaves_no_pytest_cache`
  Fails on old code on `assert not (lint_repo / ".pytest_cache").exists()`:
  old code's command had no `-p no:cacheprovider`.
- `tests/test_lint.py::test_lint_skips_verify_for_a_record_with_an_existing_validate_error`
  Fails on old code the same way as the two "never runs pytest" tests above
  (`_verify_findings` ran unconditionally, before the skip-set existed).
- `tests/test_lint.py::test_a_verify_entry_with_a_non_string_severity_does_not_crash`
  and `test_a_pytest_verify_entry_with_a_non_string_severity_does_not_crash`
  Call `_run_verify_entry` / `_run_pytest_verify_entry` directly (see
  I-F3-5). Fail on old code with `TypeError: unhashable type: 'list'`.
- `tests/test_lint.py::test_verify_timeout_env_var_rejects_nan_and_falls_back_to_the_default`
  Fails on old code: `_verify_timeout_seconds()` returns `nan` instead of
  `60.0`.
- `tests/test_lint.py::test_verify_timeout_env_var_rejects_infinity_and_zero_and_negative`
  Fails on old code for each of `inf`, `-inf`, `0`, `-5`: each comes back
  verbatim instead of `60.0`.
- `tests/test_lint.py::test_a_timed_out_pytest_verify_entry_leaves_no_grandchild_process`
  A pytest test that spawns its own `sleep 30` grandchild and writes its pid
  to a file, verified with `SCRIBE_VERIFY_TIMEOUT=8`. Fails on old code on
  `os.kill(grandchild_pid, 0)` not raising `ProcessLookupError`: old code's
  `subprocess.run(..., timeout=...)` kills only the direct `uv` child, so the
  grandchild `sleep` is still alive after lint returns. Run 3 times in
  isolation plus once inside the full suite, all stable (see I-F3-6 on the
  timeout value chosen).
- `README.md`: added one sentence to the verify-engines paragraph stating
  that lint refuses a target the validator would reject and skips verify on
  a record with an existing schema error, and updated the shown command to
  include `-p no:cacheprovider -- <target>`.

## Suite

- `uv run --frozen pytest -q -p no:cacheprovider tests/test_index.py
  tests/test_lint.py tests/test_schema.py`: 69 passed.
- Full suite `uv run --frozen pytest -q -p no:cacheprovider`: **436 passed,
  3 skipped** in ~102s.
- `git diff --check`: clean.
- The em and en dash scan over src and tests: no matches.

## Decisions (I-F3-N)

1. **I-F3-1**: Renamed `schema._validate_pytest_target` to
   `schema.validate_pytest_target` (dropped the leading underscore) instead
   of adding a second copy of the rule or importing the private name across
   modules. This codebase has no existing precedent for one module importing
   another's underscore-prefixed helper (checked: only `Problem`, `KEYS`,
   `validate_record` cross `schema.py`'s boundary elsewhere), and the task
   explicitly asked for "no duplicate rule text."
2. **I-F3-2**: `_retired_state` reports the reason as the literal string
   `"backtracked"`, matching the existing pattern where `expired` reports
   `"expired"` (not a longer phrase). Consistent with the reviewer's
   suggestion in the defect description.
3. **I-F3-3**: Left `03-plan-v2.md` section 3.5 rule 2 alone even though its
   literal text ("Active = ... `effective_state in (proposed, implemented,
   backtracked)` ...") still lists `backtracked` as Active. That line
   predates `effective_authority` (commit `3050f09`) gating Active on
   ratification; per the task's explicit instruction, backtracked now goes
   to Retired instead. Not updating the plan doc's prose since the task
   scope was the code fix and its tests, not a plan-doc rewrite; flagging
   here in case a documentation pass is wanted later.
4. **I-F3-4**: Chose "skip silently" over "skip and add a second finding"
   for Codex item 2 (verify entries on records with an existing validate
   error). The record already has its problem reported once via
   `_validate_findings`; a second `verify_error` for the same root cause
   (a bad target, wrong key set, etc.) would be redundant noise without new
   information.
5. **I-F3-5**: A side effect of I-F3-4: any target the pytest runner's own
   `_pytest_target_problem` would reject is, by construction (same shared
   function, same `store`), also always rejected by `validate_record` first
   in the `scribe lint` flow, so the skip added for item 2 means the
   runner's own check is unreachable through the public `scribe lint`/CLI
   surface for that specific failure mode; it only actually fires for a
   caller that invokes `_run_pytest_verify_entry` without first validating.
   To still prove those specific lines are correct (not just consistent with
   the skip), three tests (`test_a_verify_entry_with_a_non_string_severity_does_not_crash`,
   `test_a_pytest_verify_entry_with_a_non_string_severity_does_not_crash`)
   call the private `_run_verify_entry` / `_run_pytest_verify_entry`
   functions directly, departing from this test file's established
   convention of testing only through the public `run_lint`/CLI surface.
   The two `--version`/absolute-path CLI-level tests were updated to assert
   on `invalid_verify` (from validate) with `verify_error` absent, rather
   than the originally-planned `verify_error`, to match this final,
   consistent behavior.
6. **I-F3-6**: The process-group-kill test
   (`test_a_timed_out_pytest_verify_entry_leaves_no_grandchild_process`)
   needed `SCRIBE_VERIFY_TIMEOUT=8`, not a tight value like 2: a full
   suite run flaked once at `timeout=2` because `uv run --frozen pytest`
   startup overhead alone exceeded 2 seconds under load, killing the process
   before the grandchild was ever spawned. Re-verified stable at
   `timeout=8` across 3 isolated runs and one full-suite run. Kept the test
   rather than dropping it, since it is the only test that actually proves
   the process-group kill reaches a grandchild.
7. **I-F3-7**: `lint.py`'s `ACTIVE_STATES`/`_is_active` (used for
   `review_overdue` and `unreviewed_implemented`) was left unchanged after
   reading its docstring: it is deliberately state-based, not
   `effective_authority`-based, so it can still catch lifecycle smells on
   records nobody has ratified. No contradiction with the index fix (Defect
   A), which is about which section a record's line appears in, not whether
   lint should warn about it.

## Proposed commits

Two commits, matching the file split above (README.md's one sentence rides
with the lint/schema commit since it documents that behavior).

**Commit 1** (Defect A): `src/scribe/index.py`, `tests/test_index.py`

```
fix: Show backtracked records in the decision index

A ratified record whose effective_state is backtracked matched neither
the Active nor the Retired branch of render_index, so it silently
vanished from INDEX.md. _retired_state now reports "backtracked" for
such a record, the same way it already does for expired, so every
record appears in the index exactly once.
```

**Commit 2** (Defect B): `src/scribe/lint.py`, `src/scribe/schema.py`,
`tests/test_lint.py`, `tests/test_schema.py`, `README.md`

```
fix: Validate pytest verify targets before spawning them

scribe lint ran a verify entry's engine: pytest target through a real
pytest subprocess after checking only that it was a non-empty string,
so a target like "--version" that the schema validator already
rejects still spawned pytest and, since --version exits 0, was
reported as passed. The pytest runner now reuses the schema's own
target rule before spawning anything, passes -p no:cacheprovider and
a -- separator, skips verify entirely for a record that already has a
schema error, rejects option-shaped targets, type-checks engine and
severity before a set-membership test, rejects a non-finite or
non-positive SCRIBE_VERIFY_TIMEOUT, and kills the whole process group
(not just the direct child) on a timeout.
```
