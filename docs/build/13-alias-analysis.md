# Alias analysis

Scope: how `scribe new` names records (`slugify`, `alias_stem`, `unique_alias`
in src/scribe/newrecord.py), whether the aliases mean anything, and what to
change. Eight real records: seven in docs/decisions, one in
scribe-playground/03-refactor.

## Existing aliases

Len is the whole key; the slug follows the 9-character `D-YYMMDD-` prefix and
is cut at 40.

| Alias | Len | Named by | Rating |
|---|---|---|---|
| D-260908-one-way-door-defer-not-stop | 36 | hand | informative: subject `one-way-door`, verdict `defer`, rejected option `not-stop`; no filler |
| D-260908-unreviewed-may-supersede-ratified | 42 | hand | informative: subject, modal verb, object; every word is a ledger term |
| D-260908-verbatim-quote-is-the-evidence | 39 | hand | informative: `is-the` is filler (6 chars) but it reads as a sentence |
| D-260909-history-replay-validation-every-changed | 49 | slugify | useless: cut lands inside the parenthetical; `deferred` is at character 95 of the title, so the alias cannot say whether the check was built or skipped |
| D-260909-post-commit-skips-its-backlink-write-whi | 49 | slugify | weak: `skips-backlink-write` is a verdict, `its` filler, `whi` a chopped `while`, condition `during rebase` lost |
| D-260909-tests-keep-copying-the-live-docs-decisio | 49 | slugify | weak: verdict `keep-copying` survives, `the` filler, `decisio` chopped, `as fixture` lost |
| D-260909-the-git-hooks-keep-reading-records-and-a | 49 | slugify | useless: leading `the`, `keep-reading-records` is what hooks always do, verdict (`working tree, not staged index`) past the cut, tail `and-a` is noise |
| D-260909-non-positive-width-height-or-radius-rais | 49 | hand per brief, byte-identical to `slugify(title)` | weak: 34 chars of subject enumeration, `or` filler, `raises ValueError inline` chopped to `rais` |

Pattern: every slugify alias fills all 40 characters, four of five end
mid-word, and none contains the verdict, because the titles put the mechanism
first and the ruling last. The cut length is not the problem; the title is the
wrong source.

## What the seeds do right

- Grammar: each is a clause, subject then verdict (`one-way-door: defer, not
  stop`; `unreviewed may supersede ratified`; `verbatim quote is the
  evidence`). The reader gets the ruling, not the topic.
- Verdict word: `defer`, `supersede`, `is-the-evidence`. One also names the
  rejected option (`not-stop`), the densest information in the ledger.
- Length: slugs of 27, 33 and 30 characters, four to five words, no chopped
  word. They stop when the meaning is complete.
- Separate from the title: titles are 100 to 160 character sentences with the
  mechanism; the alias is a written headline, not a compression. Its words
  are ledger vocabulary (one-way-door, unreviewed, ratified, verbatim), so a
  grep for the concept hits the file.

## Fixed width

Where equal length actually matters:

- INDEX.md rows are `alias | state | review | by | affects | title` as plain
  list items. In a terminal, padding aligns column 2 only; later columns drift
  because `proposed` and `implemented` differ in length. On GitHub spaces
  collapse in a proportional font, so neither cut nor padding aligns anything.
  Today's INDEX is already misaligned (36, 42, 39 and 49 character aliases).
- Trailers `Decision: <alias> <ulid>`: a fixed width would align the ULIDs in
  `git log --format=%(trailers)`, but only if every alias hits the cap, which
  the seeds do not.
- `ls docs/decisions`: sorted by the date prefix; slug length is irrelevant.
- Hook injection lines are capped (`MAX_LINE_CHARS`); a 49-character alias
  spends budget the title needs.
- Typing `scribe lookup <alias>` or `supersedes:`: a key ending in `whi` is
  hard to type and remember.

Conclusion: keep the hard cap (40 slug characters, 49 alias) for line budgets
and typing, drop the idea that aliases should reach it, and align in the
renderer (`ljust` in `_active_line`/`_queue_line` for terminals, or a
markdown table for GitHub, which changes the lines `tests/test_index.py`
asserts with `startswith`). Never cut mid-word: cutting at the last hyphen
before 40 alone removes `whi`, `decisio`, `and-a` and `rais`.

## Options

1. Agent-written `slug` field (the proposal). For: the agent knows the verdict
   at write time; the seeds prove a written headline works. Against:
   validation checks shape, not meaning; a model asked for "3 to 6 words"
   paraphrases the title unless told to write the ruling; `required` breaks
   the `tests/fixtures/new_spec*.json` specs and every hand-written spec, and
   a fallback contradicts `required`. The proposed stopword list includes
   `keep`, the verdict word in three of the four 2026-09-09 titles (`keep
   reading`, `keep copying`, `keeps its checks`); dropping it deletes the
   ruling.
2. Verdict-first template `<verb>-<object>` enforced by a verb list. For: the
   INDEX reads as a list of rulings, as with git's imperative subjects.
   Against: two of three seeds are subject-first
   (`unreviewed-may-supersede-ratified`) and would be rejected; a verb list
   is a maintenance chore. Usable as a warning, not an error.
3. Slug from `decision` text. Worked by hand on the four agent records:
   `scribe-check-keeps-its-current-history-c`, `proposed-not-yet-implemented-
   post-commit`, `tests-conftest-py-copies-only-the-three`, `commit-msg-and-
   prepare-commit-msg-keep-l`. Worse: the paragraph opens with
   implementation detail. Reject.
4. Stopword stripping only. Worked by hand (list minus `keep`, plus
   parenthetical removal and word-boundary cut): `history-replay-validation-
   deferred-until`, `post-commit-skips-backlink-write-while`, `tests-keep-
   copying-live-docs-decisions-ledger`, `git-hooks-keep-reading-records-
   attestations`, `non-positive-width-height-radius-raises`. Three of five
   become informative, two stay weak (condition or contrast still missing).
   Deterministic, zero agent burden, but it cannot move a verdict forward
   when the title places it late.
5. Two-part `D-YYMMDD-<area>-<verb-object>`. For: groups by subsystem within
   a date, like a Conventional Commits scope. Against: area already lives in
   `tags` and `affects`, which are mutable; an immutable copy needs a
   controlled vocabulary (`hook`/`hooks`/`githooks`) and costs 5 to 10 of the
   40 characters. Allow an area word, do not require one.
6. Prior art. ADR tools (adr-tools, log4brains, MADR) use `NNNN-full-title.md`
   uncut, and MADR tells authors to write the title as the decision in short
   form ("Use Markdown ADRs"), which is why those filenames read well. Jira
   keys (`PROJ-123`) are opaque and aligned by construction; scribe already
   has that key, the ULID, so a meaningless alias is a second opaque key.
   Conventional Commits and git: a 50-character imperative subject apart from
   the body. All put a short written headline next to the long text; none
   derives it.

## Recommendation

Adopt the `slug` field, but as the agent-written headline of the ruling, not
a short title: the skill says "the verdict, with a verb, as the seeds do",
and the validator checks shape only. Make it optional in the schema and
mandatory in the skill: when absent, `scribe new` derives one with the
improved fallback (parentheticals removed, stopwords without `keep`, cut at a
word boundary) and warns `slug_derived`, so hand-written specs and the test
fixtures keep working while a skipped field stays visible. Keep the
40-character slug cap and the 60-character alias cap in `ALIAS_RE`; aim for
20 to 35 characters and let the renderer pad. This keeps the fixed column
where it is visible without truncating a key, and restores what made the
seeds good: someone writing the ruling in five words.

## Migration

Aliases are filenames (`alias_filename_mismatch`), trailer tokens on six
commits in history, and `SEED_RECORD_ALIASES` in tests/conftest.py. A rename
is a delete plus an add, and `record_deleted` fails CI with no escape; fixing
trailers means rewriting published history, which the owner's rules forbid.

- The three seeds: leave alone, they are the model to copy.
- The four 2026-09-09 records: leave alone. Superseding each with a
  better-named copy would retire four records for cosmetics and double the
  queue. They carry review dates (2026-10-07, 2026-12-08); each successor
  gets a proper slug and the old alias retires naturally. `scribe lookup`
  resolves the ULID too, so nothing depends on the alias reading well.
- The playground record: a scratch tree, not a ledger. Reset it or leave it.
- No rename or `display_alias` feature: two keys per record reopens
  immutability.

## Validation and skill wording

Validator rules for `slug` when present (errors unless noted):

- Characters: `^[a-z0-9]+(?:-[a-z0-9]+)*$` (no leading, trailing or double
  hyphen).
- Length: 8 to 40 characters, 2 to 7 words.
- Leading word not in `the a an this that about on how decision record`.
- No stopword from `the a an its of to in and or is are` anywhere; contrast
  words (`not`, `over`, `instead`) stay allowed.
- Verb presence: warning only, when no word is in a short verdict list
  (`keep defer skip pin use drop reject allow deny supersede require prefer
  raise return`); the seeds show subject-first slugs are fine.
- Uniqueness: keep the `-2` suffix but warn `slug_collision`: two same-day
  records with the same ruling usually means a duplicate record.
- Fallback: when `slug` is absent, derive it and warn `slug_derived` with the
  derived value.

Wording for skills/decide/SKILL.md, under "Rules for the spec":

> - `slug` is the alias headline, 2 to 6 words, 8 to 40 characters, lowercase
>   words joined by hyphens. Write the ruling, not the topic: name what was
>   decided so a reader of `INDEX.md` or `git log` knows the verdict without
>   opening the file. Include the verb (`keep`, `defer`, `skip`, `pin`,
>   `supersede`), and when a rejected alternative is the point, name it
>   (`defer-not-stop`). Do not copy the title, do not start with `the`, and
>   do not describe the mechanism; the title carries that. Good:
>   `defer-history-replay-check`, `hooks-read-working-tree-not-index`,
>   `pin-test-fixture-to-seeds`, `skip-backlink-write-during-rebase`. Bad:
>   `history-replay-validation-every-changed`, `the-git-hooks-keep-reading`.
>   If you leave it out, scribe derives one from the title and warns; that
>   alias is usually worse, so always write it.

And in the example spec: `"slug": "defer-history-replay-check",` directly
under `title`.
