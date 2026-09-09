# Handoff: scribe build, evening of 2026-09-08

Written by the main Fable 5.1 session for the next session (after a compaction or a usage-limit reset). Everything below is on disk and committed unless marked otherwise.

## Day 2 addendum (2026-09-09, read this first)

- State: 38 commits on `nikita/feat/scribe-bootstrap`, tree clean, nothing pushed, no GitHub repo. `uv run pytest -q`: 411 passed, 3 skipped. lint, index --check, validate, `check --base 3a5b1d2` and `claude plugin validate .` green. Live headless plugin test passed again through the new registration (`python3 -I -S hooks/supervise.py`).
- Done today: V1 supervisor (commit 94f5971, hardened in 3050f09 with a per-run deny token); Batch A groups 1 to 3 (96a8bd0, c80c5c2, 16ae245); Codex review of groups 1 and 2 (`08-codex-review-batch-a.md`, its follow-ups fixed in 3050f09); Batch B with the owner's calls: V12 attested-live-not-superseded authority (3050f09), V21 subdirectory warning (2b81766), V3 dirty-ledger refusal and base-tip check (9d8cb06), V19 no pending cap (6057c02), V8 one ledger lock (406cced), V6 record_deleted (16ae245). Reports: `07-batch-a-report.md`, `09-batch-b-report.md` plus `09-batch-b-item-{2,3,4,5}.md`. Decisions I74 to I119 and M10 in the log; owner answers recorded in the triage doc's Batch B section (all six decided as recommended).
- Live finding (V21): when Claude Code starts in a repository subdirectory, no project settings load at all (`/`, `**` and `//` rules, `settings.json` and `settings.local.json` all tested with `pipeline/step8_deny_rule_test.sh`), so the RATIFICATIONS deny rule only protects root-started sessions. Mitigated by warnings, not fixable from inside the plugin; the user-level rule `Edit(**/docs/decisions/RATIFICATIONS.jsonl)` is the workaround.
- Model rules from the owner: Codex gpt-5.6-terra implements, gpt-5.6-luna reads and extracts, reviews on gpt-5.6-sol or gpt-6-astra by stakes; Sonnet 5 implements on the Claude side, Opus reviews. Codex quota ran out twice today (both times "try again at 5:27 PM").
- Leftovers for the owner: four throwaway worktrees and branches `nikita/fix/batch-b-{v3,v8,v19,v21}` under `/home/alfakentavr/scribe-wt/` (their diffs are merged; `git worktree remove --force` and `git branch -D` each when convenient; not deleted by the session per the no-deletion rule); patches at `/home/alfakentavr/scribe-wt/*.patch`.
- Next: Batch C records via `/scribe:decide` (V7 history replay, V13 staged-content hooks, V23 fixture rewrite); a final Codex validation pass (astra) over commits 94f5971..406cced before any merge; playground dry run by the owner (shims refreshed today); GitHub repo and push remain owner decisions; Q1 to Q6 still open; TaskCompleted enforce-mode behaviour now keeps the flag (revisit with gates).

## State in one paragraph

`scribe` is built. All 16 plan tasks are done and committed on branch `nikita/feat/scribe-bootstrap` in `/home/alfakentavr/scribe` (24 commits, nothing pushed, no GitHub repo created yet). `uv run pytest -q` gives 333 passed, 3 skipped (the deferred tests). `scribe lint`, `scribe index --check`, `scribe validate docs/decisions` and `scribe check --base 3a5b1d2` are all green. The plugin loads live: a headless `claude -p --plugin-dir /home/alfakentavr/scribe` run fired SessionStart, UserPromptSubmit, the Edit injection (the model reported the right record alias) and Stop. Three playground repos for the owner are ready at `/home/alfakentavr/scribe-playground/`.

## Where everything is

- Design source of truth: `~/.claude/.claude/worktrees/decision-scribing-glossary/research/decision-scribing/README.md` sections 10 to 16, plus `build-brief.md` and `AUTONOMOUS_DECISIONS_09_08_2026.md` in that directory. That worktree branch `nikita/docs/decision-scribing-glossary` has 5 unpushed commits.
- Plan chain: `docs/build/01-plan.md` (Fable planner), `02-plan-review.md` (Codex gpt-6-astra, 30 findings), `03-findings-response.md` and `03-plan-v2.md` (Fable reviser; v2 is the binding plan), `04-progress.md` (per-task status and who built it), `04-implementation-report.md` (Codex T16 report plus main-session addendum with the live test and docs check), `04b-codex-validation.md` (Codex read-only validation of the finished code; see below), this file.
- Pipeline scripts and prompts: `docs/build/pipeline/`. Codex runs go through `codex_resume_detached.sh` or the `step4*.sh` scripts (setsid, 20-minute hard cap, `< /dev/null`, network on, .git read-only inside the sandbox so the main session commits).
- Decisions log for the build: `AUTONOMOUS_DECISIONS_09_08_2026.md` at the repo root (P planner, R reviser, I implementers, M main session, O owner requests). Owner questions Q1 to Q6 are batched there and still open.
- Seed records: `docs/decisions/D-260908-*.md` (three, ratified, now `implemented` with links), `RATIFICATIONS.jsonl`, generated `INDEX.md`.
- Playgrounds: `/home/alfakentavr/scribe-playground/README.md` explains the three repos (01-add-feature, 02-fix-bug, 03-refactor with a supersede demo), the two ways to fill a record, and how to reset with the `playground-start` tag.

## Decisions taken tonight that the owner has not yet seen in full

- M1 to M9 in the decisions log. Most consequential: Codex could not commit or reach the network inside its sandbox, so the main session commits between slices; Codex hit its quota mid-T3 and the owner switched implementation to Claude subagents (Fable, then Opus, then Sonnet per the owner's budget note); Codex returned for T16 and the validation pass.
- Templates live at `src/scribe/templates/` (I19), not a top-level `templates/`.
- Record front matter is re-serialised by `relink` and the hooks (quoted dates, flow-style lists, YAML comments dropped). Bodies are verified byte-identical. If the owner wants comment-preserving YAML, that is a follow-up.
- `post-commit` writes backlinks after the commit, so the tree is dirty right after a commit that cites a record; a follow-up commit is needed (see commit 89a60d2 for the pattern). Candidate improvement: have the shim print the reminder more loudly, or document it in the README.

## Unverified items still open

- U2: whether PreToolUse Bash hooks fire for a skill's inline `!` command. Not documented. Only matters once gates run in enforce mode.
- U3: Windows behaviour of the lock adapter and the git-hook shim. Untested; the owner's Windows machine is the place to try.
- U1 is resolved (docs confirm `$ARGUMENTS` substitution in inline commands).

## Codex validation verdict (04b-codex-validation.md, 2026-09-08 21:51)

"Fix first": 1 blocker, 16 majors, several minors; bodies and attestations confirmed unchanged; Codex could not run uv in its read-only sandbox, the main session reproduced the green suite.

- V1: fixed 2026-09-09 (M10): `hooks/supervise.py` wraps every uv call, hooks.json registers `python3 -I .../hooks/supervise.py`, the shim imports the same script, `scribe.protocol` carries the `[scribe-deny]` marker; 12 tests in `tests/test_supervise.py` break uv on purpose. Original finding kept below for the record.
- V1 (blocker, as found): when `uv run` itself fails (missing uv, broken cache, stale lock) the registered hook command exits 2 before Python starts, and Claude Code treats exit 2 on PreToolUse or UserPromptSubmit as a denial; the git shim likewise cannot catch uv failing, so prepare-commit-msg can block a commit even in warn mode. Fix: a dependency-free supervisor (plain `python3` script, no imports beyond stdlib) that runs uv, maps any startup failure to exit 0 with one stderr line, and forwards exit 2 only when the application deliberately returned it. Update hooks.json `command` and the shim template, add tests that break uv on purpose. This is the first thing to do next session; until then the risk is limited to machines where uv is broken (the live test on this machine passed).
- V2 (major): fixed in this session (`skills/init/SKILL.md` argument-hint quoted; all five skill front matters now parse).
- V3 to V17 (major): CI range semantics, attestation completeness, deletion bypass, concurrency, symlinks, Unicode paths, post-commit recovery, gate authorization scope. Each needs a read and a decision (fix, defer with a scribe record, or reject with reason). Good candidates for the first real `/scribe:decide` records.

## Next steps, in order

1. V1 is done. Triage V3 to V21 in `docs/build/04b-codex-validation.md`; the triage lives in `docs/build/06-validation-triage.md`. Anything fixed goes through `/commit` on the same branch.
2. Owner decisions waiting: create the GitHub repository and push (never done without asking); open a draft PR or merge to `main` locally; answer Q1 to Q6 in the decisions log; whether to convert the most consequential I and M lines into scribe records (dogfooding beyond the three seeds).
3. Owner exercise: work through the playgrounds; feedback there is the first real usability signal for the record form.
4. Later: enable gates (`SCRIBE_GATES: enforce` in `.claude/scribe/config.json`) only after the deferred two-worktree test is un-skipped and green; the weekly lint schedule; Windows test.

## How to continue from a cold session

```
cd /home/alfakentavr/scribe
git status --short && git log --oneline | head -5
uv run pytest -q
uv run scribe lint && uv run scribe index --check
claude --plugin-dir /home/alfakentavr/scribe     # then /reload-plugins, /scribe:decide
```

Standing rules: `/commit` skill for every commit, ask before push or PR, branch names `nikita/<type>/<kebab>`, plain hyphens only, Sonnet for implementation subagents and Opus for review, Codex runs detached with the 20-minute cap.
