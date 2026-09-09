# Review fix F2: record files land executable (100755)

Fixes the defect from `docs/build/11-fable-final-review.md`, "New defects" item 2:
commit 406cced's `_write_record_exclusive` (`src/scribe/newrecord.py`) called
`os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)` with no explicit mode, so
`os.open` fell back to its default of 0o777. Masked by a typical umask this
still leaves the execute bits set, so new records landed as 0o775 on disk and
git committed them as `100755`, while the three seed records are `100644`.

## What changed

- `src/scribe/newrecord.py`, `_write_record_exclusive`: the `os.open` call now
  passes an explicit mode of `0o644`, with a comment noting the umask still
  applies on top of it (normal, expected behaviour, not a bug). Records are
  data, never executable.
- `src/scribe/record.py`, `Record.save`: the temp-file write used
  `Path.write_text`, which opens with the platform default mode `0o666`. That
  happens to collapse to the same value as `0o644` under a typical `0o022`
  umask (both give `0o644`), which is why three of the four records written
  on 2026-09-09 came out `100755` (bug) while the fourth flipped to `100644`
  the first time `save()` rewrote it (coincidence of a `0o022` umask, not a
  fix). `save()` now creates its temp file with `os.open(..., 0o644)` too, so
  it agrees with `_write_record_exclusive` under any umask, not just the
  common one.

## Why `save()` normalizes rather than literally preserves mode

`save()` writes through a temp file and atomically replaces the target via
`os.replace`. On POSIX, `rename(2)` (what `os.replace` uses) swaps the
directory entry to point at the temp file's inode; the resulting file's mode
is whatever the temp file was created with, not whatever the old file's mode
was. This was already true before this fix (that's exactly how the fourth
record silently flipped from 100755 to 100644 in commit history), I did not
change that shape, only made the temp file's mode deterministic (0o644 minus
umask) instead of accidental (0o666 minus umask, which only equals 0o644
minus umask under umasks like 0o022 or 0o077 where the extra write bit in
0o666 was already going to be masked off anyway).

I decided not to add code to read the existing file's mode and reapply it
bit-for-bit before replacing (decision I-F2-1 below): every record in this
project is meant to be a plain, non-executable data file, so "preserving"
a stray custom mode (e.g. a manually `chmod`ed file) would perpetuate the
exact class of bug being fixed here rather than correct it. Normalizing to
`0o644 & ~umask` on every write is the simpler and safer behavior, and it is
what the code already did by accident under common umasks.

## Tests

Added to `tests/test_new.py`:

- `test_new_writes_a_record_with_no_execute_bit`: runs `scribe new` and
  asserts the written record's mode has no execute bits
  (`mode & 0o111 == 0`) and matches `0o644` under the umask in force. Fails
  on the old code on the `mode & 0o111 == 0` assertion (old code produces
  `0o775` under a `0o002` umask; `0o775 & 0o111 == 0o111`, not `0`).
- `test_save_rewrite_keeps_the_record_at_0o644`: runs `scribe new`, then
  calls `Record.save()` on the freshly loaded record (the same rewrite path
  ratify and supersession bookkeeping use), and asserts the mode still
  equals `0o644 & ~umask`. Fails on the old code on the final
  `mode == 0o644 & ~fixed_umask` assertion: under the `0o002` umask this
  test forces, old `save()`'s `0o666`-based temp file comes out `0o664`,
  not `0o644`.
- Both tests use a `fixed_umask` fixture that forces the process umask to
  `0o002` for the duration of the test and restores it afterward. `0o002`
  was chosen because it is the umask value where `0o666` and `0o644`
  diverge (`0o664` vs `0o644`); a `0o022` umask (this machine's actual
  ambient umask, confirmed via `umask`) would make both old and new code
  agree by coincidence and the second test would not have caught the bug.
  Both tests are skipped on Windows (`sys.platform == "win32"`) since POSIX
  mode bits don't apply there; no existing skip helper for this in the repo,
  so I used the plain `pytest.mark.skipif` idiom directly.
- Verified both new tests fail on the pre-fix code (checked out `HEAD`'s
  versions of `newrecord.py` and `record.py` into the worktree, reran just
  these two tests, restored the fix) with exactly the assertions named above,
  then confirmed both pass again on the fixed code.

## Suite results

- `tests/test_new.py`: 20 passed.
- `tests/test_ratify.py`, `tests/test_store.py`, `tests/test_schema.py`,
  `tests/test_check.py`, `tests/test_relink.py`, `tests/test_lookup.py`,
  `tests/test_timing.py`, `tests/test_hook_session.py`,
  `tests/test_hook_gate.py`, `tests/test_githooks.py`,
  `tests/test_hook_injection.py` (every file that calls `Record.save()`):
  254 passed.
- Full suite `uv run --frozen pytest -q -p no:cacheprovider`: **426 passed,
  3 skipped** in 129 s.
- `git diff --check`: clean (no whitespace errors).
- The em and en dash scan over src and tests: no matches.

## Other `O_CREAT` sites checked

`rg -n "O_CREAT" src/scribe` found only the one call site in
`_write_record_exclusive` (fixed here). The ledger append in
`src/scribe/ratify.py:63` and the session-state appends in
`src/scribe/state.py:75,139` use `Path.open("a", ...)`, which is Python's
buffered text `open()`: same default-mode behaviour, but these are
append-only JSONL/state files, not the committed `.md` records the defect
report is about, and the report does not flag them. I left them untouched
rather than expanding scope on my own judgment; flagging as I-F2-3 below in
case the owner wants the same 0o644 treatment applied there too.

## Decisions

- **I-F2-1**: `Record.save()` normalizes an existing file's mode back to
  `0o644 & ~umask` on every rewrite rather than reading and reapplying the
  file's current on-disk mode. Rationale: records are meant to always be
  plain non-executable data files; literally preserving a stray mode (e.g.
  the very 100755 bug this fix corrects) would make `save()` complicit in
  keeping a bad mode around forever instead of correcting it on next write.
- **I-F2-2**: Chose `0o002` as the forced umask in the new tests rather than
  relying on the ambient umask (which turned out to already be `0o002` on
  this machine, by coincidence) or hardcoding a check against the CI's
  actual umask. Rationale: the test must be deterministic and must fail on
  the old code regardless of what umask the runner happens to have;
  `0o002` is the specific value that exposes the `0o666`-vs-`0o644` base
  mismatch, so forcing it makes the test's failure-on-old-code property a
  fact of the code rather than an accident of the environment.
- **I-F2-3**: Did not touch `ratify.py`'s ledger append or `state.py`'s
  state-file appends, even though they also create files via default-mode
  `open()`. Out of scope per the defect report (which is specifically about
  committed `.md` record files going in as `100755`); flagged for the owner
  to decide whether the ledger/state files warrant the same treatment.
- **I-F2-4**: Did not add a helper/constant shared between `newrecord.py`
  and `record.py` for the `0o644` literal (e.g. a `RECORD_FILE_MODE`
  constant in a shared module). Two call sites with an explanatory comment
  at each is not yet a 3+ repetition per the DRY threshold in
  `coding-general-core.md`, and a shared constant would need a new import
  edge between two currently-independent modules for a single integer.
- **I-F2-5**: Did not touch the three seed records or any other files under
  `docs/decisions` in this worktree, per instructions: the main session
  handles mode corrections on the shared checkout.

## Proposed commit message

```
fix: Create record files at mode 0o644 instead of the O_CREAT default

_write_record_exclusive in newrecord.py let os.open fall back to its
default mode 0o777, so new decision records landed on disk (and in git)
as 100755 instead of the 100644 the seed records use. Pass 0o644
explicitly there and make Record.save's temp-file write use the same
explicit mode, so a fresh record and any later rewrite always agree
regardless of the process umask.
```

## Result

426 passed, 3 skipped.
