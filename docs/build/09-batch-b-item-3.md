# Batch B, Item 3 report (worktree v8)

This file replaces the shared `docs/build/09-batch-b-report.md` /
`AUTONOMOUS_DECISIONS_09_08_2026.md` locations for this worktree-isolated run,
per the deviations the main session gave for Item 3 only. It covers Item 3
(V8, "one ledger lock everywhere") and nothing else.

## Item 3 (V8)

### What changed

- `src/scribe/state.py`: added the shared constant `LEDGER_LOCK_FILE =
  "ratify.lock"` and a `ledger_lock_path(root)` helper next to the existing
  `state.json.lock` machinery, so every ledger-file writer locks the same
  file `ratify.py` already used.
- `src/scribe/ratify.py`: `LOCK_FILE` now re-exports `state.LEDGER_LOCK_FILE`
  (kept as an attribute so `ratify_module.LOCK_FILE` still resolves for
  existing tests) and `apply_verdict` locks via `ledger_lock_path` instead of
  building the path from `state_dir(...) / LOCK_FILE` inline. No behavioral
  change to ratify/reject.
- `src/scribe/newrecord.py`: `create_record` now runs its whole mutating
  region (alias reservation, validation, write, supersede reconciliation,
  index regen, optional `--register`) inside `locked(ledger_lock_path(...))`,
  reloading `store.records(refresh=True)` right after the lock is acquired.
  The actual file write goes through a new `_write_record_exclusive`, which
  tries `stem`, then `stem-2`, `stem-3`, ... via `os.open(path, O_CREAT |
  O_EXCL | O_WRONLY)`; a collision advances to the next suffix instead of
  overwriting the other writer's file. Bounded by `MAX_ALIAS_ATTEMPTS = 1000`;
  exhausting it returns a clean `alias_reservation_failed` problem and writes
  nothing. `unique_alias` is now a documented best-effort pre-check only, and
  the stem computation is factored out as `alias_stem` so both paths agree
  on the numbering sequence. On a lock timeout: one line to stderr, nothing
  written, `create_record` returns `(None, [])` (the CLI then prints "no
  record written" and exits 1).
- `src/scribe/githooks/post_commit.py`: `run` takes the same ledger lock
  around the whole implementing-commit pass, reloading records right after
  acquiring it. On a lock timeout: one stderr line, nothing written, and it
  still returns 0 (git hooks fail open; this was already `post-commit`'s
  design for every other error path).
- `src/scribe/relink.py`: `run_relink` takes the ledger lock around the whole
  rebuild, reloading records right after. On a lock timeout: one stderr line,
  returns `(1, [])` so the CLI prints nothing extra and exits 1.
- `src/scribe/lint.py`: only the mutating half of `--expire` takes the lock.
  `_stale_proposal_findings` now delegates to a new `_expire_stale`, which
  reloads records after acquiring the lock and recomputes the stale set from
  the fresh reload before expiring it. On a lock timeout: one stderr line and
  a `ledger_lock_timeout` (severity `error`) finding, so `run_lint`'s existing
  "any error -> exit 1" rule makes the whole command non-zero without new
  exit-code plumbing; the plain (non-expired) `proposal_stale` warnings from
  the pre-lock scan are still reported as before.
- Tests: `tests/test_new.py`, `tests/test_githooks.py`, `tests/test_relink.py`,
  `tests/test_lint.py` (see below).

### Files changed

- `src/scribe/state.py`
- `src/scribe/ratify.py`
- `src/scribe/newrecord.py`
- `src/scribe/githooks/post_commit.py`
- `src/scribe/relink.py`
- `src/scribe/lint.py`
- `tests/test_new.py`
- `tests/test_githooks.py`
- `tests/test_relink.py`
- `tests/test_lint.py`

### Tests added, and what fails on the old code

- `tests/test_new.py::test_new_alias_race_with_a_pre_created_file_advances_to_the_next_suffix`
  pins `unique_alias` to an alias whose file was pre-created (simulating a
  same-title race the pre-check missed), then asserts `code == 0`, the record
  lands at `{alias}-2.md` with `data["alias"] == "{alias}-2"`, and the
  pre-existing file's content is untouched. On the old code, `create_record`
  called `path.write_text(...)` unconditionally: it would silently overwrite
  the "other writer's" file instead of landing at `-2`, so the content
  assertion and the `-2.md` existence assertion both fail.
- `tests/test_new.py::test_new_lock_timeout_exits_nonzero_without_writing`
  holds `ratify.lock` past `LOCK_TIMEOUT_S`, runs `scribe new --register`,
  and asserts `code == 1`, `"ledger lock timeout"` in stderr, no new record
  file, and no `state.json`. On the old code `create_record` never touched
  any lock, so this would succeed (`code == 0`) with the lock held.
- `tests/test_githooks.py::test_post_commit_lock_timeout_fails_open_without_writing`
  holds the lock past the timeout, calls `post_commit_module.run([])`
  directly, and asserts `code == 0`, `"ledger lock timeout"` in stderr, the
  record's data unchanged, and its id still pending. On the old code
  `post_commit.run` never took any lock, so it would link and consume the
  pending id regardless.
- `tests/test_relink.py::test_relink_lock_timeout_exits_nonzero_without_writing`
  holds the lock past the timeout, runs `scribe relink` as a subprocess, and
  asserts `returncode == 1`, `"ledger lock timeout"` in stderr, and the
  record's data unchanged. On the old code `run_relink` never took any lock,
  so it would relink normally (`returncode == 0`) with the lock held.
- `tests/test_lint.py::test_expire_lock_timeout_reports_error_and_changes_nothing`
  holds the lock past the timeout, runs `scribe lint --expire --json`, and
  asserts `code == 1`, `"ledger lock timeout"` in stderr, a
  `ledger_lock_timeout` finding, and the stale record still `proposed`. On
  the old code `_stale_proposal_findings` never took any lock, so it would
  expire the record and exit 0 regardless.

No existing test encoded the V8 defect as expected behavior, so nothing
needed to change under "fix, and say so."

### Suite count

`uv run pytest -q`: **394 passed, 3 skipped** (baseline before this item was
389 passed, 3 skipped; +5 new tests, 0 removed, 0 changed assertions in
existing tests).

### Non-obvious decisions (I-lines)

- I-V8-1: `create_record` takes the ledger lock unconditionally, not only
  when `--register` is passed. The item text names "`scribe new
  --register`", but plain `scribe new` (no `--register`) still mutates other
  ledger records through `reconcile_supersession` + `write_index` whenever
  the spec carries `supersedes`, which is exactly the lost-update case V8
  describes ("New, post-commit, relink, and expiry can load and overwrite
  the same record independently"). Locking only when `--register` is set
  would leave that path unprotected, so the lock wraps the whole mutating
  region of `create_record` regardless of the flag. This matches
  `docs/build/06-validation-triage.md`'s own phrasing ("take the ratify lock
  in `new`, `post-commit`, `relink` and `lint --expire`") more literally than
  the flag-qualified wording in the item text.
- I-V8-2: on an alias collision at write time, the loser advances to the
  next numbered suffix (`-2`, `-3`, ...) rather than failing cleanly, bounded
  by `MAX_ALIAS_ATTEMPTS = 1000`. This matches `unique_alias`'s own existing
  behavior for the ordinary (non-race) case, so a racing writer gets the same
  outcome a later, non-racing writer would have gotten. Exhausting all 1000
  numbered attempts (only plausible under a pathological or adversarial
  collision) still fails cleanly with an `alias_reservation_failed` problem
  and writes nothing.
- I-V8-3: the shared lock file keeps the name `ratify.lock` (now defined
  once as `state.LEDGER_LOCK_FILE`) rather than introducing a new file name.
  Renaming would be free-standing churn with no behavioral benefit, and
  `ratify.LOCK_FILE` is kept as an alias so `tests/test_ratify.py`'s existing
  `ratify_module.LOCK_FILE` reference keeps working unchanged.
- I-V8-4: the four new call sites print their lock-timeout line straight to
  stderr, matching the "one stderr line" wording in the item text. Ratify's
  own existing lock-timeout message is left untouched (it still goes to
  stdout via the CLI's `print(outcome.message)`, per
  `tests/test_ratify.py::test_ratify_lock_timeout_exits_nonzero_without_ledger_writes`,
  which this item does not touch) - the two are cosmetically inconsistent
  with each other, but changing ratify's existing, already-tested behavior
  was out of scope for this item.
- I-V8-5: for `lint --expire`, a lock timeout is surfaced as an `error`
  severity finding (`ledger_lock_timeout`) instead of new exit-code
  plumbing, since `run_lint` already exits 1 on any error-severity finding.
  This keeps `_expire_stale` a plain function returning `list[Finding]`
  rather than needing a parallel "did the lock time out" return channel.
- I-V8-6: did not touch `RECORDS_WRITTEN_CAP` / the `pending_decisions` cap
  in `state.py` or its use in `newrecord._register`, per the explicit
  instruction that another agent owns V19 there. The only `state.py` change
  is the new `LEDGER_LOCK_FILE` constant and `ledger_lock_path` helper, added
  well away from the cap constants and `update_state`.

### Proposed commit message

```
fix: Serialize ledger writes across new, post-commit, relink, lint

New, post-commit, relink, and lint --expire now reserve record filenames
with exclusive create and share ratify's ledger lock, reloading records
after acquiring it; a lock timeout writes nothing and exits like ratify
(non-zero for CLI commands, exit 0 for the post-commit git hook).
```

## Remaining

Nothing remaining for Item 3. Only Item 3 (V8) was in scope for this
worktree; Items 0, 1, 2, 4, and 5 from `step10_prompt.txt` belong to other
worktrees/agents and were not touched here.
