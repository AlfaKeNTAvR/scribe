# Review fix G3: index lock races, add-then-delete, and shim startup isolation

Fixes three gaps from `docs/build/11-fable-final-review.md` ("V8: closed, with
one regression"; "V6: closed") and its "08-review follow-ups" section ("the
git shim re-execs itself under `-I -S` ... but the first interpreter start
still honours the user's `PYTHONHOME`"), plus `docs/build/06-validation-triage.md`
(owner calls: V6 "no `--allow-delete` escape"; V8 "one worktree-local ledger
lock").

## Gap 1 (V8): INDEX.md writes and checks now go through the ledger lock

**Files:** `src/scribe/index.py`, `src/scribe/lint.py`, `src/scribe/cli.py`.

`src/scribe/index.py` gained two lock-guarded wrappers around the existing
`check_index`/`write_index`, `locked_check_index` and `locked_write_index`.
Both take `state.ledger_lock_path`, reload `store.records(refresh=True)`
only after the lock is held, then delegate to the plain function. On a lock
timeout they return `(target, False, False)`; the third element (`acquired`)
tells the caller not to act on the other two.

`src/scribe/cli.py`'s `_index_command` (`scribe index` / `scribe index
--check`) now calls the locked wrappers instead of `check_index`/
`write_index` directly. On a timeout it prints one stderr line
(`scribe index: ledger lock timeout; nothing written` or the `--check`
equivalent) and exits 1, writing nothing.

`src/scribe/lint.py`'s `_index_findings` (the store-wide `index_stale` rule,
with or without `--fix-index`) now calls the same two wrappers instead of
the plain functions. On a timeout it prints one stderr line and returns a
single `ledger_lock_timeout` error finding, which forces `scribe lint`'s
exit code to 1 the same way `_expire_stale`'s existing timeout path already
does.

`_expire_stale` (the `--expire` path) now calls `write_index(store)`
directly, still inside the lock it already held, right after saving the
expired/restored records, instead of leaving INDEX.md to a later
(previously unlocked) pass. `write_index` is called only when something
was actually expired (see I-G3-2).

### Tests added

`tests/test_index.py`:
- `test_index_write_lock_timeout_exits_nonzero_without_writing` -- holds the
  lock past 2 s, asserts `scribe index` exits 1, prints "ledger lock
  timeout", and never creates INDEX.md. **Fails on the old code**: it took
  no lock, so it wrote INDEX.md and exited 0 immediately (elapsed time
  under 2 s).
- `test_index_check_lock_timeout_exits_nonzero` -- same for `scribe index
  --check`. **Fails on the old code** the same way (immediate exit 0/1
  from a normal check, not a timeout).

`tests/test_lint.py`:
- `test_lint_index_check_lock_timeout_reports_error_and_writes_nothing` --
  plain `scribe lint` (no `--fix-index`) now blocks on the lock too. Asserts
  `code == 1`, `"ledger lock timeout"` in stderr, `"ledger_lock_timeout"` in
  the findings, and INDEX.md unchanged on disk. **Fails on the old code**:
  `assert elapsed >= 2.0` fails (old `_index_findings` never touched the
  lock, so it ran straight through in milliseconds).
- `test_lint_fix_index_lock_timeout_reports_error_and_writes_nothing` --
  same for `--fix-index`. **Fails on the old code** on the same `elapsed >=
  2.0` assertion.
- `test_expire_regenerates_the_index_without_a_separate_index_run` -- writes
  a stale proposal, runs `scribe index` once, then `scribe lint --expire`,
  then reads INDEX.md straight off disk (no second `scribe index` call) and
  asserts the record shows up under `## Retired` as `expired`. **Fails on
  the old code**: `assert "D-260908-sound-choice" in retired_section` fails
  because the old `_expire_stale` never wrote the index, so the on-disk
  file still shows the pre-expiry `## Review queue` state ('D-260908-sound-choice'
  is entirely absent from the `## Retired` section).

## Gap 2 (V6): add-then-delete inside the checked range now fails `scribe check`

**Files:** `src/scribe/gitutil.py`, `src/scribe/check.py`.

`gitutil.py` gained `deleted_paths_in_range(base, head, subdir, cwd)`: one
`git log --format= --name-only -z --diff-filter=D <base>..<head> --
<subdir>` call, decoded through the existing `_paths_from_z` helper (the
same `--format=` + `-z` idiom `commit_changed_paths` already uses for its
root-commit branch). This is the "one `git log` call over the range" the
task asked for, rather than a diff or tree listing per commit.

`check.py`'s `_deleted_record_reasons` is split into `_deleted_record_paths`
(the set logic) and `_deleted_record_reasons` (rendering). The new set
logic is:

```
head_paths = tree_record_paths("HEAD")
base_paths = tree_record_paths(base)
range_deleted = {p for p in deleted_paths_in_range(base, "HEAD") if it looks like a D-*.md record}
missing = (base_paths | range_deleted) - head_paths
```

Union-then-subtract instead of the old plain `base_paths - head_paths`: a
record added after `base` and deleted again before `HEAD` is present in
neither tree, so the old two-tree diff could never see it; it does appear
in `range_deleted` (the commit that deleted it is inside `base..HEAD`), and
subtracting `head_paths` at the end still correctly drops a record that was
deleted and then restored before `HEAD`. The final `sorted()` over a
Python `set` also guarantees a path deleted more than once in the range
(deleted, restored, deleted again) produces exactly one `record_deleted`
line, not one per deletion commit.

The reason string's wording changed from "was present at {base} and is
missing at HEAD" to "was deleted inside this range and is missing at HEAD",
since the old phrasing is false for the add-then-delete case (the record
was never present at `base`). `_alias_at(root, base, path)` is unchanged
and still falls back to the filename stem when the path never existed at
`base`, per its existing documented behavior; this is the pragmatic choice
for the add-then-delete case rather than adding a second git call to find
the alias from the deleting commit's parent tree.

Kept self-contained per the coordinator's note that the main tree has since
changed `check.py`'s signature (precomputed path sets, `GitError` on the
strict path): this diff only touches `_deleted_record_reasons` and adds
`_deleted_record_paths` next to it, using the same `gitutil` call
conventions (`_git` returning `CompletedProcess`, no exceptions) already in
this file, so it should three-way merge without needing to track the main
tree's refactor.

### Tests added (`tests/test_check.py`)

- `test_adding_then_deleting_a_record_inside_the_range_fails` -- on a branch
  off `main`, `scribe new` a plain record, commit, delete the file, commit
  again, then `scribe check --base main`. Asserts `code == 1` and
  `f"record_deleted: {alias}"` in stdout. **Fails on the old code**: the
  `record_deleted: {alias}` substring is absent (old `_deleted_record_reasons`
  computes `base_paths - head_paths`, and this alias is in neither tree).
- `test_adding_and_keeping_a_record_inside_the_range_passes` -- same setup
  without the deletion; asserts `(code, stdout.strip()) == (0, "scribe
  check: ok")`. Companion/regression guard, not expected to fail on the old
  code (add-then-keep already passed before this fix; the existing
  `test_a_plain_unreviewed_record_passes` already covered this shape, this
  one just pairs explicitly with the add-then-delete test above).
- `test_a_record_deleted_before_the_base_is_not_reported_twice` -- deletes
  a record (`D-260908-verbatim-quote-is-the-evidence`, chosen because no
  other seed record's `relates_to` points at it, unlike `RATIFIED_A`) in the
  commit that becomes `main`'s tip, then branches and adds unrelated code;
  asserts `scribe check --base main` passes cleanly and
  `stdout.count("record_deleted") == 0`. This is a dedup/false-positive
  guard on the union logic (a record deleted before the range even starts
  is outside `base..HEAD`, so `deleted_paths_in_range` never sees it and it
  is not double-counted against the base-vs-HEAD source). **Does not fail
  on the old code**: the old single-source diff also correctly ignores a
  deletion that happened before `base`, so there is nothing here that only
  the new code gets right; it is a regression guard confirming the new
  union path did not introduce a false positive or a duplicate line
  (I-G3-3).

## Gap 3 (shim isolation): the shebang isolates the first interpreter start on POSIX

**Files:** `src/scribe/init_repo.py`, `src/scribe/templates/githook_shim.py`.

`init_repo.py` gained `shim_shebang(platform)`. On POSIX it returns
`/usr/bin/env -S python3 -I -S` instead of the old `/usr/bin/env python3`;
the Windows branch (`platform == "nt"`) is unchanged (`/usr/bin/env
python`). `render_shim` now calls `shim_shebang` instead of building the
old plain string inline.

`-S` tells `env` to split the rest of the shebang line into separate
arguments instead of passing it as one opaque string to the interpreter;
without it, the kernel still only recognizes one "optional-arg" token on
the shebang line, so `env` would receive `-I -S` glued onto `python3` as
part of a single string it cannot exec. `-S` is supported by GNU coreutils
`env` 8.30+ (2018), the `env` shipped with macOS since at least 10.15, and
MSYS2's `env`.

The template's own in-script re-exec (`if not sys.flags.isolated: ...
os.execv(..., ["-I", "-S", ...])`) is untouched and still runs: on POSIX
`sys.flags.isolated` is already `True` by the time this line runs (the
shebang did the isolating), so the `if` is false and the re-exec is
skipped; on Windows (no `-S` in that shebang) it still fires and is the
only isolation path there, exactly as before this change. Comments in both
files were updated to say so; no behavior in the re-exec path itself
changed.

Verified empirically (not just by reading the man page) before writing the
fix:
- `PYTHONHOME=/nonexistent python3 -c "print(1)"` -- fatal error,
  `ModuleNotFoundError: No module named 'encodings'`, exit 1.
- `PYTHONHOME=/nonexistent python3 -I -c "print(1)"` -- prints `1`, exit 0.
- A real `#!/usr/bin/env -S python3 -I -S` script run with
  `PYTHONHOME=/nonexistent` printed `sys.flags.isolated == 1` and the
  broken `PYTHONHOME` untouched in `os.environ` -- confirms `-S` is
  supported by this machine's `env` and that isolation is active from the
  very first process, not just after a re-exec.

### Tests added

`tests/test_supervise.py`:
- `test_installed_shim_survives_a_broken_pythonhome` -- runs `scribe init`,
  makes a real commit through the installed `prepare-commit-msg` /
  `commit-msg` / `post-commit` shims with `PYTHONHOME=/nonexistent` in the
  environment (same style as the existing
  `test_installed_shim_lets_the_commit_through_when_uv_is_broken`). Asserts
  the commit's exit code is 0 and no `hook-errors.log` was written. **Fails
  on the old code**: `assert result.returncode == 0` fails; reproduced by
  reverting `init_repo.py` and re-running, which fails with the interpreter
  crashing during `init_fs_encoding` before the shim's own code (or the
  re-exec's `try/except`) ever executes, so git reports the hook as failed
  and aborts the commit.

`tests/test_init.py`:
- `test_init_installs_four_managed_executable_hooks` -- the existing
  `assert text.startswith(...)` line was updated from `"#!/usr/bin/env
  python3\n"` to `"#!/usr/bin/env -S python3 -I -S\n"`. Not a new test, but
  it would otherwise fail on the new code (the old assertion is what the
  fix intentionally changes), so it counts as the direct check that
  `render_shim` produces the new shebang.

## Suite results

- `tests/test_index.py tests/test_lint.py`: 48 passed.
- `tests/test_check.py tests/test_gitutil.py tests/test_new.py`: 51 passed.
- `tests/test_init.py tests/test_supervise.py`: 39 passed.
- Full suite, `uv run --frozen pytest -q -p no:cacheprovider`: **437 passed,
  3 skipped in 95.52s**. No flake; `tests/test_timing.py` did not need a
  rerun.
- `git diff --check`: clean, no whitespace errors.
- The em-dash and en-dash literal-character scan over `src`, `tests` and
  `README.md`: no output.

## Decisions

- **I-G3-1**: `_index_findings`'s plain (no `--fix-index`) path now takes
  the ledger lock even though it never writes. The task's own test
  requirement ("assert `scribe index` and `scribe lint` write nothing and
  report the timeout") only makes sense if a lock-only *check* still blocks
  and reports a timeout, since there is nothing else for a read-only pass
  to time out on. The alternative (only lock the `--fix-index`/write path)
  would leave a plain `scribe lint` reading `INDEX.md` and the records
  against a filesystem another writer is mid-mutating, which is the same
  class of race this whole gap is about, just for a read instead of a
  write.
- **I-G3-2**: `_expire_stale` writes the index only when `stale` is
  non-empty (i.e. only when it actually changed something). It does not
  unconditionally call `write_index` on every `--expire` invocation. If
  nothing was stale, no records changed, so `INDEX.md` cannot have gone out
  of sync from this call; the following (still separate, still
  lock-guarded) `_index_findings` pass in `lint_store` catches any
  unrelated staleness the same way it always did.
- **I-G3-3**: `test_a_record_deleted_before_the_base_is_not_reported_twice`
  does not fail on the old code (see the test list above). Keeping it
  anyway: it is the regression guard for the union-of-two-sources logic
  the fix introduces, and the task's phrase "is not reported twice" reads
  most naturally as "a deletion entirely outside the checked range must
  not resurface, whether once or twice" -- a case the old single-source
  code also happened to get right, for a simpler reason (it never looked
  at range-wide deletions at all). Documented here rather than claiming a
  false "fails on old code" (same posture as `12-review-fix-f1.md`'s
  I-F1-3).
- **I-G3-4**: Deleted-but-never-present-at-base records still resolve their
  alias through `_alias_at(root, base, path)`, which falls back to the
  filename stem when `base` never had the file (the existing documented
  behavior of that helper, unchanged). Considered adding a second `git`
  call per such path (find the deleting commit via `git log -1
  --diff-filter=D --format=%H <base>..HEAD -- <path>`, then read the alias
  from `<that commit>^:<path>`) for a friendlier message, but the task's
  cost constraint is about the range-wide listing staying at one `git log`
  call, not about per-path alias lookups, and the filename-stem fallback
  is already an accepted, documented outcome of this helper for other
  callers. Kept the simpler, already-existing code path.
- **I-G3-5**: `_deleted_record_reasons`'s message wording changed from "was
  present at `{base}` and is missing at HEAD" to "was deleted inside this
  range and is missing at HEAD", because the old phrasing is factually
  wrong for a record that was only ever added and deleted after `base`. No
  test asserts the old exact wording (checked: only the alias substring and
  "retire it with expired or backtracked" are asserted anywhere in
  `tests/test_check.py`), so this is a safe wording change, not a behavior
  change.
- **I-G3-6**: Kept `gitutil.deleted_paths_in_range` as a flat, possibly
  duplicated list (like every other `_paths_from_z`-based helper in this
  file) rather than deduplicating inside `gitutil.py`. Deduplication
  happens once, in `check._deleted_record_paths`, via the set comprehension
  and the final set union; pushing dedup into `gitutil.py` would hide that
  decision from the one caller that actually needs it and would diverge
  from every sibling helper's return-a-list-from-`_paths_from_z` shape.
- **I-G3-7**: The Windows shim shebang is unchanged (`/usr/bin/env python`,
  no `-S`, no `-I -S`), per the task's explicit instruction not to touch
  the Windows branch beyond what keeps it working. This means the
  PYTHONHOME startup race the task describes is still theoretically
  possible on Windows; that gap is pre-existing (U3/the Windows path was
  already "best effort, untested" per the README) and out of scope here.
- **I-G3-8**: No preflight check for whether the local `env` supports `-S`.
  The task allowed either a cheap test or documenting the failure mode in
  the README; a preflight check would need to actually exec a `-S`-shebang
  script (not just parse `env --version` output, which does not reliably
  advertise the flag across GNU/BSD/MSYS2), which is more machinery than
  this gap's blast radius justifies for a currently-hypothetical old-`env`
  environment. Documented instead, in both README.md's Windows caveats
  section and `init_repo.shim_shebang`'s docstring.

## Proposed commit messages

**Gap 1**

Files: `src/scribe/index.py`, `src/scribe/lint.py`, `src/scribe/cli.py`,
`tests/test_index.py`, `tests/test_lint.py`.

```
fix: Take the ledger lock for every INDEX.md read and write

scribe index and scribe lint's index rule read and wrote INDEX.md
without the ledger lock every other writer (new, ratify, post-commit,
relink, lint --expire) already takes, so a concurrent writer could
race a stale in-memory record list onto disk. index.py gains
locked_check_index/locked_write_index, which take the lock, reload
records from disk, then delegate to the existing plain functions;
cli.py and lint.py use them instead of calling check_index/write_index
directly, and lint's --expire path now regenerates INDEX.md itself
before releasing its own lock instead of leaving it to a later,
separately-locked pass.
```

**Gap 2**

Files: `src/scribe/gitutil.py`, `src/scribe/check.py`,
`tests/test_check.py`.

```
fix: Catch a record added and deleted inside the same checked range

scribe check's record_deleted rule (V6) compared the base tree against
HEAD, so a record committed after the base and deleted again before
HEAD was invisible: neither tree carries it. gitutil gains
deleted_paths_in_range, one `git log --diff-filter=D --name-only -z`
call over the whole base..HEAD range; check._deleted_record_reasons
unions that with the existing base-vs-HEAD tree diff before comparing
against HEAD, so a mid-range add-then-delete is now flagged the same
way a straightforward deletion always was.
```

**Gap 3**

Files: `src/scribe/init_repo.py`, `src/scribe/templates/githook_shim.py`,
`tests/test_supervise.py`, `tests/test_init.py`, `README.md`.

```
fix: Isolate the git hook shim's first interpreter start on POSIX

The installed git hook shims re-exec themselves under `python3 -I -S`
before importing the supervisor, but the first, unisolated interpreter
start still honoured the caller's PYTHONHOME and PYTHONPATH, so a
broken PYTHONHOME could crash Python before that re-exec ever ran,
blocking a commit. init_repo.render_shim now writes the shebang as
`#!/usr/bin/env -S python3 -I -S` on POSIX, so the very first process
starts already isolated; the in-script re-exec is untouched and stays
as the isolation path on Windows (whose shebang is unchanged) and as a
fallback for a POSIX env too old to support -S.
```

## Report

`docs/build/12-review-fix-g3.md` (this file).
