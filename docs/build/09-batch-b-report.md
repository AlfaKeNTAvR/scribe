# Batch B validation fixes

## Item 0 (follow-ups and V1)

Files changed: README.md, hooks/hooks.json, hooks/supervise.py, src/scribe/hooks/pre_tool_use_gate.py, src/scribe/policy.py, src/scribe/protocol.py, src/scribe/templates/githook_shim.py, tests/test_hook_gate.py, tests/test_hook_launcher.py, tests/test_supervise.py, tests/test_timing.py, AUTONOMOUS_DECISIONS_09_08_2026.md and this report.

Regression tests added or corrected, with the assertion that fails on the old code:

- `test_traceback_marker_impersonation_is_fail_open` requires an un-tokened traceback marker to exit 0; old code treated it as a deliberate denial.
- `test_marker_forces_blocking_status` requires a valid marker to force exit 2 for Claude hooks and exit 1 for git hooks even when the child returns 0; old code forwarded the child status.
- The denylist negative case requires `rm build` followed by a separate `printf` command holding `-rf /tmp/example` not to match; old whitespace collapsing falsely matched it.

Suite: targeted hook and supervisor tests pass. Full-suite verification follows the remaining Batch B items.

```text
fix: Harden gate state and denial supervision

Read pending decisions from the returned locked state and keep denylist scans within command boundaries. Token denial markers per invocation and isolate every supervisor entrypoint so crashes cannot impersonate a block.
```

## Item 1 (V12)

Files changed: src/scribe/store.py, src/scribe/index.py, src/scribe/githooks/commit_msg.py, src/scribe/hooks/pre_tool_use_gate.py, src/scribe/hooks/reconcile.py, src/scribe/lint.py, tests/test_hook_gate.py, tests/test_index.py, AUTONOMOUS_DECISIONS_09_08_2026.md and this report.

Most of this item was already implemented in the interrupted Codex run: `Store.effective_authority` (attestation-backed: latest attestation ratified, its `body_sha256` matches the current body, `effective_state` in proposed/implemented, no effective supersession edge), consumed by `pre_tool_use_gate.action_is_ratified` (covers both the Bash and PowerShell gate, which share `command_verdict`), `index.render_index`'s active list, and `githooks.commit_msg.active_records`. The `write_ratified_action_record` test helper already wrote a matching RATIFICATIONS.jsonl attestation, and `reconcile.task_completed` already kept `decision_worthy` set after an enforce-mode denial while clearing it in shadow mode. The only actual breakage was `src/scribe/lint.py` still importing the `ACTIVE_STATES` constant that Item 1 removed from `index.py`, which kept the whole suite from collecting.

Fix: restored `ACTIVE_STATES` as a lint.py-local constant instead of routing lint's lifecycle checks through `effective_authority`. Lint's `_is_active` feeds `unreviewed_implemented`, which requires `review_state == "unreviewed"` in the same check; `effective_authority` requires `review_state == "ratified"`, so reusing it there would make that finding unreachable. This is a second, deliberately distinct "active" (lifecycle liveness, not ratified authority) from the one Item 1 unifies for the gate, INDEX.md and commit-msg.

Also verified the suspected Item 0 defect (marker-line filter comparing against the bare `DENY_MARKER` instead of the tokened marker) and found it not present: `hooks/supervise.py` already filters on the local tokened `marker` variable. No change made there.

Regression tests, with the assertion that fails on the old code (pre-Item-1 `action_is_ratified`/`active_records`/`render_index`, which checked only `review_state`/`effective_state` and never an attestation, and pre-Item-1 `task_completed`, which unconditionally cleared the flag):

- `test_hook_gate.py::test_action_authority_requires_live_matching_attestation[unattested]` requires `action_is_ratified` to return `False` once RATIFICATIONS.jsonl is emptied; the old check never read an attestation and would still return `True`.
- `test_hook_gate.py::test_action_authority_requires_live_matching_attestation[expired]` and `[superseded]` require `False` once `effective_state` is flipped; same reason.
- `test_hook_gate.py::test_action_authority_requires_live_matching_attestation[body_hash_mismatch]` requires `False` once the record body changes after being attested; the old check had no concept of a body hash at all.
- `test_hook_gate.py::test_task_completed_enforce_exits_two` requires `session_state(tmp_repo)["decision_worthy"]` to still be set (not `None`) after an enforce-mode denial; the old code cleared it unconditionally.
- `test_hook_gate.py::test_task_completed_reports_capture_missing_once` (pre-existing, unchanged) requires the flag to be cleared in shadow mode, covering the other half of the same behaviour.
- `test_index.py::test_active_holds_only_effectively_attested_authority` requires "## Active decisions (1)" holding only `D-260902-active-predecessor`; the old, state-only definition put 4 records in that section.
- `test_index.py::test_unattested_record_is_not_active` requires `D-260908-proposed-unreviewed` (never ratified) to be absent from the active section; the old code rendered it there with a regret/review line.

Suite: `uv run pytest -q` -> 397 passed, 3 skipped (the full, final suite for Items 0 and 1 together; no other items were started).

```text
fix: Share one ratified-authority predicate across gate and docs

Back the Bash/PowerShell gate, INDEX.md's active list and commit-msg's active-record check with one `Store.effective_authority` predicate keyed on a live, unexpired, unsuperseded, attestation-matched record, and stop clearing an enforce-mode decision-worthy flag until a record actually lands.
```

## Combined commit for Items 0 and 1

```text
fix: Harden gate state, denial supervision and ratified authority

Read pending decisions from the returned locked state, keep denylist scans within command boundaries, and token denial markers per invocation so a crash can no longer impersonate a block. Share one attestation-backed `effective_authority` predicate across the Bash/PowerShell gate, INDEX.md and commit-msg, and stop clearing an enforce-mode decision-worthy flag until a record actually lands.
```

## Item 5 (V21)

Done by a Sonnet worktree agent; full section, tests and I-lines (folded in as I102 to I106) in `09-batch-b-item-5.md`. Suite in that worktree: 392 passed, 3 skipped on base a4a721a.

## Item 2 (V3)

Done by a Sonnet worktree agent; full section, tests and I-lines (folded in as I107 to I110) in `09-batch-b-item-2.md`. Suite in that worktree: 393 passed, 3 skipped on base a4a721a.
