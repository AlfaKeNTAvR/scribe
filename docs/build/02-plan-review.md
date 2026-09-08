# Plan review (step 2, Codex gpt-6-astra)
Verdict: revise.
The architecture and task decomposition are sound, and most phase 1 to 3 requirements are represented.
Six blockers would currently break lifecycle correctness, ratification authority, record validation, or CI enforcement.
Several acceptance tests contradict their stated behavior or depend on later tasks.
Revise the plan before implementation; a full redesign is unnecessary.

F1

- Severity: blocker
- Plan section or task id: 3.5 rules 1 to 3, 4.10, T4, T9, T12
- What is wrong: Any `supersedes` edge retires the old record even when the new record is rejected. `scribe reject` leaves `supersedes` intact, so both records disappear from injection: the rejected successor is excluded and the ratified predecessor remains retired. The CI check then passes, even though no active governing decision remains.
- What to change: Define when a supersession edge is effective. At minimum, rejected successors must not retire predecessors. Specify behavior for expired and backtracked successors too. Add an end-to-end test that creates B superseding A, rejects B, and confirms A returns to Active and PreToolUse injection.
- Confidence: high

F2

- Severity: blocker
- Plan section or task id: 3.2 `affects`, 4.7 item 2, P21, T2, T14
- What is wrong: The schema allows only `path` and `package`, but the Bash gate requires `{type: action, pattern: ...}` and says the validator accepts it. T14 cannot create a valid authorization record under T2's schema.
- What to change: Add `action` to the schema with exact validation and matching semantics, or move action authorization to a separate typed field. Add valid, invalid, matching, and non-matching action tests.
- Confidence: high

F3

- Severity: blocker
- Plan section or task id: 5.1, 5.3 item 4, T10
- What is wrong: A commit that only adds a decision receives its own `Decision:` trailer. `post-commit` correctly does not mark it implemented, but then removes its id from every session's `pending_decisions`. The subsequent implementing commit therefore receives no trailer or backlink.
- What to change: Consume a pending id only after a commit records at least one implementation path for it. Distinguish trailers caused by staging the record from trailers selected through pending state. Test the required two-commit sequence: record-only commit, then code commit.
- Confidence: high

F4

- Severity: blocker
- Plan section or task id: 3.2 `title`, T2, three hand-written records
- What is wrong: The A13 title is 163 characters while the format caps titles at 120. T2 requires all three records to validate with zero errors but also tells the implementer never to edit their bodies. Since the H1 must equal the title, the acceptance test is impossible under those instructions.
- What to change: Raise the title limit to at least 163, preferably 200, unless the owner explicitly authorizes rewriting the still-uncommitted record body and recomputing its attestation. Add a direct validation test for all three records.
- Confidence: high

F5

- Severity: blocker
- Plan section or task id: 3.7, 4.10, 4.13, 5.5 item 6, T9, T11, R3
- What is wrong: The claimed human-only ratification boundary is not implemented. `Write(path)` permission rules are accepted but never consulted, and unanchored `Edit(docs/...)` is relative to the current directory. More fundamentally, Edit rules do not stop an arbitrary Python subprocess such as `scribe ratify` from writing the attestation. The plan acknowledges the bypass but still treats the attestation as human authorization. Official permission behavior is documented under [Read and Edit rules](https://code.claude.com/docs/en/permissions).
- What to change: Design one testable human-triggered path and reject agent-triggered CLI ratification. Add `disable-model-invocation: true` to the human skills, anchor the valid rule as `Edit(/docs/decisions/RATIFICATIONS.jsonl)`, remove the ineffective `Write(...)` rule, and add a reliable guard for raw Bash invocation. If no reliable guard is available this run, explicitly state that ratification is advisory and do not claim the file proves human authorization.
- Confidence: high

F6

- Severity: blocker
- Plan section or task id: 5.4, T11, T12, T15, R7
- What is wrong: `/scribe:init` installs a workflow whose `SCRIBE_SOURCE` is a nonexistent placeholder. Every pull request in an initialized repository will fail before `scribe check` runs, so it cannot serve as the required selective merge gate.
- What to change: Make the generated workflow executable without an unpublished repository, for example by vendoring a versioned checker, accepting a resolvable source during init, or withholding the workflow until configured. Add a test that rejects the supersede case and passes an ordinary branch using the generated workflow's actual command.
- Confidence: high

F7

- Severity: major
- Plan section or task id: 10.3 lifecycle, 3.2 cross-field rules, 4.10, T9
- What is wrong: There is no complete transition matrix for ratification and effective states. It is unclear whether a rejected record may later be ratified, whether ratifying a rejected record supersedes the earlier attestation, and which transitions update or restore predecessors. T9 tests ratification only; `reject` has no direct acceptance test.
- What to change: Specify allowed transitions, idempotency, predecessor behavior, attestation ordering, and exit codes. Test ratify, reject, repeat calls, reject-then-ratify, ratify-then-reject, and invalid transitions.
- Confidence: high

F8

- Severity: major
- Plan section or task id: 3.7, 4.10, T9
- What is wrong: Ratification updates the record before appending its attestation. A failed append leaves a ratified but invalid record; concurrent ratifications can also race. Index regeneration can fail after both authority files change.
- What to change: Lock ratification operations, stage both representations, and define rollback or recovery behavior. Add injected-failure tests for record save, attestation append, and index regeneration, plus a concurrent-writer test.
- Confidence: high

F9

- Severity: major
- Plan section or task id: 4.2, 4.7, 4.8, T6, T8, T14
- What is wrong: `TaskCompleted` checks `decision_worthy`, but no planned producer ever sets it true. `scribe decide` adds a pending id without setting the flag, and ExitPlanMode only computes a verdict. The README also requires a `capture_missing` event, which the plan replaces with a generic gate-log entry.
- What to change: Define when the flag is set and cleared, preferably per task rather than only per session. Emit a typed `capture_missing` event. Test both producers, successful capture, missing capture, task completion, and cleanup.
- Confidence: high

F10

- Severity: major
- Plan section or task id: 4.2, 4.3, 4.9, T6, T8
- What is wrong: The README requires session, prompt, and task correlation and says `task_refs` are set from scratch state. The planned state has no task identity or task refs, and UserPromptSubmit records only timestamps and prompt ids. `scribe new` relies on manually supplied `task_refs`.
- What to change: Add current task refs or task correlation to scratch state and specify how `scribe new` consumes them, or explicitly defer task correlation and update the README conformance statement.
- Confidence: high

F11

- Severity: major
- Plan section or task id: 5.4 item 1, P10, T12
- What is wrong: The source design blocks a branch that "introduces or depends on" an unreviewed successor. The plan checks only changed decision files. A branch can change governed code under a pre-existing unreviewed successor without modifying that record and pass CI.
- What to change: Define dependency using changed paths and matching `affects`, or Decision trailers reachable from the branch range. Add a test where the successor already exists at the branch base and the branch changes code governed by it.
- Confidence: high

F12

- Severity: major
- Plan section or task id: 5.2 item 4, T10
- What is wrong: Commit validation warns only when there is no `Decision:` trailer. A trailer for an unrelated record satisfies the check even if none of its `affects` patterns match the staged governed path.
- What to change: Require at least one resolved, active, overlapping decision for each governed staged path. Add tests for an unrelated valid trailer, an inactive trailer, and multiple governed paths.
- Confidence: high

F13

- Severity: major
- Plan section or task id: 5.2, 4.12, P17, T10, T12, T13
- What is wrong: README 10.4 requires `verify` entries against staged content in `commit-msg` and committed content in CI. The plan explicitly defers both and runs them only through manual lint. The deferral is documented, but no task records the missing hook-row behavior or creates deferred executable tests.
- What to change: Keep the deferral if necessary, but add explicit skipped tests for staged and CI verification and state the activation condition. Do not describe commit validation as implementing the full README row.
- Confidence: high

F14

- Severity: major
- Plan section or task id: 5.1 item 1, 5.3, T10
- What is wrong: `prepare-commit-msg` says it exits without changes for `source=commit` with a SHA, then says new trailers are still added. The amend acceptance test expects no duplicate link, while section 5.3 says amend creates a new SHA and leaves the old link until relink.
- What to change: Choose exact amend behavior. Test an amend with no new pending decision and an amend with a newly pending decision. Assert the precise pre-relink and post-relink link sets rather than "no duplicate link."
- Confidence: high

F15

- Severity: major
- Plan section or task id: 5.3 `relink`, T15
- What is wrong: `relink --since <ref>` says it rebuilds every record from scratch from only the selected history range. That can delete valid implementation links older than `<ref>`.
- What to change: Either remove `--since`, scan all reachable history before destructive replacement, or preserve links outside the selected range. Add a record with one old and one new linked commit and prove both survive.
- Confidence: high

F16

- Severity: major
- Plan section or task id: T6 acceptance test
- What is wrong: `python3 -m json.tool .claude-plugin/plugin.json hooks/hooks.json` treats the second path as an output file and overwrites `hooks/hooks.json` with formatted manifest JSON.
- What to change: Run `json.tool` separately for each file, or use a short read-only loop. Add `claude plugin validate .` when available.
- Confidence: high

F17

- Severity: major
- Plan section or task id: T12 acceptance test
- What is wrong: After `scribe ratify B`, the test expects `scribe check --base main` to pass, but the check is defined over `<base>...HEAD`. Unless the ratification and regenerated index are committed, HEAD still contains the unreviewed version.
- What to change: Commit the ratification, attestation, history, and regenerated index before rerunning the check. Assert the append-only attestation check across that commit.
- Confidence: high

F18

- Severity: major
- Plan section or task id: T13, T14, T15 dependencies
- What is wrong: T13 expects real-repository verification to fail until T14, while tasks are promised green after each task. T15 runs the full suite but does not depend on T13 or T14. The prose order hides dependencies that isolated subagents need.
- What to change: Run T14 before the real-repository portion of T13, or split that acceptance test into a later task. Add T13 and T14 as T15 dependencies and list every task that modifies an earlier task's skipped test.
- Confidence: high

F19

- Severity: major
- Plan section or task id: 4.1 item 6, 4.4, T7, R2, P23
- What is wrong: The fixed edit-path budget is under one second, but hooks.json permits three seconds and the internal 700 ms timer starts only after Python imports. It does not cover `uv`, interpreter, or dependency startup. The test covers only a warm environment and may skip when uv is missing.
- What to change: Measure total process time, cold and warm. Set the hook timeout to at most one second or use a launch path demonstrated to remain under the budget. A missing uv must fail the test environment setup rather than skip the primary performance requirement.
- Confidence: high

F20

- Severity: major
- Plan section or task id: 4.1 launchers, T6, T7, T14
- What is wrong: Fail-open behavior still depends on successfully writing the error or gate log. If `.claude/scribe` is unwritable, full, or cannot be created, the exception handler can itself raise and return a nonzero status.
- What to change: Wrap diagnostic writes independently and make the outermost entrypoint unconditionally return 0 for advisory hooks and gate crashes. Test unwritable state and log paths.
- Confidence: high

F21

- Severity: major
- Plan section or task id: 1 non-goal 2, 4.1 `run_gate`, 4.7, P9, T14
- What is wrong: Shipping `SCRIBE_GATES=enforce` means inherited user or CI environment can turn phase 3 scaffolds fail-closed even though this run promises they are always fail-open. Tests proving exit 2 do not require exposing a production switch.
- What to change: Remove the runtime switch from the shipped path for this release, or require an explicit versioned configuration that init never enables. Unit-test gate verdicts separately and test that production dispatch always exits 0.
- Confidence: high

F22

- Severity: major
- Plan section or task id: 4.1 item 2, hooks.json, T6, Windows best effort
- What is wrong: Hook commands use shell form, so Claude Code invokes `sh -c`, Git Bash, or PowerShell. This weakens the "no bash in hooks" claim and makes path quoting platform-dependent. Claude Code recommends exec form with `args` when a command references path placeholders. See [hook exec form](https://code.claude.com/docs/en/hooks).
- What to change: Use `"command": "uv"` and an `args` array containing `run`, `--frozen`, `--project`, `${CLAUDE_PLUGIN_ROOT}`, and the subcommand. Update T6 to assert the structured argv.
- Confidence: high

F23

- Severity: major
- Plan section or task id: Phase 1 scope, section 8, T2 through T5
- What is wrong: The repository has no commits, so the three hand-written records do not yet have the required `Decision:` and `Session:` trailers. No task explicitly owns the initial record commit; section 8 only discusses trailers on later implementing commits.
- What to change: Assign a task to commit the three records with their own trailers before implementation links are expected, or make the orchestrator's first commit explicitly responsible. Add a reverse-lookup acceptance test against those real commits.
- Confidence: high

F24

- Severity: minor
- Plan section or task id: 3.2 `task_refs`
- What is wrong: `task_refs` accepts arbitrary strings despite the fixed decision limiting them to GitHub Issue or Linear identifiers.
- What to change: Define and validate the accepted forms, while allowing an empty list. Add rejected examples for prose and unrelated identifiers.
- Confidence: high

F25

- Severity: minor
- Plan section or task id: 3.2 `verify`, P17
- What is wrong: README 10.2 lists `grep` and `jsonpath` as allowlisted engines. The plan silently narrows the schema to `grep`; P17 defers where verification runs, not the `jsonpath` engine.
- What to change: Implement `jsonpath`, or explicitly defer it in non-goals and add a fixture proving it is rejected with a deliberate unsupported-engine message.
- Confidence: high

F26

- Severity: minor
- Plan section or task id: 3.1 ULID, T2
- What is wrong: The regex accepts 26-character Crockford strings above the maximum 128-bit ULID, such as values beginning with `8` through `Z`. A canonical ULID must not exceed `7ZZZZZZZZZZZZZZZZZZZZZZZZZ`.
- What to change: Reject overflow during decode and add boundary tests for the maximum valid and first invalid values.
- Confidence: high

F27

- Severity: minor
- Plan section or task id: 4.2 state locking, T6
- What is wrong: "Use `msvcrt.locking`" is not enough for an isolated implementer. It needs an existing byte range, correct file positioning, retry behavior, and unlock handling. No Windows-oriented lock acceptance test is specified.
- What to change: Specify the lock-file algorithm and bounded retry behavior. Unit-test the platform adapter with mocked `msvcrt`, while keeping native Windows verification explicitly deferred.
- Confidence: medium

F28

- Severity: minor
- Plan section or task id: 5 git-hook shim, T11, R10
- What is wrong: `#!/usr/bin/env python3` is not reliably available in native Git for Windows installations, where only `python.exe` or the `py` launcher may exist. `scribe init` also installs shims without checking that `uv` is available.
- What to change: Treat the Windows shim as an explicit known limitation, add an init preflight for uv and interpreter resolution, and generate a platform-appropriate shim where possible. Keep failure open but report it during init rather than at every commit.
- Confidence: high

F29

- Severity: minor
- Plan section or task id: T1, T6
- What is wrong: T1 allows a missing `uv.lock` to be deferred to step 5, but every hook command added by T6 uses `uv run --frozen`. Later tasks are not implementable if T1 takes that fallback.
- What to change: Make a valid lockfile a prerequisite for T6 and later tasks. If locking cannot run, stop the implementation pipeline with a clear blocked result.
- Confidence: high

F30

- Severity: minor
- Plan section or task id: All `UNVERIFIED` annotations, R1, R3, R10
- What is wrong: Several annotations are now resolvable. Matcher alternatives, timeout units, timeout fail-open behavior, common stdin fields, `prompt_id`, Edit and Write `file_path`, Bash `command`, ExitPlanMode `plan`, Stop fields, PreToolUse and SessionStart `additionalContext`, `${CLAUDE_PLUGIN_ROOT}` in plugin skills, the manifest, and the marketplace shape are documented. `${CLAUDE_SESSION_ID}` is documented as skill substitution, but the plan relies on it as a process environment variable without evidence. `CLAUDECODE` remains unverified. `setup-uv@v6` exists but is not the claimed latest major; current upstream examples use newer versions.
- What to change: Remove resolved `UNVERIFIED` labels and cite the minimum supported Claude Code version. Pass `--session "${CLAUDE_SESSION_ID}"` explicitly from the skill instead of assuming an environment variable. Do not use `CLAUDECODE` as an authority signal until verified. Pin a current setup-uv release or commit.
- Confidence: high for documented fields and substitutions; medium for the absence of a reliable `CLAUDECODE` contract

Things the plan does well

- It preserves the fixed markdown store, immutable body, separate review and effective states, and derived supersession model.
- Advisory hooks consistently target fail-open behavior and bounded retrieval output.
- The index puts supersedes-ratified records first and keeps generation deterministic.
- The three attestation hashes and ULID timestamps are internally consistent.
- The task graph is broadly acyclic, and most modules have concrete files and focused acceptance tests.
---
Produced by `docs/build/pipeline/step2_review.sh` (gpt-6-astra, read-only, reasoning high) in two 9-minute slices, the second via `codex_resume.sh`. 11 web searches were used to check hook mechanics.
