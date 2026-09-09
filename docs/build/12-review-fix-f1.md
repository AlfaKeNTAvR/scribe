# Review fix F1: denylist misses backslash-continued commands

Fixes docs/build/11-fable-final-review.md, "New defects" item 1: commit
3050f09 made `policy.matching_rules` split a Bash/PowerShell command on
newlines to keep a rule from reading across separate commands (the rm
boundary fix, docs/build/08-codex-review-batch-a.md "New defects", second
item; AUTONOMOUS_DECISIONS_09_08_2026.md I100-I110). That split did not know
about backslash line continuation, so a denylisted command split across
lines with a trailing `\` stopped matching its rule.

## What changed

`src/scribe/policy.py`:

- Added `LINE_CONTINUATION` (`\\\r?\n`) and `join_line_continuations`, which
  collapses a backslash immediately followed by an optional `\r` and `\n`
  into a single space.
- `matching_rules` now calls `join_line_continuations` on the command before
  the existing `re.split(r"\r?\n|;|&&|\|\||\|", ...)` and per-segment
  `collapse_whitespace`. A real, non-continued newline (no backslash before
  it) is untouched and still acts as a command boundary, so the rm
  boundary fix from 3050f09 is unaffected.

No change to `pre_tool_use_gate.py`: it only calls `policy.matching_rules`
and `policy.denied_rule`, so the fix is contained to `policy.py`.

## Tests added (`tests/test_hook_gate.py`)

All four live next to `test_matching_rules_reports_every_hit_in_order`.

- `test_denylist_matches_backslash_continued_git_push` - reviewer repro 1:
  `"git push origin main \\\n  --force"`. Fails on the old code with
  `AssertionError: assert None == 'git-push-force'` (verified by reverting
  `policy.py` to `git show HEAD:src/scribe/policy.py` and re-running).
- `test_denylist_matches_backslash_continued_rm` - reviewer repro 2:
  `"rm -rf \\\n  /tmp/x"`. Fails on the old code the same way:
  `assert None == 'rm-rf-outside-worktree'`.
- `test_denylist_matches_backslash_continued_crlf` - same continuation with
  a Windows CRLF line ending (`\\\r\n`), since PowerShell is one of the two
  gated tools. Fails on the old code: `assert None == 'git-push-force'`.
- `test_denylist_allows_rm_boundary_across_a_real_newline` - regression
  guard: `"rm build\nprintf '%s\\n' -rf /tmp/example"` (a plain, non-
  continued newline) must still return `None`. This one does **not** fail
  on the old code (see I-F1-3) - it passes on both, which is the point: it
  proves the fix does not reopen the boundary bug the newline split was
  originally added to close.

Verification method: copied the fixed `policy.py` aside, checked out
`git show HEAD:src/scribe/policy.py` in its place, ran
`pytest -k "backslash_continued or rm_boundary_across"` (3 failed, 1
passed, as listed above), then restored the fixed file.

## Suite results

- `uv run --frozen pytest -q -p no:cacheprovider tests/test_hook_gate.py`:
  101 passed.
- Full suite `uv run --frozen pytest -q -p no:cacheprovider`: 428 passed, 3
  skipped, in 138.97s.
- `git diff --check`: clean, no whitespace errors.
- The em and en dash scan over src and tests: no output.

## Decisions

- **I-F1-1**: Join continuations with a single space, not by deleting the
  backslash-newline outright. Real shell line continuation removes exactly
  the backslash and the newline, leaving any indentation on the next line
  intact; a space is enough here because every segment is run through
  `collapse_whitespace` right after, which collapses that indentation (and
  the inserted space) to one space anyway. Behaviorally identical, simpler
  regex.
- **I-F1-2**: Treat a backslash-newline inside quotes as a continuation too,
  same as bare code. Getting this shell-exact would need a quote-aware
  tokenizer; this gate only ever needs to widen a segment to catch more
  denylisted commands, never narrow one to miss them, so over-joining is
  the safe direction. Said explicitly in the code comment above
  `LINE_CONTINUATION`.
- **I-F1-3**: The rm-boundary regression test does not fail on the old
  code, unlike the task's general "each new test must fail on the old
  code" framing. This is not an oversight: the old code already treats
  every newline (continued or not) as a hard boundary, so it already
  returns `None` for that input, for a different (more aggressive, and now
  redundant) reason than the fix does. A test proving preservation of
  already-correct behavior cannot also be a red test on the code being
  preserved. Kept the test anyway since the task asked for it as a
  regression guard, and called out the discrepancy here instead of forcing
  a misleading "fails on old code" claim.
- **I-F1-4**: No CRLF-only (bare `\r` with no `\n`) continuation case added.
  Old Mac (pre-OS X) line endings are not a realistic input for Claude Code
  tool payloads or any shell scribe is expected to gate, and the task's
  Windows case is CRLF (`\r\n`), which `LINE_CONTINUATION` already covers.

## Proposed commit message

```
fix: Join backslash-continued lines before the denylist newline split

policy.matching_rules split every command on newlines to keep the rm
rule from reading past a command boundary (3050f09), but that split
ignored backslash line continuation, so a denylisted command written
across two lines with a trailing backslash (git push --force, rm -rf)
matched no rule. Join a backslash followed by an optional CR and a
newline into the same logical line before splitting, leaving a real,
non-continued newline as a boundary so the rm fix still holds.
```
