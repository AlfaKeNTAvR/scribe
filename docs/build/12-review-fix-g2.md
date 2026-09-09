# Review fix G2: `-z` path decoding and malformed enum-field crashes

Fixes two gaps handed to this run as V14 and V17 (Batch A group 3). The doc
named in the assignment, `docs/build/11-codex-final-validation.md`, does not
exist in this worktree; the matching "V14" / "V17" / "Batch A group 3" /
"New defects" sections live in `docs/build/11-fable-final-review.md` instead
(same content shape, different reviewer name and filename - see I-G2-1). That
file's V14 and V17 entries say "closed"; this run found each one had a real
follow-up gap, not a fully open regression, as detailed below.

## Gap 1 (V14): `-z` pathname output run through `text=True`

`src/scribe/gitutil.py`'s `_git` ran every git subprocess, including the five
`-z` (NUL-terminated) pathname commands, with `text=True`. That mode does
two things beyond decoding: it applies universal-newline translation (a raw
`\r` inside a field becomes `\n`) and decodes stdout as UTF-8 with strict
errors (a non-UTF-8 byte sequence raises `UnicodeDecodeError`). Both byte
sequences are legal in a Linux filename. The newline case silently corrupts
the returned path; the decode case raises out of the git call entirely,
which in a hook means the fail-open supervisor swallows the whole hook.

### What changed

`src/scribe/gitutil.py`:

- Added `_git_bytes`, identical to `_git` but `text=False`, used only by the
  five `-z` pathname callers.
- `_paths_from_z` now takes a `CompletedProcess[bytes]`, splits stdout on
  `b"\0"`, and decodes each field with `os.fsdecode` (surrogateescape), which
  round-trips any byte sequence to a `str` that still compares equal to
  `os.fsdecode`d filesystem paths for the same bytes.
- The five callers (`staged_paths`, `staged_paths_against`,
  `commit_changed_paths` - both its root-commit and non-root branch -,
  `diff_names`, `tree_record_paths`) now call `_git_bytes` instead of `_git`.
  Every other `_git` call (rev-parse, log, status, merge-base, etc.) is
  untouched and stays `text=True`, per the assignment.

### Tests added (`tests/test_gitutil.py`)

- `test_staged_paths_preserves_carriage_return_and_non_utf8_filenames` and
  `test_diff_names_preserves_carriage_return_and_non_utf8_filenames`: two new
  names, `CARRIAGE_RETURN` (a literal `\r` inside the name) and `NON_UTF8`
  (built with `os.fsdecode(b"src/non-utf8-\xff\xfe.py")`, i.e. two bytes that
  are not valid UTF-8 anywhere). Both skip on Windows and skip (rather than
  fail) if the filesystem itself refuses to create the file.
- Verified against the pre-fix code (`git stash` the `gitutil.py` hunk only,
  rerun, reapply): both new tests fail with
  `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff in position 36:
  invalid start byte`, raised inside `subprocess.run`'s own newline
  translation, before either `assert set(...) == set(BINARY_UNSAFE_NAMES)`
  is reached. The four pre-existing tests in the file are unaffected by the
  stash/reapply (still pass on both old and new code).

### Incidental fix required

`tests/test_store.py::test_git_utilities_normalize_git_results` faked
`scribe.gitutil._git` with `str` responses to test `staged_paths`; since
`staged_paths` now calls `_git_bytes`, the fake needed a second function
(`fake_git_bytes`, `bytes` responses) for the `-z` call. `_git` is still
faked for the two non-path calls (`toplevel`, `git_path_hooks`) in the same
test (I-G2-9).

## Gap 2 (V17 follow-up): non-string enum fields crash set/dict lookups

`docs/build/11-fable-final-review.md`'s V17 entry closed the crash inside
`schema.validate_record` (wrong-type enum values raising before a Problem
could be produced) and added `Store.records()`'s catch of `FrontMatterError`
for structurally broken files. Neither covers a file that parses as
perfectly valid YAML but gives `review_state`, `effective_state` or
`supersedes` the wrong *type* (e.g. `effective_state: []`, a valid YAML flow
list). `Record.load` only calls `frontmatter.split`, never
`schema.validate_record`, so such a record loads through unchanged, and the
first place that treats one of these fields as a set member or a dict key
raises `TypeError: unhashable type: 'list'` - which, because these all run
in one pass over every record, takes every other record down with it too.

I-G2-2: the assignment described this crash as living in
`pre_tool_use_edit.py`'s `superseded_keys` (line 102), triggered by
`effective_state: []` or `review_state: 5`. Both were checked by running the
actual functions against the pre-fix code before writing any test, per the
"each must fail on the old code" requirement:

- `effective_state: []` does **not** crash `superseded_keys`,
  `active_records` or `governing_records`: their effective-state checks
  (`EDGE_EFFECTIVE_STATES`, `ACTIVE_EFFECTIVE_STATES`) are **tuples**, and
  `x not in a_tuple` is a linear equality scan, not a hash lookup, so an
  unhashable `x` is merely excluded, not a crash.
- `review_state: 5` does not crash anywhere either: `5` is hashable, so
  `REVIEW_ORDER.get(5, ...)` (the one place `review_state` is used as a dict
  key, in `governing_records`'s sort) just misses and returns the default.
- The real crash sites are: `Store.effective_edges` and
  `Store.effective_authority` (`effective_state` tested with `not in {..}`,
  a **set**), `reconcile_supersession` (`supersedes` used as a dict key via
  `by_id.get(...)`, and `effective_state` against a set), and
  `session_start.py`'s own `review_queue_counts` (`supersedes` tested with
  `in ratified_keys`, a set). `pre_tool_use_edit.py` *does* crash, but from
  `review_state` being **unhashable** (e.g. `review_state: []`, not `5`) via
  the same `REVIEW_ORDER.get(...)` call once a record with a normal
  `effective_state` reaches `governing_records`'s sort.

Given that, the fix targets the fields and call sites that actually crash,
and treats the assignment's field list (`effective_state`, `review_state`,
`supersedes`) as the right scope, substituting `review_state: []` for
`review_state: 5` in the one test where the value's type, not just its
enum-membership, is what matters (I-G2-4).

### What changed

`src/scribe/schema.py`:

- Added `unhashable_enum_reason(mapping)`: returns the first reason
  `review_state`, `effective_state` or `supersedes` is not a string (or, for
  `supersedes`, string-or-null), else `None`. Reuses the existing `_is_str`
  helper `validate_record` already uses for the same fields, so the schema
  stays the single source of truth for what counts as a valid type here
  (I-G2-5) - this is deliberately narrower than `validate_record`: it only
  guards the type shape that would otherwise crash a set/dict lookup, not
  full enum-value or cross-field conformance, which stays on the
  `scribe validate` / `commit-msg` path through `validate_record`.

`src/scribe/store.py`:

- `Store.records()` now calls `unhashable_enum_reason` on every loaded
  record and skips + logs (same one-line `log_hook_error` call already used
  for `FrontMatterError`) a record that fails it. This is the boundary the
  assignment asked to prefer: every downstream consumer that reads through
  `store.records()` - `effective_edges`, `effective_authority`,
  `reconcile_supersession` (called from `lint.py`), `lint.py`'s own
  `ACTIVE_STATES` set check, `index.py`, `relink.py`, `commit_msg.py`,
  `prepare_commit_msg.py` - is protected by this one change, so none of them
  needed their own guard (I-G2-6).

`src/scribe/hooks/session_start.py` and `src/scribe/hooks/pre_tool_use_edit.py`:

- Both hooks read front matter through their own private loader instead of
  `Store.records()` (to stay independent of `Record`'s stricter body
  handling / for the injection hook's own deadline budget), so the
  store-level fix does not reach them. Both loaders now call
  `unhashable_enum_reason` right after `split()` succeeds and skip + log the
  same way. For `pre_tool_use_edit.py` specifically, this is defense in
  depth rather than a fix for a reproduced crash on `effective_state` or
  `supersedes` (see above), but it is a genuine fix for `review_state`, and
  it keeps every raw-front-matter loader in the codebase agreeing on what a
  malformed record is.

### Hooks checked with no change needed

- `src/scribe/hooks/reconcile.py` (TaskCompleted/Stop): does not read
  `effective_state`, `review_state` or `supersedes` at all.
- `src/scribe/githooks/post_commit.py`: same - no reads of these fields.
- `src/scribe/githooks/commit_msg.py`, `src/scribe/githooks/prepare_commit_msg.py`,
  `src/scribe/relink.py`, `src/scribe/index.py`, `src/scribe/lint.py`: all
  read records exclusively through `store.records()`, so the store-level fix
  covers them (I-G2-7).

### Tests added

`tests/test_store.py`:

- `test_records_skips_a_record_with_a_list_effective_state`: one good record
  plus one with `effective_state: []`. Fails on the old code at the
  `store.effective_edges()` call itself (`TypeError: unhashable type:
  'list'`, raised before either assertion after it runs), because old
  `records()` loads the bad record unfiltered and `effective_edges` tests
  `effective_state` for set membership.
- `test_records_skips_a_record_with_a_non_string_supersedes`: one good
  record plus one with `supersedes: []`. Fails on the old code at the
  `reconcile_supersession(store.records(), "scribe-lint")` call itself
  (same `TypeError`, from `by_id.get(successor.data.get("supersedes"))`).

`tests/test_hook_injection.py`:

- `test_malformed_review_state_is_skipped_and_injection_still_works`: one
  good record (the seeded `INDEX_RECORD`) plus one with `review_state: []`
  and a normal `effective_state`. Fails on the old code at the
  `handle(edit_payload(...))` call itself: `governing_records`'s sort raises
  `TypeError: unhashable type: 'list'` from `REVIEW_ORDER.get(...)`, so
  `context_of(...)` never runs.

`tests/test_hook_session.py`:

- `test_session_start_skips_a_record_with_non_string_supersedes`: one
  unreviewed good record plus one with `supersedes: []`. On the old code the
  `run_hook(...)` subprocess itself is what fails: `review_queue_counts`
  raises inside the hook process, the launcher's fail-open supervisor
  swallows it, and `result.stdout` comes back empty, so
  `assert "1 unreviewed decisions, 0 supersede" in result.stdout` fails
  against `''` - the exact "one malformed record silently takes the hook
  down" failure mode the assignment described.

All four were confirmed to fail on the old code by stashing only the
Gap 2 source hunks (`schema.py`, `store.py`, the two hooks), rerunning, and
reapplying the stash.

## Suite

- `uv run --frozen pytest -q -p no:cacheprovider tests/test_gitutil.py
  tests/test_store.py tests/test_hook_injection.py tests/test_hook_session.py`:
  69 passed.
- `uv run --frozen pytest -q -p no:cacheprovider` (full suite): **434 passed,
  3 skipped in 81.77s**. `tests/test_timing.py` did not flake, no rerun
  needed.
- `git diff --check`: clean.
- The em and en dash scan over src and tests: no output.

## Decisions

- **I-G2-1**: Read `docs/build/11-fable-final-review.md` in place of the
  non-existent `docs/build/11-codex-final-validation.md`; its "V14", "V17",
  "Batch A group 3" and "New defects" sections match the assignment's
  description closely enough (same content shape, different reviewer name)
  to be confident it is the intended source.
- **I-G2-2**: Verified the assignment's literal crash description
  (`superseded_keys`, `effective_state: []`, `review_state: 5`) against the
  actual pre-fix code by running it, not just reading it, before writing any
  test - per the "each must fail on the old code" requirement, a test that
  cannot be shown to fail on old code is not evidence of a fix. Two of the
  three named triggers do not reproduce; see the real crash sites listed
  above.
- **I-G2-3**: Fixed at the store level (`Store.records()`) as the
  assignment's preferred option, using the schema's own type-check helper so
  `validate_record` stays the single source of truth for "is this the right
  type" - `Store.records()` and the two hook loaders all call the same
  `schema.unhashable_enum_reason`, never duplicate the check.
- **I-G2-4**: Used `review_state: []` instead of the assignment's literal
  `review_state: 5` for the `pre_tool_use_edit.py` test, since `5` is
  hashable and does not reproduce any crash; `unhashable_enum_reason` still
  rejects `review_state: 5` too (it is a real schema violation, just not a
  crash trigger), so the fix's scope is unchanged, only the test's chosen
  value.
- **I-G2-5**: `unhashable_enum_reason` lives in `schema.py` next to
  `_in_str_set`/`_enum` and reuses `_is_str`, rather than duplicating a type
  check in `store.py` or the hooks, so a future change to what counts as a
  valid `review_state`/`effective_state`/`supersedes` type only needs to
  happen once.
- **I-G2-6**: Did not add a redundant guard inside `effective_edges`,
  `effective_authority` or `reconcile_supersession` themselves - all three
  only ever receive records that already passed through
  `Store.records()` in production code, so guarding the boundary once is
  sufficient and keeps the crash-prevention logic in one place. (The
  existing direct-call tests in `test_store.py` that construct `Record`
  objects by hand and assign `store._records` still bypass `records()` on
  purpose, to unit-test `effective_edges`/`reconcile_supersession` in
  isolation - that is unchanged and unaffected by this fix.)
- **I-G2-7**: Confirmed by grep that `hooks/reconcile.py` (TaskCompleted/Stop)
  and `githooks/post_commit.py` do not read `effective_state`,
  `review_state` or `supersedes` at all, so neither needed a change despite
  being named in the assignment's hook list.
- **I-G2-8**: Added a separate `_git_bytes` helper rather than changing
  `_git` itself or adding a `text` parameter to it, so every non-path
  command (rev-parse, log, status, merge-base, interpret-trailers) is
  visibly untouched and still returns `str`.
- **I-G2-9**: Updated (rather than left broken) the one pre-existing test
  that monkeypatched `_git` for a `-z` command
  (`test_git_utilities_normalize_git_results`); this is a direct, necessary
  consequence of Gap 1's fix, not a new behavior being tested.

## Proposed commits

1. `fix: Decode git -z pathname output in binary mode`

   `_git`'s `text=True` ran the five `-z` pathname commands through
   universal-newline translation and strict UTF-8 decoding, corrupting a
   filename with a raw carriage return and raising `UnicodeDecodeError` (hook
   fail-open) on a non-UTF-8 filename. Adds a `text=False` `_git_bytes`
   helper for those five callers and decodes each NUL-separated field with
   `os.fsdecode`.

   Files: `src/scribe/gitutil.py`, `tests/test_gitutil.py`,
   `tests/test_store.py`.

2. `fix: Skip records whose enum fields have the wrong type`

   A record whose `effective_state`, `review_state` or `supersedes` value is
   not a string (e.g. `effective_state: []`) is valid YAML and used to load
   straight through `Store.records()` and two hooks' own front-matter
   loaders, then crash the first set/dict lookup that assumed a hashable
   string, taking every other record in the same pass down with it. Adds a
   narrow type check in `schema.py`, reused at each loader boundary, so such
   a record is skipped and logged instead, matching the existing V17
   pattern for structurally broken files.

   Files: `src/scribe/schema.py`, `src/scribe/store.py`,
   `src/scribe/hooks/session_start.py`,
   `src/scribe/hooks/pre_tool_use_edit.py`, `tests/test_store.py`,
   `tests/test_hook_injection.py`, `tests/test_hook_session.py`.
