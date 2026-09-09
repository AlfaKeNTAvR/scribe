# Batch B, Item 5 report (worktree v21)

Written from the worktree /home/alfakentavr/scribe-wt/v21, branch
nikita/fix/batch-b-v21, base commit a4a721a. Per the deviation instructions
for this worktree, this file replaces the shared
docs/build/09-batch-b-report.md section and AUTONOMOUS_DECISIONS append that
step10_prompt.txt otherwise directs to. The main session renumbers the
I-lines below when folding this into the shared files.

## Item 5 (V21)

V21, "subdirectory start": live testing (docs/build/pipeline/step8_deny_rule_test.sh)
showed that no project settings (`.claude/settings.json` or
`settings.local.json`, whether the rule is `/relative`, `**/any-depth`, or
`//absolute`) load when Claude Code starts in a subdirectory of the
repository. The `Edit(/docs/decisions/RATIFICATIONS.jsonl)` deny rule
therefore only protects sessions started at the repository root, silently,
with no signal to the user. This item adds three advisory-only surfaces of
that limitation; none of them make the rule load below the root, since that
is not fixable from inside the plugin.

Files changed:
- `src/scribe/hooks/session_start.py`: new `subdirectory_hint(cwd, root)`
  helper; `handle()` now compares `payload_cwd(payload)` against
  `repo_root(payload)` and, when they differ, prepends the hint line to
  `additionalContext` (still exit 0, still advisory; the existing
  unreviewed-queue message is now appended after the hint rather than being
  the only possible line).
- `src/scribe/init_repo.py`: `follow_ups()` always appends a next-steps line
  naming the repository root and the user-settings workaround.
- `README.md`: the ratification-model paragraph now states that the leading
  `/` anchors at the session's primary working directory (not the repository
  root, which is what it said before and what V21 found to be wrong), that no
  project settings load below the root at all, and that a session that must
  start below the root should add `Edit(**/docs/decisions/RATIFICATIONS.jsonl)`
  to the user's own settings instead.
- `tests/test_hook_session.py`: two new tests.
- `tests/test_init.py`: one new test.

Test names and the assertion that fails on the old code:
- `test_session_start_hints_when_started_below_repo_root` (new) - asserts
  `additionalContext` contains the subdirectory-start hint (root path,
  "not active here", "start Claude at <root>", and the
  `Edit(**/docs/decisions/RATIFICATIONS.jsonl)` suggestion) when the payload
  `cwd` is a subdirectory of the repo. Fails on the old `handle()`, which
  never looks at `payload_cwd` and returns `None` for an empty review queue
  regardless of where the session started.
- `test_session_start_root_cwd_has_no_subdirectory_hint` (new) - asserts the
  hint text is absent when the payload `cwd` equals the repository root.
  This is the negative case; it does not fail on the old code (the old code
  never emits the hint at all) but is included per the task's requirement to
  test both directions explicitly, and it guards the new code against
  emitting the hint unconditionally.
- `test_init_next_steps_hint_the_subdirectory_start_limitation` (new) -
  asserts `scribe init`'s stdout contains a next-steps line naming the
  repository root and the `Edit(**/docs/decisions/RATIFICATIONS.jsonl)`
  workaround. Fails on the old `follow_ups()`, which never mentions the
  subdirectory-start limitation.

No existing test encoded the defect; no existing test needed to change to
stay green (verified: `test_second_run_is_unchanged_everywhere` still passes
because the new next-steps line uses the same `"  - "` prefix as the other
follow-up lines, which that test's `scribe init: ` prefix filter already
excludes).

Suite count after this item: 392 passed, 3 skipped (was 389 passed, 3
skipped before; +3 for the tests above).

Proposed commit message:

```
fix: Warn when a session cannot enforce the ratification deny rule

Live testing showed no project settings load when Claude Code starts
below the repository root, so the RATIFICATIONS.jsonl deny rule is
silently inactive there. SessionStart and scribe init now say so, and
README states the real anchor and the user-settings workaround.
```

## Decisions (I-V21-*)

- I-V21-1: Put the subdirectory check in `session_start.py` rather than a
  shared helper module. `init_repo.py` needed a similar but statically-worded
  reminder (it has no live session `cwd` to compare against; it always runs
  at the resolved repository root), so the two messages are separate literals
  rather than a shared formatting function. Revisit if a third call site
  needs the same wording verbatim.
- I-V21-2: `handle()` in `session_start.py` no longer returns `None`
  unconditionally when the review queue is empty; it now returns `None` only
  when both the subdirectory hint and the queue message are absent. This
  changes behavior for a root-started session with an empty queue (still
  silent, unchanged) and for a subdirectory-started session with an empty
  queue (now prints the hint, previously silent). No existing test asserted
  silence for a subdirectory-started session, so nothing broke, but this is
  the one behavioral change worth flagging: sessions started below the root
  will now always see one line of `additionalContext` on the first prompt,
  even with zero unreviewed decisions.
- I-V21-3: Chose to compare `payload_cwd(payload)` (the raw, resolved
  session cwd) against `repo_root(payload)` (the git toplevel) rather than
  re-deriving "is this the root" some other way, since `launcher.py` already
  exposes both and both are already resolved `Path` objects, so `==` is a
  safe comparison without extra normalization.
- I-V21-4: `scribe init`'s hint is unconditional (always appended to
  next-steps), not gated on whether the current invocation happened to run
  from a subdirectory, since `run_init` always resolves `start` up to the
  repository root before doing anything (`gitutil.toplevel(start)`), so there
  is no "started below root" signal available inside `init` itself to
  condition on. The hint is forward-looking advice for future sessions, not a
  diagnosis of the current one.
- I-V21-5: Did not write anything to `.claude/settings.json` or any user
  settings file, per the task's explicit "do not write user settings"; the
  README and the two hints only name the rule the user would need to add by
  hand (`Edit(**/docs/decisions/RATIFICATIONS.jsonl)`, no leading slash, so
  it does not anchor to a settings source and instead matches at any depth
  from wherever the user's own settings file lives).

## Remaining

None. Item 5 is complete: code, tests, README, suite green.

## Commands run and their output

`uv run pytest -q`:
```
392 passed, 3 skipped in 76.36s (0:01:16)
```

`uv run scribe lint`:
```
3 records, 0 errors, 0 warnings, 0 info
```

`uv run scribe index --check`:
```
docs/decisions/INDEX.md is up to date
```

`uv run scribe validate docs/decisions`:
```
3 records, 0 errors, 0 warnings
```

`uv run scribe check --base 3a5b1d2`:
```
scribe check: ok
```

the required em-dash/en-dash `rg` scan, run with `--hidden` but without the
`--glob '!.git'` clause (that clause was refused by this session's
worktree-safety command filter, which treats any occurrence of the substring
"git" in a command as a git invocation to verify; ripgrep already excludes
the `.git` directory by default, so the flag was dropped rather than worked
around):
```
(no output, exit 1 = no matches)
```

`git diff --check`:
```
(no output, exit 0)
```

Files changed (absolute paths):
- /home/alfakentavr/scribe-wt/v21/README.md
- /home/alfakentavr/scribe-wt/v21/src/scribe/hooks/session_start.py
- /home/alfakentavr/scribe-wt/v21/src/scribe/init_repo.py
- /home/alfakentavr/scribe-wt/v21/tests/test_hook_session.py
- /home/alfakentavr/scribe-wt/v21/tests/test_init.py
- /home/alfakentavr/scribe-wt/v21/docs/build/09-batch-b-item-5.md (this report)

DONE: 392 passed, 3 skipped
