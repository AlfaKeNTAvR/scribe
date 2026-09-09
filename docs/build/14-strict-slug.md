# Strict verdict-first slug (Codex strict)

Base: `docs/build/13-codex-alias-analysis.md` (the chosen design), informed by
`docs/build/13-alias-analysis.md` (Fable's validation and skill-wording ideas;
the owner picked strict over its lenient/fallback variant).

## What changed

### `src/scribe/newrecord.py`

- Deleted `slugify`, `SLUG_MAX_LENGTH`, `SLUG_FALLBACK` (only caller was
  `create_record`; only other references were the two tests updated below and
  the historical `docs/build/13-alias-analysis.md`, left as-is).
- Deleted `_alias_candidates`, `MAX_ALIAS_ATTEMPTS`, and the now-unreachable
  `alias_reservation_failed` problem: nothing generates numbered suffixes
  anymore, so nothing needs an attempt cap. Dropped the now-unused
  `collections.abc.Iterator` import.
- Added `SLUG_VERBS` (module-level tuple, the exact 27 verbs from the brief,
  unchanged), `SLUG_FILLER_WORDS`, `SLUG_MIN_WORDS` / `SLUG_MAX_WORDS` (3, 6),
  `SLUG_MAX_CHARS` (40), and `validate_slug(slug)`, which raises `SpecError`
  naming the specific rule broken (missing key, too long, bad shape/hyphen
  placement, too few words, too many words, first word not a verdict verb,
  filler word present) instead of one combined regex message, so a caller
  finds a mismatched fixture is not a red flag. `SPEC_FRONT_MATTER_KEYS` gains
  `"slug"`.
- `alias_stem` is unchanged. `unique_alias(store, slug, today)` no longer
  generates `-2`, `-3` candidates: it raises `SpecError` the moment the
  computed `D-YYMMDD-<slug>` file already exists, asking for a more specific
  slug. `_write_record_exclusive` no longer retries suffixes either: it
  attempts exactly that one filename under `os.O_EXCL` and raises the same
  `SpecError` message on a race (another writer wins between the check and
  the write), rather than falling back to `-2`.
- `create_record` calls `validate_slug(spec.get("slug"))` before acquiring the
  ledger lock (so an obviously-bad spec never touches the lock), then
  `unique_alias` inside the lock as before. `build_front_matter` needs no new
  code to drop `slug` from the stored record: the existing final key filter
  (`{key: values[key] for key in KEYS if key != "history"}`) already excludes
  it, since `schema.KEYS` has no `"slug"` entry and never gets one.

### `src/scribe/cli.py`

`_new_command` wraps the `create_record` call in its own `try/except
SpecError`, printing `f"{args.spec}: {exc}"` then `"no record written"` and
returning 1 -- a second, separate `try` from the existing one around
`load_spec`, so an unrelated spec-loading failure (bad JSON, unknown key)
keeps its original output exactly as before.

### Fixtures

`tests/fixtures/new_spec.json`, `new_spec_supersedes.json`, and
`check_spec_supersedes.json` each gained a `slug` naming their fixture's own
decision: `require-json-spec-file`, `record-supersession-after-write`,
`block-unreviewed-successor-merge`. No other spec fixture exists in this
worktree (`rg` found only these three; there is no `scribe-playground` copy
here). `tests/test_check.py`'s `SUCCESSOR_SLUG` and `tests/test_ratify.py`'s
`SUCCESSOR_SLUG` were updated to the new slugs (previously the title, run
through the now-deleted `slugify`); `test_check.py`'s
`test_a_ratification_added_to_the_target_after_the_fork_is_honoured` now reads
the predecessor's slug straight from the fixture instead of calling
`slugify(title)`.

### `tests/test_new.py`

Removed `test_slugify_lowercases_collapses_and_trims` (tested the deleted
function) and the two suffix tests
(`test_new_twice_with_the_same_title_appends_a_suffix`,
`test_new_alias_race_with_a_pre_created_file_advances_to_the_next_suffix`),
replaced by:

- `test_new_requires_a_slug` -- drop `slug` from the spec. Fails on old code
  on `assert code == 1` (old code has no `slug` concept, writes normally,
  exits 0).
- `test_new_slug_needs_at_least_three_words` -- `slug: "run-quick"`. Fails on
  old code on `assert "at least 3" in stdout` (old code rejects the spec too,
  but for `unknown spec keys: slug`, a different message).
- `test_new_slug_rejects_more_than_six_words` -- 7-word slug. Fails on old
  code on `assert "at most 6" in stdout` (same old-code reason as above).
- `test_new_slug_rejects_more_than_forty_characters` -- 42-character,
  otherwise-valid slug. Fails on old code on `assert "at most 40" in stdout`.
- `test_new_slug_rejects_bad_characters` -- repeated hyphen. Fails on old code
  on `assert "repeated hyphen" in stdout`.
- `test_new_slug_first_word_must_be_a_verdict_verb` -- `"topic-json-spec-file"`.
  Fails on old code on `assert "verdict verb" in stdout`.
- `test_new_slug_rejects_filler_tokens_anywhere` -- `"keep-the-json-spec"`
  (valid verb, filler mid-slug). Fails on old code on
  `assert "filler word" in stdout`.
- `test_new_slug_collision_refuses_with_a_more_specific_slug_message` -- a
  file already sits at today's `D-YYMMDD-require-json-spec-file.md`. Fails on
  old code on `assert code == 1` (old code silently appends `-2` and exits 0;
  new code refuses instead of choosing a name for you).
- `test_new_alias_race_raises_the_same_collision_message` -- kept from the
  deleted suffix test, retargeted: `unique_alias` is monkeypatched to a
  filename another writer already created, and the assertions now expect the
  same collision `SpecError` (via exclusive create) rather than a `-2`
  fallback. Fails on old code on `assert code == 1`.
- `test_new_slug_forms_the_alias` -- happy path: asserts
  `record.data["alias"] == f"D-{stamp}-{slug}"` verbatim, no suffix.

Every `assert code == 1` / `assert "<phrase>" in stdout` case above also
asserts `record_files(tmp_repo) == before` (a before/after snapshot, since
`tmp_repo` starts with the three seed records, not zero).

### `tests/test_githooks.py`

`new_pending` gained an optional `slug` parameter (default: the fixture's own
slug). Four tests create two or more records in the same repo on the same day
by title alone; each now passes its own explicit `slug` so the aliases no
longer collide now that nothing auto-suffixes: the `Batch pending record {i}`
loop (`slug=f"batch-pending-record-{i}"`), the two rebase tests'
`first`/`second` pair (`record-first-rebase-item` /
`record-second-rebase-item`), and the amend test's `second`
(`record-second-decision-after-amend`). `tests/test_deferred.py`'s
`@pytest.mark.skip`-marked two-worktree test also creates several records
from one spec by title alone and would hit the same collision if ever
unskipped; left untouched per that file's own "no task may un-skip or modify
another task's test" rule, flagged here for whoever unskips it.

### `skills/decide/SKILL.md`

Added `slug` to the front-matter key list and the JSON example (right after
`title`), and the exact paragraph the brief specified, under "Rules for the
spec".

### `README.md`

One paragraph in "Record format" stating the alias rule (required `slug`,
verb list in `newrecord.SLUG_VERBS`, no automatic suffixing, refuses on
collision) and that every alias written before this change is unaffected and
still validates against the unchanged `schema.ALIAS_RE`.

## Decisions

- `I-H1-1`: Implemented the brief's single regex
  (`^[a-z0-9]+(?:-[a-z0-9]+){2,5}$`) as separate checks (length, then shape,
  then word-count floor, then word-count ceiling, then verb, then filler)
  instead of one `fullmatch`, so "too few words," "too many words," and "bad
  characters" each get their own message and their own test can assert
  exactly which rule fired. A comment next to `_SLUG_SHAPE_RE` documents that
  the two checks together are equivalent to the one regex.
- `I-H1-2`: `SLUG_VERBS` is exactly the 27 verbs listed in the brief, in the
  same order, with nothing added or removed.
- `I-H1-3`: `SLUG_FILLER_WORDS` is exactly the 9 filler tokens listed in the
  brief (`the a an its and or of to in`), nothing added or removed.
- `I-H1-4`: The collision message ("a record with alias `<stem>` already
  exists; choose a more specific slug") is shared verbatim between
  `unique_alias`'s pre-check and `_write_record_exclusive`'s `O_EXCL` race
  path, per the brief ("it now fails with the same message on a race").
- `I-H1-5`: `cli.py` wraps `create_record` in its own `try/except SpecError`,
  separate from the existing one around `load_spec`, so a pre-existing
  load-spec failure (bad JSON, unknown key) keeps printing exactly what it
  printed before -- only the new slug/collision failures gained the second
  `"no record written"` line.
- `I-H1-6`: No `values.pop("slug", None)` needed in `build_front_matter`:
  `schema.KEYS` never had a `"slug"` entry, so the existing final
  `{key: values[key] for key in KEYS if key != "history"}` filter already
  drops it. Left a comment instead of dead code.
- `I-H1-7`: Fixture slugs were chosen to summarize each fixture's own
  `decision` text, not its title, matching the skill's own instruction:
  `require-json-spec-file`, `record-supersession-after-write`,
  `block-unreviewed-successor-merge`.
- `I-H1-8`: The collision test keeps `slug` in the colliding spec (rather than
  omitting it) so new code actually reaches the collision-check path being
  tested; this means the "fails on old code" contrast for that test is via
  `unknown spec keys: slug` (old code) vs. a real `-2` write (also old code,
  different spec shape) rather than a single clean before/after pair. Both
  assertions in the test (`code == 1`, message text) fail on old code either
  way; noted here since it is a slightly indirect contrast, not a defect.
- `I-H1-9`: `tests/test_deferred.py`'s skipped two-worktree test was left
  untouched (would need per-title slugs if ever unskipped) because that
  file's own module docstring forbids another task from modifying its tests.

## Test run

- Targeted runs before the full suite, all passing: `tests/test_new.py` (27),
  `tests/test_check.py` (33), `tests/test_ratify.py` (20),
  `tests/test_githooks.py` (25, after the `new_pending` slug fix below).
- Full suite: `uv run --frozen pytest -q -p no:cacheprovider` (187.67 s, ran
  with a 450 s timeout): 485 passed, 3 skipped (the pre-existing deferred
  tests in `tests/test_deferred.py`). `tests/test_timing.py` passed in this
  same run; no separate rerun was needed.
- `git diff --check`: clean.
- Searched `src tests skills README.md` for em dash and en dash characters
  with `rg`: no matches.

## Proposed commit message

```
feat: Require an agent-written, verdict-first slug for scribe new

scribe new derived the alias from the first 40 characters of the title,
producing aliases like D-260909-the-git-hooks-keep-reading-records-and-a
that carry no verdict. The spec now requires a slug (3 to 6 words, a
verdict verb first, no filler, at most 40 characters); the alias becomes
D-YYMMDD-<slug> verbatim, and a collision refuses with a message asking
for a more specific slug instead of silently appending -2. Existing
records and their aliases are untouched: schema.ALIAS_RE and the 8-to-60
stored-alias length rule are unchanged; this only tightens what scribe
new itself accepts.
```

DONE: 485 passed, 3 skipped
