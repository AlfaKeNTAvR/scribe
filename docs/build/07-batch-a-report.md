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

## Group 2

Completed V15, V16, V18, V19 template and explicit empty lists, and V20. Decisions: I80-I84. The pending-decision cap is unchanged.

Files changed: src/scribe/matching.py, src/scribe/hooks/pre_tool_use_edit.py, src/scribe/githooks/post_commit.py, src/scribe/newrecord.py, src/scribe/gitutil.py, src/scribe/relink.py, src/scribe/lint.py, src/scribe/lookup.py; tests/test_matching.py, tests/test_hook_injection.py, tests/test_githooks.py, tests/test_new.py, tests/test_relink.py; AUTONOMOUS_DECISIONS_09_08_2026.md and this report.

Regression tests added, with the assertion that fails on the old code:

- V15: test_to_repo_relative_canonicalizes_symlinks_and_missing_targets requires both existing and new files through a checkout symlink to resolve inside, and escaping symlinks including symlink/.. to resolve outside; old code misclassified them. test_to_repo_relative_treats_cross_drive_as_outside requires None instead of a relpath ValueError.
- V16: test_post_commit_retry_finishes_after_each_persistence_step (record, index, pending) reloads the store after an injected post-write failure. It requires completed index and pending cleanup, with index/pending spies called again on retry; old code returned early once links existed. test_post_commit_saves_proposed_lifecycle_when_link_already_exists requires implemented to persist; old code changed it only in memory.
- V18: test_large_record_body_is_not_decoded_by_injection requires a matching record with a 1 MB undecodable body to remain injectable; old full-file decoding skipped it. test_deadline_is_checked_after_matching_and_formatting requires no output after simulated expensive formatting; old code emitted. test_block_truncates_long_target_without_losing_footer_or_links requires the complete footer and record link after target truncation; old whole-block truncation lost them. Existing line-cap coverage also checks limits shorter than the ellipsis.
- V19: test_new_preserves_explicit_empty_session_lists requires both lists to remain empty despite session defaults; old code filled them. test_new_preserves_literal_template_tokens_in_evidence requires the exact quoted token text in the saved body; old repeated replacement altered EVIDENCE_POINTERS inside evidence.
- V20: test_lookup_lint_and_relink_agree_on_existing_unreachable_commit creates a real amended-away object and verifies that it still exists. Lookup must mark its abbreviated link, lint must warn for exactly that link, and relink must retain only the reachable implementation. Old lookup omitted the warning. The test also requires exactly one reachable-history scan per command and accepts reachable seven-character abbreviations.

Suite: UV_CACHE_DIR=/tmp/scribe-uv-cache UV_OFFLINE=1 uv run pytest -q -> 373 passed, 3 skipped. Warm injection median 0.510 s; bytecode-cold 0.644 s. git diff --check passed.

Incremental commit patch: /tmp/scribe-batch-a-commits/group-2.patch.

```text
fix: Recover post-commit work and preserve retrieval inputs

Finish interrupted backlink cleanup and keep injection within its path and time boundaries. Preserve explicit record inputs and make lookup, lint and relink share reachable commit checks.
```
