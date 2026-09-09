# Q3 / O5: the `post-rewrite` git hook

Implements the fourth scribe-managed git hook so `git commit --amend` and
`git rebase` relink `implementation_links` automatically, closing the gap
Q3 in `AUTONOMOUS_DECISIONS_09_08_2026.md` left open ("keep `scribe relink`
manual, or install a `post-rewrite` hook"). Branch
`nikita/feat/q3-post-rewrite-hook`.

## Files changed

- `src/scribe/githooks/post_rewrite.py` (new). The hook entry point. git
  passes the rewrite kind (`amend` or `rebase`) as `argv[1]` and one
  `<old-sha> <new-sha>` pair per rewritten commit on stdin. The hook drains
  stdin defensively (never blocks, never crashes on an unavailable or
  terminal stdin), then reuses `run_relink` from `relink.py` verbatim rather
  than duplicating its logic. Guarded against re-entry with
  `SCRIBE_IN_POST_REWRITE` (same pattern as `post_commit.GUARD_ENV`).
  `SCRIBE_SKIP_HOOKS` is honoured for free: it is already checked once,
  centrally, in `githooks.dispatch` before any hook module loads. On the V8
  ledger lock timeout, `run_relink` itself already prints the one stderr
  line and writes nothing; this hook only turns that non-zero return into
  exit 0. On any other crash, `githooks.dispatch`'s existing
  `except BaseException` wrapper logs to `hook-errors.log` and exits 0, the
  same as the other three hooks.
- `src/scribe/githooks/__init__.py`: registered `"post-rewrite":
  "scribe.githooks.post_rewrite"` in `HOOK_MODULES`.
- `src/scribe/init_repo.py`: `HOOK_NAMES` grew a fourth entry,
  `"post-rewrite"`. Every other behaviour in this module (shim rendering,
  idempotency, the foreign-hook-kept-unless-`--force` path with the
  `.pre-scribe` backup, `chaining_instructions` for `core.hooksPath`) already
  iterates `HOOK_NAMES` generically, so `post-rewrite` picked up the same
  install/keep/replace/backup treatment as the other three hooks with no
  further code change.
- `src/scribe/cli.py`: the `git-hook` subcommand's `--help` text now lists
  `post-rewrite` alongside the other three hook names.
- `tests/test_githooks.py`: added `post_rewrite` to the `HOOKS` tuple that
  `install_hooks` installs into the tmp repo for every test in this file,
  and four new tests (below). Updated two existing amend tests whose
  assertions encoded the old, pre-`post-rewrite` behaviour (stale link
  survives an amend until a manual `scribe relink`); see "Tests updated,
  and why" below.
- `tests/test_init.py`: renamed
  `test_init_installs_three_managed_executable_hooks` to
  `test_init_installs_four_managed_executable_hooks`, updated its
  `HOOK_NAMES` set assertion to include `"post-rewrite"`, and extended the
  foreign-hook-kept test's other-hooks-untouched loop to include
  `"post-rewrite"`.
- `README.md`: the `init` row and the `git-hook` row in the CLI table now
  name all four hooks; the `relink` row notes that amend and rebase relink
  automatically through the hook and that `scribe relink` remains available
  for a history rewritten somewhere the hook never ran (for example another
  clone); the fail-open section's git-hooks bullet names `post-rewrite` and
  describes its relink-on-rewrite behaviour and shared V8 lock timeout
  contract.

## Tests added

All in `tests/test_githooks.py`, under a new
`# --- post-rewrite: relink on amend/rebase (O5, Q3) ---` section:

- `test_rebase_onto_end_to_end_leaves_both_records_linked_to_new_shas`: a
  real, interactive-free `git rebase --onto` over a two-commit range (one
  implementing commit per record, disjoint files) run with the hooks fully
  enabled. Fails on the old code because `post-rewrite` was never installed,
  so nothing would run `git-hook post-rewrite` at all after the rebase (the
  installed-hooks tuple wouldn't even contain the file); the assertion that
  actually catches a regression is that both records end up linked to their
  post-rebase shas with neither original sha left reachable.
- `test_post_rewrite_after_rebase_relinks_both_records_and_drops_stale_shas`:
  the surgical half of the same contract. Builds two already-stale,
  committed links (as a hand fix-up or an out-of-band `scribe relink` would
  leave them) pointing at shas a rebase is about to make unreachable,
  performs the rebase with `SCRIBE_SKIP_HOOKS=1` so `post_commit` cannot
  also relink each replayed commit for real (isolating exactly what
  `post_rewrite.run` does), then calls `post_rewrite.run(["rebase"])`
  directly. Fails on the old code: the module does not exist. Asserts the
  exact stderr notice (`scribe: relinked 2 record(s) after rebase; run git
  add docs/decisions ...`) and that both records now show only the new shas.
- `test_post_rewrite_writes_nothing_when_no_record_is_involved`: an amend of
  a commit that never carried a `Decision:` trailer. Fails on the old code
  the same way (module missing); on the new code, asserts no `scribe:
  relinked` notice and an unchanged `git status --porcelain`.
- `test_post_rewrite_lock_timeout_fails_open_without_writing`: holds the V8
  ledger lock externally (`fcntl.flock`) across a `git commit --amend`.
  Asserts the amend still exits 0, one `ledger lock timeout` line reaches
  stderr, no `scribe: relinked` notice appears, and the record on disk is
  byte-for-byte unchanged (`post_commit` shares the same lock, so it cannot
  write either). This is the direct test for the requirement "on lock
  timeout a git hook must print one stderr line, write nothing and exit 0."

Also added, in `tests/test_init.py`: the renamed
`test_init_installs_four_managed_executable_hooks` exercises the same
install/idempotency/executable-bit checks for all four hooks generically
(no new code needed there beyond the `HOOK_NAMES` tuple growing).

## Tests updated, and why

Two amend tests in `tests/test_githooks.py` encoded the pre-`post-rewrite`
behaviour, where a stale link from before an amend survived until a human
ran `scribe relink` by hand:

- `test_amend_keeps_one_trailer_and_adds_a_link_for_the_new_sha` renamed to
  `test_amend_keeps_one_trailer_and_relinks_to_the_new_sha`. Old assertion:
  `link_commits(saved) == {old_sha[:12], new_sha[:12]}` (both shas present
  after the amend). New assertion: `link_commits(saved) == {new_sha[:12]}`
  (only the new sha; `post_commit` still appends the new link first, then
  the `post-rewrite` hook that fires right after the amend runs `scribe
  relink` and drops the now-unreachable old sha before the commit returns).
  Also asserts the record's history now shows exactly one `relinked` entry.
- `test_amend_with_a_newly_pending_decision_adds_its_trailer_and_link`: same
  fix applied to the first record's link-set assertion (the second record,
  which never had a stale link, is untouched).

## Empirical finding worth flagging: `post-commit` already fires during a
non-conflicting `git rebase`

Not a defect to fix here, just a fact this task's tests had to design
around and that is worth the owner knowing: in this git version, a plain
non-interactive `git rebase` (no conflicts) fires the installed
`post-commit` hook for every replayed commit, not only `post-rewrite` once
at the end. That means `post-commit` already relinks each replayed
commit's own record as it goes; a rebase test that also expects
`post-rewrite`'s relink to find stale content to prune has to either (a)
work with disjoint files/records so replay never collides on
`docs/decisions/*.md` mid-rebase (the end-to-end test above), or (b)
suppress `post-commit`'s replay-time relinking with `SCRIBE_SKIP_HOOKS=1`
to isolate `post-rewrite`'s own contribution (the surgical test above). A
commit whose own patch touches `docs/decisions/*.md` (for example a
"docs: add record" commit, or a commit made only to snapshot the dirty
backlinks `post-commit` leaves unstaged) reliably conflicts if it sits in
the same rebased range as an implementing commit ahead of it, because the
literal file content it wants to introduce collides with what
`post-commit` has already written into the (unstaged) working tree during
replay. This is a pre-existing property of `post-commit`'s design (it
writes files but never stages them), not something introduced by this
change, and it would affect a real user's multi-commit rebase over
decision-touching history the same way. Filed here rather than fixed,
since fixing it (for example, having `post-commit` stage its own writes)
is a separate design decision outside Q3's scope.

## Suite count

Baseline before this change: `411 passed, 3 skipped`. After: `415 passed,
3 skipped` (4 new tests in `test_githooks.py`; `test_init.py`'s count is
unchanged at 23, since the renamed test replaces the old one one-for-one).

## Proposed commit message

```
feat: Add the post-rewrite hook so amend and rebase relink automatically

Installs a fourth scribe-managed git hook that reuses `scribe relink`'s
logic after `git commit --amend` or `git rebase`, so implementation_links
stay current without a manual `scribe relink`; `scribe init` now installs
four hook shims instead of three.
```

## I-lines

- I-Q3-1. `post_rewrite.run` calls `run_relink(root)` unconditionally
  (subject to the guard and skip-hooks checks) rather than trying to use the
  old/new sha pairs on stdin to scope the relink. Reason: `run_relink`
  itself has no range option by design (plan/relink.py docstring) and always
  walks the whole history; parsing the stdin pairs to decide whether to run
  at all would duplicate matching logic `run_relink` already does
  internally, against the instruction not to duplicate its logic. stdin is
  still read (drained), just not parsed, so git is never left blocking on
  the pipe.
- I-Q3-2. Chose to read stdin defensively (catching `OSError`, `ValueError`,
  `AttributeError`, and checking `isatty()`/`None` first) rather than
  asserting a real pipe is always present. Reason: the module is also
  called directly by unit tests (not through a real git subprocess), where
  `sys.stdin` can be pytest's `DontReadFromInput` (raises `OSError` on
  `read()`) or, in principle, `None`; the existing `read_payload` helper in
  `src/scribe/hooks/launcher.py` already establishes this exact
  try/except-around-`stream.read()` pattern in this codebase for the
  Claude Code hook's JSON-on-stdin path, so this follows precedent rather
  than inventing a new one.
- I-Q3-3. The one-line notice `post_rewrite` prints on a successful,
  non-empty relink is `scribe: relinked <n> record(s) after <kind>; run git
  add docs/decisions ...`, deliberately worded like `post_commit`'s `scribe:
  linked <n> record(s) to <sha>; run git add docs/decisions ...` rather than
  reusing `run_relink`'s own per-record lines (`relinked <alias>: <n>
  commit(s)`) verbatim. Reason: the task asked for "the same one-line
  notice post-commit uses," and `run_relink`'s own lines are designed for
  `scribe relink`'s CLI output (one line per changed record, no count
  summary), not for a single hook-level notice; `<kind>` (`amend` or
  `rebase`) is substituted in place of `post_commit`'s commit sha since a
  rewrite notice is about the whole operation, not one commit.
- I-Q3-4. Did not add a `post-rewrite`-specific line to
  `chaining_instructions` (the `core.hooksPath` fallback message) beyond
  what `HOOK_NAMES` already drives automatically. Reason: that function
  already loops over `HOOK_NAMES` generically to build both the shim list
  and the manual chaining command list, so `post-rewrite` appears there for
  free; no test needed changing beyond the existing `for name in
  HOOK_NAMES` loop already used in `tests/test_init.py`.
- I-Q3-5. Left the `test_githooks.py` module docstring's "T11: the three
  git hooks" wording as-is rather than renaming it to "four." Reason: `T11`
  names a plan task id from the original build, not a live invariant any
  test enforces; renaming a historical label carried a risk of implying a
  plan-document edit that was out of scope, for a comment with no test
  dependency on the exact word "three."
- I-Q3-6. Flagged, but did not fix, the empirical finding that
  `post-commit` fires per replayed commit during a non-conflicting `git
  rebase` and can conflict with a same-range commit that patches
  `docs/decisions/*.md` (see the dedicated section above). Reason: out of
  Q3's scope (installing `post-rewrite`), and fixing it (e.g., having
  `post-commit` stage its own writes) is a design decision with its own
  tradeoffs the owner should see separately.
