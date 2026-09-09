# Review fix G1: attestation integrity and authority (V5, V12)

Branch `nikita/fix/review-g1-attestation-authority`, base `49dcbf1`. Source of
the two gaps: `docs/build/11-fable-final-review.md` V5 and V12 (Batch B), and
the original wording in `docs/build/04b-codex-validation.md`.

## Gap 1 (V5): attestation lines were only checked for truthiness

`Store.attestation_line_problems` (`src/scribe/store.py`) previously required
each of `id, alias, verdict, by, at, via, body_sha256` to be truthy
(`not item.get(key)`) and nothing more. A line like
`{"id": ..., "by": 123, "at": "yesterday", "via": ["cli"]}` is truthy on every
required key and passed.

### What changed

- `src/scribe/schema.py`: added `attestation_item_problems(item) -> list[tuple[str, str]]`,
  plus the constants it needs (`REQUIRED_ATTESTATION_KEYS`, `ATTESTATION_VERDICTS`,
  `ATTESTATION_VIA_VALUES`, `ATTESTATION_SHA256_RE`). It checks, per field:
  - `id`: canonical ULID (`ulid.is_valid`, already used for record ids).
  - `alias`: a string.
  - `verdict`: one of `ratified`, `rejected` (the values `ratify.VERDICTS` writes).
  - `body_sha256`: a 64-character lowercase hex string (`^[0-9a-f]{64}$`).
  - `by`: a non-empty string.
  - `at`: an ISO-8601 UTC datetime, reusing the existing `_valid_datetime`
    (same helper `ratified_at` is checked against).
  - `via`: one of `skill`, `cli`, `hand-written` (the values `ratify.VIA_VALUES` writes).
  - `note`: a string or null, only if present (it is not a required key).
  Every check goes through `_is_str`/`_in_str_set` (already in schema.py),
  which test `isinstance(value, str)` before any membership or regex test, so
  a list or a dict in a field never raises `TypeError`: it is reported as a
  problem instead. Missing-key detection stays as `attestation_incomplete`,
  now with a companion `attestation_invalid_field` code for a present-but-wrong
  field. A field already reported missing is not also reported invalid.
- `src/scribe/store.py`: `attestation_line_problems` now calls
  `attestation_item_problems` per parsed line instead of only checking
  missing keys inline; the local `REQUIRED_ATTESTATION_KEYS` constant moved
  to `schema.py` (its natural owner now that the field checks live there).
- `src/scribe/schema.py`, `validate_record`: the existing `unattested_review_state`
  / `state_behind_attestation` block now treats an attestation with any
  `attestation_item_problems` as no attestation at all (see Gap 2, same fix).

### Tests (fail on old code as stated)

- `tests/test_store.py::test_attestation_line_problems_reports_an_invalid_field`
  (parametrized, one case per field: `id`, `alias`, `verdict`, `body_sha256`,
  `by`, `at`, `via`, `note`). Assertion that fails on old code:
  `[p.code for p in problems] == ["attestation_invalid_field"]`: the old code
  returns `[]` for every case (verified by checking out the pre-fix
  `store.py`/`schema.py` and re-running; all 8 cases failed with
  `assert [] == ['attestation_invalid_field']`).
- `tests/test_store.py::test_attestation_line_problems_accepts_the_real_ledger`:
  loads the live `docs/decisions/RATIFICATIONS.jsonl` and asserts
  `attestation_line_problems(text) == []`.
- `tests/test_check.py::test_appending_an_attestation_with_a_wrong_typed_field_fails`:
  end-to-end through `scribe check`. Assertion that fails on old code:
  `code == 1` and `"attestation_invalid_field" in stdout` (old code exits 0).
- `tests/test_schema.py::test_attestation_with_a_wrong_typed_field_does_not_satisfy_ratified_state`:
  end-to-end through `validate_record` (what `scribe validate` calls).
  Assertion that fails on old code: `"unattested_review_state" in {...}`: on
  old code the set is empty, because `by: 123`'s truthy verdict/body_sha256
  match was all the old check looked at (verified by checking out the pre-fix
  files: `assert 'unattested_review_state' in set()` fails).
- `tests/test_store.py::test_attestation_line_problems_reports_an_incomplete_line`:
  adjusted the fixture's `body_sha256` from `"a"` to `"a" * 64` so this test
  isolates missing-key detection from the new hex-format check (the old
  1-character value now also trips `attestation_invalid_field`, which the
  test's original intent, per its own docstring, was not testing).

## Gap 2 (V12): a malformed latest attestation still granted authority

`Store.effective_authority` only checked `latest.get("verdict")` and
`latest.get("body_sha256")` against the record. A bare pre-V5
`{id, verdict, body_sha256}` line matches both and granted authority even
though `attestation_line_problems` (Gap 1) would already fail that ledger in
`scribe check`.

### What changed

- `src/scribe/store.py`, `Store.effective_authority`: added
  `attestation_item_problems(latest)` to the deny conditions. A structurally
  invalid latest line is now treated as no authority, full stop: not as
  "fall back to an earlier valid line for this id."
- `Store.latest_attestation` is unchanged: it still returns the literal
  latest line, malformed or not. `ratify.apply_verdict`'s V10 recovery path
  reads that literal line to detect and repair a stalled ratification, and it
  is already gated by `ratify._ledger_broken` (which itself calls
  `attestation_line_problems` over the whole file) before it is ever reached,
  so no malformed line can exist there in practice. Filtering inside
  `latest_attestation` would have hidden the very state that recovery path
  needs to see. See I-G1-1.
- Every other authority consumer already goes through `effective_authority`
  and needed no direct change: `index.render_index`'s Active section
  (`store.effective_authority(record)`), `commit_msg.active_records`
  (same call), and the Bash gate's `pre_tool_use_gate.action_is_ratified`
  (same call). No separate "injection hook" reads `latest_attestation`
  directly for authority; grep confirmed only `pre_tool_use_gate.py` and it
  goes through `effective_authority`. See I-G1-2.
- `src/scribe/schema.py`, `validate_record`'s attestation block (shared with
  Gap 1): also guarded with `attestation_item_problems`, so a malformed
  attestation can no longer satisfy `unattested_review_state` by accident,
  and can no longer drive `state_behind_attestation` off a non-string
  `verdict` (which would otherwise crash `{"ratified": ..., "rejected": ...}.get(verdict, verdict)`
  on an unhashable value such as a list). See I-G1-3.

### Test (fails on old code as stated)

- `tests/test_store.py::test_effective_authority_requires_a_structurally_valid_latest_line`:
  writes the pre-V5 three-field line, asserts `not store.effective_authority(record)`;
  then writes a well-formed line for the same record and asserts
  `store.effective_authority(record)` is true. Assertion that fails on old
  code: the first assertion (old code returns `True` for the malformed line).
- `tests/test_hook_gate.py::test_action_authority_requires_live_matching_attestation[malformed]`
  (new parametrize case on the existing test): writes the same three-field
  line for the fixture's ratified one-way-door record and asserts
  `not pre_tool_use_gate.action_is_ratified(...)`. Assertion that fails on
  old code: `action_is_ratified` returns `True` there (verified by checking
  out the pre-fix files: `assert not True` fails with
  `AssertionError: assert not True`).

Both tests double as the "index lists it correctly" and "gate denies"
checks the task asked for: `action_is_ratified` is exactly what the Bash gate
verdict is built from (`pre_tool_use_gate.command_verdict`), and
`effective_authority` is exactly what `index.render_index`'s Active section
and `commit_msg.active_records` are built from, so a single fixed function
covers all three call sites without a fourth end-to-end test duplicating the
same assertion through more machinery.

## Collateral fix: `tests/test_index.py` fixture used the alias as the id

`write_fixture_record` set `data["id"] = alias` (e.g.
`"D-260901-ratified-predecessor"`), not a real ULID. `fixture_store` then
wrote attestations using that same non-ULID as `id`. Once
`attestation_item_problems` started requiring a canonical ULID, this fixture's
attestations all became invalid and `effective_authority` denied authority
for every ratified fixture record, failing
`test_active_holds_only_effectively_attested_authority` and
`test_rejected_successor_leaves_its_predecessor_active`. Fixed by generating a
real ULID (`scribe.ulid.generate()`) for the record `id` while leaving
`alias` untouched; nothing else in the file keys off the literal id value
(`supersedes=...` and all assertions use the alias). See I-G1-4.

## Suite

Ran, in order: the five touched/adjacent files together, then the group plus
`test_index.py`, `test_githooks.py`, `test_lint.py`, then the full suite twice
(`uv run --frozen pytest -q -p no:cacheprovider`, no `test_timing.py` flake on
either run):

```
441 passed, 3 skipped
```

`git diff --check`: clean. The em dash and en dash scan over `src` and
`tests` (ripgrep for both dash characters): no matches.
`uv run --frozen scribe check --base 3a5b1d2`: `scribe check: ok`.
`uv run --frozen scribe validate docs/decisions`: `7 records, 0 errors, 0 warnings`.

## Decisions (I-G1-*)

- **I-G1-1**: `latest_attestation` stays unfiltered; `effective_authority` is
  the one place that decides whether the literal latest line is trustworthy
  authority. Rationale: `ratify.apply_verdict`'s V10 recovery compares the
  record against the literal latest line, and that path is already protected
  by `_ledger_broken` running `attestation_line_problems` over the whole file
  before `latest_attestation` is ever called there, so filtering inside
  `latest_attestation` would be a no-op for recovery but would remove a
  literal "what does the ledger currently say" primitive other callers might
  reasonably want later. One function (`attestation_item_problems`) is the
  single source of truth either way.
- **I-G1-2**: did not add a check to `commit_msg.review_claims` or
  `schema.validate_record`'s `state_behind_attestation` path beyond what Gap 1
  already required there. Both already call `latest_attestation` directly
  rather than `effective_authority`, but neither grants Bash-gate-style
  authority; they are diagnostics (a warning that a claimed review_state has
  no matching attestation, or that the ledger is ahead of the record). The
  task listed exactly three authority consumers to fix
  (`effective_authority`, `index`'s Active section, `commit_msg.active_records`)
  plus the Bash gate; all four route through `effective_authority` already and
  needed no separate edit. `state_behind_attestation` did get the same
  `attestation_item_problems` guard as `unattested_review_state`, but that is
  Gap 1's field-validity fix (see I-G1-3), not a Gap 2 authority change.
- **I-G1-3**: extended the `unattested_review_state` / `state_behind_attestation`
  block in `schema.validate_record` to use `attestation_item_problems` rather
  than leaving it on the old verdict/body_sha256-only check. Two reasons:
  (a) it is the only route through which `scribe validate` can surface a
  field-level attestation problem for a ratified/rejected record, since
  `scribe validate <dir>` globs `D-*.md` files and never reads
  `RATIFICATIONS.jsonl` directly; (b) the old `state_behind_attestation`
  branch built `{"ratified": "ratify", "rejected": "reject"}.get(verdict, verdict)`
  from an unvalidated `verdict`, which raises `TypeError: unhashable type`
  for `verdict: ["cli"]`: a real crash, not just a missed diagnostic, closed
  by the same guard.
- **I-G1-4**: regenerated `tests/test_index.py`'s fixture record ids as real
  ULIDs instead of reusing the alias string. Required because
  `attestation_item_problems` now rejects a non-ULID `id`, and that fixture's
  own attestations were keyed on the record's (non-ULID) id; no test in that
  file asserts on the literal id value, only on alias and section membership.
- **I-G1-5**: did not de-duplicate the `via` value literal
  (`("skill", "cli", "hand-written")`) that already exists separately in
  `ratify.VIA_VALUES` and `cli.py`'s `--via` argparse `choices`. Gap 1 asked
  to validate against "the values ratify writes," which `schema.ATTESTATION_VIA_VALUES`
  now does correctly (it matches both existing literals), but consolidating
  all three into one shared constant touches two files outside the two gaps'
  file list (`ratify.py`, `cli.py`) for a cosmetic DRY win with no behavior
  change. Left as a follow-up rather than done silently under this fix.
- **I-G1-6**: `attestation_item_problems` returns `(code, message)` tuples
  rather than `Problem` objects directly, so `store.attestation_line_problems`
  can prefix each with its own `line {n}:` text while `effective_authority`
  and `validate_record` can use the list's truthiness alone without caring
  about line numbers that do not apply to a single already-parsed dict.

## Proposed commits

1. `fix: Validate attestation line fields, not just their truthiness`
   Body: `attestation_line_problems` accepted any truthy value for a required
   field (`by: 123`, `at: "yesterday"`, `via: ["cli"]` all passed). Adds
   per-field type and value checks in `schema.attestation_item_problems`,
   reused by `store.attestation_line_problems` and `validate_record`'s
   attestation cross-checks, so `scribe check` and `scribe validate` both
   report a malformed field instead of silently accepting it.
   Files: `src/scribe/schema.py`, `src/scribe/store.py`, `tests/test_store.py`,
   `tests/test_check.py`, `tests/test_schema.py`.

2. `fix: Require a structurally valid attestation for gate authority`
   Body: `effective_authority` granted Bash-gate and index/commit-msg
   authority from the latest attestation line as long as its verdict and
   body_sha256 matched, even when the line was otherwise malformed (missing
   actor, timestamp, or invocation path). Now requires the line to also pass
   the same field-level checks `scribe check` uses, denying authority for a
   ledger that check would already fail. Also fixes an existing test fixture
   that relied on a non-ULID record id, which the new check now catches.
   Files: `src/scribe/store.py`, `tests/test_store.py`, `tests/test_hook_gate.py`,
   `tests/test_index.py`.

(`src/scribe/schema.py`'s `validate_record` change and its test appear in
commit 1 because it is the field-validity fix that lets `scribe validate`
surface these problems; `store.effective_authority`'s change is entirely
commit 2's concern and does not depend on it.)
