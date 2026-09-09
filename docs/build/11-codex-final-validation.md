# Codex final validation before v0.1.0

fix first

Reviewed the eight specified commits against HEAD `2ce6ae8`. Read-only checks passed: seven records validate, INDEX.md is current, and `check --base 3a5b1d2` succeeds. The reported suite result is 424 passed, 3 skipped; I did not rerun pytest or uv. Test counterfactuals are assessed from source. Reproductions below are reasoned unless identified as executed.

## Batch A group 3

- **V5 - partial.** [check.py:104](/home/alfakentavr/scribe/src/scribe/check.py:104), `_validate_all_records`, checks unchanged records; `test_appending_a_contradictory_attestation_fails_an_unchanged_record` would fail previously. Malformed JSON and truncated-tail tests cover substantive fixes. However, [store.py:175](/home/alfakentavr/scribe/src/scribe/store.py:175), `attestation_line_problems`, checks only truthiness of required values. A line with valid identity/hash/verdict but `by: 123`, `at: "yesterday"`, and `via: ["cli"]` passes structural validation. Validate field types and permitted values.

- **V6 - partial.** [check.py:163](/home/alfakentavr/scribe/src/scribe/check.py:163), `_deleted_record_reasons`, rejects deletion of records present at the fork point. `test_deleting_a_standalone_ratified_record_fails` and the chain-deletion test would fail previously. The owner's broader "never delete a committed record" rule remains incomplete: commit a new unreviewed record after the base, then delete it and restore the index in another commit. Neither endpoint contains it, so deletion is invisible.

- **V14 - partial.** [gitutil.py:16](/home/alfakentavr/scribe/src/scribe/gitutil.py:16), `_paths_from_z`, fixes Git quoting. `test_staged_paths_preserves_special_filenames` and the diff/root/non-root tests would fail previously. However, `_git`, line 7, still uses `text=True`: carriage returns in filenames undergo newline translation, and non-UTF-8 filename bytes now raise decoding errors rather than arriving as Git's ASCII escapes. Use binary pathname output with filesystem decoding.

- **V17 - regressed.** The original enum and ULID fixes work. I executed streamed-input validation: `review_state: []` produces `invalid_enum`; the maximum ULID produces `ulid_date_out_of_range`. Their named tests would fail previously. Collection isolation remains incomplete: [pre_tool_use_edit.py:102](/home/alfakentavr/scribe/src/scribe/hooks/pre_tool_use_edit.py:102), `superseded_keys`, still crashes on `effective_state: []`, suppressing unrelated retrieval. Additionally, `0677c09` introduces another schema crash: a grep-shaped verify entry with `engine: []` raises `TypeError` at [schema.py:461](/home/alfakentavr/scribe/src/scribe/schema.py:461), `_validate_verify`. I reproduced that through `validate /dev/stdin`; the previous comparison reported an unknown engine.

## Batch B

- **V3 - partial.** [check.py:226](/home/alfakentavr/scribe/src/scribe/check.py:226), `run_check`, implements the approved dirty-ledger interim; `_supersede_gate`, line 85, receives base-tip authority. `test_a_dirty_ledger_is_refused` and `test_a_ratification_added_to_the_target_after_the_fork_is_honoured` would fail previously. The original Git-error requirement remains unresolved: [gitutil.py:41](/home/alfakentavr/scribe/src/scribe/gitutil.py:41), `is_dirty`, ignores failure status; pathname/range helpers return empty results on failure; `check_range` substitutes the base when merge-base fails. Failed inspection must produce an explicit check failure.

- **V8 - partial.** The principal record writers now share `ratify.lock`; new, post-commit, relink, and expiry reload after acquisition. Their lock-timeout tests would fail previously, and the alias-collision test establishes overwrite prevention. However, [lint.py:161](/home/alfakentavr/scribe/src/scribe/lint.py:161), `_index_findings`, writes outside the lock using cached records. [cli.py:215](/home/alfakentavr/scribe/src/scribe/cli.py:215), `_index_command`, also writes without locking. Schedule: lint loads old records, ratify updates records/index under lock, then lint overwrites INDEX.md from its old snapshot. `_expire_stale`, line 314, also releases the lock without regenerating the index. Exclusive creation introduces the executable-file defect listed below.

- **V12 - partial.** [store.py:111](/home/alfakentavr/scribe/src/scribe/store.py:111), `effective_authority`, correctly enforces matching hash, ratified state, live lifecycle, and absence of effective supersession. `test_action_authority_requires_live_matching_attestation` would fail previously. But `latest_attestation` still accepts the original three-field `{id, verdict, body_sha256}` object; that incomplete object authorizes through the new predicate despite failing V5's separate integrity check. Authority must require a structurally valid attestation. TaskCompleted flag retention is **closed**: `test_task_completed_enforce_exits_two` now asserts retention and would fail previously.

- **V19 - closed.** [newrecord.py:313](/home/alfakentavr/scribe/src/scribe/newrecord.py:313), `_register`, removes the pending cap. `test_pending_decisions_has_no_cap_and_all_survive_as_trailer_candidates` would previously retain only 20 of 25 IDs. The earlier template and explicit-empty-list fixes remain intact. The helper-only `push_recent(..., None)` test does not distinguish old code: Python already permits `items[:None]`.

- **V21 - closed for the owner's advisory scope.** [session_start.py:33](/home/alfakentavr/scribe/src/scribe/hooks/session_start.py:33), `subdirectory_hint`, and `init_repo.follow_ups` provide the requested warning. `test_session_start_hints_when_started_below_repo_root` and `test_init_next_steps_hint_the_subdirectory_start_limitation` would fail previously. This establishes warning behavior; it does not independently repeat the reported host experiment.

## 08-review follow-ups

- **State-lock false denial - partial.** [pre_tool_use_gate.py:105](/home/alfakentavr/scribe/src/scribe/hooks/pre_tool_use_gate.py:105), `plan_verdict`, now reads the returned snapshot correctly. The requested contention regression test is absent. `test_exit_plan_mode_allows_with_pending_decision_but_still_flags` exercises normal acquisition and passes old code.

- **rm command boundaries - regressed.** [policy.py:145](/home/alfakentavr/scribe/src/scribe/policy.py:145), `matching_rules`, fixes the reported rm/printf false positive; its new `test_denylist_allows` case would fail previously. But unconditional newline splitting loses shell continuations. Reproduction: the two-line Bash command `git push \` followed by `--force` is one force-push command. Old matching detects it; new matching splits it and returns no rule. Handle escaped newlines before separating commands.

- **Crash impersonating denial - partial.** [supervise.py:40](/home/alfakentavr/scribe/hooks/supervise.py:40), `run`, introduces a fresh token and fixes the reported accidental-marker collision. However, `test_traceback_marker_impersonation_is_fail_open` emits `RuntimeError: [scribe-deny]`, not a standalone marker. Old code also passes that test. Exercise the actual multiline traceback reproduction.

- **Denial losing blocking status - closed.** `supervise.run`, line 58, forces Claude exit 2 and Git exit 1. `test_marker_forces_blocking_status` meaningfully detects the previous behavior.

- **Registered supervisor site initialization - closed.** `hooks/hooks.json` adds `-S` alongside `-I`; `test_hooks_json_every_handler_is_exec_form` checks the changed argument prefix and would fail previously.

- **Git-shim startup isolation - partial.** [githook_shim.py:14](/home/alfakentavr/scribe/src/scribe/templates/githook_shim.py:14) re-executes too late. [init_repo.py:74](/home/alfakentavr/scribe/src/scribe/init_repo.py:74), `render_shim`, still generates plain `/usr/bin/env python3`. With `PYTHONHOME=/nonexistent`, Python can fail before executing the shim, blocking a commit. Existing shim tests break uv, not Python initialization. Isolation must apply to the first interpreter launch.

## Pytest verify engine

**Partial.** [lint.py:480](/home/alfakentavr/scribe/src/scribe/lint.py:480), `_run_pytest_verify_entry`, uses an argument array and correctly sets `cwd=store.root`. Pass/fail inversion and ordinary timeout reporting have meaningful tests.

- **Argument injection:** line 516 lacks `--` before `target`. A repository file named `--help` makes that target pass existence validation, but pytest interprets it as an option and exits successfully without running tests. I executed shape validation through stdin and confirmed `--help` is accepted. Also, `lint_store`, line 630, executes entries despite earlier validation errors. Reject option-shaped targets, terminate options, and skip invalid entries.
- **Timeout handling:** `_verify_timeout_seconds`, line 456, accepts `nan` and `inf`; these can cause uncaught selector exceptions. Require a positive finite value. `subprocess.run` kills only its direct process on timeout, so test descendants can survive. The timeout test checks a finding, not process-tree cleanup.
- **Malformed values:** the `engine: []` crash above is new; the runner's severity membership at line 494 similarly crashes on `severity: []`.

## Post-rewrite hook

**Partial.** [post_rewrite.py:48](/home/alfakentavr/scribe/src/scribe/githooks/post_rewrite.py:48), `run`, delegates correctly. The updated amend test meaningfully verifies stale-link removal.

No nested ledger-lock acquisition appears in this path: post-rewrite calls [relink.py:96](/home/alfakentavr/scribe/src/scribe/relink.py:96), `run_relink`, which acquires once. Post-commit releases its own lock before the subsequent post-rewrite invocation. Relink issues read-only Git commands, so it does not recursively trigger these hooks.

The guard is process-local. It cannot suppress earlier post-commit invocations in sibling processes during rebase. I127 therefore remains consequential: replay an implementing commit followed by its backlink snapshot commit. [post_commit.py:108](/home/alfakentavr/scribe/src/scribe/githooks/post_commit.py:108), `run`, dirties the record before the snapshot patch applies, causing the reported replay conflict. Post-rewrite runs too late to prevent it. The smoke test discards backlinks; the surgical test disables hooks. Neither covers this normal history. This is a pre-existing integration defect, not a newly introduced lock deadlock.

## New defects

- **P1:** pytest option injection and execution of invalid entries, `0677c09`, detailed above.
- **P2:** incomplete timeout bounds and descendant cleanup, `0677c09`, detailed above.
- **P2:** malformed verify values crash validation/lint, `0677c09`, executed reproduction above.
- **P2:** continued Bash commands evade deny rules, `3050f09`, reproduction above.
- **P2:** raw non-UTF-8 Git filenames now crash pathname decoding, `16ae245`.
- **P2:** [newrecord.py:177](/home/alfakentavr/scribe/src/scribe/newrecord.py:177), `_write_record_exclusive`, omits `os.open`'s mode argument, defaulting to `0777` before umask. With umask `022`, new Markdown records become `0755`. Commit `3ca275f` contains executable new records; `2ce6ae8` cleans existing modes but leaves this source defect. Pass `0o666` explicitly and test the resulting mode.