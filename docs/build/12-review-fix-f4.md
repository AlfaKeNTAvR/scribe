# Closing three 11-fable-final-review gaps (f4)

Worktree /home/alfakentavr/scribe-wt/f4, branch nikita/test/review-f4-test-gaps-and-trailer, base c7dbf0f.
Read docs/build/11-fable-final-review.md (only present in the main /home/alfakentavr/scribe checkout, not
in this worktree) for "08-review follow-ups" and "New defects" items 5, 6, 7.

## Gap 1 (New defects item 6): supervisor impersonation test did not exercise the token fix

File: `tests/test_supervise.py`, function `test_traceback_marker_impersonation_is_fail_open`.

The old fake `uv` printed `RuntimeError: [scribe-deny]` on one line. That line was never an exact
match for the pre-3050f09 `DENY_MARKER = "[scribe-deny]"` (whole-line list membership, not substring),
so the old code already handled it correctly by accident; the test could not tell old code from new.

Change: the fake `uv` now prints two bare lines, `[scribe-deny]` and `[scribe-deny wrongtoken]`
(no backticks, per the fake-uv-on-PATH note), then exits 1. Assertion unchanged: `result.returncode == 0`.

Verified against `git show 3050f09^:hooks/supervise.py` (pre-fix): the bare `[scribe-deny]` line is an
exact whole-line match for the old literal `DENY_MARKER`, so the old code treats it as `deliberate=True`
and forwards `completed.returncode` (1) unchanged. Failing assertion on old code:
`assert result.returncode == 0` -> `AssertionError: assert 1 == 0`.
Passes on current `hooks/supervise.py` (token-based marker never matches a bare or wrong-token line).

## Gap 2 (New defects item 7): no regression test for the P2 state-lock false-deny fix

File: `tests/test_hook_gate.py`, new function
`test_exit_plan_mode_allows_with_pending_decision_despite_held_state_lock`.

`plan_verdict` (src/scribe/hooks/pre_tool_use_gate.py) was fixed in 3050f09 to read `pending` from the
state `update_state` returns rather than from the `mutate` closure, which never runs when the lock times
out. `update_state`'s "return `load_state` on timeout" behavior in src/scribe/state.py predates 3050f09
and was not itself changed.

Test: seed a session's `pending_decisions` (unlocked, like the existing
`test_exit_plan_mode_allows_with_pending_decision_but_still_flags`), then hold the real `state.json.lock`
with `fcntl.flock` across a real `LOCK_TIMEOUT_S = 2.0 s` timeout (same pattern
`tests/test_state.py::test_posix_contention_drops_state_update` uses, but without monkeypatching the
timeout because the hook runs in a subprocess via the `run_hook` fixture and can't see a patched
module constant). Runs the gate under `SCRIBE_GATES=enforce` on the ExitPlanMode fixture. Asserts the
verdict is allow (`returncode == 0`, log entry `verdict == "allow"`) and that the call returns in
bounded time (`elapsed < 5.0`, actual ~2.1 s, i.e. the lock timeout plus a small margin, not a hang).

Decision I-F4-1: the task text says "run the gate on a command that a ratified record authorizes" and
"find an existing authorized-command test to copy the setup." Only `plan_verdict` ever calls
`update_state`; the Bash/PowerShell denylist path (`command_verdict` / `action_is_ratified`) never
touches state.json, so a ratified-record Bash test cannot distinguish old from new code under lock
contention by construction. I read "authorizes" as the general concept (an existing authorization
already present, ratified record for a command or pending decision for a plan) and modeled the new test
on `test_exit_plan_mode_allows_with_pending_decision_but_still_flags` instead, since that is the only
existing test whose setup actually exercises the P2 code path.

Verified against `git show 3050f09^:src/scribe/hooks/pre_tool_use_gate.py` (pre-fix): `pending` is
initialized to `[]` and only extended inside `mutate`, which never runs when the lock times out; the
discarded `update_state(...)` return value carried the on-disk pending decisions but the old code never
looked at it. Failing assertion on old code: `assert result.returncode == 0` ->
`AssertionError: assert 2 == 0` (false deny under enforce).

## Gap 3 (New defects item 5): duplicate Decision: trailer

Files: `src/scribe/githooks/prepare_commit_msg.py` (new function `already_trailed`, called from `run`),
`tests/test_githooks.py` (two new tests).

`add_trailer_to_file` (src/scribe/gitutil.py) uses `git interpret-trailers --if-exists addIfDifferent`,
which compares the literal trailer text. An alias-only trailer the author typed by hand and the
`alias ULID` form `prepare_commit_msg.run` is about to add are different text for the same record, so
both landed on 27aefbe. Fix is entirely in `prepare_commit_msg.py`, not in `gitutil.py`: before adding a
candidate's trailer, `already_trailed` re-reads the message file's existing `Decision:` trailers and
resolves them through the store, reusing `commit_msg.decision_values` and `commit_msg.resolve_trailers`
rather than duplicating that logic. If any existing trailer already resolves to the candidate record
(by id, not by object identity, since `Store.resolve` may return distinct `Record` instances across
calls), the candidate is skipped and the human's trailer is left untouched; `gitutil.add_trailer_to_file`
was not changed.

Two new tests in `tests/test_githooks.py`:
- `test_alias_only_trailer_already_naming_the_record_gets_no_second_trailer`: commits a message that
  already carries `Decision: <alias>` for the record being staged; asserts exactly one `Decision:` line
  survives, unchanged.
- `test_a_different_existing_alias_still_gets_the_pending_trailer_appended`: commits a message carrying
  `Decision: <alias-of-an-unrelated-existing-record>`; asserts both trailers end up present (the
  unrelated one untouched, the new record's `alias ULID` appended), guarding against `already_trailed`
  over-suppressing.

Verified against `git show HEAD:src/scribe/githooks/prepare_commit_msg.py` (pre-fix, i.e. this
worktree's base c7dbf0f, since this bug predates and is unrelated to 3050f09): committing with the
alias-only trailer already present produces two `Decision:` lines. Failing assertion on old code:
`assert trailer_lines(message, "Decision") == [f"Decision: {alias}"]` ->
`AssertionError`, left side had the extra `Decision: D-260909-hook-test-record 01M241H78NSMZ7Q2DQ578V709P`
line.

## Decisions log

- I-F4-1: see Gap 2 above (which existing test the "authorized" setup phrase maps to).
- I-F4-2: compared records by `str(record.data.get("id"))` equality in `already_trailed` rather than by
  Python object identity (`is`), since `Store.resolve` is not guaranteed across all call sites to return
  the same cached `Record` instance; id equality is the correct and simpler invariant.
- I-F4-3: `already_trailed` re-reads the message file fresh on every loop iteration in `run` (via
  `decision_values`) rather than accumulating already-added ids in a local set, so a trailer added
  earlier in the same `run` call for a different candidate is also visible to later iterations. This
  costs one extra `git interpret-trailers`-adjacent file read plus a `parse_trailers` call per
  candidate, negligible next to the `add_trailer_to_file` subprocess it guards.
- I-F4-4: the gate-lock test (Gap 2) uses the real 2.0 s `LOCK_TIMEOUT_S` rather than monkeypatching it
  down, because `run_hook` drives the hook through a subprocess (`python -m scribe hook gate`) that does
  not see this process's monkeypatched module attributes. This adds about 2 s to the suite.
- I-F4-5: the project's PostToolUse edit hook reformats whole files on save (line width), so the diffs
  for `tests/test_hook_gate.py` and `tests/test_supervise.py` also reflow a few pre-existing lines
  (parametrize/def wrapping) that this task did not otherwise touch. No behavior change; called out here
  since CLAUDE.md asks for tradeoffs to be surfaced even when small.

## Suite

- `tests/test_supervise.py tests/test_hook_gate.py tests/test_githooks.py`: 138 passed.
- Full suite `uv run --frozen pytest -q -p no:cacheprovider`: 427 passed, 3 skipped in 131.60 s. No
  rerun of `tests/test_timing.py` needed; it was not flaky this run.
- `git diff --check`: clean.
- `rg` for em dash and en dash characters across src tests hooks: no matches.

## Proposed commits

Files for the `test:` commit (gaps 1 and 2, no production code changed):
- `tests/test_supervise.py`
- `tests/test_hook_gate.py`

Message:
```
test: Make the two follow-up regression gaps from 11-fable-final-review bite

The impersonation test's fake uv printed the deny marker embedded in a
longer traceback line, which the pre-3050f09 whole-line comparison
already ignored, so the test passed on both the broken and fixed
supervisor. It now prints a bare `[scribe-deny]` line and a
`[scribe-deny wrongtoken]` line, which the token fix must both reject.
Also adds the missing gate-level regression test for the P2 state-lock
false deny: holding state.json.lock past its 2 s timeout while an
already-authorized ExitPlanMode call runs must still allow, not deny.
```

Files for the `fix:` commit (gap 3):
- `src/scribe/githooks/prepare_commit_msg.py`
- `tests/test_githooks.py`

Message:
```
fix: Skip a Decision trailer already present under another form

`add_trailer_to_file` compares trailer text verbatim, so an alias-only
Decision trailer the author typed by hand did not stop
prepare-commit-msg from adding a second `alias ULID` trailer for the
same record (both landed on 27aefbe). prepare-commit-msg now resolves
every existing Decision trailer through the store before adding one,
reusing commit_msg's trailer-resolution helper, and skips a record
already present under either form without rewriting the human's
trailer.
```

DONE: 427 passed, 3 skipped
