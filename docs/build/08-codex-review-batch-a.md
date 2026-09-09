# Codex review of Batch A groups 1 and 2

fix first

Reviewed `96a8bd0`, `c80c5c2`, `94f5971`, and I74-I84. Line numbers refer to committed versions. The checkout contains additional uncommitted changes, so passing working-tree checks do not establish commit-level correctness. Validate, lint, index check, `check --base 4dc44ee`, and lookup passed. Commit-range whitespace checks passed. Regression-test counterfactuals below are assessed from source; pytest and uv were not run.

## V4 - closed

[check.py:80](/home/alfakentavr/scribe/src/scribe/check.py:80), `_supersede_gate`, now uses `implementation_paths`.

`test_dependency_gate_uses_implementation_paths` covers empty, action-only, package-only, negated, and store-only paths. The positive dependency cases and matching store-only exclusion would fail against the old predicate.

## V7 - closed

[history_check.py:67](/home/alfakentavr/scribe/src/scribe/history_check.py:67), `compare_record_versions`, compares complete normalized bodies without `rstrip()`, matching the scoped intent and I75.

All three `test_body_trailing_bytes_are_immutable` cases would fail previously because trailing newlines, spaces, and tabs were ignored.

## V9 - partial

[ratify.py:89](/home/alfakentavr/scribe/src/scribe/ratify.py:89), `apply_verdict`, correctly returns retryable exit 1 before ledger writes. The real-lock timeout test would fail previously.

[state.py:191](/home/alfakentavr/scribe/src/scribe/state.py:191), `update_state`, correctly drops unlocked mutations, and the corrected contention test would fail previously. However, callers relying on mutation callbacks to obtain read results were not adapted. This introduces the false denial described under New defects.

## V10 - closed

[ratify.py:96](/home/alfakentavr/scribe/src/scribe/ratify.py:96), `apply_verdict`, checks current-body attestation agreement before idempotence, restores attested actor/time, and appends a new attestation for an opposite-verdict reversal.

The recovery test would previously substitute Bob and the retry timestamp. The contradictory-attestation test would previously append nothing and report success. Both now exercise the intended behavior.

## V11 - partial

[pre_tool_use_gate.py:63](/home/alfakentavr/scribe/src/scribe/hooks/pre_tool_use_gate.py:63), `command_verdict`, checks every matched rule and records matched/uncovered lists. The compound force-push/publish test would fail previously.

[policy.py:51](/home/alfakentavr/scribe/src/scribe/policy.py:51), the rm rule, catches the required later outside target. However, its broader scan introduces cross-command false positives. Command-boundary coverage is missing; see New defects.

## V15 - closed

[matching.py:87](/home/alfakentavr/scribe/src/scribe/matching.py:87), `to_repo_relative`, canonicalizes root and target with `realpath`, including missing suffixes, and handles cross-drive `ValueError`.

The checkout-symlink and escaping-symlink assertions would fail previously, as would the simulated cross-drive test. Native Windows behavior remains unverified by that simulation.

## V16 - closed

[post_commit.py:79](/home/alfakentavr/scribe/src/scribe/githooks/post_commit.py:79), `run`, separates implemented records from newly linked and changed records. It saves lifecycle changes and retries index/pending cleanup when links already exist.

The persistence-step retry tests would fail against the old early return. The existing-link/proposed-lifecycle test would previously leave the lifecycle change unsaved.

## V18 - closed

[pre_tool_use_edit.py:77](/home/alfakentavr/scribe/src/scribe/hooks/pre_tool_use_edit.py:77), `load_front_matters`, stops at the closing delimiter before decoding the body. `handle`, line 225, checks the deadline after formatting. `format_block`, line 194, reserves intact footer/link space.

The undecodable 1 MB body, expensive-formatting, and long-target tests each have assertions the old implementation would fail.

## V19 - closed

[newrecord.py:184](/home/alfakentavr/scribe/src/scribe/newrecord.py:184), `render_body`, performs one substitution pass. `build_front_matter`, lines 227 and 235, distinguishes absent keys from explicit empty lists.

The literal-token test would previously alter inserted evidence; the empty-list test would previously inherit session values. Both scoped fixes match I80.

## V20 - closed

[gitutil.py:102](/home/alfakentavr/scribe/src/scribe/gitutil.py:102), `ReachableCommits`, shares a reachable-history snapshot and cached abbreviation resolution across lookup, lint, and relink.

The real amended-away-object test would previously miss lookup/lint warnings. It also checks reachable abbreviations and one history scan per command. Relink preserves resolved insertion order.

## V22 - closed

[schema.py:224](/home/alfakentavr/scribe/src/scribe/schema.py:224), `validate_record`, maps verdict values to actual CLI verbs.

The diagnostic extraction/healing test exercises both ratify and reject. Old diagnostics would produce nonexistent subcommands.

The accompanying CI-source conformance fix is also closed: [init_repo.py:98](/home/alfakentavr/scribe/src/scribe/init_repo.py:98), `check_command`, uses `shlex.quote`; the punctuation/space round-trip test would fail previously.

## New defects

- **P2 - State-lock contention can falsely deny ExitPlanMode.** Introduced by [state.py:192](/home/alfakentavr/scribe/src/scribe/state.py:192), `update_state`, interacting with [pre_tool_use_gate.py:89](/home/alfakentavr/scribe/src/scribe/hooks/pre_tool_use_gate.py:89), `plan_verdict`. Reproduction by control-flow reasoning: seed a session with pending decisions, hold `state.json.lock` beyond two seconds, and submit a storage-related plan in enforce mode. The skipped callback never populates local `pending`, so the gate returns deny despite existing pending decisions. Previously the callback populated it. Read from the returned state independently of whether the update succeeded, and add this contention test.

- **P2 - rm detection borrows flags and targets from later commands.** Introduced in [policy.py:51](/home/alfakentavr/scribe/src/scribe/policy.py:51), `RULES`, through `matching_rules`. Reproduction input: `rm build\nprintf '%s\n' -rf /tmp/example`, with the first `\n` representing a command-separating newline. `collapse_whitespace` removes that boundary; the new scan finds printf's `-rf` and `/tmp/example` and classifies the preceding ordinary rm as recursive outside deletion. The old immediate-option scan did not match. Preserve command boundaries before scanning targets and test this negative case.

These reproductions were reasoned from committed code, not executed as shell commands.

## V1 supervisor

**partial.** [supervise.py:40](/home/alfakentavr/scribe/hooks/supervise.py:40), `run`, correctly catches missing uv and maps ordinary unmarked startup failures to zero. The added launcher/shim tests meaningfully cover those original failures.

Two protocol gaps remain:

- **Crash output can impersonate denial.** Lines 44-45 trust any standalone `[scribe-deny]` stderr line. An import-time `RuntimeError("\n[scribe-deny]\n")` produces that line in its traceback. When forwarded through uv, its exit 1 is treated as deliberate and can block a git commit. The fixed string establishes no application provenance; uv and its children share the captured diagnostic channel.
- **A received denial can lose blocking semantics.** Line 53 returns the process status unchanged. If the application emits the marker and then terminates abnormally, a Claude hook can receive a status other than 2, which is nonblocking. Marker-plus-exit-zero also returns zero. [Claude exit-code documentation](https://code.claude.com/docs/en/hooks#exit-code-output). Use a dedicated per-invocation result protocol and translate a validated denial into the hook's required blocking status.

`python3 -I` with this script is a reasonable Linux/macOS registration **when a working Python 3.8+ is available**. Isolation excludes the script directory, user site-packages, and Python environment overrides. [Python documentation](https://docs.python.org/3/using/cmdline.html#cmdoption-I). However, `-I` still permits system site initialization; adding `-S` removes that dependency. [Site initialization documentation](https://docs.python.org/3/library/site.html).

The installed shim lacks equivalent isolation: [githook_shim.py:1](/home/alfakentavr/scribe/src/scribe/templates/githook_shim.py:1), rendered by `init_repo.render_shim`, uses plain `env python3`. A broken `PYTHONHOME` can terminate Python before its exception handler runs and block a commit. Apply equivalent isolation to that entrypoint.
---
Produced by `docs/build/pipeline/step9_review.sh` (gpt-6-astra, read-only sandbox, one 20-minute slice) against commits 96a8bd0, c80c5c2 and 94f5971, 2026-09-09 13:2x EDT.
