# Codex validation (step 4b, gpt-6-astra)

- Verdict: fix first.
- The current three-record ledger is valid, and all three original bodies and attestations are unchanged.
- A launcher failure can block tools and commits despite the promised fail-open behavior.
- CI integrity checks, concurrent writes, and attestation recovery have substantive correctness gaps.
- Review baseline: `89a60d2`; no files changed by this review. The full test suite could not start in the read-only sandbox.

Definition-of-done results follow. Every attempted `uv run` acceptance command exited 2 before application startup: `Could not acquire lock`, `Could not create temporary file`, `Read-only file system (os error 30)` under `/home/alfakentavr/.cache/uv`. Read-only application checks were repeated through `.venv/bin/python -B -m scribe`. Those fallback results are distinguished from the exact acceptance commands.

1. Tests and measured injection times - FAIL to verify, environment blocked. `uv run pytest -q` executed no tests. The reported `333 passed, 3 skipped`, warm `0.372 s`, cold `0.531 s` remain implementer evidence, not independently reproduced results.
2. Validate three records - FAIL to execute the exact command. Installed-interpreter fallback exited 0: `3 records, 0 errors, 0 warnings`.
3. Lint - FAIL to execute the exact command. Fallback exited 0: `3 records, 0 errors, 0 warnings, 0 info`; no `verify_failed` or `verify_error`.
4. Index - FAIL to execute the exact command. Fallback exited 0: `docs/decisions/INDEX.md is up to date`; headings are Review queue (0), Active decisions (3), Retired (0).
5. CI check - FAIL to execute the exact command. Fallback `check --base 3a5b1d2` exited 0: `scribe check: ok`.
6. Lookup after relink - PASS through the installed interpreter. All three aliases show bootstrap trailer commit `25bb0e7` and implementing commits: A10 includes `64864e9`, A13 includes `ae40787`, A12 includes `e7c2684`. Existing relink output was inspected; relink was not rerun.
7. JSON and Claude validation - PASS. All three `python3 -m json.tool` commands exited 0. `claude plugin validate .` exited 0, reporting marketplace validation with one missing-description warning. This did not establish that the skills load.
8. Hook registrations - PASS. Seven handlers use `command: uv` and an argument array; Edit|Write has timeout 1.
9. Skill front matter and session argument - FAIL semantically. All three literal `disable-model-invocation: true` strings exist and decide passes the quoted session argument, but init's front matter is invalid YAML.
10. Dogfood installation - PASS. Three executable scribe-managed shims exist; the specified deny rule is present; config is shadow/warn.
11. Prohibited dash scan - PASS. The requested `rg` command returned no output, exit 1. The previously reported prompt defect has been repaired.
12. Implementation report - PASS for the required artifact and recorded I-item register. The report exists and covers I1-I73; the additional defects below qualify its completion claims.
13. Immutable bootstrap bodies - PASS. Byte comparisons against `3a5b1d2` matched for all three bodies: 6604, 5764, and 5588 bytes. `RATIFICATIONS.jsonl` also matches the bootstrap bytes.

The following reproductions used existing files, pure functions, or mocked reads and writes in memory. No destructive command shown below was executed.

**V1 - blocker - Startup failures bypass every fail-open dispatcher**

File/function: [hooks/hooks.json](/home/alfakentavr/scribe/hooks/hooks.json), [githook_shim.py](/home/alfakentavr/scribe/src/scribe/templates/githook_shim.py), launcher entrypoints.

The exact registered injection command exited 2 on uv's cache failure. Python never reached `run_advisory`. Claude Code documents exit 2 as blocking PreToolUse and UserPromptSubmit, so this infrastructure failure becomes a tool or prompt denial. The git shim similarly replaces itself with uv and cannot catch uv's subsequent failure; prepare-commit-msg can prevent a commit even in warn mode. This affects the installed execution path, not merely the test environment. [Claude Code exit-code reference](https://code.claude.com/docs/en/hooks#exit-code-2)

Fix: put a dependency-free supervisor outside uv and application imports. Map startup failures to 0, and forward a deliberate enforcement denial only through an explicit application result protocol. Revise the plan's literal `command: uv` requirement accordingly. Test uv failure, missing dependencies, and import failure through the registered command and installed shim.

Confidence: high.

**V2 - major - The init skill has invalid YAML**

File/function: [skills/init/SKILL.md](/home/alfakentavr/scribe/skills/init/SKILL.md:5), front matter.

`argument-hint: [--force] [--ci-source <spec>]` starts a YAML sequence followed by an unexpected second sequence. Parsing produced `expected <block end>, but found '['`. Literal-string tests cannot establish that Claude recognizes the human-only flag when its containing front matter is malformed. Actual host behavior on this malformed skill remains unverified.

Fix: quote the whole hint, then parse every skill's front matter in tests and exercise `/scribe:init` in the host.

Confidence: high for invalid YAML; medium for the exact host consequence.

**V3 - major - CI mixes committed ranges with working-tree authority**

File/function: [check.py](/home/alfakentavr/scribe/src/scribe/check.py:133), `check_range`, `_validate_changed_records`; `history_check._read_version`.

Changed paths and commits come from Git, but records, attestations, index, and current versions come from disk. An uncommitted ratification can therefore make a committed unreviewed successor pass locally. Conversely, unrelated working-tree changes can fail a valid committed range. Section 5.4 specifies HEAD content.

I43 also replaces the supplied base ref with the merge base for checking historical ratification. That loses a ratification added to the target branch after the feature branch forked.

Fix: introduce a revision-backed store for CI and consistently inspect HEAD. Use the merge base for branch deltas, but preserve the specified base-tip authority check. Add dirty-worktree and diverged-target tests. Git range failures must produce explicit check failures; currently several helpers turn failures into empty results.

Confidence: high.

**V4 - major - CI uses a different implementation predicate from the git hooks**

File/function: [check.py](/home/alfakentavr/scribe/src/scribe/check.py:58), `_supersede_gate`.

The dependency arm calls `matches_affects`, contrary to the shared `implementation_paths` rule required by sections 5.3 and 5.4 and R8. With empty `affects`, `implementation_paths(record, ["src/example.py"])` returned that path, while `_supersede_gate` returned no reason. Thus an existing unreviewed successor can govern a code-only branch according to post-commit but escape CI when no trailer is present. Action-only and package-only records have the same inconsistency.

Fix: use `implementation_paths` in the dependency arm. Test empty affects, non-path affects, negation, and decision-store-only changes.

Confidence: high.

**V5 - major - Attestation integrity is checked incompletely**

File/function: [store.py](/home/alfakentavr/scribe/src/scribe/store.py), `latest_attestation`; [check.py](/home/alfakentavr/scribe/src/scribe/check.py:102), `_validate_changed_records`.

Malformed JSONL lines are silently ignored. A matching line containing only `id`, `verdict`, and `body_sha256`, without actor, timestamp, alias, or invocation path, passed validation in an in-memory probe.

CI validates only changed record files. Appending a rejection for an otherwise unchanged ratified record returned `scribe check: ok`, while validating that record returned `unattested_review_state`. Appending preserves the prefix, so the append-only check does not catch this.

Fix: validate the complete attestation file structurally, report malformed lines, and cross-check every record affected by appended attestations. Prefer validating all current records for this small store. Handle incomplete final lines explicitly before further appends.

Confidence: high.

**V6 - major - Deleting records bypasses ledger immutability**

File/function: [history_check.py](/home/alfakentavr/scribe/src/scribe/history_check.py:86), `check_records_against_base`; `check._validate_changed_records`.

Both functions skip deleted records. A simulated deletion of all base records, with a regenerated empty index and untouched attestations, returned `scribe check: ok`.

I45 documents this choice, but it defeats the product's immutable-ledger intent and the decide skill's instruction never to delete the predecessor. This is a plan gap as well as an implementation concern.

Fix: reject deletion of previously committed records, with an explicit diagnostic. Represent retirement through lifecycle transitions. Test deletion of a standalone ratified record and deletion of an entire supersession chain.

Confidence: high.

**V7 - major - Mutable changes need no corresponding history**

File/function: [history_check.py](/home/alfakentavr/scribe/src/scribe/history_check.py:40), `compare_record_versions`; `schema._validate_history`.

The checks verify that old history remains a prefix, but never require appended entries to explain changed mutable fields. Changing `effective_state` from proposed to expired with identical history produced no comparison finding. A direct edit can therefore remove a decision from retrieval without leaving the required transition history.

The body comparison also uses `rstrip()`, allowing trailing body changes despite the byte-immutability rule. Hash normalization and body immutability are separate requirements.

Fix: replay appended changes from the base state, verify old/new continuity and final mutable values, and compare normalized body text without stripping its trailing content.

Confidence: high.

**V8 - major - Record mutations are not serialized across writers**

File/function: [newrecord.py](/home/alfakentavr/scribe/src/scribe/newrecord.py:280), `create_record`; `ratify.apply_verdict`; `post_commit.run`; `relink.run_relink`; `Record.save`.

Only ratify/reject share `ratify.lock`. New, post-commit, relink, and expiry can load and overwrite the same record independently. Atomic replacement prevents partial files, but not lost updates. A concurrent post-commit save can overwrite a newly ratified review state and history.

Two `new` processes with the same title can both select the same unused alias and then overwrite one another through `write_text`. Neither identity survives reliably.

Fix: serialize every ledger mutation through one worktree-local transaction lock, reload after acquiring it, reserve new filenames exclusively, and regenerate the index from the committed transaction state. Use unique temporary spec files in the decide skill instead of its shared `/tmp/scribe-spec.json` example.

Confidence: high from the write paths; concurrent schedules were not executed.

**V9 - major - The ratification lock becomes optional under contention**

File/function: [state.py](/home/alfakentavr/scribe/src/scribe/state.py:118), `locked`; [ratify.py](/home/alfakentavr/scribe/src/scribe/ratify.py:87), `apply_verdict`.

After two seconds, `locked` yields `False`; ratification ignores that value and continues appending attestations and replacing records without exclusivity. The scratch-state fallback specified by the plan is inappropriate for an authoritative ledger transaction. Even scratch-state writers can overwrite one another after timeout.

The concurrency test launches two quick ratifications of different records. It does not hold the lock beyond the timeout or exercise conflicting verdicts on one record.

Fix: separate lock policies. Authoritative mutations must wait or return a retryable error without writing. Advisory state updates can fail open by dropping the update rather than performing an unlocked overwrite.

Confidence: high.

**V10 - major - Recovery changes the recorded actor and can falsely report success**

File/function: [ratify.py](/home/alfakentavr/scribe/src/scribe/ratify.py:87), `apply_verdict`.

An in-memory recovery with an existing attestation by `@alice` wrote `ratified_by: @bob` and a later timestamp into the record while appending zero attestations. I31 explicitly chooses this behavior, but it contradicts the attestation's role as authority.

The idempotent branch checks only the record's verdict. With a ratified record and a latest rejected attestation, `ratify` returned `already ratified` without resolving the contradiction.

Fix: establish consistency with the latest attestation before declaring idempotence. Recovery must copy its actor and verdict timestamp; recovery history can have its own later event timestamp. An intentional reversal must append a new authoritative line.

Confidence: high.

**V11 - major - One authorized action permits other unauthorized actions**

File/function: [pre_tool_use_gate.py](/home/alfakentavr/scribe/src/scribe/hooks/pre_tool_use_gate.py:61), `command_verdict`; `policy.denied_rule`.

`matching_rules("git push --force origin main && npm publish")` returned both rule names. `command_verdict` checked only the first and allowed the whole command when force-push was covered, without requiring publish coverage.

This corrupts shadow measurements today and becomes an enforcement bypass later.

Fix: evaluate every matched rule and deny if any lacks valid authorization. Include the complete matched and uncovered rule lists in the event. Add a compound-command test with only one action covered.

Confidence: high.

**V12 - major - Gates trust unattested and retired records as authorization**

File/function: [pre_tool_use_gate.py](/home/alfakentavr/scribe/src/scribe/hooks/pre_tool_use_gate.py:40), `action_is_ratified`.

The function checks front-matter strings only. It does not check attestation, current body hash, effective state, or incoming supersession edges. An expired, unattested record marked ratified allowed the action in the probe. The test helper `write_ratified_action_record` itself creates no attestation, so the tests encode this weakness.

Section 4.7's literal predicate omits lifecycle filtering, but section 3.7 says the review state has no authority without attestation.

Fix: require matching attestation and define whether retired decisions may authorize actions. Reuse a shared effective-authority predicate rather than another independent lifecycle interpretation.

Confidence: high.

**V13 - major - Git-hook checks inspect the working tree instead of staged record content**

File/function: [commit_msg.py](/home/alfakentavr/scribe/src/scribe/githooks/commit_msg.py:132), `staged_records`, `review_claims`; `prepare_commit_msg.record_carried`.

These functions select records by staged filename but load their contents and attestations from disk. A reviewed working-tree version can validate an unreviewed or malformed staged version. An unstaged attestation can satisfy the staged-record check even though the commit will omit it. The inverse causes false warnings or rejection.

This is separate from the explicitly deferred staged `verify` engine. Record and attestation checks are already promised.

Fix: read staged records and the staged attestation ledger through an index-backed store. Test partial staging, unstaged ratification, and staged/working-tree identity differences.

Confidence: high.

**V14 - major - Git pathname decoding corrupts ordinary Unicode filenames**

File/function: [gitutil.py](/home/alfakentavr/scribe/src/scribe/gitutil.py:23), pathname-returning helpers.

The helpers split newline-delimited Git output and replace backslashes with slashes. Git can quote and escape filenames. Feeding the standard quoted representation of `src/café.py` produced `"src/caf/303/251.py"` instead of the filename. Tabs, newlines, quotes, and literal backslashes have related problems.

This can lose trailers and injection-related governance checks, produce wrong backlinks, or miss CI dependencies.

Fix: request NUL-delimited output with `-z`, decode individual pathname fields, and stop treating Git's escape syntax as Windows separators. Add real Git tests with these filenames.

Confidence: high.

**V15 - major - Symlinked absolute paths miss injection**

File/function: [matching.py](/home/alfakentavr/scribe/src/scribe/matching.py:85), `to_repo_relative`; `pre_tool_use_edit.target_path`.

Repository discovery resolves symlinks, but target normalization uses `abspath`, not the same canonicalization. An existing repository file addressed through `/proc/self/cwd/src/scribe/index.py` returned `None` as outside the repository. The same mismatch occurs with a checkout reached through a symlink. Conversely, lexical containment can classify a symlink escaping the repository as inside.

Fix: apply one explicit canonicalization policy to both root and target, including nonexistent Write targets and symlinked parent directories. Treat Windows cross-drive paths as outside rather than allowing `relpath` to raise.

Confidence: high for the Linux reproduction; Windows behavior remains unverified.

**V16 - major - Post-commit cannot recover after saving links but before cleanup**

File/function: [post_commit.py](/home/alfakentavr/scribe/src/scribe/githooks/post_commit.py:65), `run`.

Records are saved before the index is written and pending IDs are consumed. If either later operation fails, retrying finds the links already present and returns immediately because `linked` is empty. A probe confirmed zero index-write and pending-consumption calls on retry.

The stale pending decision can acquire a trailer on another commit. An already-linked proposed record can also be changed in memory by `mark_implemented` without being saved.

Fix: track successfully implemented records separately from newly added links. Always finish index regeneration and pending consumption for the committed implementation, and save any lifecycle change. Test failures after each persistence step.

Confidence: high.

**V17 - major - Malformed schema values can crash validation and suppress unrelated retrieval**

File/function: [schema.py](/home/alfakentavr/scribe/src/scribe/schema.py:93), `validate_record`, `_enum`; `store.records`.

`review_state: []` raised `TypeError: unhashable type: 'list'`. The valid maximum ULID `7ZZZZZZZZZZZZZZZZZZZZZZZZZ` raised `ValueError: year 10889 is out of range` during the date-warning calculation.

Store loading also aborts the whole collection on one malformed file. Injection skips YAML parse failures, but a parseable malformed mapping or invalid glob can fail later and suppress the complete injection block.

Fix: type-check before membership, hashing, and date conversion; represent out-of-range ULID dates as diagnostics; isolate malformed records throughout collection and matching. Tests should assert useful diagnostics and preservation of unrelated valid candidates.

Confidence: high.

**V18 - minor - Injection reads complete bodies despite the front-matter-only requirement**

File/function: [pre_tool_use_edit.py](/home/alfakentavr/scribe/src/scribe/hooks/pre_tool_use_edit.py:69), `load_front_matters`, `handle`.

`path.read_text()` loads every full record, then `split` normalizes and slices the entire string. This violates section 4.4 item 4 and makes large immutable evidence bodies part of the edit-path cost. There is also no deadline check after matching and formatting.

The 5-record, 220-character line, and 1600-character block limits are implemented. The real 1-second uv budget was not remeasured here.

Fix: stream only through the closing front-matter delimiter and check the deadline before emitting. Test large bodies and expensive matching, not only 103 ordinary-sized records. Keep the footer and record links intact when truncating unusually long target paths.

Confidence: high.

**V19 - minor - Record creation does not preserve explicit input faithfully**

File/function: [newrecord.py](/home/alfakentavr/scribe/src/scribe/newrecord.py:168), `render_body`, `build_front_matter`, `_register`.

Repeated template replacement rescans inserted user content. Evidence containing literal `{{EVIDENCE_POINTERS}}` was changed by the later replacement pass.

Explicit empty `task_refs` and `provenance.prompt_ids` are treated as absent and replaced with session values, contrary to section 4.9's “if given” rule. The probe returned `["LIN-1"]` and `["prompt1"]` for explicitly empty lists.

`pending_decisions` is also silently capped at 20, although the plan caps `records_written`, not pending work.

Fix: substitute template tokens in one pass over the original template, distinguish missing keys from empty values, and retain pending IDs until consumption or the specified session expiry.

Confidence: high.

**V20 - minor - Reachability warnings test object existence**

File/function: [lint.py](/home/alfakentavr/scribe/src/scribe/lint.py:265), `_unreachable_link_findings`; `lookup.format_links`; `gitutil.commit_exists`.

`rev-parse <sha>^{commit}` establishes that the object exists, not that it is reachable. After amend or rebase, the obsolete object commonly remains available, so lint and lookup omit the promised warning until object pruning. Relink uses a reachable commit set and can disagree with both commands.

Fix: use a shared reachable-set check, with abbreviation resolution, for relink, lint, and lookup. Test an amended-away commit that still exists in the object database.

Confidence: high.

**V21 - minor - The documented deny-rule anchor assumes a root-started session**

File/function: [init_repo.py](/home/alfakentavr/scribe/src/scribe/init_repo.py), `DENY_RULE`, `ensure_settings`; README ratification model.

The README equates the project-settings anchor with the repository root. Current documentation describes it as the session's primary working directory. Starting Claude in a repository subdirectory can therefore make `/docs/decisions/RATIFICATIONS.jsonl` refer to the wrong location. This is a documented risk; the live nested-start case was not exercised. [Claude Code path-rule reference](https://code.claude.com/docs/en/permissions#read-and-edit)

Fix: verify root, nested-directory, and linked-worktree starts in the host, then choose a rule that protects the actual ledger in those cases or explicitly constrain supported startup location. Preserve the honest statement that arbitrary subprocess writes are not prevented.

Confidence: medium.

**V22 - minor - Recovery guidance names commands that do not exist**

File/function: [schema.py](/home/alfakentavr/scribe/src/scribe/schema.py:217), attestation recovery diagnostic; `tests/test_schema.py`, `tests/test_ratify.py`.

The diagnostic says `run scribe ratified ...` or `run scribe rejected ...`. The CLI commands are `ratify` and `reject`. Both tests assert the incorrect instruction, illustrating implementation output being accepted as the behavioral contract.

Fix: map verdict values to command names and test that the suggested command actually parses and heals the state.

Confidence: high.

**V23 - minor - The test suite overstates integration coverage**

File/function: [tests/conftest.py](/home/alfakentavr/scribe/tests/conftest.py), hook/skill tests, `test_timing.py`, `test_deferred.py`.

Most hook tests enter through Python after successful imports, missing V1. Skill tests search for strings, missing V2. Gate authorization fixtures lack attestations. Concurrency covers only short, nonconflicting ratifications. Reachability tests use nonexistent hashes rather than existing unreachable commits.

The shared fixture copies the live ledger, assumes exactly three records, and partially resets its lifecycle. Further dogfooding can break unrelated tests. Timing tests delete bytecode caches in the source checkout. Exactly three skips is also environment-dependent: the root-permission test adds another skip, and unguarded `fcntl`/`os.geteuid` usage prevents native Windows collection.

Fix: use stable valid fixture records, keep selected explicit dogfood checks, and add the negative cases identified above. Make timing setup isolated. Treat the three deferred tests as named deferrals rather than proof of untested behavior.

Confidence: high.

Conformance coverage beyond individual findings:

- Sections 3.1-3.4: ordinary identity, field, options-table, Evidence, cross-reference, and history-shape checks exist. Exceptions include V6, V7, V17, and V19. Path fields are not consistently validated as repository-relative POSIX paths, and filename equality is checked only when the supplied stem already starts with `D-`.
- Sections 3.5-3.6: deterministic queue grouping and active/retired routing match the normal specified cases. Flow-style serialization and bootstrap hashes match. Byte-immutability enforcement is weaker than body preservation, as V7 explains.
- Sections 3.7-3.8: normal verdict transitions and effective supersession are implemented. Rejected, expired, and backtracked successors contribute no effective edge; superseded successors retain their edge; reconciliation restores the predecessor's recorded proposed/implemented state. Attestation and transaction failures are V5 and V8-V10.
- Sections 4.1-4.3: registrations, default config, payload handling, tracker extraction, caps, session pruning, and ordinary dispatcher policies are present. Fail-open execution is incomplete at startup, V1; lock fallback is V9.
- Sections 4.4-4.6: ordinary retrieval, ordering, caps, validation output, and trailer parsing are implemented. Path, malformed-input, body-reading, and reachability exceptions are V14, V15, V17, V18, and V20.
- Sections 4.7-4.8: shadow/enforce dispatch and flag/reconcile flows exist. The gate defects are V11-V12. The `rm` rule also misses a later outside target in `rm -rf build /tmp/other`. TaskCompleted clears its flag even after an enforce denial, so a retry is allowed without remediation; that follows the plan but must be reconsidered before enforcement.
- Sections 4.9-4.13: the five skills and CLI operations exist. New-record fidelity, recovery, init YAML, and actual skill expansion remain qualified by V2, V10, V19, and V22. Only lint runs verify, as explicitly deferred.
- Sections 5.1-5.3: the registered-record two-commit sequence, duplicate-trailer prevention, amend-parent comparison, Session trailer suppression, governed-path warnings, and backlink generation are implemented and have behavioral test scenarios. Staged-content and interrupted post-commit handling remain defective. The first commit's implementation-link fallback exists, but no fresh initial-commit, detached-HEAD, rebase, or merge-conflict scenario was executed in this review.
- Sections 5.4-5.5: CI's ordinary supersession path and init's preflight, foreign-hook preservation, config defaults, and idempotent writes are implemented. CI correctness is qualified by V3-V7. Full linked-worktree behavior remains deferred. Generated shell commands also leave filesystem CI-source paths unquoted.
- Claude Code mechanics: current documentation supports exec-form `args`, plugin-root substitution, the used stdin fields including injected ExitPlanMode `plan`, additionalContext output, and command-hook timeout behavior. This confirms the schema assumptions, not actual delivery in a live session. [Hooks reference](https://code.claude.com/docs/en/hooks)
- Skill mechanics: human-only front matter, session substitution, and pre-model inline execution are documented. U1, argument substitution inside the inline command, and U2, actual hook firing for that command, remain unverified here. U3, native Windows behavior, also remains unverified. [Skills reference](https://code.claude.com/docs/en/skills)

What is well done:
- The original records and attestation hashes survived implementation intact.
- Effective supersession handles rejection, expiry, backtracking, and chains coherently.
- The ordinary two-commit trailer flow has meaningful behavioral tests.
- The code is readable, and the decision ledger makes disputed implementation choices traceable.
---
Produced by `docs/build/pipeline/step4b_validate.sh` (gpt-6-astra, read-only sandbox, reasoning high, one 20-minute slice) against commit 89a60d2. The sandbox could not run `uv`, so the test suite results it lists as "FAIL to verify" were reproduced by the main session: 333 passed, 3 skipped.
