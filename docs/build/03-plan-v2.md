# Scribe implementation plan v2 (step 3 of 5)

Written 2026-09-08 by the Fable 5.1 reviser after the step 2 review (`docs/build/02-plan-review.md`, findings F1 to F30; responses in `docs/build/03-findings-response.md`). This file replaces `docs/build/01-plan.md` completely: the implementer reads only this file and the repository. Design source of truth: `research/decision-scribing/README.md` sections 10 to 16 in the `~/.claude` repo; scope and fixed decisions: `build-brief.md` next to it. `Pn` refers to planner choices and `Rn` to reviser choices in `/home/alfakentavr/scribe/AUTONOMOUS_DECISIONS_09_08_2026.md`. `UNVERIFIED` marks the three remaining claims about Claude Code mechanics that the docs do not settle; they are listed in section 10 with the module that isolates each. Everything else about Claude Code in this plan was checked against `https://code.claude.com/docs/en/hooks`, `/plugins-reference`, `/permissions` and `/skills` on 2026-09-08; minimum supported Claude Code version 2.1.228, tested locally against 2.1.265.

All repository paths are relative to `/home/alfakentavr/scribe` unless absolute. Every path inside records, state and hook output is a forward-slash, repository-relative POSIX path.

## 0. Implementer contract and definition of done

### 0.1 Implementer contract (binds the step 4 orchestrator and its subagents)

1. Work the task list in section 6 in order of dependency. For each task: read the task text, spawn one subagent with the task text plus sections 2, 3, 4 and 5 of this plan, let the subagent implement the behaviour and its tests, then the orchestrator itself runs `uv run pytest -q` and the task's acceptance command(s) from `/home/alfakentavr/scribe`. Only then is the task done. Tasks whose dependency edges are satisfied may run in parallel (at most 3), but the acceptance run is always sequential per task and `uv run pytest -q` must be green after every completed task.
2. Never mark a task done with a red test or a failed acceptance command. Send the failure back to the same subagent once; if still red, fix it, and record why in `docs/build/04-progress.md`.
3. Never edit the bodies of the three hand-written records in `docs/decisions/` (everything after the closing `---`). Their front matter changes only through scribe commands (`post-commit`, `relink`, `ratify`, `reject`), never by hand. Never edit `docs/decisions/RATIFICATIONS.jsonl` by hand.
4. Never touch `docs/build/` except `04-progress.md` and, at the end, `04-implementation-report.md`.
5. Any choice this plan leaves open: pick the simplest option that keeps the tests green, append one line `In. <choice>: <reason>` under `## Step 4 implementer decisions` in `AUTONOMOUS_DECISIONS_09_08_2026.md`, continue. Do not stop to ask.
6. Commit after each task with the message type and title rules in the orchestrator prompt. Where a task says "Decision trailer", the commit message ends with exactly those trailer lines. Never push, rebase, force, or delete branches.
7. `uv` only: `uv sync`, `uv add`, `uv run`. No `pip`, no global installs. Hooks and git hooks in Python, never bash. Plain hyphens only, no em dashes, no emojis, in every file.
8. If T1 cannot produce `uv.lock` (no network and no cache), stop and report `BLOCKED: uv lock failed` instead of continuing without it.

### 0.2 Definition of done (checked by the step 5 reviewer)

1. `uv run pytest -q` is green with exactly 3 skipped tests (two-worktree scenario, staged verify, CI verify) and prints the measured injection hook times.
2. `uv run scribe validate docs/decisions` prints `3 records, 0 errors, 0 warnings`.
3. `uv run scribe lint` on this repository exits 0 with no `verify_failed` and no `verify_error`.
4. `uv run scribe index --check` exits 0; `docs/decisions/INDEX.md` lists the three records under Active decisions and a Review queue of 0.
5. `uv run scribe check --base <first commit>` exits 0 on this repository.
6. `uv run scribe lookup D-260908-verbatim-quote-is-the-evidence` prints the bootstrap commit and at least one implementing commit for each of the three records after `uv run scribe relink` (step 5 runs relink once; see section 8).
7. `python3 -m json.tool .claude-plugin/plugin.json`, `python3 -m json.tool hooks/hooks.json` and `python3 -m json.tool .claude-plugin/marketplace.json` each succeed; `claude plugin validate .` passes when `claude` is on PATH.
8. Every hook entry in `hooks/hooks.json` is exec form (`"command": "uv"` with an `args` array), the `Edit|Write` entry has `"timeout": 1`.
9. `skills/ratify/SKILL.md`, `skills/reject/SKILL.md`, `skills/init/SKILL.md` carry `disable-model-invocation: true`; `skills/decide/SKILL.md` passes `--session "${CLAUDE_SESSION_ID}"`.
10. `.git/hooks/prepare-commit-msg`, `commit-msg`, `post-commit` in this repository are scribe shims; `.claude/settings.json` denies `Edit(/docs/decisions/RATIFICATIONS.jsonl)`; `.claude/scribe/config.json` has `SCRIBE_GATES: shadow`.
11. No file in the repository contains an em dash (U+2014) or an en dash (U+2013): `rg -n -e $'\u2014' -e $'\u2013' .` returns nothing (bash ANSI-C quoting builds the two characters from their code points, so this plan itself contains neither).
12. `docs/build/04-implementation-report.md` exists and lists every deviation from this plan with its `In` item.
13. The three record bodies are byte-identical to the bootstrap commit (`git diff <bootstrap sha> -- docs/decisions/D-*.md` shows front-matter changes only, or nothing).

## 1. Goal and non-goals

Goal (this run):

1. A Claude Code plugin `scribe` in `~/scribe`, loadable with `claude --plugin-dir ~/scribe`, shipping five skills (`/scribe:decide`, `/scribe:ratify`, `/scribe:reject`, `/scribe:init`, `/scribe:lint`), a Python CLI (`uv run scribe ...`), Claude Code hooks (advisory, fail-open) and git hooks installed per repository by `/scribe:init`.
2. Phase 1: the record schema (section 3), a validator, the three real records (already in `docs/decisions/`, committed by T1 with `Decision:` trailers), a trailer-to-record reverse lookup, and the DEMM grade (`docs/build/01-records-grading.md`, already written).
3. Phase 2: decide, ratify, reject, init, lint skills; `INDEX.md` generator with the review queue first; `prepare-commit-msg`, `commit-msg` (warn only), `post-commit` git hooks; `PreToolUse` injection on Edit and Write matched by `affects`.
4. Phase 3, scaffolded only: `ExitPlanMode` policy, Bash denylist, `TaskCompleted` and `Stop` reconcile, all registered and running in shadow mode (compute the verdict, log it, exit 0); the CI check `scribe check` that fails on an unreviewed record superseding a ratified one.

Non-goals (this run):

1. No vector store, git notes, MCP server, event log (README 10.6), friction log, retro or promotion ladder (README 10.5), weekly scheduler.
2. No enforcement by the phase 3 gates: production dispatch always exits 0. The `enforce` mode exists only through the repo-local config file (section 4.1 item 6), which `scribe init` never sets to `enforce`; tests set it in temporary repositories.
3. No `FileChanged`, `PostToolUse`, `PostToolBatch`, `InstructionsLoaded` hooks (README 10.4 observation rows).
4. No Windows testing; Windows is best effort by construction (Python via `uv`, forward-slash paths, exec-form hooks, no bash). Known Windows gaps are listed in section 10 and in the README.
5. No GitHub repository creation, no push, no publishing.
6. No task identity from `TaskCreated` in scratch state (README 10.4 "task correlation"): tracker ids are extracted from prompts (section 4.3) and `TaskCompleted` payload fields are used when present; correlating a decision to a Claude Code task id is deferred.
7. No `jsonpath` verify engine (README 10.2 allowlist): the validator rejects it with a deliberate message (section 3.2).
8. No running of `verify` entries in `commit-msg` or `scribe check` (README 10.4 "Commit validation" row): `scribe lint` runs them; two skipped tests document the deferred behaviour and its activation condition (section 5.2).
9. No proof of human authorization for ratification beyond the construction in section 3.7 and 4.10.

## 2. Repository layout

Every path the finished repository contains after T16. `(gen)` = generated and committed; `(local)` = git-ignored.

```
.claude-plugin/plugin.json               manifest: name scribe, version 0.1.0, description, author
.claude-plugin/marketplace.json          single-entry marketplace (name, owner{name,email}, plugins[{name, source: "./", description, version}])
.claude/settings.json                    dogfood: permissions.deny ["Edit(/docs/decisions/RATIFICATIONS.jsonl)"], written by scribe init (T15)
.claude/scribe/                          (local) state.json, state.json.lock, config.json, hook-errors.log, gate-log.jsonl
.github/workflows/ci.yml                 scribe's own tests: setup-uv@v10, uv sync --frozen, uv run pytest -q
.github/workflows/scribe-check.yml       (gen by scribe init --ci-source ., dogfood) the merge gate, section 5.4
.gitignore                               .venv/, __pycache__/, *.pyc, .pytest_cache/, .ruff_cache/, .claude/scribe/ (the old docs/decisions/.scratch/ line removed, P7)
.python-version                          3.12 (P3)
AUTONOMOUS_DECISIONS_09_08_2026.md       pipeline decisions log, appended by every step
README.md                                install, CLI reference, record format summary, ratification model, denylist, fail-open policy, Windows caveats
pyproject.toml                           project scribe 0.1.0, requires-python >=3.11, deps pyyaml>=6.0, dev pytest>=8, console script scribe = scribe.cli:main
uv.lock                                  committed; hooks run uv run --frozen
hooks/hooks.json                         Claude Code hook registrations, exec form, section 4.1
skills/decide/SKILL.md                   /scribe:decide, section 4.9
skills/ratify/SKILL.md                   /scribe:ratify, human only, section 4.10
skills/reject/SKILL.md                   /scribe:reject, human only, section 4.10
skills/init/SKILL.md                     /scribe:init, human only, section 4.11
skills/lint/SKILL.md                     /scribe:lint, section 4.12
src/scribe/__init__.py                   __version__ = "0.1.0"
src/scribe/__main__.py                   python -m scribe -> cli.main
src/scribe/cli.py                        argparse: validate, index, relink, lookup, new, ratify, reject, lint, check, init, hook <event>, git-hook <name>
src/scribe/ulid.py                       stdlib ULID: generate(), is_valid(), timestamp_ms() with overflow check (P2, F26)
src/scribe/frontmatter.py                split(text) -> (mapping, body), join(mapping, body); PyYAML, key order preserved, section 3.6
src/scribe/schema.py                     field table, enums, validate_record(mapping, body, store=None) -> list[Problem]
src/scribe/record.py                     Record: load(path), save(), apply_change(field, new, event, by, **extra) appends history; body_sha256()
src/scribe/store.py                      repo root discovery, record iteration, alias/ULID resolution, effective supersession edges, reconcile_supersession()
src/scribe/matching.py                   affects glob matcher and path normalisation, section 4.4
src/scribe/index.py                      INDEX.md generator, section 3.5
src/scribe/lookup.py                     trailer parsing, commit -> records, record -> commits, section 4.6
src/scribe/newrecord.py                  scribe new: slug, alias, template fill, state registration, section 4.9
src/scribe/ratify.py                     ratify/reject: transition matrix, attestation, locking, section 4.10 and 3.8
src/scribe/lint.py                       lint rules, section 4.12
src/scribe/history_check.py              immutable_changed and history_rewritten against a base ref; used by lint and check
src/scribe/check.py                      CI check, section 5.4
src/scribe/relink.py                     rebuild implementation_links from git trailers, section 5.3
src/scribe/links.py                      implementation_paths(record, changed_paths): the one rule for "which changed paths implement this record" (post-commit and relink)
src/scribe/state.py                      scratch state .claude/scribe/state.json with lock adapter, section 4.2
src/scribe/config.py                     .claude/scribe/config.json reader with defaults, section 4.1 item 6
src/scribe/policy.py                     phase 3 denylist rules and plan-policy keywords, section 4.7
src/scribe/init_repo.py                  git hook shim installer, config, workflow, gitignore and settings.json merge, section 5.5
src/scribe/gitutil.py                    subprocess wrappers: toplevel, git-path hooks, staged paths, trailers, diff-tree, rev-list
src/scribe/hooks/__init__.py
src/scribe/hooks/launcher.py             run_advisory(fn) and run_gate(fn, mode): the two dispatcher policies, section 4.1
src/scribe/hooks/session_start.py        SessionStart, section 4.3
src/scribe/hooks/user_prompt_submit.py   UserPromptSubmit, section 4.3
src/scribe/hooks/pre_tool_use_edit.py    PreToolUse Edit|Write injection, section 4.4
src/scribe/hooks/pre_tool_use_gate.py    PreToolUse ExitPlanMode and Bash|PowerShell, shadow mode, section 4.7
src/scribe/hooks/reconcile.py            TaskCompleted and Stop, shadow mode, section 4.8
src/scribe/githooks/__init__.py
src/scribe/githooks/prepare_commit_msg.py  section 5.1
src/scribe/githooks/commit_msg.py        section 5.2
src/scribe/githooks/post_commit.py       section 5.3
src/scribe/templates/record_template.md  body skeleton filled by scribe new
src/scribe/templates/githook_shim.py     text of the installed git hook file, section 5
src/scribe/templates/scribe-check.yml    text of the CI workflow dropped by init, with {{SCRIBE_CHECK_COMMAND}} placeholder, section 5.4
tests/conftest.py                        fixtures: tmp_repo, run_cli, run_hook, write_record, set_config
tests/fixtures/hooks/*.json              stdin payloads per hook event
tests/fixtures/records/*.md              valid and invalid records
tests/fixtures/new_spec.json             spec for scribe new
tests/test_cli.py tests/test_ulid.py tests/test_frontmatter.py tests/test_schema.py tests/test_matching.py
tests/test_index.py tests/test_lookup.py tests/test_state.py tests/test_hook_launcher.py tests/test_hook_session.py
tests/test_hook_injection.py tests/test_timing.py tests/test_new.py tests/test_ratify.py tests/test_hook_gate.py
tests/test_githooks.py tests/test_check.py tests/test_lint.py tests/test_init.py tests/test_relink.py
tests/test_deferred.py                   three skip-marked tests: two-worktree scenario, staged verify, CI verify
docs/decisions/D-260908-unreviewed-may-supersede-ratified.md   record A10 (hand-written, immutable body)
docs/decisions/D-260908-one-way-door-defer-not-stop.md         record A13
docs/decisions/D-260908-verbatim-quote-is-the-evidence.md      record A12
docs/decisions/RATIFICATIONS.jsonl       append-only attestations, section 3.7
docs/decisions/INDEX.md                  (gen) by scribe index, first produced in T4
docs/build/01-*.md, 02-plan-review.md, 03-*.md   pipeline handoffs (read-only for the implementer)
docs/build/04-progress.md, 04-implementation-report.md          written by step 4
```

## 3. Record format specification

### 3.1 File and identity

1. Path: `docs/decisions/<alias>.md`, alias `D-YYMMDD-<slug>`, slug `[a-z0-9]+(-[a-z0-9]+)*`, total alias length 8 to 60 characters. The filename stem MUST equal `alias` (validator error `alias_filename_mismatch`). Rationale (P4): humans read filenames and `git log --stat`; the ULID stays inside as the identity, so two branches producing the same alias surface as an add/add conflict at merge; lint flags `duplicate_alias` if both survive.
2. `id`: ULID, 26 characters, Crockford base32 alphabet `0123456789ABCDEFGHJKMNPQRSTVWXYZ`, uppercase, regex `^[0-9A-HJKMNP-TV-Z]{26}$`, and the decoded value MUST fit in 128 bits, so the first character is `0` to `7` and `7ZZZZZZZZZZZZZZZZZZZZZZZZZ` is the maximum (`invalid_ulid` otherwise, F26). Generated by `src/scribe/ulid.py` (48-bit millisecond timestamp plus 80 random bits from `os.urandom`). Immutable. The validator checks that the timestamp prefix decodes to a date within 1 day of `date` (`ulid_date_mismatch`, warning).
3. Immutable once the record's first commit exists: `id`, `alias`, `title`, `date`, `schema_version`, `task_refs`, `decided_by`, `recommended_by`, `provenance`, `affects`, `tags`, `reversibility`, `blast_radius`, `regret_when`, `review`, `verify`, `relates_to`, and the whole body. Checked by `history_check.py` against `git show <base>:<path>` (used by `scribe lint` and `scribe check`); the validator alone cannot see history.
4. Mutable keys, the only ones: `review_state`, `effective_state`, `ratified_by`, `ratified_at`, `implementation_links`, `supersedes`, `history`. Every change to a mutable key appends one `history` entry with `field`, `old`, `new` (section 3.3).

### 3.2 Front matter keys

YAML between the first line `---` and the next line `---`. Key order in the file is the order below. `req` = required, may not be null.

| Key | Type | Allowed values or format | Mutable | Notes |
|---|---|---|---|---|
| `id` | str, req | ULID rules above | no | identity |
| `alias` | str, req | `^D-\d{6}-[a-z0-9]+(-[a-z0-9]+)*$` | no | equals filename stem |
| `title` | str, req | 3 to 200 chars, single line | no | equals the H1 text (F4: A13's title is 163 chars) |
| `date` | date, req | `YYYY-MM-DD` | no | decision date |
| `schema_version` | int, req | `1` | no | |
| `task_refs` | list[str], req (may be empty) | each item matches one of `^[A-Z][A-Z0-9]{1,9}-\d+$` (Linear, Jira-style), `^#\d+$` (issue in this repo), `^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#\d+$` (GitHub `owner/repo#n`) | no | brief: GitHub Issues or Linear ids; anything else is `invalid_task_ref` (F24) |
| `review_state` | enum, req | `unreviewed`, `ratified`, `rejected` | yes | what the human said |
| `effective_state` | enum, req | `proposed`, `implemented`, `superseded`, `expired`, `backtracked` | yes | what the code does |
| `decided_by` | enum, req | `human`, `agent-recommended`, `agent` | no | historical attribution (P5); never changes on ratification |
| `recommended_by` | str or null, req | e.g. `claude-code`, `codex`, `human` | no | |
| `ratified_by` | str or null, req | e.g. `@nikita` | yes | non-null iff `review_state != unreviewed` (`ratified_fields_inconsistent`); for a rejected record it names who rejected |
| `ratified_at` | datetime or null, req | ISO 8601 UTC `YYYY-MM-DDTHH:MM:SSZ` | yes | same rule |
| `provenance` | map, req | keys below, all present | no | |
| `provenance.authored_by` | enum | `human`, `agent`, `agent-drafted` | no | |
| `provenance.agent` | str or null | | no | |
| `provenance.model` | str or null | | no | |
| `provenance.session` | str or null | | no | pointer, not proof (A12) |
| `provenance.prompt_ids` | list[str] | | no | may be empty; filled by `scribe new` from scratch state |
| `provenance.trigger` | enum | `user-prompt`, `hook`, `automation`, `self-initiated` | no | |
| `provenance.source_messages` | list[str] | | no | may be empty |
| `affects` | list[map], req (may be empty) | items `{type: path|package|action, pattern: str, negate: bool=false}` | no | `path`: forward-slash repo-relative glob (section 4.4). `package`: accepted, ignored by every consumer this run (P21). `action`: a denylist rule name `^[a-z][a-z0-9-]*$`, consumed by the Bash gate (section 4.7), ignored by the edit hook; lint warns `unknown_action` if the name is not in `policy.RULE_NAMES` (F2). `negate` is only meaningful for `path` (validator error `negate_on_non_path`) |
| `implementation_links` | list[map], req (may be empty) | items `{commit: ^[0-9a-f]{7,40}$, paths: list[str]}` | yes | code to decision |
| `tags` | list[str], req (may be empty) | `^[a-z0-9-]+$` | no | |
| `reversibility` | enum, req | `two-way-door`, `one-way-door`, `unknown` | no | |
| `blast_radius` | enum, req | `component`, `team`, `cross-team`, `org` | no | |
| `regret_when` | str or null, req | 200 chars max | no | |
| `review` | date or null, req | `YYYY-MM-DD` | no | |
| `verify` | list[map], req (may be empty) | items `{id: ^[a-z0-9-]+$, engine: grep, pattern: str, paths: list[str], expect: match|no-match, severity: error|warning}` | no | `engine` accepted: `grep` only. `engine: jsonpath` is an error with the exact message `unsupported_engine: jsonpath is on the README allowlist but not implemented in this release`; any other value is `unknown_engine` (F25). `pattern` is a Python `re` regex applied per line; `match` = every file selected by `paths` contains a matching line; `no-match` = no selected file does. Run by `scribe lint` only |
| `supersedes` | str or null, req | ULID or alias of one existing record | yes | one edge, inverse derived (section 3.8) |
| `relates_to` | list[str], req (may be empty) | ULIDs or aliases | no | |
| `history` | list[map], req, at least 1 item | items `{at: datetime, event: enum, by: str, session?: str, commit?: str, field?: str, old?: any, new?: any}` | append only | `event` in `proposed`, `implemented`, `ratified`, `rejected`, `superseded`, `restored`, `expired`, `backtracked`, `link_added`, `supersedes_set`, `relinked`. First entry MUST be `proposed`. Non-decreasing `at`. Every event other than `proposed`, `link_added`, `relinked` MUST carry `field`, `old`, `new` |

Cross-field rules enforced by the validator (error unless stated):

1. `review_state == unreviewed` implies `ratified_by == null` and `ratified_at == null`; the other two states imply both non-null.
2. `effective_state == superseded` with a store available: warning `superseded_without_successor` when no effective edge (section 3.8) points at the record.
3. `effective_state == backtracked` requires a non-empty `## Attempted and failed` section.
4. `effective_state == implemented` with empty `implementation_links`: warning `implemented_without_links`.
5. `supersedes` and every `relates_to` entry MUST resolve when a store is available (`dangling_reference`); a record MUST NOT supersede itself.
6. `review_state in (ratified, rejected)` requires that the latest attestation line for this `id` in `RATIFICATIONS.jsonl` has the same `verdict` and a `body_sha256` equal to the current body hash (`unattested_review_state`). The converse: `review_state == unreviewed` while an attestation exists for the id is the error `state_behind_attestation` with the message `run scribe <verdict> <alias> again to apply the recorded verdict` (F8 recovery). Both skipped with `--no-attestation` for unit fixtures.
7. Unknown top-level keys are an error (`unknown_key`).
8. Every `history` entry with `field` names a mutable key (`history_immutable_field`).

### 3.3 History entries

One flow mapping per line:

```yaml
history:
  - { at: 2026-09-08T20:37:41Z, event: proposed, by: "Nikita Boguslavskii", session: session_01A6tVoZuuWqu56QxEqtAjRw }
  - { at: 2026-09-09T10:02:00Z, event: implemented, by: scribe-post-commit, commit: 3f2a9c1d0e7b, field: effective_state, old: proposed, new: implemented }
  - { at: 2026-09-09T10:02:00Z, event: link_added, by: scribe-post-commit, commit: 3f2a9c1d0e7b, new: { commit: 3f2a9c1d0e7b, paths: ["src/scribe/index.py"] } }
```

`by` is a free string: a person, an agent (`claude-code`), or a scribe component (`scribe-post-commit`, `scribe-ratify`, `scribe-reject`, `scribe-new`, `scribe-relink`, `scribe-lint`). Every mutation goes through `Record.apply_change`, the only code path that appends history.

### 3.4 Body

After the closing `---`, exactly this sequence; the validator checks presence and order of the H1 and H2 headings and the stated content rules:

```
# <title, must equal front matter title>

> <Y-statement, one or more `>` lines>          (required)

## Question                      (required, non-empty)
## Criteria                      (required, non-empty)
## Constraints and assumptions   (required, non-empty)
## Options considered            (required; table with header `| Option | For | Against | Evidence | Why rejected |`, at least 2 data rows, exactly one row whose last cell is `chosen`)
## Decision                      (required, non-empty)
## Consequences                  (required, non-empty)
## Attempted and failed          (optional; required non-empty when effective_state == backtracked)
## Evidence                      (required; at least one `>` blockquote line: the decisive user turn verbatim, A12, P18)
```

No other H2 headings (`unexpected_section`). H3 and deeper are free. The body is immutable.

### 3.5 INDEX.md

Generated by `scribe index` into `docs/decisions/INDEX.md`; `scribe index --check` exits 1 if the file on disk differs from the generated text. Layout, exact section names:

```
# Decision index

Generated by `scribe index` from N records. Do not edit by hand.

## Review queue (K)

Ordered: records that supersede a ratified record first, then implemented, then proposed; newest first within each group.

1. [supersedes ratified] D-260910-foo | implemented | unreviewed | agent | supersedes D-260908-bar | <title>
2. D-260909-baz | implemented | unreviewed | agent | <title>
3. D-260909-qux | proposed | unreviewed | agent-recommended | <title>

## Active decisions (M)

D-260908-unreviewed-may-supersede-ratified | proposed | ratified | human | src/scribe/index.py src/scribe/check.py src/scribe/templates/scribe-check.yml | <title>. Regret: <regret_when>. Review 2026-12-08.

## Retired (R)

D-260908-bar | superseded by D-260910-foo | ratified | human | <title>
D-260901-old | rejected | rejected | agent | <title>
D-260801-stale | expired | unreviewed | agent | <title>
```

Rules:

1. Review queue = every record with `review_state: unreviewed`, whatever its `effective_state`. Group 1 = records whose `supersedes` resolves to a record with `review_state: ratified`; marker `[supersedes ratified]` at the start of the line and `supersedes <alias>` in the line. Group 2 = `effective_state: implemented`. Group 3 = the rest. Within a group: `date` descending, then alias.
2. Active = records with `review_state != rejected`, `effective_state in (proposed, implemented, backtracked)`, and no effective incoming edge (section 3.8). The indexer trusts edges, not the predecessor's `effective_state`; disagreement is a lint warning `effective_state_stale`.
3. Retired = records with an effective incoming edge (`superseded by <alias>`), rejected records, expired records, and records marked `superseded` without an effective edge (shown as `superseded (stale)`).
4. Line fields: alias, effective state (or `superseded by X`), review state, decided_by, space-joined `affects` path patterns (negated prefixed `!`; omitted on Retired lines), title, then `Regret: ...` and `Review YYYY-MM-DD.` when present. One line per record.
5. Deterministic output, no timestamps.

### 3.6 Parsing and serialization

1. Front matter parsed with `yaml.safe_load`; the body is everything after the closing `---\n`, preserved byte for byte on save (only the front matter is re-serialized). YAML comments in the front matter are not preserved on save (PyYAML limitation, R6); the three hand-written records carry such comments on `source_messages`, and losing them is accepted because comments are not keys.
2. Serialization: `yaml.safe_dump(mapping, sort_keys=False, allow_unicode=True, width=1000)` with `history`, `affects`, `implementation_links`, `verify` items forced to flow style via a custom representer. Dates and datetimes are written as plain ISO strings; the loader accepts both YAML timestamps and strings and normalizes datetimes to UTC `Z` form.
3. Line endings: read tolerant of `\r\n`, write `\n`.
4. `body_sha256` = SHA-256 hex of UTF-8 `body.rstrip()` where `body` is the text after the closing `---\n` with `\r\n` normalized to `\n`. This exact definition reproduces the three committed attestation hashes (checked by the reviser: `rstrip` only, not `strip`; the leading blank line before the H1 is part of the hashed text). Do not change it.

### 3.7 RATIFICATIONS.jsonl

`docs/decisions/RATIFICATIONS.jsonl`, committed, append only, one JSON object per line:

```json
{"id": "01M21BV91NZSW1HMJ127KZAA5J", "alias": "D-260908-unreviewed-may-supersede-ratified", "verdict": "ratified", "by": "@nikita", "at": "2026-09-08T20:37:41Z", "body_sha256": "<hex>", "via": "hand-written", "note": "Interview answer A10"}
```

`verdict` in `ratified`, `rejected`; `via` in `skill`, `cli`, `hand-written`, set from the CLI flag `--via` (default `cli`; the skills pass `--via skill`). The latest line for an `id` is authoritative. Validator rule 6 (section 3.2) makes a record's `review_state` worthless without a matching line, so editing a record alone cannot ratify it.

What this file is and is not (F5): `scribe init` adds `Edit(/docs/decisions/RATIFICATIONS.jsonl)` to `permissions.deny` in the target repo's `.claude/settings.json`; the leading `/` anchors at the settings source (the repository root) and an `Edit` rule also covers the `Write` tool (Claude Code 2.1.228 or later; `Write(...)` path rules are accepted but never consulted, so none is written). This blocks the agent's file tools. It does not block a subprocess: an agent could run `scribe ratify` through Bash. In this release, human-only ratification is by construction of the skills (section 4.10), not by proof; the attestation line records who ran the verdict and through which path (`via`). The README states this plainly.

### 3.8 Lifecycle: effective supersession and the transition matrix

Effective edge (F1): the edge `S supersedes P` is effective iff `S.review_state != rejected` and `S.effective_state in (proposed, implemented, superseded)`. A rejected, expired or backtracked successor does not retire its predecessor; a superseded successor still retires its predecessor, so chains hold. The indexer and the injection hook use effective edges only. `store.reconcile_supersession(records, by)` is the one function that keeps predecessors' `effective_state` in step with the edges: for every record with an effective incoming edge and `effective_state in (proposed, implemented)`, set `superseded` (history event `superseded`, `by` as given); for every record with `effective_state: superseded` and no effective incoming edge, set the value recorded as `old` in its latest `superseded` history entry (history event `restored`). It is called by `scribe new` (after writing a record with `supersedes`), `scribe ratify`, `scribe reject`, and `scribe lint --expire`. It is not called by `scribe index`, which stays read-only (P14).

Review transitions (`scribe ratify` / `scribe reject`, F7):

| From | Command | Result | Attestation | History | Exit |
|---|---|---|---|---|---|
| unreviewed | ratify | ratified | append `ratified` | 3 entries `ratified` (review_state, ratified_by, ratified_at) | 0 |
| unreviewed | reject | rejected | append `rejected` | 3 entries `rejected` | 0 |
| ratified | ratify | unchanged | none | none | 0, prints `already ratified by <who> at <when>` |
| rejected | reject | unchanged | none | none | 0, prints `already rejected ...` |
| ratified | reject | rejected (reversal) | append `rejected` | 3 entries `rejected` with old values | 0 |
| rejected | ratify | ratified (reversal) | append `ratified` | 3 entries `ratified` with old values | 0 |
| any | either, unknown id | nothing | none | none | 1 |
| unreviewed but attestation exists for id | the same verdict | record updated to the attested verdict | none (latest line already matches) | 3 entries | 0 (heals `state_behind_attestation`) |

`effective_state` never changes on ratify or reject of the record itself (a rejected implemented record stays `implemented`, lint flags `rejected_but_implemented`), but the predecessor of a rejected or re-ratified successor changes through `reconcile_supersession`. Ratification of a superseded or expired record is allowed (history is history).

## 4. Hook and skill behaviour

### 4.1 Common mechanics

1. Registration: `hooks/hooks.json` with a top-level optional `description` and `hooks: {"<Event>": [{"matcher": "...", "hooks": [<handler>]}]}`. Every handler is exec form (F22):

```json
{"type": "command", "command": "uv", "args": ["run", "--frozen", "--project", "${CLAUDE_PLUGIN_ROOT}", "scribe", "hook", "<event-name>"], "timeout": <seconds>}
```

Registered entries and timeouts: `SessionStart` (no matcher) 120; `UserPromptSubmit` 10; `PreToolUse` matcher `Edit|Write` command `pre-tool-use-edit` timeout 1; `PreToolUse` matcher `ExitPlanMode` command `gate` timeout 10; `PreToolUse` matcher `Bash|PowerShell` command `gate` timeout 10; `TaskCompleted` (no matcher) `reconcile` 10; `Stop` (no matcher) `reconcile` 10. `timeout` is integer seconds; on expiry Claude Code cancels the hook, discards its output and the tool call proceeds, which is the mechanical fail-open ceiling for the edit path (F19).
2. `--frozen` uses the committed `uv.lock`. The first invocation after install creates `.venv` inside the plugin directory (seconds, possibly network); SessionStart pays that cost.
3. Input: JSON on stdin. Fields used: `session_id`, `prompt_id` (absent before the first prompt), `cwd`, `hook_event_name`; `tool_name`, `tool_input` for PreToolUse (`tool_input.file_path`, absolute, for Edit and Write; `tool_input.command` for Bash and PowerShell; `tool_input.plan` for ExitPlanMode); `prompt` for UserPromptSubmit; `task_id`, `task_subject` for TaskCompleted; `stop_hook_active`, `last_assistant_message` for Stop. Every read is `payload.get(...)`; a missing field never crashes a hook.
4. Output: advisory hooks print nothing or one JSON object and exit 0. PreToolUse injection prints `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "<block>"}}`; SessionStart prints `{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "..."}}`. Output strings are capped by Claude Code at 10,000 characters; the injection block is capped at 1600 by us. Gates in enforce mode block with exit 2 and the reason on stderr; in this run they never do.
5. Two dispatcher policies, `src/scribe/hooks/launcher.py` (F20):
   - `run_advisory(fn)`: reads stdin, parses JSON (empty or invalid input: exit 0 silently), calls `fn(payload)`, prints its return value if any, exits 0. Any `BaseException` from `fn` is caught; the launcher tries to append one line `scribe: <event> failed: <type>: <msg>` to `.claude/scribe/hook-errors.log` (created if missing, truncated to the newest half above 200 KB) and, when `SCRIBE_DEBUG=1`, to stderr; each of those writes is itself wrapped so a failing write is dropped. The outermost `main` returns 0 on every path, including a failure inside the logging.
   - `run_gate(fn, mode)`: `fn` returns `Verdict(allow: bool, reason: str, event: dict)`. `mode` comes from `config.gates_mode()` (section 4.1 item 6): `shadow` (default) appends the verdict to `.claude/scribe/gate-log.jsonl` and exits 0; `enforce` exits 2 with the reason on stderr for a deny, 0 otherwise. A crash in `fn` or the launcher logs loudly (stderr, always) and exits 0 in both modes (a gate crash must not block; the deliberate deny is the only exit 2).
6. Repo-local configuration, `src/scribe/config.py`: `<root>/.claude/scribe/config.json`, `{"version": 1, "SCRIBE_GATES": "shadow" | "enforce", "SCRIBE_COMMIT_MSG": "warn" | "enforce"}`. Missing file or key means `shadow` and `warn`. Environment variables are not consulted for these two switches (F21). `scribe init` writes the file with the safe values and never sets `enforce`; tests write `enforce` into the tmp repo's config through the `set_config` fixture. `SCRIBE_SKIP_HOOKS=1` (environment) still disables the git hooks, because that switch only fails further open. `SCRIBE_DEBUG=1` (environment) only adds stderr output.
7. Time budget: the edit hook has an internal deadline of 700 ms from process start (`time.monotonic()` at import of `pre_tool_use_edit`), checked every 20 record files; on expiry it prints nothing and exits 0. `tests/test_timing.py` measures the whole `uv run ... scribe hook pre-tool-use-edit` subprocess (section 7 item 5).
8. Repository root: `git -C <cwd> rev-parse --show-toplevel` with `cwd` from the payload (inside a linked worktree this is the worktree). Not a repo, or no `docs/decisions/`: exit 0 silently. Store path is always `<root>/docs/decisions`.
9. Paths are POSIX-style strings relative to the repository root; conversion happens once at the boundary (`matching.to_repo_relative`), which also lowercases both sides on Windows.

### 4.2 Scratch state

`<root>/.claude/scribe/state.json` (P7, README 10.4). Shape:

```json
{
  "version": 1,
  "sessions": {
    "<session_id>": {
      "started_at": "2026-09-08T20:37:41Z",
      "last_prompt_at": "2026-09-08T20:41:00Z",
      "prompt_ids": ["..."],
      "task_refs": ["LIN-123", "owner/repo#42"],
      "pending_decisions": ["01M21BV91NZSW1HMJ127KZAA5J"],
      "decision_worthy": {"set_at": "2026-09-08T20:45:00Z", "areas": ["dependency", "schema"], "prompt_id": "..."},
      "records_written": [{"id": "01M21...", "at": "2026-09-08T20:46:00Z"}]
    }
  }
}
```

`prompt_ids` keeps the last 20, `task_refs` the last 10 (most recent first, deduplicated), `records_written` the last 20. `decision_worthy` is `null` when unset. Written by SessionStart, UserPromptSubmit, the gate hook (flag), `scribe new`; read by `prepare-commit-msg`, `TaskCompleted`; pruned by `post-commit` (consumed ids) and by every writer (sessions with `last_prompt_at` or `started_at` older than 7 days dropped). Corrupt JSON is treated as empty state and logged, never raised.

Locking (F27), `state.py`: writes go through `with locked(<root>/.claude/scribe/state.json.lock):` then read-modify-write with temp file plus `os.replace`. The lock file is opened `a+`; POSIX: `fcntl.flock(fd, LOCK_EX | LOCK_NB)`; Windows: `fd.seek(0)` then `msvcrt.locking(fd.fileno(), msvcrt.LK_NBLCK, 1)` (one byte at offset 0; Windows allows locking a range beyond the end of an empty file, so the file is never written to). On `BlockingIOError` or `OSError` retry every 50 ms for up to 2 s, then proceed without the lock and log `state lock timeout`. Unlock in `finally` (`LOCK_UN` / `LK_UNLCK`). The platform branch lives in one adapter function so the Windows path can be unit-tested with a fake `msvcrt` module injected into `sys.modules`.

### 4.3 SessionStart and UserPromptSubmit (advisory)

SessionStart (`scribe hook session-start`), P16:

1. Ensures `sessions[session_id]` exists with `started_at`.
2. If the repo has a store: counts the review queue and, when K > 0, prints `{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "scribe: <K> unreviewed decisions, <J> supersede a ratified one. Run /scribe:lint or open docs/decisions/INDEX.md."}}`. Prints nothing when K == 0.
3. Exit 0 always. Also warms the venv by existing.

UserPromptSubmit (`scribe hook user-prompt-submit`), F10: updates `last_prompt_at`; appends `prompt_id` when present; extracts tracker ids from `prompt` with the three `task_refs` regexes of section 3.2 (word-bounded) and pushes them to `task_refs`. No stdout. Exit 0.

### 4.4 PreToolUse on Edit and Write: injection (advisory)

Registration: matcher `Edit|Write`, command `pre-tool-use-edit`, timeout 1.

1. Read `tool_input.file_path` (absolute per the docs; still resolved against `cwd` if relative); missing: exit 0.
2. Resolve repo root from `cwd`; no store: exit 0.
3. Convert to repo-relative POSIX (`os.path.relpath`, backslashes to `/`, strip `./`); a result starting with `..` (outside the repo) exits 0.
4. Load front matter only for every `docs/decisions/D-*.md`; skip files that fail to parse (log). Do not read bodies.
5. Candidates: `review_state != rejected`, `effective_state in (proposed, implemented, backtracked)`, no effective incoming edge (section 3.8, derived from the loaded set). A record matches when at least one non-negated `type: path` entry matches and no negated `type: path` entry matches. `package` and `action` entries are ignored here.
6. Glob semantics (`matching.py`, own translation to `re`): `**` matches any sequence including `/`; `*` any run without `/`; `?` one character except `/`; `[abc]`, `[!abc]` classes; a pattern without `/` matches the basename at any depth; anchored both ends; patterns normalized (backslashes to `/`, leading `./` and `/` stripped).
7. Order: ratified first, then unreviewed; within each, implemented before proposed; then `date` descending. Cap 5 records.
8. Block (each record line at most 220 characters, whole block at most 1600):

```
Governing decisions for src/scribe/index.py:
- D-260908-unreviewed-may-supersede-ratified (proposed, ratified by human): <title>. Regret when: <regret_when truncated to 100 chars>.
- D-260910-foo (implemented, unreviewed, supersedes ratified D-260908-bar): <title>.
These are retrieval candidates, not confirmed matches. If this edit conflicts with one, surface it and ask; do not silently comply or silently violate. Full text: docs/decisions/<alias>.md ...
```

Zero matches: print nothing. Exit 0 always.

### 4.5 `scribe validate`

`scribe validate [paths...] [--no-attestation] [--json]`. Default: the whole store. Runs sections 3.1 to 3.4 and the attestation rules; output `<path>: <severity>: <code>: <message>` per problem, then `N records, E errors, W warnings`. Exit 1 on any error.

### 4.6 `scribe lookup`

`scribe lookup <sha | ulid | alias>`:

1. Commit-ish (`git rev-parse --verify --quiet <arg>^{commit}`): print the commit's `Decision:` trailers resolved as `<alias> <ulid> <path> (<review_state>, <effective_state>)`; unknown tokens print `UNKNOWN <token>` and set exit 1.
2. Else resolve as ULID or alias; print the record path, then every commit whose trailers reference it (`git log --all --format=%H%x09%s --grep=<ulid> --grep=<alias>` as prefilter, trailers parsed as the truth), then `implementation_links`, marking links whose commit is not reachable with `(not in this history)`.
3. Exit 0 when found, 1 when not.

Trailer format (P6): `Decision: <alias> <ulid>`; the parser accepts either token alone.

### 4.7 PreToolUse on ExitPlanMode and Bash|PowerShell: gates, shadow mode

Two entries, matchers `ExitPlanMode` and `Bash|PowerShell`, both `scribe hook gate`, wrapped by `run_gate`.

1. Denylist, `policy.py`, `RULES: list[(name, compiled regex)]` over `tool_input.command` after collapsing whitespace: `git-push-force` (`git push` with `--force` or `-f`, not `--force-with-lease`), `git-branch-delete-force` (`git branch -D`), `git-reset-hard-remote` (`git reset --hard` naming `origin/`), `rm-rf-outside-worktree` (`rm -rf` on a target starting with `/`, `~` or `..`), `alembic-migrate`, `prisma-migrate-deploy`, `flyway-migrate`, `terraform-apply-destroy`, `kubectl-apply-delete`, `helm-install-upgrade`, `docker-push`, `npm-publish`, `cargo-publish`, `twine-upload`, `uv-publish`, `gh-release-create`, `gh-pr-merge`, `http-write` (`curl`, `wget`, `http` with `-X POST|PUT|PATCH|DELETE` or `--data`). `RULE_NAMES` is the set of names; these are the values `affects` `action` patterns use (F2).
2. Bash verdict: if a rule matches and no record with `review_state: ratified`, `reversibility: one-way-door` has an `affects` entry `{type: action, pattern: <rule name>}`, deny with reason `scribe: '<name>' is on the irreversible-action denylist; record it with /scribe:decide (reversibility: one-way-door) and get it ratified before running it`. Else allow.
3. ExitPlanMode policy: `tool_input.plan` scanned for the keyword lists per README 10.4 policy area (`dependency`, `add package`, `public API`, `schema`, `migration`, `storage`, `concurrency`, `thread`, `safety`, `interface`, `deviat`). Any hit: set `sessions[sid].decision_worthy = {set_at, areas, prompt_id}` in scratch state (F9). If in addition `pending_decisions` is empty, verdict deny with reason `scribe: plan touches <areas>; run /scribe:decide before leaving plan mode`; else allow.
4. Log line for every verdict: `{"at", "event": "gate_verdict", "tool", "verdict", "reason", "command_head" (first 80 chars, Bash only), "areas" (ExitPlanMode only)}` appended to `.claude/scribe/gate-log.jsonl`. Shadow mode exits 0 (P9, A13 measurement); `enforce` in `config.json` exits 2 on deny (tests only).

### 4.8 TaskCompleted and Stop: reconcile, shadow mode

Both `scribe hook reconcile`; TaskCompleted through `run_gate`, Stop through `run_advisory`.

1. TaskCompleted (F9): if `sessions[sid].decision_worthy` is set and `records_written` has no entry with `at >= decision_worthy.set_at`: verdict deny with reason `scribe: task '<task_subject>' flagged decision-worthy (<areas>) but no record was written`, and append a typed event `{"at", "event": "capture_missing", "session_id", "task_id", "task_subject", "areas", "flagged_at"}` to the gate log. In every case, clear `decision_worthy` afterwards (one report per flag). Exit 0 in shadow mode.
2. Stop: if `stop_hook_active` is true, exit 0 immediately. Otherwise append `{"at", "event": "stop_reconcile", "session_id", "pending_decisions", "has_last_message": bool}` to the gate log. No stub record is written in this run (README 10.4 Stop row deferred until the two-worktree test). Exit 0.

### 4.9 `/scribe:decide` and `scribe new`

`skills/decide/SKILL.md` front matter: `name: decide`, `description: Record a decision before the first implementing edit; writes docs/decisions/<alias>.md with review_state unreviewed and registers it for the next commit's Decision trailer.`, `allowed-tools: Bash(uv run --frozen --project ${CLAUDE_PLUGIN_ROOT} scribe *)`.

Body instructs the agent to:

1. Fill a JSON spec (below) from the conversation, quoting the decisive user turn verbatim into `evidence_quote`; for a self-initiated decision write `(no user turn; self-initiated)` and `trigger: self-initiated`.
2. Write the spec to a temp file and run `uv run --frozen --project ${CLAUDE_PLUGIN_ROOT} scribe new --spec <file> --register --session ${CLAUDE_SESSION_ID}` (both substitutions are documented for plugin skill content; unquoted so the command matches the skill's `allowed-tools` rule textually, R11).
3. Read the printed path and confirm the record in one line.
4. One-way-door rule (A13): with `reversibility: one-way-door`, do not stop; leave `review_state: unreviewed`, continue independent work, list every pending one-way-door alias in a single `**Next:**` block at the end of the run; block early only when the remaining work depends on it; never run the denied action.
5. Supersede rule (A10): when replacing an existing decision, set `supersedes` to its alias even if ratified; the indexer puts it at the top of the review queue and the CI check blocks merge until reviewed.

`scribe new --spec <file> [--by <name>] [--session <id>] [--register]`: spec keys mirror the front matter minus generated ones (`id`, `alias`, `date`, `schema_version`, `review_state`, `effective_state`, `ratified_*`, `implementation_links`, `history`) plus body fields `y_statement`, `question`, `criteria`, `constraints`, `options` (list of `{option, for, against, evidence, why_rejected, chosen: bool}`), `decision`, `consequences`, `attempted_and_failed` (optional), `evidence_quote`, `evidence_pointers` (list[str]). Behaviour: generate ULID; alias from today's UTC date and a slug from `title` (lowercase ASCII, non-alphanumerics to hyphens, collapsed, trimmed to 40 chars, `-2`, `-3` on collision); `task_refs` = spec value if given, else the session's `task_refs` from scratch state, else `[]`; `provenance.prompt_ids` = spec value if given, else the session's last prompt id, else `[]` (F10); render the body from `record_template.md`; `review_state: unreviewed`, `effective_state: proposed`, one `proposed` history entry (`by` = `--by` or `provenance.agent`; `session` = `--session` when given, else omitted); validate before writing (invalid: print problems, write nothing, exit 1); if `supersedes` is set, call `reconcile_supersession(by="scribe-new")`; regenerate `INDEX.md`; with `--register`, append the ULID to `sessions[<session or "unknown">].pending_decisions` and to `records_written`. Print the path. Exit 0.

### 4.10 `/scribe:ratify`, `/scribe:reject`, `scribe ratify`, `scribe reject`

Skills (F5): front matter `name: ratify` (or `reject`), `description: Human only: record your verdict on a decision. The agent must never invoke this.`, `disable-model-invocation: true`, `argument-hint: <alias-or-ulid> [note]`, `allowed-tools: Bash(uv run --frozen --project ${CLAUDE_PLUGIN_ROOT} scribe *)`. Body of `ratify` (the `reject` skill is identical with `reject`):

```
Verdict recorded by scribe before the model saw this text:

!`uv run --frozen --project ${CLAUDE_PLUGIN_ROOT} scribe ratify --via skill $ARGUMENTS`

Report the line above to the user verbatim, then show the review queue count from docs/decisions/INDEX.md. Never run scribe ratify or scribe reject yourself.
```

The inline `!` command runs at skill expansion, before the model receives the content, so the model is never the actor on the human path. A non-zero exit aborts the skill invocation and shows the CLI's message to the user, which is the wanted behaviour for an unknown id, so no `|| true`. The command is unquoted so that it matches the `allowed-tools` rule textually (both carry the same `${CLAUDE_PLUGIN_ROOT}` substitution, the pattern the skills doc shows); a plugin root containing spaces is a known Windows caveat (R11). Whether `$ARGUMENTS` is substituted inside an inline `!` command is UNVERIFIED (section 10, U1); the fallback is a body that instructs the model to run the same command, a one-file change per skill. `--by` is omitted in the skill: the CLI defaults it to `@` plus the first token of `git config user.name` lowercased, and normalizes any `--by` value that lacks a leading `@` the same way.

CLI `scribe ratify <id> [--by <who>] [--note <text>] [--at <iso>] [--via skill|cli|hand-written]` and `scribe reject ...` implement section 3.8 with this order (F8):

1. Acquire the exclusive lock `<root>/.claude/scribe/ratify.lock` (same adapter as `state.py`; the directory is created if missing; nothing extra lands in `docs/decisions/`).
2. Resolve the record; apply the transition matrix; idempotent cases print and exit 0 without further steps.
3. Append the attestation line (single `write` of one line ending in `\n`, `flush`, `os.fsync`). This is the authority.
4. Apply the three field changes through `apply_change`, save the record via temp file plus `os.replace`.
5. `reconcile_supersession(by="scribe-<verb>")`, saving any predecessor it changes.
6. Regenerate `INDEX.md`. Print `ratified <alias> by <who> (via <via>)` or the reject equivalent. Exit 0.

Recovery: a crash after step 3 leaves `state_behind_attestation` (validator rule 6), healed by re-running the same command (matrix last row). A crash after step 4 leaves `effective_state_stale` or `index_stale`, healed by `scribe lint --fix-index` (regenerates the index) or the next `ratify`/`reject`. Concurrency: two processes ratifying different records serialize on the lock; the test proves both lines land and the file stays valid JSONL.

### 4.11 `/scribe:init`

Skill: `name: init`, `disable-model-invocation: true`, `argument-hint: [--force] [--ci-source <spec>]`, `allowed-tools: Bash(uv run --frozen --project ${CLAUDE_PLUGIN_ROOT} scribe *)`, body runs `uv run --frozen --project ${CLAUDE_PLUGIN_ROOT} scribe init $ARGUMENTS` through the model's Bash tool (init has no authority concern) and prints what was written plus the follow-ups. Behaviour in section 5.5.

### 4.12 `/scribe:lint` and `scribe lint`

Skill: `name: lint`; body runs `scribe lint` and, if there are unreviewed records, presents the review queue as a numbered list and offers to walk the owner through them one at a time (ask, do not act).

`scribe lint [--base <ref>] [--expire] [--fix-index] [--json]`: runs `validate`, `index --check`, and the rules below; exit 1 on any error, 0 otherwise.

| Code | Severity | Rule |
|---|---|---|
| `duplicate_alias` | error | two files share an alias or an id |
| `alias_filename_mismatch`, `dangling_reference`, `unattested_review_state`, `state_behind_attestation`, `invalid_task_ref`, `unsupported_engine` | error | from validate |
| `immutable_changed` | error | for records present at `--base` (default `origin/main` if it exists, else `HEAD~1`, else skipped), an immutable key or the body differs from `git show <base>:<path>` (`history_check.py`) |
| `history_rewritten` | error | the base version's `history` is not a prefix of the current one |
| `index_stale` | error | `INDEX.md` differs from generated; `--fix-index` regenerates instead |
| `effective_state_stale` | warning | edge state and `effective_state` disagree in either direction (section 3.8) |
| `unknown_action` | warning | an `affects` `action` pattern is not in `policy.RULE_NAMES` |
| `rejected_but_implemented` | warning | rejected and implemented and not superseded or backtracked |
| `review_overdue` | warning | `review` date past and record active |
| `unreviewed_implemented` | info | active, implemented, unreviewed |
| `proposal_stale` | warning | proposed, unreviewed, no links, `date` older than 30 days; with `--expire` set `effective_state: expired` (`by: scribe-lint`) and run `reconcile_supersession` |
| `verify_failed` | per entry severity | run each `verify` entry (files selected by `paths` globs, section 4.4 semantics, excluding `.git/`); an unreadable file or invalid regex is `verify_error` (error), distinct from no-match |
| `duplicate_pending` | info | scratch state ids that resolve to no record (pruned) |
| `unreachable_link` | warning | an `implementation_links` commit is not reachable; suggests `scribe relink` |

### 4.13 Agent-facing versus human-facing skills

`decide` and `lint` are for the agent and the owner. `ratify`, `reject`, `init` carry `disable-model-invocation: true` (the model cannot invoke them; the description is not even loaded into its context). Section 3.7 states what this does and does not guarantee.

## 5. Git hooks installed by `/scribe:init` and the CI check

All three git hooks are Python shim files (P12):

```python
#!/usr/bin/env python3
# scribe-managed v1  -- do not edit; re-run `scribe init --force` to refresh
import os, sys
PLUGIN_ROOT = r"/home/alfakentavr/scribe"   # baked in by scribe init
HOOK = "prepare-commit-msg"
if os.environ.get("SCRIBE_SKIP_HOOKS") == "1":
    sys.exit(0)
try:
    os.execvp("uv", ["uv", "run", "--frozen", "--project", PLUGIN_ROOT, "scribe", "git-hook", HOOK, *sys.argv[1:]])
except OSError as exc:
    sys.stderr.write(f"scribe: {HOOK} skipped ({exc})\n")
    sys.exit(0)
```

On Windows (`os.name == "nt"` at init time) the shebang is `#!/usr/bin/env python` (F28) and `os.execvp` is replaced by `subprocess.call` plus `sys.exit(code)` because `execvp` does not replace the process on Windows. `scribe git-hook <name>` entrypoints exit 0 on every failure in this run. `PLUGIN_ROOT` is `Path(scribe.__file__).resolve().parents[2]` at init time.

### 5.1 `prepare-commit-msg`

Arguments: `<msg-file> [<source> [<sha>]]`.

1. Exit 0 without changes when `source` is `merge` or `squash`, or when `SCRIBE_SKIP_HOOKS=1`. Amend (`source == commit` with a sha) runs the normal logic (F14): existing trailers are kept, new ones are added, `addIfDifferent` prevents duplicates.
2. Repo root; no store: exit 0.
3. Staged paths: `git diff --cached --name-only --diff-filter=ACMR`, POSIX relative.
4. Candidate ids, deduplicated, in this order, each tagged with its origin for logging:
   a. record-carried: every staged `docs/decisions/D-*.md` contributes its own id;
   b. pending: every id in `pending_decisions` of every session whose record exists and whose `affects` is empty or has a `type: path` entry matching at least one staged path (README 10.4).
5. For each id: `git interpret-trailers --in-place --if-exists addIfDifferent --trailer "Decision: <alias> <ulid>" <msg-file>`.
6. `Session:` trailer: skip if the message already has `Claude-Session:` or `Session:`; else the session with the latest `last_prompt_at` (or `started_at`); none: skip.
7. Never fail the commit: exceptions logged to `hook-errors.log`, exit 0.

### 5.2 `commit-msg` (warn only in this run)

Argument `<msg-file>`. Trailers via `git interpret-trailers --parse`. Each check prints `scribe: warning: ...` to stderr:

1. Every `Decision:` value resolves (ULID, alias, or both; disagreement warns `alias/ulid mismatch`).
2. Each resolved record passes `validate`.
3. A referenced record has `review_state: rejected`.
4. Governed paths (F12): for each staged path P matched by the `affects` of at least one active record, the message must carry a `Decision:` trailer resolving to an active record whose `affects` match P; otherwise `governed path <P> changed without a matching decision link (candidates: <aliases>)`. A trailer for an unrelated or inactive record does not satisfy P.
5. A staged record has `review_state != unreviewed` without a matching attestation (the "agent ratified itself" tell).
6. A staged record is `unreviewed` and `supersedes` a ratified record: `scribe: notice: <alias> supersedes ratified <alias>; the CI check will block merge until it is reviewed`.

Exit 0 always with `SCRIBE_COMMIT_MSG: warn` (default). With `enforce` in `config.json`, checks 1, 2 and 5 exit 1. Not implemented from README 10.4 "Commit validation" (F13): running `verify` entries against staged content; `tests/test_deferred.py::test_commit_msg_runs_verify_on_staged_content` is skip-marked with the activation condition "enable after 14 days of dogfood `scribe lint` with zero `verify_error`".

### 5.3 `post-commit`

1. Guards: `SCRIBE_SKIP_HOOKS=1` or `SCRIBE_IN_POST_COMMIT=1` (set by the hook itself before touching git) exit 0.
2. `sha = git rev-parse HEAD` (stored as 12 chars); trailers from `git log -1 --format=%(trailers:key=Decision,valueonly)`; changed paths from `git diff-tree --no-commit-id --name-only -r HEAD` (root commit: `git show --name-only --format= HEAD`).
3. For each resolved record: `paths = links.implementation_paths(record, changed_paths)`: changed paths outside `docs/decisions/` that match a non-negated `type: path` entry of `affects` (and no negated one); when `affects` has no `path` entries, every changed path outside `docs/decisions/`. If `paths` is non-empty: append `{commit: sha, paths}` unless a link with that sha exists (idempotent), history `link_added`; if `effective_state == proposed`, set `implemented` (history `implemented`); remove the id from every session's `pending_decisions` (F3: consumed only here). If `paths` is empty: nothing changes and the id stays pending.
4. Save records, regenerate `INDEX.md`.
5. Print `scribe: linked <n> record(s) to <sha>; run git add docs/decisions to include the backlinks in your next commit` to stderr when n > 0. Exit 0 always.

Amend and rebase: SHAs change and the stale link stays. `scribe relink` (F15) walks `git rev-list --all`, parses each commit's trailers, computes `implementation_paths` per record and rebuilds `implementation_links` as: links whose commit is reachable are kept (paths refreshed), links whose commit is not reachable are dropped, missing ones are added; one `relinked` history entry per changed record; `effective_state` becomes `implemented` for a proposed record that gains its first link. There is no range option.

### 5.4 CI check: `scribe check` and `scribe-check.yml`

`scribe check --base <ref>` prints reasons and exits 1 when any of these hold, else prints `scribe check: ok` and exits 0. Range: `<base>...HEAD`; changed records `git diff --name-only <base>...HEAD -- docs/decisions/`; changed paths overall `git diff --name-only <base>...HEAD`; commits `git rev-list <base>..HEAD`.

1. Supersede gate (F11): for every record R in HEAD with `review_state: unreviewed` whose `supersedes` resolves to a record with `review_state: ratified` in the base tree or in HEAD, fail if R's file is among the changed records, or any changed path matches R's `affects` (`implementation_paths` non-empty), or any commit in the range carries a `Decision:` trailer for R. Message `<R alias> supersedes ratified <P alias> and this branch introduces or depends on it`.
2. A changed record fails `validate` (including attestation rules).
3. `INDEX.md` is stale.
4. `RATIFICATIONS.jsonl` is not append-only relative to the base (base content must be a prefix of HEAD content).
5. `immutable_changed` or `history_rewritten` for any record present at the base (`history_check.py`).

Ordinary unreviewed records do not fail the check. Not implemented (F13): running `verify` on committed content; `tests/test_deferred.py::test_check_runs_verify_on_committed_content` is skip-marked with the same activation condition as section 5.2.

Workflow written by `scribe init --ci-source <spec>` (F6) at `.github/workflows/scribe-check.yml` from `templates/scribe-check.yml`:

```yaml
# scribe-managed v1
name: scribe-check
on:
  pull_request:
jobs:
  scribe-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: astral-sh/setup-uv@v10
      - run: {{SCRIBE_CHECK_COMMAND}} --base "origin/${{ github.base_ref }}"
```

`{{SCRIBE_CHECK_COMMAND}}` is rendered from the spec: a filesystem path (`.` means this repository is the scribe checkout, used for dogfood; any other existing path is accepted with a printed warning that it only works where that path exists) renders `uv run --frozen --project <path> scribe check`; a `git+https://` or `https://` URL renders `uvx --from "<url>" scribe check`. Without `--ci-source` init writes no workflow and prints `scribe: no CI workflow written; re-run with --ci-source <git+https URL or path> once the scribe package is reachable from CI`. Until the scribe repository exists on GitHub (Q1), the dogfood repo uses `.`.

### 5.5 `scribe init [--force] [--hooks-dir <path>] [--ci-source <spec>]`

1. Root = `git rev-parse --show-toplevel`; refuse outside a repo.
2. Preflight (F28): `shutil.which("uv")` and the shim interpreter (`python3` on POSIX, `python` on Windows) must be found; otherwise print `scribe: preflight failed: <what> not on PATH; hooks would silently skip` and exit 1 before writing anything.
3. Hooks directory: `git rev-parse --git-path hooks`. If `core.hooksPath` is set and `--hooks-dir` was not given: print the path and the chaining line, install nothing, exit 1. With `--hooks-dir`, install there.
4. For each of `prepare-commit-msg`, `commit-msg`, `post-commit`: missing: write the shim, `chmod 0o755`; present with marker `# scribe-managed`: overwrite; present without marker: skip with `scribe: existing <name> hook kept; use --force to replace (a backup <name>.pre-scribe is written)`, exit 1 at the end; with `--force`, rename to `<name>.pre-scribe` and write.
5. `.gitignore`: append `.claude/scribe/` if absent.
6. `.claude/scribe/config.json`: write `{"version": 1, "SCRIBE_GATES": "shadow", "SCRIBE_COMMIT_MSG": "warn"}` if missing; never overwrite an existing file (F21).
7. `.github/workflows/scribe-check.yml`: only with `--ci-source` (section 5.4); write if missing or scribe-managed, else skip unless `--force`.
8. `.claude/settings.json`: read (create `{}` if missing), ensure `permissions.deny` contains `Edit(/docs/decisions/RATIFICATIONS.jsonl)`, remove a legacy `Write(docs/decisions/RATIFICATIONS.jsonl)` or `Edit(docs/decisions/RATIFICATIONS.jsonl)` entry if present, write back with 2-space indent preserving other keys. Invalid JSON: skip with a message.
9. `docs/decisions/`: create if missing with an empty `RATIFICATIONS.jsonl` and a generated `INDEX.md`.
10. Print every path written, kept, skipped, and the follow-ups (commit the new files; add branch protection requiring the `scribe-check` job). Exit 0 unless a foreign hook was skipped or preflight failed.
11. Idempotent: a second run changes nothing and prints `unchanged` per path.

## 6. Task list for the implementer

"AT" = acceptance test, run from `/home/alfakentavr/scribe` by the orchestrator. Size: S under 1 hour, M 1 to 3 hours, L over 3 hours for one gpt-5.6-sol subagent. `uv run pytest -q` must be green after each task. Dependency edges are exact; a task may start when all its dependencies are done. Where a task says "Decision trailer", the task's commit message ends with the given line(s) (the trailer format is `Decision: <alias> <ulid>`). ULIDs: A10 `01M21BV91NZSW1HMJ127KZAA5J` (`D-260908-unreviewed-may-supersede-ratified`), A13 `01M21BVA0X8D5FZCRZNX848569` (`D-260908-one-way-door-defer-not-stop`), A12 `01M21BVB05VVF1XV54Y66AWV6E` (`D-260908-verbatim-quote-is-the-evidence`).

### T1 Bootstrap commit and project skeleton (S)
Deps: none.
Step 1, the bootstrap commit (F23), before any code: `git add .gitignore AUTONOMOUS_DECISIONS_09_08_2026.md docs/` and commit with message title `docs: Add the first three scribe decision records and the build plan`, body one sentence, and these trailer lines exactly:
```
Decision: D-260908-unreviewed-may-supersede-ratified 01M21BV91NZSW1HMJ127KZAA5J
Decision: D-260908-one-way-door-defer-not-stop 01M21BVA0X8D5FZCRZNX848569
Decision: D-260908-verbatim-quote-is-the-evidence 01M21BVB05VVF1XV54Y66AWV6E
Session: session_01A6tVoZuuWqu56QxEqtAjRw
```
If the records are already committed when T1 starts, verify with `git log --format=%B -n 1 -- docs/decisions` that the three trailers exist; if they do not, make an empty commit (`--allow-empty`) carrying them.
Step 2, files: `pyproject.toml` (`[project] name = "scribe"`, `version = "0.1.0"`, `requires-python = ">=3.11"`, `dependencies = ["pyyaml>=6.0"]`, `[dependency-groups] dev = ["pytest>=8"]`, `[project.scripts] scribe = "scribe.cli:main"`, `[build-system]` hatchling with `src` layout, `[tool.pytest.ini_options] testpaths = ["tests"]`), `.python-version` (`3.12`), `uv.lock` via `uv lock` (hard requirement, F29: failure means `BLOCKED`), `src/scribe/__init__.py`, `__main__.py`, `cli.py` (subparser scaffold; `--version` prints `scribe 0.1.0 (<plugin root>)`), `tests/conftest.py` (fixtures `tmp_repo`, `run_cli`; see section 7), `tests/test_cli.py`, `.gitignore` (add `.claude/scribe/`, remove `docs/decisions/.scratch/`), `README.md` stub.
AT: `uv run scribe --version` prints `scribe 0.1.0 (/home/alfakentavr/scribe)`; `uv run pytest -q` reports 1 passed; `test -f uv.lock`; `git log --format=%B -n 1 <bootstrap sha> | grep -c '^Decision: '` prints 3.

### T2 ULID, front matter, schema, validator (M)
Deps: T1.
Files: `src/scribe/ulid.py`, `frontmatter.py`, `schema.py`, `record.py`, `store.py` (minimal: iterate, resolve, attestation lookup), `cli.py` (`validate`), `tests/test_ulid.py`, `test_frontmatter.py`, `test_schema.py`, `tests/fixtures/records/{valid_minimal.md, bad_ulid.md, ulid_overflow.md, missing_evidence_quote.md, unknown_key.md, ratified_without_attestation.md, unreviewed_with_attestation.md, bad_task_ref.md, jsonpath_engine.md, action_affects_valid.md, action_affects_bad_name.md, negate_on_action.md}`.
Behaviour: sections 3.1 to 3.4, 3.6 (including the exact hash definition), 3.7 lookup, 4.5. `Record.apply_change` and `body_sha256` live here. ULID boundary tests: `7ZZZZZZZZZZZZZZZZZZZZZZZZZ` valid, `80000000000000000000000000` invalid (F26). Title limit 200 (F4). `task_refs` regexes (F24). `jsonpath` message (F25). `action` type (F2).
AT: `uv run scribe validate docs/decisions` prints `3 records, 0 errors, 0 warnings` (if the validator disagrees with a record, fix the validator or log the defect; never edit a record); `uv run scribe validate tests/fixtures/records/bad_ulid.md` exits 1 mentioning `invalid_ulid`; `uv run scribe validate tests/fixtures/records/jsonpath_engine.md` output contains `unsupported_engine: jsonpath is on the README allowlist but not implemented in this release`; `uv run pytest -q` green.
Decision trailer: `Decision: D-260908-verbatim-quote-is-the-evidence 01M21BVB05VVF1XV54Y66AWV6E`.

### T3 Store, git utilities, affects matcher (S)
Deps: T2.
Files: `src/scribe/store.py` (full: effective edges per section 3.8, `reconcile_supersession`), `gitutil.py` (toplevel, staged paths, `git-path hooks`), `matching.py`, `tests/test_matching.py` (table-driven, at least 20 cases: `**`, basename patterns, negation, backslash normalization, outside-repo path, Windows case-insensitivity under a monkeypatched `os.name`), `tests/test_store.py` (effective-edge cases: rejected, expired, backtracked and superseded successors; reconcile marks and restores).
AT: `uv run pytest tests/test_matching.py tests/test_store.py -q` green; `uv run python -c "from scribe.matching import matches; assert matches('src/**', 'src/a/b.py'); assert not matches('src/*.py', 'src/a/b.py'); assert matches('*.sql', 'db/x.sql')"`.

### T4 INDEX.md generator (M)
Deps: T3.
Files: `src/scribe/index.py`, `cli.py` (`index`, `index --check`), `tests/test_index.py` (fixture store with: one unreviewed record superseding a ratified one, one implemented unreviewed, one proposed, one rejected successor whose predecessor must appear under Active, one expired, one marked `superseded` with no effective edge shown as `superseded (stale)`), `docs/decisions/INDEX.md` (generated, committed).
Behaviour: section 3.5 over effective edges (F1).
AT: `uv run scribe index && uv run scribe index --check` exits 0; `grep -c '^## Review queue (0)$' docs/decisions/INDEX.md` prints 1; `grep -c '^## Active decisions (3)$' docs/decisions/INDEX.md` prints 1; the test asserts the `[supersedes ratified]` line is first in the queue and that the rejected successor's predecessor is Active.
Decision trailer: `Decision: D-260908-unreviewed-may-supersede-ratified 01M21BV91NZSW1HMJ127KZAA5J`.

### T5 Reverse lookup (S)
Deps: T3.
Files: `src/scribe/lookup.py`, `gitutil.py` (trailer parsing via `git interpret-trailers --parse`, `git log --format=%(trailers:...)`, `rev-list --all`), `cli.py` (`lookup`), `tests/test_lookup.py` (tmp repo commits with alias-only, ulid-only and both-token trailers; unknown token).
Behaviour: section 4.6.
AT: `uv run scribe lookup D-260908-verbatim-quote-is-the-evidence` prints the record path and the bootstrap commit sha (F23); `uv run scribe lookup <bootstrap sha>` prints the three aliases; `uv run scribe lookup nope` exits 1.

### T6 Plugin manifest, hooks.json, launcher, config, scratch state, session hooks (M)
Deps: T3.
Files: `.claude-plugin/plugin.json` (`{"name": "scribe", "version": "0.1.0", "description": "Records agent decisions, links them to code, injects them before edits, queues them for human ratification.", "author": {"name": "Nikita Boguslavskii"}}`), `hooks/hooks.json` (every entry of section 4.1 item 1 in exec form; the `pre-tool-use-edit`, `gate` and `reconcile` entrypoints are registered now and ship as no-op advisory stubs that T7 and T10 fill), `src/scribe/hooks/launcher.py`, `session_start.py`, `user_prompt_submit.py`, `state.py`, `config.py`, `cli.py` (`hook <event>` dispatch), `tests/fixtures/hooks/{session_start.json, user_prompt_submit.json, user_prompt_with_refs.json, malformed.txt}`, `tests/test_hook_launcher.py` (fail-open with `.claude/scribe` read-only, with `.claude/scribe` being a regular file, with malformed stdin, with a raising `fn`; production `run_gate` exits 0 on deny in shadow and 2 in enforce via `set_config`), `tests/test_state.py` (lock adapter with a fake `msvcrt` in `sys.modules`, bounded retry, corrupt JSON, 7-day prune), `tests/test_hook_session.py` (task_refs extraction, prompt_ids cap).
Behaviour: sections 4.1 to 4.3.
AT: `python3 -m json.tool .claude-plugin/plugin.json > /dev/null` and `python3 -m json.tool hooks/hooks.json > /dev/null` each exit 0 (separate commands, F16); `command -v claude > /dev/null && claude plugin validate . || echo 'claude not on PATH, skipped'`; `uv run scribe hook user-prompt-submit < tests/fixtures/hooks/user_prompt_with_refs.json` exits 0 with empty stdout and `.claude/scribe/state.json` gains the session with `task_refs` containing `LIN-123`; `uv run scribe hook session-start < tests/fixtures/hooks/malformed.txt` exits 0 silently; a test asserts every handler has `"command": "uv"` and `args` starting `["run", "--frozen", "--project", "${CLAUDE_PLUGIN_ROOT}", "scribe", "hook"]`, and the `Edit|Write` entry has `"timeout": 1`.

### T7 PreToolUse injection hook and timing (M)
Deps: T6.
Files: `src/scribe/hooks/pre_tool_use_edit.py`, `tests/fixtures/hooks/{pre_tool_use_edit_match.json, pre_tool_use_edit_nomatch.json, pre_tool_use_write_outside_repo.json}`, `tests/test_hook_injection.py`, `tests/test_timing.py`.
Behaviour: section 4.4, section 7 item 5 (F19).
AT: with the three real records copied into a tmp store and a fixture pointing at `<tmp_repo>/src/scribe/index.py`, stdout is JSON whose `hookSpecificOutput.additionalContext` contains `D-260908-unreviewed-may-supersede-ratified` and `These are retrieval candidates`; the no-match fixture prints nothing; both exit 0; `uv run pytest tests/test_timing.py -q -s` prints `warm median: <x> s` under 1.0 and `bytecode-cold: <y> s` under 2.0 with 100 generated records, and fails (not skips) when `uv` is missing.

### T8 `scribe new` and the decide skill (M)
Deps: T4, T6.
Files: `src/scribe/newrecord.py`, `templates/record_template.md`, `cli.py` (`new`), `skills/decide/SKILL.md`, `tests/test_new.py`, `tests/fixtures/new_spec.json`, `tests/fixtures/new_spec_supersedes.json`.
Behaviour: section 4.9 (task_refs and prompt_ids from state, F10; `reconcile_supersession` on `supersedes`).
AT: in a tmp repo with a session in state carrying `task_refs: ["LIN-7"]`, `uv run scribe new --spec tests/fixtures/new_spec.json --register --session test-session` creates `docs/decisions/D-<today>-<slug>.md` that validates, has `task_refs: [LIN-7]`, regenerates `INDEX.md` with the alias in the review queue, and `state.json` lists the ULID under `pending_decisions` and `records_written`; the same spec twice yields `<slug>-2`; the supersedes spec marks the predecessor `effective_state: superseded` with a `superseded` history entry; `grep -c 'disable-model-invocation' skills/decide/SKILL.md` prints 0 and `grep -c 'CLAUDE_SESSION_ID' skills/decide/SKILL.md` prints at least 1.
Decision trailers: `Decision: D-260908-one-way-door-defer-not-stop 01M21BVA0X8D5FZCRZNX848569` and `Decision: D-260908-verbatim-quote-is-the-evidence 01M21BVB05VVF1XV54Y66AWV6E`.

### T9 Ratify and reject (M)
Deps: T4, T7.
Files: `src/scribe/ratify.py`, `cli.py` (`ratify`, `reject`), `skills/ratify/SKILL.md`, `skills/reject/SKILL.md`, `tests/test_ratify.py`.
Behaviour: sections 3.8, 4.10 (F1, F5, F7, F8).
AT: in a tmp repo: `uv run scribe ratify <alias> --by @tester --note t` sets `review_state: ratified`, 3 history entries, one JSONL line with `via: cli`; the same command again exits 0 printing `already ratified`, no new line; `reject` then `ratify` on the same record each append a line and 3 entries; hand-editing another record to `ratified` without attestation makes `validate` exit 1 with `unattested_review_state`; deleting the record change but keeping the attestation gives `state_behind_attestation` and a re-run heals it; end-to-end (F1): ratified A, unreviewed B with `supersedes: A` (A shows `superseded`, index Retired), `scribe reject B`, then A is `effective_state: proposed` with a `restored` entry, Active in the index, and the injection hook for a path in A's `affects` returns A and not B; injected failures (monkeypatched `os.replace`, attestation append, index write) leave a state the validator names and a re-run heals; two subprocesses ratifying different records concurrently produce two valid lines; `grep -c 'disable-model-invocation: true' skills/ratify/SKILL.md skills/reject/SKILL.md` prints 1 for each file; both skills contain a line starting with ``!`uv run``.

### T10 Phase 3 gate scaffolds (M)
Deps: T6.
Files: `src/scribe/policy.py`, `hooks/pre_tool_use_gate.py`, `hooks/reconcile.py`, `tests/fixtures/hooks/{gate_bash_force_push.json, gate_bash_force_with_lease.json, gate_bash_safe.json, gate_powershell_publish.json, gate_exit_plan_mode.json, task_completed.json, stop.json, stop_active.json}`, `tests/test_hook_gate.py`.
Behaviour: sections 4.7, 4.8 (F2 action matching, F9 flag and `capture_missing`, F21 config mode).
AT: force-push fixture: exit 0 and `gate-log.jsonl` gains a `gate_verdict` deny line; with `set_config(SCRIBE_GATES=enforce)`: exit 2, stderr contains `irreversible-action denylist`; force-push with a ratified one-way-door record whose `affects` has `{type: action, pattern: git-push-force}`: allow; `--force-with-lease`: allow; `gate_powershell_publish.json` (`tool_name: PowerShell`, `npm publish`): deny logged; ExitPlanMode fixture mentioning `add package` with empty pending decisions: deny logged and `decision_worthy` set in state; then `task_completed.json` for that session: `capture_missing` event logged, exit 0, flag cleared; after a `records_written` entry newer than the flag: allow, no event; `stop_active.json`: exit 0, no log line; `uv run pytest -q` green; `grep -c SCRIBE_GATES src/scribe/hooks/pre_tool_use_gate.py` prints at least 1 (A13's verify entry).
Decision trailer: `Decision: D-260908-one-way-door-defer-not-stop 01M21BVA0X8D5FZCRZNX848569`.

### T11 Git hooks: prepare-commit-msg, commit-msg, post-commit (L)
Deps: T5, T9.
Files: `src/scribe/githooks/{prepare_commit_msg.py, commit_msg.py, post_commit.py}`, `src/scribe/links.py`, `cli.py` (`git-hook <name>`), `gitutil.py` (interpret-trailers, diff-tree), `tests/test_githooks.py`, `tests/test_deferred.py` (adds the skip-marked `test_commit_msg_runs_verify_on_staged_content`).
Behaviour: sections 5.1 to 5.3 (F3, F12, F13, F14). Tests install the entrypoints as hook files that call `sys.executable -m scribe git-hook <name>` (no shim, no uv).
AT: in a tmp repo: (a) commit a new record file only: message gains `Decision: <alias> <ulid>`, `post-commit` adds no link, the id stays pending; (b) then stage `src/x.py` matching the record's `affects: src/**` and commit: trailer added from pending state, `effective_state: implemented`, one link, pending id removed (F3 two-commit sequence); (c) stage `notes.md` outside `affects` with a pending id: no trailer; (d) `git commit --amend --no-edit` on (b): no duplicate trailer, links are exactly `{old sha, new sha}` (the post-relink set `{new sha}` is asserted in T15's `test_relink.py`, not here); (d2) amend with a newly pending decision whose `affects` match the amended paths: its trailer is added and it gains a link for the new sha; (e) `Claude-Session:` present: no `Session:` added; (f) `commit-msg` with an unknown decision prints `scribe: warning` and the commit succeeds; with `set_config(SCRIBE_COMMIT_MSG=enforce)` it fails; (g) F12: a trailer for an unrelated active record while a governed path is staged warns `governed path`; an inactive (rejected) record's trailer warns too; two governed paths each get their own warning; (h) `uv run pytest -q` reports 1 skipped.

### T12 CI check (M)
Deps: T4, T9.
Files: `src/scribe/check.py`, `src/scribe/history_check.py`, `cli.py` (`check`), `tests/test_check.py`, `tests/test_deferred.py` (adds the skip-marked `test_check_runs_verify_on_committed_content`).
Behaviour: section 5.4 (F11, F17), `history_check.py` reused by T13.
AT: tmp repo: `main` has ratified, attested A; branch `feat` adds unreviewed B with `supersedes: A` and regenerates the index: `uv run scribe check --base main` exits 1 printing `B supersedes ratified A`; `scribe ratify B`, `git add -A && git commit` (ratification, attestation, history, index), then `check` exits 0 and the append-only rule passes across that commit (F17); a branch adding a plain unreviewed record exits 0; a branch deleting a line from `RATIFICATIONS.jsonl` exits 1; a branch rewriting a record body exits 1 with `immutable_changed`; F11: B exists at the branch base, the branch only changes `src/x.py` matching B's `affects`: exit 1; `uv run pytest -q` reports 2 skipped.
Decision trailer: `Decision: D-260908-unreviewed-may-supersede-ratified 01M21BV91NZSW1HMJ127KZAA5J`.

### T13 Lint and the lint skill (M)
Deps: T5, T10, T12.
Files: `src/scribe/lint.py`, `cli.py` (`lint`), `skills/lint/SKILL.md`, `tests/test_lint.py`.
Behaviour: section 4.12.
AT: fixtures trigger each rule once and the test asserts the code; `uv run scribe lint` on this repository exits 0 with no `verify_failed` and no `verify_error` (every `verify` target of the three records exists by now: `src/scribe/index.py` and `check.py` from T4 and T12, `hooks/pre_tool_use_gate.py` containing `SCRIBE_GATES` from T10, `schema.py` from T2, `templates/record_template.md` and `skills/decide/SKILL.md` from T8; `templates/scribe-check.yml` appears only in A10's `affects`, not in a `verify` entry, so T14 is not needed); `--expire` on a 40-day-old proposed fixture sets `expired` with a history entry and restores its predecessor if any.

### T14 `scribe init` and the init skill (M)
Deps: T11, T12.
Files: `src/scribe/init_repo.py`, `templates/githook_shim.py`, `templates/scribe-check.yml`, `cli.py` (`init`), `skills/init/SKILL.md`, `tests/test_init.py`.
Behaviour: section 5.5 and the shim in section 5 (F5 deny rule, F6 `--ci-source`, F21 config, F28 preflight).
AT: in a tmp repo, `uv run scribe init --ci-source /home/alfakentavr/scribe` writes three executable hooks containing `# scribe-managed`, appends `.claude/scribe/` to `.gitignore`, writes `config.json` with `shadow`/`warn`, writes the workflow whose `run:` line starts with `uv run --frozen --project /home/alfakentavr/scribe scribe check`, and `.claude/settings.json` with exactly the deny rule `Edit(/docs/decisions/RATIFICATIONS.jsonl)`; without `--ci-source` no workflow is written and the hint is printed; a second run prints `unchanged` for every path and changes no file; a foreign `commit-msg` is kept with exit 1, `--force` replaces it leaving `commit-msg.pre-scribe`; `core.hooksPath` set exits 1 with chaining instructions; with `PATH` lacking `uv` (monkeypatched `shutil.which`) preflight exits 1 and writes nothing; the installed shim, run end to end, adds a trailer to one real commit (requires `uv` on PATH, which the test asserts rather than skips); F6 end to end: the `run:` line extracted from the generated workflow, with `--base main` substituted for the GitHub expression, exits 1 on the supersede branch and 0 on an ordinary branch.

### T15 Relink, marketplace, own CI, README, dogfood init (M)
Deps: T11, T13, T14.
Files: `src/scribe/relink.py`, `cli.py` (`relink`), `tests/test_relink.py`, `.claude-plugin/marketplace.json` (`{"name": "scribe", "owner": {"name": "Nikita Boguslavskii", "email": "bognik3@gmail.com"}, "plugins": [{"name": "scribe", "source": "./", "description": "...", "version": "0.1.0"}]}`), `.github/workflows/ci.yml` (checkout, `astral-sh/setup-uv@v10`, `uv sync --frozen`, `uv run pytest -q`), `README.md` (install with `claude --plugin-dir ~/scribe` then `/reload-plugins`; CLI table; record format summary pointing at this plan's section 3; ratification model exactly as section 3.7 states it; denylist; fail-open policy; config file; Windows caveats: shim interpreter, lock adapter untested, PowerShell tool matcher), then `uv run scribe init --ci-source .` on this repository (writes `.git/hooks/*`, `.claude/settings.json`, `.claude/scribe/config.json`, `.github/workflows/scribe-check.yml`, `.gitignore` line).
Behaviour: section 5.3 relink (F15).
AT: `uv run pytest -q` green; `python3 -m json.tool .claude-plugin/marketplace.json > /dev/null`; `head -c 200 .git/hooks/prepare-commit-msg | grep -c scribe-managed` prints 1; `uv run scribe check --base <bootstrap sha>` exits 0; `test_relink.py`: in a tmp repo with one old linked commit and one new one `uv run scribe relink` keeps both (F15); after `git commit --amend` of the newest commit the links are exactly `{new sha}` plus the old one, with one `relinked` history entry (this completes T11's case (d)).

### T16 Deferred two-worktree test, final sweep (S)
Deps: T15.
Files: `tests/test_deferred.py` (adds `test_two_worktree_supersede`, skip reason `deferred: two-worktree supersede test, enable before turning any gate to enforce`, body contains the full scenario of section 7 item 4), `README.md` (test section), `AUTONOMOUS_DECISIONS_09_08_2026.md` (implementer's `I` items consolidated).
AT: `uv run pytest -q` prints `N passed, 3 skipped`; `uv run scribe lint` exits 0; `uv run scribe index --check` exits 0; `uv run scribe validate docs/decisions` prints `3 records, 0 errors, 0 warnings`; `git status --short` is clean after the commit; the section 0.2 checklist is run and its results written into `docs/build/04-implementation-report.md`.

## 7. Test strategy

1. Layout: `tests/` flat, one file per module, fixtures under `tests/fixtures/`. `conftest.py` provides `tmp_repo` (a `git init`ed temp dir with `user.name`, `user.email`, `commit.gpgsign=false`, `core.hooksPath` unset, `docs/decisions/` with the three real records and their `RATIFICATIONS.jsonl` copied in, `.claude/scribe/` created), `run_cli(args, cwd, env)` (in-process `scribe.cli.main`, captures stdout, stderr, exit code), `run_hook(event, payload_dict, cwd, env)` (subprocess `sys.executable -m scribe hook <event>` with JSON on stdin), `write_record(store, **overrides)` (valid record from a template, one field changed per test), `set_config(root, **switches)` (writes `.claude/scribe/config.json`).
2. Hooks: stdin fixtures, assert stdout (parsed as JSON when non-empty), stderr, exit code. Every hook has a happy path, a malformed-stdin case (exit 0, empty stdout) and a missing-store case. Gates run once in shadow and once with `set_config(SCRIBE_GATES="enforce")`.
3. Git hooks: real `git` in `tmp_repo`, entrypoints installed as hook files calling `sys.executable -m scribe git-hook <name>`; one shim test in T14 requires `uv` on PATH and fails if absent.
4. Deferred two-worktree scenario (T16 stub): worktree A ratifies X on `main`; worktree B (branch `feat`) writes Y with `supersedes: X` via `scribe new`, commits; `scribe index` in B shows Y first in the queue with `[supersedes ratified]` and X Retired; `scribe check --base main` in B exits 1; after `scribe ratify Y` and a commit, merging `feat` into `main` in A passes `check`; injection for a path in X's `affects` returns Y in B and X in A before the merge. Enable before any gate is switched to enforce.
5. Timing (F19): `tests/test_timing.py` locates `uv` with `shutil.which` (`pytest.fail` if missing), generates 100 records in a tmp store, runs `uv run --frozen --project /home/alfakentavr/scribe scribe hook pre-tool-use-edit` as a subprocess three times and asserts the median wall time under 1.0 s, prints it as `warm median: <x> s`; then removes `src/**/__pycache__`, runs once with `PYTHONDONTWRITEBYTECODE=1`, prints `bytecode-cold: <y> s` and asserts under 2.0 s. A fresh-venv cold start is not measured (network; absorbed by SessionStart's 120 s timeout).
6. `uv run pytest` is the single command; CI runs the same. No test touches the network or the user's home directory; `HOME` points at a temp dir for hook tests.
7. Total skipped tests at the end: exactly 3, all in `tests/test_deferred.py`. No task may un-skip or modify another task's skipped test.

## 8. Dogfooding

1. The three hand-written records are scribe's first ledger: `review_state: ratified`, attested `via: hand-written`, `effective_state: proposed` until code lands. T1 commits them with their own trailers (F23); because that commit changes no `affects` path, it creates no implementation link (section 5.3 rule).
2. Implementing tasks and their trailers are stated in section 6: A10 by T4 and T12; A13 by T8 and T10; A12 by T2 and T8.
3. Git hooks are not installed in this repository until T15 runs `scribe init --ci-source .`, so the orchestrator writes the trailers by hand in the commit messages of T2, T4, T8, T10, T12. Step 5 runs `uv run scribe relink` once, which turns those trailers into `implementation_links` and flips the three records to `implemented`, then commits the front-matter change.
4. From T8 on, design-shaping choices the implementer makes (a new field, a changed enum, an open behaviour) are also recorded with `uv run scribe new --spec ...` as `decided_by: agent`, `review_state: unreviewed`, quoting the plan line or the `I` item as Evidence. Before T8, `I` items in the decisions file are the record.
5. Step 5 runs `/scribe:decide` once with the plugin loaded via `claude --plugin-dir ~/scribe`, which is the end-to-end check of `${CLAUDE_PLUGIN_ROOT}`, `${CLAUDE_SESSION_ID}`, skill invocation, hook registration and the two UNVERIFIED skill items in section 10.

## 9. Risks and open questions (defaults chosen)

R1. Human-only ratification (F5). Default: `disable-model-invocation`, the inline `!` path in the two skills, the anchored `Edit` deny rule, the `via` tag, and a README that says the attestation records the actor and path but does not prove a human. Batched owner question Q5: accept this for now, or invest in a stronger mechanism (a separate reviewing identity, or signed attestations) in a later run.

R2. Cold start of `uv run` after install. Default: SessionStart (120 s) pays it; the edit hook's 1 s timeout cuts off a cold edit-path call silently once. Accepted.

R3. Scratch state under two sessions in one worktree and `/batch` worktrees. Default: worktree-local file keyed by session id, locked writes, `prepare-commit-msg` filters pending ids by `affects` overlap, `post-commit` consumes only linked ids. Residual: a pending decision with empty `affects` attaches to the next commit from any session in that worktree; the README tells users to fill `affects`.

R4. Amend and rebase change SHAs. Default: `scribe relink` rebuilds from trailers over all reachable history; lint flags `unreachable_link`. No `post-rewrite` hook this run (Q3).

R5. `post-commit` writes land in the next commit, so a branch's last commit leaves the tree dirty by generated files. Default: accepted (README 10.4); `scribe check` catches a stale index before merge.

R6. CI workflow needs a reachable scribe package. Default: `--ci-source`, dogfood uses `.`; Q1 stays open.

R7. ExitPlanMode keyword policy will produce false positives. Default: shadow only; keywords in `policy.py`; the gate log gives the false-positive rate.

R8. Windows: shim interpreter, `msvcrt` lock adapter, PowerShell tool. Default: best effort by construction, listed in section 10 and the README.

R9. One-way-door "never act" is enforced only by instructions while the gate is in shadow mode. Default: accepted for this run (A13 asked for frequency data first); the gate log supplies it.

R10. PyYAML drops front-matter comments on save. Default: accepted; the body is byte-preserved and comments are not keys. The three records lose their `source_messages` comments the first time a scribe command saves them (relink in step 5).

R11. Skill commands are written unquoted so they match their `allowed-tools` rule textually and run without a permission prompt; a plugin root path containing spaces breaks them. Default: accepted (the owner's Ubuntu path has no spaces); listed under Windows caveats in the README. The hook commands are not affected because exec form passes `${CLAUDE_PLUGIN_ROOT}` as one argument.

## 10. UNVERIFIED register

Everything else in this plan about Claude Code was checked against the docs on 2026-09-08 (see the head of `03-findings-response.md`). These three remain and are each isolated so the step 5 review can fix them in minutes:

| Id | Claim | Isolated in | Fallback if false | Checked by |
|---|---|---|---|---|
| U1 | `$ARGUMENTS` is substituted inside a skill's inline `` !`...` `` command before it runs | `skills/ratify/SKILL.md`, `skills/reject/SKILL.md` (two lines) | replace the inline command with an instruction to the model to run the same CLI command (the v1 design); nothing else changes | step 5 typing `/scribe:ratify <alias>` with the plugin loaded |
| U2 | PreToolUse `Bash` hooks fire for skill-injected `!` commands (the skills doc says injected commands "run through the Bash tool") | `src/scribe/policy.py` (no rule concerns ratify in this run, so nothing depends on it yet) | none needed this run; a future enforce-mode rule about `scribe ratify` would have to exempt the skill path | step 5 reading `gate-log.jsonl` after `/scribe:ratify` |
| U3 | Native Windows behaviour: `msvcrt.locking` adapter, `#!/usr/bin/env python` shim under Git for Windows, exec-form `uv.exe` resolution | `src/scribe/state.py` (lock adapter function), `src/scribe/templates/githook_shim.py`, `hooks/hooks.json` | fall back to unlocked writes with a logged warning; document the shim as manual chaining on Windows | owner's Windows smoke test (brief: best effort) |

Removed from the v1 list because the docs settle them: `additionalContext` on PreToolUse and SessionStart, `timeout` units and fail-open on expiry, matcher alternatives, all stdin field names used, `tool_input.plan` for ExitPlanMode, TaskCompleted fields, `${CLAUDE_PLUGIN_ROOT}` and `${CLAUDE_SESSION_ID}` in skill content, SKILL.md front matter keys (`disable-model-invocation`, `allowed-tools`, `argument-hint`), manifest and marketplace key sets, `claude plugin validate`, `Edit(/path)` rule anchoring and coverage of Write, exec-form hooks. Dropped from the design rather than verified: the `CLAUDECODE` environment variable and `CLAUDE_SESSION_ID` as a process environment variable (the session id is passed explicitly).
