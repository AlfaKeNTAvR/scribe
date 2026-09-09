# Batch A validation fixes

Scope: the 15 fix-now items in 06-validation-triage.md, in the owner's three groups. Batch B and C remain deferred. Tests use temporary repositories; no git-writing command runs against this checkout. The existing untracked pipeline files are outside this change.

The proposed commits below form the commit queue for the main session. Every group includes its regression tests and was completed before the next group began.

## Group 1

Completed V4, V7 body comparison, V9, V10, V11 including the later rm target, V22, and CI-source filesystem quoting. Decisions: I74-I79.

Files changed: src/scribe/check.py, src/scribe/history_check.py, src/scribe/ratify.py, src/scribe/state.py, src/scribe/schema.py, src/scribe/policy.py, src/scribe/hooks/pre_tool_use_gate.py, src/scribe/init_repo.py; tests/test_check.py, tests/test_ratify.py, tests/test_state.py, tests/test_schema.py, tests/test_hook_gate.py, tests/test_init.py; AUTONOMOUS_DECISIONS_09_08_2026.md and this report.

Regression tests added or corrected, with the assertion that fails on the old code:

- V4: test_dependency_gate_uses_implementation_paths (six cases). Empty, action-only and package-only affects require exit 1 for a code-only branch; old code returned 0. A store-only path matching docs/** must pass; old code denied it. Negation and empty-affects store-only cases guard the shared predicate's exclusions.
- V7: test_body_trailing_bytes_are_immutable (three cases). Each appended newline, space or tab must report immutable_changed; old rstrip comparison returned no finding.
- V9: test_ratify_lock_timeout_exits_nonzero_without_ledger_writes holds a real lock beyond two seconds and requires exit 1 plus unchanged record, attestation and index bytes; old code returned 0 and wrote them. Corrected test_posix_contention_drops_state_update requires the timed-out update to stay absent. The old test explicitly expected the defect. Renamed the Windows timeout adapter test to describe its result accurately.
- V10: test_recovery_uses_actor_and_timestamp_from_attestation requires @alice and the original verdict time after @bob retries; old code substituted @bob and the new time. test_matching_record_with_contradictory_latest_attestation_is_repaired requires a fresh ratified line and a valid record; old code said already ratified and appended nothing.
- V11: test_compound_command_denies_when_only_one_matched_rule_is_ratified requires enforce exit 2 for force-push plus publish when only force-push is covered; old code returned 0. The added test_denylist_matches case requires rm-rf-outside-worktree for rm -rf build /tmp/other; old code returned None. The compound test also checks both event rule lists.
- V22: test_state_behind_diagnostic_command_parses_and_heals replaces the old healing test and covers ratify and reject. It extracts the command from the diagnostic and runs it successfully; old output named nonexistent CLI commands. The existing schema diagnostic assertion is also corrected as documented in I79.
- Conformance: test_ci_source_filesystem_path_is_one_shell_argument requires shlex.split to preserve a path containing spaces, an apostrophe and shell punctuation as one argument; old output could not round-trip.

Suite: UV_CACHE_DIR=/tmp/scribe-uv-cache UV_OFFLINE=1 uv run pytest -q -> 361 passed, 3 skipped. Warm injection median 0.505 s; bytecode-cold 0.528 s. git diff --check passed.

Incremental commit patch: /tmp/scribe-batch-a-commits/group-1.patch. The main session can use the queued patches to preserve the group boundaries even where later groups edit the same files.

```text
fix: Close CI, gate and ratification validation gaps

Align CI dependencies with implementation links and enforce immutable body content. Honor lock failures, preserve attested recovery values, check every command rule and quote CI source paths.
```
