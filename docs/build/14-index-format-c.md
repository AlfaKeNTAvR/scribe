# 14: INDEX.md format C (heading per record)

Branch `nikita/feat/index-format-c`, base `5e2c050`. Implements the owner-approved
format C from `docs/build/13-index-preview-c.md`: one `### ` heading per record
with one `- field: value` bullet per line, instead of the old one-line
pipe-separated record.

## Confirmed: INDEX.md is read only, no other module parses its line shape

`rg -n "INDEX_FILENAME\|index_path\|Review queue" src` and a follow-up sweep for
`INDEX.md`, `render_index`, `write_index`, `check_index` turned up:

- `src/scribe/index.py` - the generator itself.
- `src/scribe/check.py` (`check_index`) - compares the on-disk file against a
  freshly rendered string byte for byte; never inspects individual lines.
- `src/scribe/cli.py`, `src/scribe/lint.py`, `src/scribe/ratify.py`,
  `src/scribe/relink.py`, `src/scribe/init_repo.py`,
  `src/scribe/githooks/post_commit.py`, `src/scribe/newrecord.py` - all call
  `write_index`/`locked_write_index`/`locked_check_index` and never read the
  result back structurally.
- `src/scribe/hooks/session_start.py` - counts the review queue from front
  matter it loads directly from each record file (`load_front_matters`), not
  from INDEX.md; its hint text just tells the human to open the file.

No module parses INDEX.md's rendered line format. The change below is safe to
make without touching any consumer other than the tests that pin the format
for humans.

## What changed

`src/scribe/index.py`:

- Removed `_queue_line`, `_active_line`, `_retired_line`, `_join_fields`,
  `_title_text`.
- Added `_record_fields` (the six standard bullets: state, by, review, title,
  affects if any, regret if any), `_record_block` (heading plus bullet lines),
  and `_queue_block` / `_active_block` / `_retired_block` (heading format and
  any extra bullet per section).
- `_affects_text` separator changed from `" "` to `", "`.
- `render_index` now joins per-record blocks with `"\n\n"` inside each section
  instead of per-record lines with `"\n"`; the three top-level section
  headings, the queue note, and the overall `"\n\n".join(blocks) + "\n"`
  structure are unchanged.
- `_sort_newest_first`, `_queue_groups`, `_retired_state`,
  `_successor_aliases`, `write_index`, `check_index`, `locked_write_index`,
  `locked_check_index` are untouched in behaviour.

Regenerated `docs/decisions/INDEX.md` with `uv run --frozen scribe index`: the
result is byte-for-byte identical to `docs/build/13-index-preview-c.md`
(`diff` reports no difference). `uv run --frozen scribe index --check`
reports "up to date" afterwards, confirming determinism.

`README.md`: the sentence at "Record format" describing INDEX.md only said
"generated, never hand-edited" with no layout detail to update in place, so a
clause was added describing the heading-per-record, bullet-per-line format
(see I-H2-6 below).

## Tests changed

`tests/test_index.py`:

- `section_lines` (collected raw non-blank lines under a heading) replaced
  with `section_blocks` (splits on `### ` headings into per-record line
  lists). Fails on the old renderer because the old output never contains a
  `### ` line, so `section_blocks` would return an empty list and every
  `queue[0]` / `active[0]` / etc. access raises `IndexError`.
- `test_review_queue_holds_every_unreviewed_record_in_group_order`: heading
  assertions changed from `"1. [supersedes ratified] ..."` prefix checks to
  `"### 1. ... [supersedes ratified]"` exact-heading checks.
- `test_queue_line_carries_states_affects_and_title` renamed
  `test_queue_block_carries_states_affects_and_title`: asserts the full
  7-line block (`supersedes`, `state`, `by`, `review`, `title`, `affects`)
  instead of one pipe-joined string.
- `test_active_holds_only_effectively_attested_authority`,
  `test_rejected_successor_leaves_its_predecessor_active`,
  `test_unattested_record_is_not_active`,
  `test_retired_states_cover_edge_rejected_expired_and_stale`,
  `test_backtracked_record_appears_in_retired_not_vanished`: all switched from
  pipe-field indexing (`line.split(" | ")[0]`) to block/heading indexing.
- Added `test_render_matches_the_format_c_heading_per_record_layout`: builds a
  3-record fixture store (a queue record that supersedes a ratified
  predecessor, one plain active record, the now-retired predecessor) and
  asserts `render_index` produces one exact, pinned multi-line string
  covering every bullet kind (`supersedes`, `state`, `by`, `review`, `title`,
  `affects`, `regret`, `retired`) and the blank-line block separator. Fails on
  the old renderer, which produces a completely different pipe-separated
  string.

`tests/test_ratify.py` (`test_rejecting_the_successor_restores_the_predecessor`):
updated two assertions from `"<alias> | superseded by <successor>"` /
`"<alias> | proposed | ratified"` to the heading+bullet form
(`"### <alias>\n- retired: superseded by <successor>"` /
`"### <alias>\n- state: proposed, ratified"`).

`tests/test_new.py` (`test_new_with_supersedes_puts_the_record_first_in_the_review_queue`):
updated the queue-heading prefix check to `"### 1. "`, the `supersedes` check
to `"- supersedes: <alias>"`, and the retired check to the heading+bullet
form.

`tests/test_githooks.py` (`test_post_commit_retry_finishes_after_each_persistence_step`):
the checked record can land either in Active decisions (plain `### <alias>`
heading) or still in the review queue (`### <n>. <alias>` heading) depending
on `review_state`, so the assertion uses a regex tolerating the optional
numeral prefix instead of a fixed string.

`tests/test_deferred.py` (`test_two_worktree_supersede`, skip-marked, does not
run): updated for consistency to the same heading+bullet form, even though the
test itself stays skipped.

`tests/test_new.py`'s other INDEX.md assertion
(`test_new_regenerates_the_index_with_the_alias_in_the_review_queue`) and
`tests/test_lint.py`, `tests/test_init.py`'s INDEX.md checks needed no change:
they only check for an alias substring or a section heading, both still true
under the new format.

## Suite result

`uv run --frozen pytest -q -p no:cacheprovider`: 479 passed, 3 skipped, in
182.35 s. `tests/test_index.py` alone: 16 passed. No flake, no rerun needed.

`git diff --check`: clean (no whitespace errors).
- The em and en dash scan over src, tests, README and INDEX: no output.

## Decisions

- **I-H2-1**: The task text specifies the standard bullet order (state, by,
  review, title, affects, regret) but only says the queue's `supersedes`
  bullet and the retired section's `retired` bullet are added "plus" that set,
  without saying where. The fixture in `docs/build/13-index-preview-c.md` has
  zero examples of either case (no queue record supersedes a ratified record,
  and Retired is empty), so there was nothing to check the placement against.
  Chose to insert both as the first bullet, immediately under the heading,
  before `state`, since both are heading-level annotations (the heading text
  itself carries `[supersedes ratified]` or, implicitly, "this record is
  retired") and this placement is the same for both cases, keeping the
  renderer's insertion logic identical (`fields.insert(0, ...)`).
- **I-H2-2**: For retired records, decided the `- retired: <state>` bullet is
  additive to the standard six bullets (matching "plus a bullet" in the task
  text) rather than replacing the `state:` bullet. So a retired record shows
  both its retired-reason bullet and its normal `effective_state,
  review_state` bullet. This differs from the old renderer, which substituted
  the retired-reason string into the position the old `state` field occupied
  and dropped `review`/`affects`/`regret` outright (via `with_tail=False`
  plus no affects field at all). The new format shows more information per
  retired record than before; flagging this as a behavior change worth a
  glance even though it matches the literal spec text.
- **I-H2-3**: `_record_fields` always emits the `review:` bullet, even when
  the underlying `review` field is empty (renders as `- review: ` with
  nothing after the colon). This only happens in test fixtures that omit
  `review`; the schema requires `review` on every real record
  (`src/scribe/schema.py` line 44), so production INDEX.md never shows an
  empty review bullet. Kept the empty-render behavior rather than adding an
  omit-when-empty rule for `review` (unlike `affects`/`regret`), since the
  task's field list marks only `affects` and `regret` as omittable.
  `test_render_matches_the_format_c_heading_per_record_layout` and a few other
  fixture-based tests pin the resulting `"- review: "` line so this is
  visible and intentional, not an oversight.
- **I-H2-4**: `_record_block`/`_record_fields` is one function pair shared by
  all three sections (queue, active, retired) rather than three separate
  renderers, per the task's singular "the block renderer" and the existing
  DRY guidance (a pattern repeating 3+ times gets a shared abstraction).
  Section-specific behavior (numbering, the supersedes/retired marker and
  bullet) is layered on by three thin wrapper functions
  (`_queue_block`/`_active_block`/`_retired_block`).
- **I-H2-5**: Blocks within a section are joined with `"\n\n"` (one blank
  line between records), matching `docs/build/13-index-preview-c.md`
  byte-for-byte (confirmed with `diff` after `scribe index`). The top-level
  document structure (heading, generated-by line, three `## ` section
  headings, queue note) is unchanged from before.
- **I-H2-6**: README.md had no existing sentence describing INDEX.md's line
  format in enough detail to "update" in the literal sense (it only said
  "generated, never hand-edited"). Added one clause to that existing sentence
  describing the new heading-per-record, bullet-per-line layout, rather than
  inventing a new paragraph elsewhere.

## Proposed commit message

```
feat: Render INDEX.md as one heading per record instead of one pipe-separated line

INDEX.md was one long pipe-separated line per decision record, which VS Code's
editor could not usefully collapse. Replaces the per-record renderer in
src/scribe/index.py with a block renderer that emits a `###` heading per
record and one `- field: value` bullet per line (format C), matching
docs/build/13-index-preview-c.md byte for byte. Updates every test asserting
on the old line format and pins the new layout with a dedicated fixture test.
```

DONE: 479 passed, 3 skipped
