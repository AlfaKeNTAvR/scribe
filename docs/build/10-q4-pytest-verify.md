# Q4: `engine: pytest` on the `verify` allowlist

Owner decision O6, question Q4 (`AUTONOMOUS_DECISIONS_09_08_2026.md`). Adds a
second `verify` engine, `pytest`, alongside the existing `grep` engine, so a
behavioural decision can point at a pytest node id instead of (or in addition
to) a regex-over-files check. `verify` entries only run inside `scribe lint`;
`commit-msg` and `scribe check` stay deferred, unchanged.

## Files changed

- `src/scribe/schema.py`
  - `_validate_verify` now branches on `engine`: `grep` keeps its existing
    key set `{id, engine, pattern, paths, expect, severity}` and
    `match|no-match` expectations; `pytest` gets a new key set
    `{id, engine, target, expect, severity}` and `pass|fail` expectations.
    `jsonpath` and any other unrecognised value keep their existing
    `unsupported_engine` / `unknown_engine` errors.
  - New `_validate_pytest_target`: `target` must be a non-empty string
    shaped like a pytest node id, `path[::name[::name...]]`. The `path`
    segment may not be absolute (`/` or `~`), may not contain a `..`
    segment, and every `::name` segment after it must be non-empty. When a
    `store` is available (same limitation as the existing `dangling_reference`
    check), the path segment must also exist on disk relative to the repo
    root, or the entry is rejected.
  - `validate_record` now passes `store` into `_validate_verify` (it already
    had `store` in scope; only the one call site changed).

- `src/scribe/lint.py`
  - `_verify_findings` now dispatches per entry on `engine`: `grep` keeps
    calling the existing `_run_verify_entry`; `pytest` calls the new
    `_run_pytest_verify_entry`.
  - New `_run_pytest_verify_entry`: runs
    `uv run --frozen pytest -q -x <target>` with `cwd` set to the repo root
    (`store.root`), only after `_pytest_available(store.root)` passes (a
    `pyproject.toml` exists and mentions `pytest`, a cheap gate, not a
    guarantee, exactly so a repo with no pytest project never pays for a
    subprocess). Bounded by `_verify_timeout_seconds()`: `SCRIBE_VERIFY_TIMEOUT`
    (seconds, float) if set, else 60. Exit code 0 is treated as "passed",
    exit code 1 as "failed"; any other exit code (collection error, usage
    error, interrupted) reports `verify_error`. A timeout
    (`subprocess.TimeoutExpired`) and a `uv`/subprocess launch failure
    (`OSError`) both report `verify_error` too, nothing here can raise out
    of `lint_store`. When the observed pass/fail disagrees with `expect`,
    reports `verify_failed` at the entry's own severity, same message shape
    as the grep engine (`verify <id>: <target> <outcome>, expected <expect>`).
  - New module constant `DEFAULT_VERIFY_TIMEOUT_SECONDS = 60.0` and helpers
    `_verify_timeout_seconds()`, `_pytest_available()`.

- `tests/test_schema.py`
  - `test_pytest_verify_entry_accepts_a_valid_node_id`: a store-backed
    record with `{engine: pytest, target: "tests/test_x.py::test_ok", expect:
    pass, severity: error}` where `tests/test_x.py` exists validates clean.
    Fails on the old code because `_validate_verify`'s fixed grep key set
    rejects any entry that carries `target` instead of `pattern`/`paths`,
    always producing `invalid_verify`.
  - `test_pytest_verify_entry_rejects_a_bad_node_id`: `target: "::test_ok"`
    (empty path segment) produces `invalid_verify`. Fails on the old code
    the same way (no `pytest` engine existed at all, so every pytest-shaped
    entry was rejected on the key-set check before the node-id shape was
    ever examined): this test specifically pins the node-id validation
    itself, not just the key set.
  - `test_pytest_verify_entry_rejects_a_target_path_that_does_not_exist`:
    `target: "tests/does_not_exist.py::test_ok"` produces `invalid_verify`
    when a store is present. Did not exist on the old code (no code path
    checked a pytest target's existence).
  - `test_verify_entry_with_an_unknown_engine_is_rejected`: `engine: "xpath"`
    (grep-shaped keys) produces `unknown_engine`. Passed on the old code
    too (the `elif engine != "grep"` branch already caught it) but is added
    here as an explicit regression pin since the condition changed shape to
    `elif engine not in {"grep", "pytest"}`.

- `tests/test_lint.py`
  - New helper `pytest_project(repo)`: writes a tiny `pyproject.toml`
    (`dependencies = ["pytest"]`) and `tests/test_target.py` (`test_ok`,
    `test_broken`, `test_slow` which sleeps 5s) into a repo, then runs
    `uv lock` so `uv run --frozen` works without touching the network at
    lint time (the lock resolves from uv's local cache in this
    environment).
  - New helper `pytest_entry(**overrides)`, mirroring the existing
    `verify_entry` helper for the grep engine.
  - `test_a_passing_pytest_verify_entry_reports_nothing`: `expect: pass`
    against `test_ok` yields no findings, exit 0. Fails on the old code
    with `invalid_verify` (no pytest engine).
  - `test_a_failing_pytest_verify_entry_reports_verify_failed`: `expect:
    pass` against `test_broken` yields `verify_failed` at the entry's
    severity, exit 1. New behaviour; nothing analogous ran on the old code.
  - `test_expect_fail_inverts_a_pytest_verify_entry`: `expect: fail` against
    `test_broken` yields no findings, exit 0, pinning the inversion.
  - `test_a_pytest_verify_entry_that_times_out_reports_verify_error`: with
    `SCRIBE_VERIFY_TIMEOUT=1` and `target: test_slow` (sleeps 5s), yields
    `verify_error` at severity error, exit 1.
  - `test_a_pytest_verify_entry_without_a_pytest_project_reports_verify_error`:
    a repo with an existing target file but no `pyproject.toml` yields
    `verify_error` (not `invalid_verify`, the target path itself is fine;
    it is the missing-pytest-project gate that fires), exit 1.
  - `test_lint_on_this_repository_has_no_verify_failure` (pre-existing,
    unchanged) still passes: the repo's three real records only use
    `engine: grep`, so this change adds a new code path they never touch.

- `README.md`: added one paragraph under "Record format" naming both
  `verify` engines (`grep`, `pytest`) and stating the pytest engine's shape,
  gate, and timeout override, plus repeating that `jsonpath` is allowlisted
  but unimplemented. README previously said nothing about engines at all
  (deferred entirely to the plan doc), so this is new content, not an edit
  to an existing engines list.

Not touched, per the task's own carve-outs: `skills/decide/SKILL.md` (does
not mention `grep`, so left alone), `src/scribe/templates/record_template.md`
(carries no engine-related comment), `docs/decisions/D-*.md`,
`RATIFICATIONS.jsonl`, `AUTONOMOUS_DECISIONS_09_08_2026.md`, and everything
else under `docs/build/`. `commit-msg` and `scribe check` were not given a
verify runner; only `scribe lint` executes `verify` entries, per the plan
and the task.

## Suite count

Baseline before this change: 411 passed, 3 skipped.
After this change: **420 passed, 3 skipped** (4 new schema tests + 5 new
lint tests = 9; no existing test was changed, none encoded now-obsolete
behaviour).

## Proposed commit message

```
feat: Add the pytest engine to verify entries

Lets a verify entry point at a pytest node id (engine: pytest, target,
expect: pass|fail) alongside the existing grep engine; scribe lint runs it
with a bounded timeout and reports verify_failed/verify_error exactly like
the grep engine does.
```

## I-lines

- I-Q4-1: `_validate_pytest_target`'s path-existence check only runs when a
  `store` is passed into `validate_record` (same as the pre-existing
  `dangling_reference` / `supersedes` checks). A bare
  `validate_record(mapping, body)` call with no store validates the node-id
  *shape* but cannot confirm the file exists. This mirrors an existing
  limitation in the file rather than introducing a new one, but flagging it
  since it means a spec-shaped-but-wrong target can slip past validation in
  contexts that never construct a `Store` (e.g. `scribe new` prior to the
  record's first save, if it ever validates before the store exists).
- I-Q4-2: "the invoked lint's own repo has a pyproject with pytest
  available" is implemented as a cheap textual gate
  (`pyproject.toml` exists and the string `"pytest"` appears in it), not an
  actual dependency-resolution check or an attempt to import pytest. A
  `pyproject.toml` that mentions "pytest" only in a comment or an unrelated
  key would pass the gate and then fail for real inside the subprocess,
  which is still caught (non-zero, non-0/1 exit, or an `OSError` on launch)
  and reported as `verify_error`, so correctness is preserved, just not by
  the gate alone. Chose the cheap heuristic over spawning a second
  subprocess (e.g. `uv run --frozen python -c "import pytest"`) to avoid
  doubling subprocess overhead on every pytest-engine entry; happy to switch
  to the stricter check if the false-positive gate (pyproject mentions
  pytest, but it is not actually installed) turns out to matter in
  practice.
- I-Q4-3: Pytest exit codes 0 and 1 are treated as normal outcomes (passed /
  failed); every other exit code (2 interrupted, 3 internal error, 4 usage
  error, 5 no tests collected, verified 4 by hand for an import error
  during collection) is treated as `verify_error`. This groups "no tests
  collected" (5) in with genuine errors rather than treating it as a kind of
  "failed"; that seemed like the safer default (a target that silently
  stops matching any test should be loud, not read as `expect: fail`
  succeeding) but is worth confirming against intent.
- I-Q4-4: The `pyproject with pytest available` gate is evaluated against
  `store.root` (the repository root that owns the decision store being
  linted), which is what the task specified ("the invoked lint's own
  repo"). It is not evaluated per verify-entry `target`: a target several
  directories deep in a monorepo with its own nested `pyproject.toml` is out
  of scope for this change.
- I-Q4-5: No new `verify_error`/`invalid_verify` sub-codes were introduced
  for the pytest engine; it reuses the same finding codes the grep engine
  already reports (`verify_failed`, `verify_error` in lint;
  `invalid_verify`, `unknown_engine`, `unsupported_engine` in validate), per
  the instruction to mirror the grep engine's behaviour and output format.
- I-Q4-6: README previously had no engines list to update (confirmed via
  `grep -i engine README.md`, zero hits). Added one short paragraph rather
  than leaving the field undocumented, since the task named this as a
  required update; kept it terse and pointed at the plan doc's fuller
  version implicitly by not duplicating field-table detail.
