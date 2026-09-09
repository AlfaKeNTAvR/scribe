# Batch B, item 4 (V19)

## Item 4 (V19)

V19, "no cap, prune on expiry". `newrecord._register` was capping a session's
`pending_decisions` at `RECORDS_WRITTEN_CAP` (20), the same constant used for
`records_written`, even though the plan (section 4.9) only caps
`records_written`. Past the 20th pending id, `push_recent` silently dropped
the oldest ones, so a busy session could lose an id before the commit that
should have consumed it ever ran.

Fix: `state.push_recent` now takes `cap: int | None`; `None` returns the
deduplicated, most-recent-first list untouched. `newrecord._register` passes
`cap=None` for `pending_decisions` and keeps `RECORDS_WRITTEN_CAP` for
`records_written`. An id now leaves `pending_decisions` only through
`post_commit.consume_pending` (a commit whose changed paths match the
record's `affects`) or through `state.prune_sessions`'s existing 7-day
session expiry; nothing else removes it. Updated the code comments on both
functions to state this and to correct the stale plan attribution (the cap
was never specified for pending ids).

Files changed:
- `src/scribe/state.py`: `push_recent` accepts `cap: int | None`; docstring
  corrected.
- `src/scribe/newrecord.py`: `_register` no longer applies `RECORDS_WRITTEN_CAP`
  to `pending_decisions`; docstring corrected.
- `tests/test_state.py`: added `test_push_recent_with_no_cap_keeps_every_item`.
- `tests/test_githooks.py`: added
  `test_pending_decisions_has_no_cap_and_all_survive_as_trailer_candidates`
  (imports `prepare_commit_msg`).

Test names and the assertion that fails on the old code:
- `tests/test_state.py::test_push_recent_with_no_cap_keeps_every_item` -
  `push_recent(list(range(30)), [30], cap=None) == [30, *range(30)]`; on the
  old code `cap` was required and any concrete int would truncate the
  31-item result, so this call could not even be made without a cap.
- `tests/test_githooks.py::test_pending_decisions_has_no_cap_and_all_survive_as_trailer_candidates` -
  registers 25 pending records in one session and asserts
  `len(pending_ids(hooked_repo)) == 25` and that all 25 ids show up as
  `"pending"`-origin candidates from `prepare_commit_msg.candidates`; on the
  old code `_register` capped `pending_decisions` at 20 via
  `RECORDS_WRITTEN_CAP`, so only the 20 most recent of the 25 would survive
  and the assertion would fail with `len(...) == 20`.

No existing test asserted the old 20-entry cap on `pending_decisions`
specifically (only `records_written` and `prompt_ids` had cap tests, and
those caps are unchanged and still correct), so no existing test needed to
change.

Suite count: `uv run pytest -q` -> `391 passed, 3 skipped` (389 baseline + 2
new tests). One unrelated test,
`tests/test_hook_injection.py::test_rejected_and_retired_records_are_not_candidates`,
failed once under full-suite load with `AttributeError: 'NoneType' object has
no attribute 'stdout'` (a subprocess timing flake in a real-subprocess hook
test, unrelated to `pending_decisions`/`push_recent`); it passed in isolation
and passed again on a second full run. Not touched.

Proposed commit message:

```
fix: Remove the 20-entry cap on pending decisions

`_register` capped a session's pending_decisions at RECORDS_WRITTEN_CAP,
the plan's cap for records_written only. An id now stays pending until a
commit consumes it or the session is pruned by the existing 7-day expiry.
```

## I-lines

I-V19-1: No existing test asserted the removed cap. The only "cap tests" in
the suite are for `records_written` (unchanged) and `prompt_ids`
(`PROMPT_IDS_CAP`, unrelated and unchanged), so per the instructions ("any
test that asserted the cap") there was nothing to update. Decision: proceed
with adding only the new coverage described in the report, without touching
any pre-existing test.

I-V19-2: `push_recent`'s signature changed from `cap: int` to `cap: int |
None` rather than adding a second helper function or a `no_cap_push`
variant. Rationale: `push_recent` is a 6-line pure function already shared
by three call sites; teaching it "no cap" is a smaller, less surprising
surface than a parallel function that duplicates its dedup logic. This is
the only touch to `state.py` for this item; the other agent's lock-usage
work is untouched (no other lines in `state.py` were changed).

I-V19-3: Chose `tests/test_githooks.py` over `tests/test_new.py` for the
25-ids test because "appear as trailer candidates" is specifically
`prepare_commit_msg.candidates`, and `test_githooks.py` already has the
`new_pending`/`pending_ids` helpers and the `hooked_repo` fixture built for
exactly this shape of test. The test calls `create_record` (via
`new_pending`) directly and calls `prepare_commit_msg.candidates` as a pure
function; it does not run 25 real `git commit`s through the installed
hooks, since `candidates()` only needs a `Store` and a staged-paths list and
neither requires a git commit to have happened. This keeps the test fast
(well under a second) while still exercising the exact code path
(`prepare_commit_msg.pending_records` -> `pending_ids`) that a real
`prepare-commit-msg` hook run would use.

I-V19-4: The flaky `test_hook_injection.py::test_rejected_and_retired_records_are_not_candidates`
failure is pre-existing subprocess-timing flakiness (a real subprocess hook
invocation whose `CompletedProcess` came back `None`), not caused by this
item's diff (`state.py`/`newrecord.py` are not imported by that test's
subprocess path in any capacity this change touches). Confirmed by rerunning
the single test in isolation (passed) and the full suite a second time
(391 passed, 3 skipped, no failures). Logged here rather than investigated
further, since Item 4's scope is the pending-decisions cap only.
