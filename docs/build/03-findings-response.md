# Response to the plan review (step 3 of 5)

Written 2026-09-08 by the Fable 5.1 reviser. Input: `docs/build/01-plan.md` (v1), `docs/build/02-plan-review.md` (F1 to F30). Output: this file and `docs/build/03-plan-v2.md`, the plan the step 4 implementer builds from. Authority order used when a finding disputed the design: `build-brief.md` fixed decisions, then `research/decision-scribing/README.md` sections 10 to 16, then the v1 plan.

Facts checked against the Claude Code docs on 2026-09-08 (hooks reference `https://code.claude.com/docs/en/hooks`, plugins reference `https://code.claude.com/docs/en/plugins-reference`, permissions `https://code.claude.com/docs/en/permissions`, skills `https://code.claude.com/docs/en/skills`): exec-form hook commands (`command` plus `args`, no shell), `timeout` in integer seconds with the hook cancelled and its output discarded on expiry (the tool call proceeds), `hookSpecificOutput.additionalContext` on `PreToolUse`, `SessionStart` and `UserPromptSubmit`, common stdin fields (`session_id`, `prompt_id` since v2.1.196, `cwd`, `hook_event_name`, `permission_mode`), `tool_input.file_path` always absolute for Edit and Write, `tool_input.command` for Bash and PowerShell, `tool_input.plan` and `planFilePath` for `ExitPlanMode`, `TaskCompleted` fields (`task_id`, `task_subject`, optional `task_description`), `Stop` fields (`stop_hook_active`, `last_assistant_message`), matcher alternatives (`Edit|Write`), `Edit(/path)` anchored at the settings source with `Write(...)` rules accepted but never consulted (Edit rules cover Write since v2.1.228), `disable-model-invocation: true` on skills, `${CLAUDE_SESSION_ID}` and `${CLAUDE_PLUGIN_ROOT}` as skill-content substitutions, `claude plugin validate <dir>`, marketplace keys (`owner.email` is required), `astral-sh/setup-uv` latest release `v10.0.1` (checked with `gh api`), local Claude Code `2.1.265`. Minimum supported Claude Code version for v2: 2.1.228 (the newest feature relied on: an `Edit` deny rule also blocking `Write`).

Counts: 23 accepted, 7 accepted with change, 0 rejected.

## Blockers

### F1 (supersede edge survives rejection): accepted
A `supersedes` edge is now "effective" only while the successor has `review_state != rejected` and `effective_state in (proposed, implemented, superseded)`; rejected, expired and backtracked successors do not retire their predecessor, and a superseded successor keeps retiring its own predecessor so chains hold. `scribe new`, `ratify`, `reject` and `lint --expire` call one shared reconcile step that marks or restores the predecessor's `effective_state` (new history event `restored`), and the indexer derives Active and Retired from effective edges only. End-to-end test B-supersedes-A, reject B, A back in Active and in injection: plan v2 section 3.8 and task T9.

### F2 (`affects` has no `action` type): accepted
`affects` items are `{type: path|package|action, pattern, negate}`; `action` patterns are denylist rule names (`^[a-z][a-z0-9-]*$`), matched by exact name against `policy.py`; the validator accepts them, the edit-time matcher ignores them, lint warns `unknown_action` when the name is not a shipped rule. Valid, invalid, matching and non-matching fixtures: plan v2 sections 3.2 and 4.7, tasks T2 and T10.

### F3 (pending id consumed by the record-only commit): accepted
`post-commit` removes an id from `pending_decisions` only after it recorded an implementation link for that commit. A link is recorded only when the commit changed at least one path matching the record's `affects` (all non-`docs/decisions/` paths when `affects` is empty). Record-carried trailers (the record file itself is staged) and pending-state trailers are distinguished in the code and in the tests, and the two-commit sequence is an acceptance test: plan v2 sections 5.1, 5.3, task T11.

### F4 (163-character title versus 120 limit): accepted
Title limit raised to 200 characters. The three records stay byte-identical; a direct validation test over `docs/decisions/` is T2's acceptance test. Plan v2 section 3.2.

### F5 (ratification is not human-only): accepted with change
Accepted: `disable-model-invocation: true` on `ratify`, `reject` and `init`; the deny rule becomes the single anchored `Edit(/docs/decisions/RATIFICATIONS.jsonl)` (covers Write per the permissions doc), the `Write(...)` rule is dropped; the `CLAUDECODE` tag is dropped; `via` is passed explicitly (`--via skill|cli|hand-written`). The human path is one testable path: the skill runs the CLI through skill inline shell injection (`` !`...` ``), which executes before the model sees the skill content, so the model is never the actor on that path. Changed: the review's "reliable guard for raw Bash invocation" is not available. A `Bash(*scribe ratify*)` deny rule would also abort the skill's injected command (skills doc: "a matching ask or deny rule still aborts the invocation regardless of allowed-tools"), and no documented environment variable identifies a Claude Code subprocess. Plan v2 therefore states in sections 3.7 and 4.10 that in this release ratification is human-triggered by construction of the skills, and the attestation line records who ran the verdict and through which path; it is not proof of human authorization. Owner question Q5 added. Tasks T9 and T14.

### F6 (dropped CI workflow cannot run): accepted with change
`scribe init` writes `.github/workflows/scribe-check.yml` only when `--ci-source <spec>` is given; without it, init prints the instruction and writes nothing. Two spec forms: a path (`.` means "this repository is the scribe checkout", used for dogfood) renders `uv run --frozen --project <path> scribe check ...`, a URL (`git+https://...@v0.1.0`) renders `uvx --from "<url>" scribe check ...`. The test extracts the `run:` line from the generated workflow and executes it in a tmp repo for both the failing supersede case and a passing ordinary branch. Vendoring a checker was rejected because it duplicates the package (P11 stands). Plan v2 section 5.4, task T14. Q1 stays open for the owner.

## Major findings

### F7 (no transition matrix): accepted
Section 3.8 of plan v2 is the matrix: allowed transitions, idempotent repeats (exit 0, no new attestation, no history), reversals (rejected to ratified and back, each appending an attestation and history), predecessor reconcile, attestation ordering, exit codes. Tests for ratify, reject, repeat, reject-then-ratify, ratify-then-reject and unknown id: task T9.

### F8 (ratify ordering, races, rollback): accepted
Order is lock, validate transition, append attestation (the authority), write record via temp plus `os.replace`, reconcile predecessor, regenerate index. The lock is an exclusive lock on `RATIFICATIONS.jsonl` with bounded retry. A record left behind by a crash between steps validates as `state_behind_attestation`, and re-running the same command heals it without a duplicate line. Injected-failure tests for record save, attestation append and index regeneration plus a two-process concurrent test: section 4.10, task T9.

### F9 (`decision_worthy` never set): accepted
The ExitPlanMode policy sets `decision_worthy` on the session (with the policy areas and the prompt id); `scribe new --register` appends to `records_written`; `TaskCompleted` denies (shadow) and emits a typed `capture_missing` gate-log event when the flag is set and no record was written after it, then clears the flag. Per-task correlation is impossible at ExitPlanMode time (no task id in that payload), so the flag is per session and carries `set_at`. Tests for both producers, capture present, capture missing, cleanup: sections 4.2, 4.7, 4.8, task T10.

### F10 (no task correlation in scratch state): accepted with change
`UserPromptSubmit` records `prompt_id` and extracts tracker ids from the prompt text (`LIN-123`, `ABC-42`, `owner/repo#42`, `#42`) into `sessions[sid].task_refs`; `scribe new` fills `task_refs` and `provenance.prompt_ids` from the spec first, then from the session. Task identity from `TaskCreated` is explicitly deferred (non-goal 6) and the README conformance statement says so. Sections 4.2, 4.3, 4.9, tasks T6 and T8.

### F11 (CI check misses "depends on"): accepted
`scribe check` fails when an unreviewed record superseding a ratified one is introduced or modified in the range, or when any path changed in the range matches that record's `affects`, or when any commit in the range carries its `Decision:` trailer. Test with the successor already at the branch base: section 5.4, task T12.

### F12 (unrelated trailer satisfies commit validation): accepted
For each staged path governed by an active record, `commit-msg` requires a resolved, active trailer whose `affects` match that path, else warns naming the candidates. Tests for an unrelated trailer, an inactive trailer and several governed paths: section 5.2, task T11.

### F13 (verify deferred silently): accepted
Two `@pytest.mark.skip` tests state the deferred behaviour (staged verify in `commit-msg`, committed verify in `scribe check`) and the activation condition (14 days of dogfood lint with zero `verify_error`); the commit-validation description says which README 10.4 rows it does not implement. Section 5.2 and 5.4, tasks T11 and T12.

### F14 (amend behaviour contradictory): accepted
`prepare-commit-msg` no longer exits early on amend; the same trailer logic runs and `addIfDifferent` prevents duplicates. `post-commit` on amend adds a link for the new sha and leaves the old one; the test asserts the exact link sets before (`{old, new}`) and after `relink` (`{new}`), for an amend with and without a newly pending decision. Sections 5.1, 5.3, task T11.

### F15 (`relink --since` deletes old links): accepted
`--since` removed. `relink` walks `git rev-list --all`, keeps every link whose commit is reachable, drops unreachable ones, adds missing ones. Test with one old and one new linked commit: section 5.3, task T15.

### F16 (`json.tool` overwrites hooks.json): accepted
Separate invocations per file, plus `claude plugin validate .` when the `claude` binary is on PATH. Task T6.

### F17 (check passes only if ratification is committed): accepted
The acceptance sequence commits the ratification, attestation and regenerated index before re-running `check`, and asserts the append-only attestation rule across that commit. Task T12.

### F18 (hidden task dependencies): accepted
Gates (T10) now precede lint (T13); lint's real-repository acceptance test runs when T13 lands. Every task lists its dependency edges explicitly, T15 depends on T11, T13 and T14, and no task modifies another task's skipped test. Section 6.

### F19 (edit-path budget not measured end to end): accepted with change
`hooks.json` timeout for the edit hook is 1 second (the documented behaviour on expiry is cancel and proceed, so this is the mechanical fail-open ceiling); the internal deadline stays 700 ms from process start. `tests/test_timing.py` measures the full `uv run ...` subprocess: warm median of 3 runs under 1.0 s with 100 records (hard assertion), and a bytecode-cold run (`src/**/__pycache__` removed, `PYTHONDONTWRITEBYTECODE=1`) printed and bounded at 2.0 s. A missing `uv` fails the test with `pytest.fail`, never skips. Changed from the review: a fresh-venv cold start is not measured in tests (it needs network and is what the 120 s SessionStart hook absorbs). Sections 4.1, 7, task T7.

### F20 (fail-open depends on writable log): accepted
The outermost entrypoint returns 0 for advisory hooks and for gate crashes regardless of what the diagnostic writes do; every log write is wrapped separately and dropped on failure. Tests point `.claude/scribe` at a read-only directory and at a file. Section 4.1, task T6.

### F21 (`SCRIBE_GATES=enforce` inherited from environment): accepted with change
The environment variable is no longer read. The switch keeps its name and moves to a repo-local, git-ignored, versioned file `.claude/scribe/config.json` (`{"version": 1, "SCRIBE_GATES": "shadow", "SCRIBE_COMMIT_MSG": "warn"}`) that `scribe init` writes with the safe values and never sets to `enforce`; tests write `enforce` into the tmp repo's config. Keeping the name keeps record A13's `verify` entry (`SCRIBE_GATES` present in `pre_tool_use_gate.py`) truthful without touching the record. The same treatment applies to P25's `SCRIBE_COMMIT_MSG`. Verdict computation is unit-tested separately from dispatch, and a test proves production dispatch exits 0. Section 4.1, 4.7, tasks T6, T10.

### F22 (shell-form hook commands): accepted
All hook entries use exec form: `"command": "uv", "args": ["run", "--frozen", "--project", "${CLAUDE_PLUGIN_ROOT}", "scribe", "hook", "<event>"]`. T6 asserts the structured argv. Section 4.1.

### F23 (no task owns the initial record commit): accepted
T1 begins with a bootstrap commit of the existing files (records, `RATIFICATIONS.jsonl`, `docs/build/`, decisions file, `.gitignore`) carrying the three `Decision: <alias> <ulid>` trailers and a `Session:` trailer. T5's acceptance test runs `scribe lookup` against that real commit. The implementation-link rule (F3) means this commit produces no links because it changes no `affects` path. Sections 6 (T1), 8.

### F24 (`task_refs` unvalidated): accepted
Accepted forms: `^[A-Z][A-Z0-9]{1,9}-\d+$` (Linear and similar), `^#\d+$`, `^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#\d+$` (GitHub). Empty list allowed; prose rejected with `invalid_task_ref`. Section 3.2, task T2.

### F25 (`jsonpath` silently dropped): accepted with change
`jsonpath` is deferred explicitly (non-goal 7); the validator rejects it with `unsupported_engine: jsonpath is on the README allowlist but not implemented in this release`, distinct from an unknown engine. Fixture in T2.

### F26 (ULID overflow): accepted
Decode rejects values above `7ZZZZZZZZZZZZZZZZZZZZZZZZZ` (`invalid_ulid`); boundary tests for the maximum valid and the first invalid value. Section 3.1, task T2.

### F27 (Windows lock underspecified): accepted
Lock algorithm specified: a sibling lock file opened `a+`, one byte at offset 0, `msvcrt.locking(fd, LK_NBLCK, 1)` after `seek(0)` on Windows, `fcntl.flock(LOCK_EX | LOCK_NB)` on POSIX, retry every 50 ms up to 2 s, then proceed without the lock and log; unlock in `finally`. Unit test with a fake `msvcrt` module; native Windows verification stays deferred. Section 4.2, task T6.

### F28 (`python3` shebang and no uv preflight): accepted
`scribe init` preflights `uv` and the hook interpreter (`python3` on POSIX, `python` on Windows) and reports once at init time; the shim keeps failing open at commit time. Windows shim is listed as a known limitation in the README. Section 5.5, task T14.

### F29 (missing `uv.lock` fallback breaks T6): accepted
A committed `uv.lock` is a hard T1 requirement; if `uv lock` cannot run, T1 fails and the orchestrator reports `BLOCKED` instead of continuing. Task T1.

### F30 (stale UNVERIFIED markers): accepted with change
Resolved markers removed with the documentation facts listed at the top of this file; `${CLAUDE_SESSION_ID}` is passed explicitly as `--session` from the skill; `CLAUDECODE` is dropped from the design; `setup-uv@v10`; minimum version cited. Changed: three items remain UNVERIFIED and are listed in one place (plan v2 section 10) with the isolating module for each: `$ARGUMENTS` substitution inside a skill's inline `!` command, whether PreToolUse Bash hooks fire for skill-injected commands (matters only once gates enforce), and Windows behaviour of the lock adapter and the git-hook shim.
