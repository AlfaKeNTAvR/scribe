# Scribe implementation plan (step 1 of 5)

Written 2026-09-08 by the Fable 5.1 planner. Design source of truth: `research/decision-scribing/README.md` sections 10 to 16 in the `~/.claude` repo (worktree `decision-scribing-glossary`); scope and fixed decisions: `build-brief.md` next to it. Readers: the Codex gpt-6-astra reviewer (step 2), the Fable reviser (step 3), the Codex orchestrator and its gpt-5.6-sol subagents (step 4). Every task in section 6 is meant to be executable from this file and the repository alone.

Conventions in this document: `UNVERIFIED` marks a claim about Claude Code mechanics that is not in the brief's "Plugin facts" bullet; the reviewer should check each one. `Pn` refers to a numbered choice in `/home/alfakentavr/scribe/AUTONOMOUS_DECISIONS_09_08_2026.md`. All repository paths are relative to `/home/alfakentavr/scribe` unless absolute.

## 1. Goal and non-goals

Goal (this run):

1. A Claude Code plugin `scribe` in `~/scribe`, installable with `claude --plugin-dir ~/scribe`, that ships five skills (`/scribe:decide`, `/scribe:ratify`, `/scribe:reject`, `/scribe:init`, `/scribe:lint`), a Python CLI (`uv run scribe ...`), Claude Code hooks (advisory, fail-open) and git hooks installed per repository by `/scribe:init`.
2. Phase 1: the record schema (section 3), a validator, three real records (already in `docs/decisions/`), a trailer-to-record reverse lookup, and a DEMM grade of the three records (`docs/build/01-records-grading.md`).
3. Phase 2: decide, ratify, reject, init, lint skills; `INDEX.md` generator with the review queue first; `prepare-commit-msg`, `commit-msg` (warn only), `post-commit` git hooks; `PreToolUse` injection on Edit and Write matched by `affects`.
4. Phase 3, scaffolded only: `ExitPlanMode` policy, Bash denylist, `TaskCompleted` and `Stop` reconcile, all registered and running in shadow mode (compute the verdict, log it, always exit 0); the CI required check `scribe check` that fails on an unreviewed record superseding a ratified one.

Non-goals (this run):

1. No vector store, git notes, MCP server, event log (README 10.6), friction log, retro or promotion ladder (README 10.5), weekly scheduler.
2. No enforcement by the phase 3 gates: they never exit 2 unless `SCRIBE_GATES=enforce` is set, which only the tests set.
3. No `FileChanged`, `PostToolUse`, `PostToolBatch`, `InstructionsLoaded` hooks (README 10.4 rows for observation and audit): observation is deferred until the ledger is in use.
4. No Windows testing; Windows is best effort by construction (Python via `uv`, forward-slash paths, no bash), not by verification.
5. No GitHub repository creation, no push, no publishing (brief: never create the GitHub repository without asking).

## 2. Repository layout

Every path the finished repo contains after T16. `(gen)` = generated, committed; `(local)` = git-ignored.

```
.claude-plugin/plugin.json               plugin manifest: name scribe, version 0.1.0, description, author (brief: verified location)
.claude-plugin/marketplace.json          single-entry marketplace so `/plugin marketplace add <path>` works on the same repo (brief: verified); exact key set UNVERIFIED, see T15
.claude/settings.json                    dogfood: permissions.deny for the attestation file, written by `scribe init` on this repo (T15)
.github/workflows/ci.yml                 scribe's own tests: uv sync, uv run pytest, on push and pull_request
.github/workflows/scribe-check.yml       (gen by scribe init, dogfood) the merge gate described in section 5.4
.gitignore                               existing, plus `.claude/scribe/`, `uv.lock` is NOT ignored
.python-version                          `3.12` (P3)
AUTONOMOUS_DECISIONS_09_08_2026.md       pipeline decisions log, P-items, appended by every step
README.md                                install (`claude --plugin-dir`, `/reload-plugins`), CLI reference, record format summary, dogfood notes
pyproject.toml                           project `scribe`, requires-python >=3.11, deps pyyaml, dev pytest; console script `scribe = scribe.cli:main`
uv.lock                                  committed so hooks can run `uv run --frozen`
hooks/hooks.json                         Claude Code hook registrations, every command via ${CLAUDE_PLUGIN_ROOT} (section 4.1)
skills/decide/SKILL.md                   /scribe:decide (section 4.9)
skills/ratify/SKILL.md                   /scribe:ratify (section 4.10)
skills/reject/SKILL.md                   /scribe:reject (section 4.10)
skills/init/SKILL.md                     /scribe:init (section 4.11)
skills/lint/SKILL.md                     /scribe:lint (section 4.12)
src/scribe/__init__.py                   `__version__ = "0.1.0"`
src/scribe/__main__.py                   `python -m scribe` -> cli.main
src/scribe/cli.py                        argparse: validate, index, relink, lookup, new, ratify, reject, lint, check, init, hook <event>, git-hook <name>
src/scribe/ulid.py                       stdlib ULID: generate(), is_valid(), timestamp_ms() (P2)
src/scribe/frontmatter.py                split(text) -> (mapping, body), join(mapping, body); PyYAML safe_load/safe_dump, key order preserved (section 3.6)
src/scribe/schema.py                     field table, enums, validate_record(mapping, body) -> list[Problem]
src/scribe/record.py                     Record dataclass: load(path), save(), apply_change(field, new, event, by) that appends history; body_sha256()
src/scribe/store.py                      repo root discovery, docs/decisions iteration, alias/ULID resolution, duplicate detection
src/scribe/matching.py                   `affects` glob matcher (section 4.4)
src/scribe/index.py                      INDEX.md generator (section 3.5)
src/scribe/lookup.py                     trailer parsing, commit -> records, record -> commits
src/scribe/newrecord.py                  `scribe new`: slug, alias, template fill, state registration
src/scribe/ratify.py                     ratify/reject: record mutation plus RATIFICATIONS.jsonl attestation (section 4.10)
src/scribe/lint.py                       lint rules (section 4.12)
src/scribe/check.py                      CI check (section 5.4)
src/scribe/relink.py                     rebuild implementation_links from git trailers (section 5.3)
src/scribe/state.py                      scratch state `.claude/scribe/state.json` read/write with file lock (section 4.2)
src/scribe/policy.py                     phase 3 denylist regexes and plan-policy keywords (section 4.7)
src/scribe/init_repo.py                  git hook shim installer, workflow drop, gitignore and settings.json merge (section 5.5)
src/scribe/gitutil.py                    subprocess wrappers: toplevel, staged paths, HEAD trailers, changed files, interpret-trailers
src/scribe/hooks/__init__.py
src/scribe/hooks/launcher.py             run_advisory(fn) and run_gate(fn): the two dispatcher policies (section 4.1)
src/scribe/hooks/session_start.py        SessionStart (section 4.3)
src/scribe/hooks/user_prompt_submit.py   UserPromptSubmit (section 4.3)
src/scribe/hooks/pre_tool_use_edit.py    PreToolUse Edit|Write injection (section 4.4)
src/scribe/hooks/pre_tool_use_gate.py    PreToolUse ExitPlanMode and Bash, shadow mode (section 4.7)
src/scribe/hooks/reconcile.py            TaskCompleted and Stop, shadow mode (section 4.8)
src/scribe/githooks/__init__.py
src/scribe/githooks/prepare_commit_msg.py (section 5.1)
src/scribe/githooks/commit_msg.py        (section 5.2)
src/scribe/githooks/post_commit.py       (section 5.3)
src/scribe/templates/record_template.md  body skeleton filled by `scribe new`
src/scribe/templates/githook_shim.py     text of the installed git hook file (section 5.5)
src/scribe/templates/scribe-check.yml    text of the CI workflow dropped by init (section 5.4)
tests/conftest.py                        fixtures: tmp_repo (git init, user.name/email, docs/decisions), run_cli, run_hook, write_record
tests/fixtures/hooks/*.json              stdin payloads per hook event
tests/fixtures/records/*.md              valid and invalid records
tests/test_ulid.py
tests/test_frontmatter.py
tests/test_schema.py
tests/test_matching.py
tests/test_index.py
tests/test_lookup.py
tests/test_hook_launcher.py
tests/test_hook_session.py
tests/test_hook_injection.py
tests/test_hook_gate.py
tests/test_new.py
tests/test_ratify.py
tests/test_githooks.py
tests/test_init.py
tests/test_check.py
tests/test_lint.py
tests/test_relink.py
tests/test_timing.py                     injection hook under 1 s with 100 records
tests/test_deferred_worktrees.py         skip-marked two-worktree supersede test (section 7.4)
docs/decisions/D-260908-unreviewed-may-supersede-ratified.md   record A10 (hand-written, step 1)
docs/decisions/D-260908-one-way-door-defer-not-stop.md         record A13
docs/decisions/D-260908-verbatim-quote-is-the-evidence.md      record A12
docs/decisions/RATIFICATIONS.jsonl       append-only attestations, one JSON object per line (section 3.7)
docs/decisions/INDEX.md                  (gen) by `scribe index`, first produced in T4
docs/build/01-plan.md                    this file
docs/build/01-records-grading.md         DEMM grade of the three records
docs/build/02-plan-review.md .. 04-implementation-report.md    later pipeline steps
```

## 3. Record format specification

### 3.1 File and identity

1. Path: `docs/decisions/<alias>.md`, alias `D-YYMMDD-<slug>`, slug `[a-z0-9]+(-[a-z0-9]+)*`, total alias length 8 to 60 characters. The filename stem MUST equal `alias` (validator error `alias_filename_mismatch`). Rationale (P4): humans read filenames and `git log --stat`; the ULID stays inside as the identity, so two branches producing the same alias surface as an add/add conflict at merge instead of two silently different records, and lint flags `duplicate_alias` if both survive.
2. `id`: ULID, 26 characters, Crockford base32 alphabet `0123456789ABCDEFGHJKMNPQRSTVWXYZ`, regex `^[0-9A-HJKMNP-TV-Z]{26}$`, uppercase. Generated by `src/scribe/ulid.py` (48-bit ms timestamp plus 80 random bits from `os.urandom`). Immutable. The validator checks the timestamp prefix decodes to a date within 1 day of `date` (`ulid_date_mismatch`, warning not error, because hand-written records may lag).
3. `alias`, `id`, `title`, `date`, `schema_version`, `task_refs`, `decided_by`, `recommended_by`, `provenance`, `affects`, `tags`, `reversibility`, `blast_radius`, `regret_when`, `review`, `verify`, `relates_to` and the whole body are immutable once the record's first commit exists (checked by `scribe lint` rule `immutable_changed` against `git show <base>:<path>`, section 4.12; the validator alone cannot see history).
4. Mutable keys, the only ones: `review_state`, `effective_state`, `ratified_by`, `ratified_at`, `implementation_links`, `supersedes`, `history`. Every change to a mutable key appends one `history` entry with `field`, `old`, `new` (section 3.3).

### 3.2 Front matter keys

YAML between the first line `---` and the next line `---`. Key order in the file is the order below (PyYAML `sort_keys=False`, section 3.6). `req` = required, may not be null. `null` = null allowed.

| Key | Type | Allowed values or format | Mutable | Notes |
|---|---|---|---|---|
| `id` | str, req | ULID regex above | no | identity |
| `alias` | str, req | `^D-\d{6}-[a-z0-9]+(-[a-z0-9]+)*$` | no | equals filename stem |
| `title` | str, req | 3 to 120 chars, single line | no | equals the H1 text |
| `date` | date, req | `YYYY-MM-DD` | no | decision date |
| `schema_version` | int, req | `1` | no | |
| `task_refs` | list[str], req (may be empty) | free, e.g. `LIN-123`, `owner/repo#42`, `#42` | no | brief: GitHub Issues or Linear ids |
| `review_state` | enum, req | `unreviewed`, `ratified`, `rejected` | yes | what the human said |
| `effective_state` | enum, req | `proposed`, `implemented`, `superseded`, `expired`, `backtracked` | yes | what the code does |
| `decided_by` | enum, req | `human`, `agent-recommended`, `agent` | no | historical attribution (P5): `human` = the owner made the call; `agent-recommended` = agent proposed, owner accepted in the same conversation; `agent` = agent's own default, nobody looked at the time. Never changes on ratification |
| `recommended_by` | str or null, req | e.g. `claude-code`, `codex`, `human` | no | |
| `ratified_by` | str or null, req | e.g. `@nikita` | yes | must be non-null iff `review_state != unreviewed` (`ratified_fields_inconsistent`) |
| `ratified_at` | datetime or null, req | ISO 8601 UTC `YYYY-MM-DDTHH:MM:SSZ` | yes | same rule |
| `provenance` | map, req | keys below, all present | no | |
| `provenance.authored_by` | enum | `human`, `agent`, `agent-drafted` | no | who wrote the file |
| `provenance.agent` | str or null | `claude-code`, `codex`, ... | no | |
| `provenance.model` | str or null | model id string | no | |
| `provenance.session` | str or null | session id string | no | pointer, not proof (A12) |
| `provenance.prompt_ids` | list[str] | | no | may be empty |
| `provenance.trigger` | enum | `user-prompt`, `hook`, `automation`, `self-initiated` | no | |
| `provenance.source_messages` | list[str] | transcript message uuids | no | may be empty; bonus pointer (A12) |
| `affects` | list[map], req (may be empty) | items `{type: path|package, pattern: str, negate: bool=false}` | no | `path` patterns are forward-slash, repo-relative globs (section 4.4); `package` entries are ignored by the edit hook in this run (P21) |
| `implementation_links` | list[map], req (may be empty) | items `{commit: ^[0-9a-f]{7,40}$, paths: list[str]}` | yes | code to decision, many to many |
| `tags` | list[str], req (may be empty) | `^[a-z0-9-]+$` | no | |
| `reversibility` | enum, req | `two-way-door`, `one-way-door`, `unknown` | no | |
| `blast_radius` | enum, req | `component`, `team`, `cross-team`, `org` | no | |
| `regret_when` | str or null, req | one sentence, 200 chars max | no | |
| `review` | date or null, req | `YYYY-MM-DD` | no | filter key for lint |
| `verify` | list[map], req (may be empty) | items `{id: ^[a-z0-9-]+$, engine: grep, pattern: str, paths: list[str], expect: match|no-match, severity: error|warning}` | no | `engine` allowlist is exactly `[grep]`; `pattern` is a Python `re` regex applied per line; `match` = every file selected by `paths` contains a matching line, `no-match` = no selected file does. Run by `scribe lint` only (P17) |
| `supersedes` | str or null, req | ULID or alias of one existing record | yes | one edge, inverse derived by the indexer; setting it appends history event `supersedes_set` |
| `relates_to` | list[str], req (may be empty) | ULIDs or aliases | no | |
| `history` | list[map], req, at least 1 item | items `{at: datetime, event: enum, by: str, session?: str, commit?: str, field?: str, old?: any, new?: any}` | append only | `event` in `proposed`, `implemented`, `ratified`, `rejected`, `superseded`, `expired`, `backtracked`, `link_added`, `supersedes_set`, `relinked`. First entry MUST be `proposed`. Entries MUST be non-decreasing in `at`. Any entry other than `proposed`, `link_added`, `relinked` MUST carry `field`, `old`, `new` |

Cross-field rules enforced by the validator (error unless stated):

1. `review_state == unreviewed` implies `ratified_by == null` and `ratified_at == null`; the other two states imply both non-null.
2. `effective_state == superseded` implies some other record in the store has `supersedes` pointing at this one (validator warning `superseded_without_successor` when the store is available; the indexer is the authority).
3. `effective_state == backtracked` requires the `## Attempted and failed` body section to be non-empty.
4. `effective_state == implemented` requires `implementation_links` non-empty (warning `implemented_without_links`, because relink can heal it).
5. `supersedes` and every `relates_to` entry MUST resolve to an existing record when validating with a store (`dangling_reference`); a record MUST NOT supersede itself.
6. `review_state in (ratified, rejected)` requires a matching attestation line in `RATIFICATIONS.jsonl` (section 3.7) whose `body_sha256` equals the current body hash (`unattested_review_state`). Skipped with `--no-attestation` for unit fixtures.
7. Unknown top-level keys are an error (`unknown_key`), so typos do not pass silently.

### 3.3 History entries

Shape (YAML flow mappings on one line each, as README 10.2 shows):

```yaml
history:
  - { at: 2026-09-08T20:37:41Z, event: proposed, by: "Nikita Boguslavskii", session: session_01A6tVoZuuWqu56QxEqtAjRw }
  - { at: 2026-09-09T10:02:00Z, event: implemented, by: scribe-post-commit, commit: 3f2a9c1d0e7b, field: effective_state, old: proposed, new: implemented }
  - { at: 2026-09-09T10:02:00Z, event: link_added, by: scribe-post-commit, commit: 3f2a9c1d0e7b, new: { commit: 3f2a9c1d0e7b, paths: ["src/scribe/index.py"] } }
```

`by` is a free string: a person (`"Nikita Boguslavskii"`, `@nikita`), an agent (`claude-code`), or a scribe component (`scribe-post-commit`, `scribe-ratify`, `scribe-relink`, `scribe-lint`). Every scribe command that mutates a record goes through `Record.apply_change`, which is the only code path that appends history, so the rule "every mutation has a history entry" is structural.

### 3.4 Body

After the closing `---`, exactly this sequence; the validator checks presence and order of the H1 and the H2 headings, ignores content except where stated:

```
# <title, must equal front matter title>

> <Y-statement blockquote: In the context of ..., facing ..., I decided ..., to achieve ..., accepting that ...>   (required, one or more `>` lines)

## Question                      (required, non-empty)
## Criteria                      (required, non-empty; QOC: what a good answer had to satisfy)
## Constraints and assumptions   (required, non-empty; assumptions the agent filled in are listed explicitly)
## Options considered            (required; a markdown table with header `| Option | For | Against | Evidence | Why rejected |`, at least 2 data rows, exactly one row marked `chosen` in the last column)
## Decision                      (required, non-empty)
## Consequences                  (required, non-empty)
## Attempted and failed          (optional; required non-empty when effective_state == backtracked)
## Evidence                      (required; MUST contain at least one `>` blockquote line: the decisive user turn quoted verbatim (A12, P18); then pointers: file:line, repo://path#Lx-Ly@sha, message uuids, test output, CI run)
```

No other H2 headings are allowed (`unexpected_section`). H3 and deeper are free. The body is immutable (section 3.1 item 3). The DEMM grade lives outside the record, in `docs/build/01-records-grading.md` (P13).

### 3.5 INDEX.md

Generated by `scribe index` into `docs/decisions/INDEX.md`; `scribe index --check` exits 1 if the file on disk differs from the generated text (used by CI and lint). Layout, exact section names:

```
# Decision index

Generated by `scribe index` from N records. Do not edit by hand.

## Review queue (K)

Ordered: records that supersede a ratified record first, then implemented, then proposed; newest first within each group.

1. [supersedes ratified] D-260910-foo | implemented | unreviewed | agent | supersedes D-260908-bar | <title>
2. D-260909-baz | implemented | unreviewed | agent | <title>
3. D-260909-qux | proposed | unreviewed | agent-recommended | <title>

## Active decisions (M)

D-260908-unreviewed-may-supersede-ratified | proposed | ratified | human | src/scribe/index.py src/scribe/check.py | Unreviewed agent records may supersede ratified ones. Regret: <regret_when>. Review 2026-12-08.

## Retired (R)

D-260908-bar | superseded by D-260910-foo | ratified | human | <title>
D-260901-old | rejected | rejected | agent | <title>
D-260801-stale | expired | unreviewed | agent | <title>
```

Rules:

1. Review queue = every record with `review_state: unreviewed`, regardless of `effective_state`, including superseded ones (a superseded unreviewed record still needs a look). Group 1 = records whose `supersedes` resolves to a record with `review_state: ratified`; they carry the literal marker `[supersedes ratified]` at the start of the line and the text `supersedes <alias>` in the line. Group 2 = `effective_state: implemented`. Group 3 = everything else. Within a group, sort by `date` descending, then alias.
2. Active = records with `effective_state in (proposed, implemented, backtracked)` and `review_state != rejected` and not superseded by any record. The indexer derives "superseded by" from other records' `supersedes` edges, it does not trust `effective_state: superseded` alone; a record that is pointed at but still says `proposed` or `implemented` is listed under Retired with `superseded by <alias>` and lint flags `effective_state_stale`.
3. Retired = superseded (by derived edge), rejected, expired.
4. Line fields: alias, effective state (or `superseded by X`), review state, decided_by, space-joined `affects` path patterns (negated ones prefixed `!`; omitted from Retired lines), title plus `Regret: ...` and `Review YYYY-MM-DD.` when present. One line per record, no wrapping.
5. Output is deterministic (sorted, no timestamps), so the file is stable across machines and `--check` is meaningful.

### 3.6 Parsing and serialization rules

1. Front matter is parsed with `yaml.safe_load`; the body is the text after the closing `---\n`, preserved byte for byte on save (only the front matter is re-serialized).
2. Serialization: `yaml.safe_dump(mapping, sort_keys=False, allow_unicode=True, width=1000)`, with `history`, `affects`, `implementation_links`, `verify` items forced into flow style (one line per item) via a custom representer, so diffs stay one line per event. Dates and datetimes are written as plain ISO strings, not YAML timestamps, to avoid timezone surprises: the loader accepts both and normalizes.
3. Line endings: read tolerant of `\r\n`, write `\n`.
4. `body_sha256` = SHA-256 hex of the body with `\r\n` normalized to `\n` and trailing whitespace stripped from the whole text; this is what attestations pin.

### 3.7 RATIFICATIONS.jsonl

`docs/decisions/RATIFICATIONS.jsonl`, committed, append only, one JSON object per line:

```json
{"id": "01M21BV91NZSW1HMJ127KZAA5J", "alias": "D-260908-unreviewed-may-supersede-ratified", "verdict": "ratified", "by": "@nikita", "at": "2026-09-08T20:37:41Z", "body_sha256": "<hex>", "via": "hand-written", "note": "Interview answer A10"}
```

`verdict` in `ratified`, `rejected`; `via` in `terminal`, `claude-code`, `hand-written` (set by the CLI: `claude-code` when the `CLAUDECODE` environment variable is present, UNVERIFIED that Claude Code sets it; else `terminal`). The latest line for an `id` is authoritative. This file is the "path the agent's deny rules block" (brief, phase 2): `scribe init` adds `Edit(docs/decisions/RATIFICATIONS.jsonl)` and `Write(docs/decisions/RATIFICATIONS.jsonl)` to `permissions.deny` in the target repo's `.claude/settings.json` (rule syntax UNVERIFIED, P8). The validator's rule 6 (section 3.2) makes a record's `review_state` worthless without a matching attestation, so editing the record alone cannot ratify it. What this does not prevent: an agent running `scribe ratify` through Bash; see section 9, R3.

## 4. Hook and skill behaviour

### 4.1 Common mechanics

1. Registration: `hooks/hooks.json` with the shape `{"hooks": {"<Event>": [{"matcher": "<regex>", "hooks": [{"type": "command", "command": "<cmd>", "timeout": <seconds>}]}]}}` (matcher and timeout semantics UNVERIFIED beyond the brief's "hooks in hooks/hooks.json with ${CLAUDE_PLUGIN_ROOT}"; `timeout` assumed to be seconds). Events without tool matchers omit `matcher`.
2. Every command is `uv run --frozen --project "${CLAUDE_PLUGIN_ROOT}" scribe hook <event-name>`. `--frozen` uses the committed `uv.lock` without resolving; the first invocation after install creates `.venv` inside the plugin directory (seconds), later ones start in about 100 to 200 ms (measured in T7's timing test). SessionStart (section 4.3) exists partly to pay that first cost before any edit.
3. Input: JSON on stdin. Fields this plan relies on (UNVERIFIED, standard hook input per Claude Code docs as remembered; the reviewer should confirm names): `session_id`, `cwd`, `hook_event_name`, `transcript_path`; `tool_name` and `tool_input` for PreToolUse (`tool_input.file_path` for Edit and Write, `tool_input.command` for Bash, `tool_input.plan` for ExitPlanMode); `prompt` for UserPromptSubmit; `stop_hook_active` and `last_assistant_message` for Stop. Missing fields never crash a hook: every read is `payload.get(...)`.
4. Output contract. Advisory hooks print either nothing or one JSON object on stdout and exit 0. For PreToolUse injection the object is `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "<block>"}}` (UNVERIFIED that PreToolUse honours `additionalContext`, P19; fallback if the reviewer says no: print the block as plain stdout, which Claude Code shows in verbose mode only, and record the gap). Gates block with exit 2 and the reason on stderr (brief: gates propagate exit 2); in this run they never do (section 4.7).
5. Two dispatcher policies, `src/scribe/hooks/launcher.py`:
   - `run_advisory(fn)`: wraps `fn(payload)` in `try/except BaseException`; on any exception writes one line `scribe: <event> failed: <type>: <msg>` to `.claude/scribe/hook-errors.log` (created if missing, capped at 200 KB by truncating the oldest half) and to stderr only if `SCRIBE_DEBUG=1`, prints nothing to stdout, exits 0. Also exits 0 if stdin is empty or not JSON.
   - `run_gate(fn)`: `fn` returns `Verdict(allow: bool, reason: str)`. If the launcher itself crashes it logs loudly (stderr, always) and exits 0. If `fn` returns deny and `SCRIBE_GATES == "enforce"`, print reason to stderr, exit 2. Otherwise (shadow mode, the default in this run) append the verdict to `.claude/scribe/gate-log.jsonl` and exit 0.
6. Time budget: edit-path hooks (section 4.4) have an internal deadline of 700 ms measured from process start (`time.monotonic()` at import); if record scanning exceeds it, the hook prints nothing and exits 0. hooks.json timeout for them is 3 seconds to absorb the cold-start case without Claude Code killing the hook (behaviour on hook timeout UNVERIFIED; the deadline makes it moot on warm runs). Other advisory hooks: 10 s. SessionStart: 120 s (cold `uv` sync).
7. Repository root: `git -C <cwd> rev-parse --show-toplevel` with `cwd` from the payload (inside a worktree this is the worktree, brief and README 13: hook `cwd` is the worktree, `CLAUDE_PROJECT_DIR` the original checkout). If not a git repo or no `docs/decisions/` directory: hooks do nothing and exit 0. Store path is always `<root>/docs/decisions`.
8. All paths handled internally are POSIX-style strings relative to the repository root; conversion happens once at the boundary (`matching.to_repo_relative`).

### 4.2 Scratch state

`<root>/.claude/scribe/state.json` (P7, README 10.4 last paragraph; `scribe init` adds `.claude/scribe/` to `.gitignore`). Shape:

```json
{
  "version": 1,
  "sessions": {
    "<session_id>": {
      "started_at": "2026-09-08T20:37:41Z",
      "last_prompt_at": "2026-09-08T20:41:00Z",
      "prompt_ids": ["..."],
      "pending_decisions": ["01M21BV91NZSW1HMJ127KZAA5J"],
      "decision_worthy": false
    }
  }
}
```

Written by SessionStart, UserPromptSubmit, `scribe new`; read by `prepare-commit-msg`; pruned by `post-commit` (consumed ids removed) and by every writer (sessions with `last_prompt_at` older than 7 days dropped). Writes go through `state.py` with an exclusive lock (`fcntl.flock` on POSIX, `msvcrt.locking` on Windows, both stdlib) and write-to-temp-then-`os.replace`, so two sessions in one worktree cannot corrupt it. Corrupt JSON is treated as empty state and logged, never raised.

### 4.3 SessionStart and UserPromptSubmit (advisory)

SessionStart (`scribe hook session-start`), P16, not in the brief's phase 2 list but needed by `prepare-commit-msg` for the `Session:` trailer and by the time budget:

1. Ensures `sessions[session_id]` exists with `started_at`.
2. If the repo has a `docs/decisions/` store: counts the review queue and prints `{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "scribe: <K> unreviewed decisions, <J> supersede a ratified one. Run /scribe:lint or open docs/decisions/INDEX.md."}}` when K > 0 (UNVERIFIED output shape for SessionStart; plain stdout is the documented fallback since SessionStart stdout is added to context). Prints nothing when K == 0.
3. Exit 0 always.

UserPromptSubmit (`scribe hook user-prompt-submit`): updates `last_prompt_at`, appends `prompt_id` if present in the payload (field name UNVERIFIED; absent is fine). No stdout. Exit 0.

### 4.4 PreToolUse on Edit and Write: injection (advisory)

Registration: matcher `Edit|MultiEdit|Write` (`MultiEdit` included harmlessly for older versions). Command `scribe hook pre-tool-use-edit`.

Logic:

1. Read `tool_input.file_path`; if missing, exit 0 silently.
2. Resolve repo root from `cwd`; if the store is missing, exit 0.
3. Convert `file_path` to repo-relative POSIX: `os.path.abspath` (relative paths resolved against `cwd`), `os.path.relpath(root)`, backslashes to `/`, strip leading `./`. If the result starts with `..` (file outside the repo), exit 0. On Windows compare case-insensitively (P: best effort).
4. Load front matter only (split at the second `---`, `yaml.safe_load`) for every `docs/decisions/D-*.md`; skip files that fail to parse (log). Do not read bodies.
5. Candidate records: `review_state != rejected`, `effective_state in (proposed, implemented, backtracked)`, and not superseded by another record (derive edges from the loaded set). A record matches when at least one non-negated `affects` entry of `type: path` matches the path and no negated `type: path` entry matches it. `type: package` entries are ignored (P21).
6. Glob semantics (`src/scribe/matching.py`, own translation to `re`, not `fnmatch`): `**` matches any sequence including `/` (so `src/**` matches `src/a.py` and `src/a/b.py`; `**/x.py` matches `x.py` at any depth including root); `*` matches any run of characters except `/`; `?` one character except `/`; `[abc]` and `[!abc]` classes; everything else literal. A pattern containing no `/` matches against the basename at any depth (gitignore convention). Matching is anchored at both ends. Patterns are normalized: backslashes to `/`, leading `./` stripped, leading `/` stripped.
7. Order: ratified first, then unreviewed; within each, implemented before proposed; then by date descending. Cap at 5 records (P: budget).
8. Output block (README 10.2, adr-kit idiom), each record line at most 220 characters, whole block at most 1600 characters:

```
Governing decisions for src/scribe/index.py:
- D-260908-unreviewed-may-supersede-ratified (proposed, ratified by human): Unreviewed agent records may supersede ratified ones. Regret when: <regret_when, truncated to 100 chars>.
- D-260910-foo (implemented, unreviewed, supersedes ratified D-260908-bar): <title>.
These are retrieval candidates, not confirmed matches. If this edit conflicts with one, surface it and ask; do not silently comply or silently violate. Full text: docs/decisions/<alias>.md
```

The `Full text` pointer is one line listing the aliases. Nothing else is printed. If zero records match, print nothing.
9. Exit 0 always. The 700 ms deadline (section 4.1 item 6) is checked after every 20 files; on expiry print nothing.

### 4.5 `scribe validate` (phase 1 CLI, used by everything)

`scribe validate [paths...] [--no-attestation] [--json]`. Default paths: the whole store. Loads each record, runs section 3.2 to 3.4 checks, resolves references against the store, checks attestations. Output: one line per problem `<path>: <severity>: <code>: <message>`, then `N records, E errors, W warnings`. Exit 1 if any error, else 0. Used by `commit-msg`, `scribe check`, `scribe lint`, tests.

### 4.6 `scribe lookup` (phase 1 CLI)

`scribe lookup <sha | ulid | alias>`:

1. If the argument is a commit-ish (`git rev-parse --verify`), print the `Decision:` trailers of that commit resolved to records: `<alias> <ulid> <path> (<review_state>, <effective_state>)`; unknown ids print `UNKNOWN <token>` and set exit 1.
2. Else resolve as ULID or alias; print the record path, then every commit whose trailers reference it: `git log --format=%H%x09%s --grep="<ulid>" --grep="<alias>"`, filtered by parsing trailers of each hit (grep is a prefilter, trailers are the truth), plus `implementation_links` from the record, marking links that are not in git history with `(not in this history)`.
3. Exit 0 when found, 1 when not.

### 4.7 PreToolUse on ExitPlanMode and Bash: gates, shadow mode (phase 3 scaffold)

Registration: two entries, matcher `ExitPlanMode` and matcher `Bash`, both running `scribe hook gate`. Wrapped by `run_gate`.

1. Bash denylist, `src/scribe/policy.py`, a list of `(name, compiled regex)` over `tool_input.command`, evaluated after collapsing whitespace: `git push --force` and `git push -f` (not `--force-with-lease`), `git branch -D`, `git reset --hard` combined with `origin`, `rm -rf` whose target is not under `cwd` (paths starting with `/`, `~`, `..`), `alembic upgrade|downgrade`, `prisma migrate deploy`, `flyway migrate`, `terraform apply|destroy`, `kubectl apply|delete`, `helm install|upgrade`, `docker push`, `npm publish`, `cargo publish`, `twine upload`, `uv publish`, `gh release create`, `gh pr merge`, `curl|wget|http` with `-X (POST|PUT|PATCH|DELETE)` or `--data`. The list is data in one place so the owner can edit it; the README documents it.
2. Verdict for Bash: if any regex matches and no record with `review_state: ratified` and `reversibility: one-way-door` has `affects` containing `{type: action, pattern: <name>}` (a third `affects` type reserved for this, accepted by the validator but unused elsewhere in this run) then deny with reason `scribe: '<name>' is on the irreversible-action denylist; record it with /scribe:decide (reversibility: one-way-door) and get it ratified before running it`. Else allow.
3. ExitPlanMode policy: `tool_input.plan` text (field UNVERIFIED) is scanned for the README 10.4 policy areas by keyword lists (`dependency`, `add package`, `public API`, `schema`, `migration`, `storage`, `concurrency`, `thread`, `safety`, `interface`, `deviat`); if any hit and the current session has no `pending_decisions` in scratch state, verdict is deny with reason `scribe: plan touches <areas>; run /scribe:decide before leaving plan mode`. Else allow.
4. In this run both verdicts are logged to `.claude/scribe/gate-log.jsonl` as `{"at", "event", "tool", "verdict", "reason", "command_head" (first 80 chars)}` and the hook exits 0. `SCRIBE_GATES=enforce` flips to exit 2; only tests set it. This shadow log is the "measure frequency before adding anything heavier" the owner asked for (A13).

### 4.8 TaskCompleted and Stop: reconcile, shadow mode (phase 3 scaffold)

Registration: `TaskCompleted` and `Stop`, both `scribe hook reconcile`, wrapped by `run_gate` (TaskCompleted is a gate in the design) and `run_advisory` (Stop) respectively.

1. TaskCompleted: if `sessions[session_id].decision_worthy` is true and `pending_decisions` is empty, verdict deny with reason `scribe: task flagged decision-worthy but no record was written`; logged, exit 0 in this run. Payload fields beyond `session_id` are not relied on.
2. Stop: if `stop_hook_active` is true, exit 0 immediately (re-entry guard). Otherwise append `{"at", "session_id", "pending_decisions", "has_last_message": bool}` to `.claude/scribe/gate-log.jsonl`. No stub record is written in this run (README 10.4 Stop row is deferred: writing records from `last_assistant_message` needs the two-worktree test first). Exit 0.

### 4.9 `/scribe:decide` skill and `scribe new`

`skills/decide/SKILL.md` front matter: `name: decide`, `description: Record a decision before the first implementing edit; writes docs/decisions/<alias>.md with review_state unreviewed and registers it for the next commit's Decision trailer.` (SKILL.md front matter keys beyond `name` and `description` UNVERIFIED; use only those two.)

Skill body instructs the agent to:

1. Fill a JSON spec (schema below) from the conversation, quoting the decisive user turn verbatim into `evidence_quote`; if there is no user turn (self-initiated), say so in the quote field as `(no user turn; self-initiated)` and set `trigger: self-initiated`.
2. Run `uv run --frozen --project "${CLAUDE_PLUGIN_ROOT}" scribe new --spec <tmpfile.json>` (UNVERIFIED that `${CLAUDE_PLUGIN_ROOT}` is available to Bash commands issued from a skill; fallback documented in the skill: `uv run --project ~/scribe`, and T8 must print the resolved path in `scribe --version` output to make this debuggable).
3. Read the printed path and confirm the record in one line to the user.
4. One-way-door rule (A13): if `reversibility: one-way-door`, do not stop; leave `review_state: unreviewed`, continue with independent work, and at the end of the run list every pending one-way-door alias in a single `**Next:**` block for the owner. Block early only when the remaining work depends on it. Never run the denied action.
5. Supersede rule (A10): when a new decision replaces an existing record, set `supersedes` to that alias, even if the old one is ratified; the indexer will put it at the top of the review queue.

`scribe new --spec <file> [--by <name>] [--session <id>] [--register]`: spec JSON keys mirror the front matter minus generated ones (`id`, `alias`, `date`, `schema_version`, `review_state`, `effective_state`, `ratified_*`, `implementation_links`, `history`) plus body fields `question`, `criteria`, `constraints`, `options` (list of `{option, for, against, evidence, why_rejected, chosen: bool}`), `decision`, `consequences`, `attempted_and_failed` (optional), `evidence_quote`, `evidence_pointers` (list of str), `y_statement`. Behaviour: generate ULID, build alias from `date` (today UTC) and a slug from `title` (lowercase ASCII, non-alphanumerics to hyphens, collapsed, trimmed to 40 chars, `-2`, `-3` appended on collision), render the body from `record_template.md`, write with `review_state: unreviewed`, `effective_state: proposed`, one `proposed` history entry (`by` = `--by` or `provenance.agent`, `session` = `--session` or `CLAUDE_SESSION_ID` env if present, UNVERIFIED, else omitted), validate (refuse to write an invalid record, print problems, exit 1), regenerate `INDEX.md`, and if `--register` (the skill always passes it) append the ULID to `sessions[<session>].pending_decisions` in scratch state (creating the session entry when the id is known; when no session id is known, use the key `"unknown"`, which `prepare-commit-msg` also reads). Print the path. Exit 0.

### 4.10 `/scribe:ratify`, `/scribe:reject`, `scribe ratify`, `scribe reject`

Skills: `name: ratify` / `name: reject`; description states "human only: run this yourself, the agent must not invoke it". Body: parse `<alias-or-ulid> [note...]` from the arguments, run `scribe ratify <id> --by <handle> --note "<note>"` (or `reject`), where `<handle>` is `@` plus `git config user.name` lowercased first token unless the user gave one, then show the record's new `review_state` line and the INDEX review queue count.

CLI `scribe ratify <id> [--by <who>] [--note <text>] [--at <iso>]`:

1. Resolve the record; refuse (exit 1) if `review_state` is already `ratified`.
2. Set `review_state: ratified`, `ratified_by`, `ratified_at` (now UTC or `--at`) through `apply_change`, three history entries (`event: ratified`, one per field, or one entry with `field: review_state` plus the other two as `field` entries; choose one entry per field for event-log friendliness).
3. Append the attestation line to `RATIFICATIONS.jsonl` (section 3.7) with the body hash after the mutation (the body does not change, so before and after are equal).
4. Regenerate `INDEX.md`. Print `ratified <alias> by <who>`. Exit 0.

`scribe reject` is identical with `verdict: rejected`, `review_state: rejected`, and additionally sets nothing on `effective_state` (a rejected record that was already implemented stays `implemented` and shows in the Retired section, so lint rule `rejected_but_implemented` can flag it for backtracking).

### 4.11 `/scribe:init`

Skill: `name: init`; body runs `scribe init [--force] [--hooks-dir <path>]` in the current repository and prints what was written and the follow-up steps (commit the workflow, add branch protection). Behaviour is in section 5.5.

### 4.12 `/scribe:lint` and `scribe lint`

Skill: `name: lint`; body runs `scribe lint` and, if there are unreviewed records, presents the review queue as a numbered list and offers to walk the owner through them one at a time (ask, do not act; the interview itself is out of scope, README 10.3 "keep the interview outside the autonomous hook path").

`scribe lint [--base <ref>] [--expire] [--json]`: runs `validate`, `index --check`, and these rules; prints problems in the validate format; exit 1 on any error, 0 otherwise.

| Code | Severity | Rule |
|---|---|---|
| `duplicate_alias` | error | two files share an alias or an id |
| `alias_filename_mismatch` | error | from validate |
| `immutable_changed` | error | for records present at `--base` (default: `origin/main` if it exists, else `HEAD~1`, else skipped), any immutable key or the body differs from `git show <base>:<path>` |
| `history_rewritten` | error | the base version's `history` list is not a prefix of the current one |
| `dangling_reference` | error | from validate |
| `unattested_review_state` | error | from validate |
| `index_stale` | error | `INDEX.md` differs from generated |
| `effective_state_stale` | warning | pointed at by a `supersedes` edge but not marked `superseded` |
| `rejected_but_implemented` | warning | `review_state: rejected` and `effective_state: implemented` and not superseded or backtracked |
| `review_overdue` | warning | `review` date in the past and record active |
| `unreviewed_implemented` | info | active, implemented, unreviewed (they never expire; they escalate in the index) |
| `proposal_stale` | warning | `proposed`, `unreviewed`, no `implementation_links`, `date` older than 30 days; with `--expire` the record is set to `effective_state: expired` via `apply_change` (`by: scribe-lint`) |
| `verify_failed` | error or warning per entry | run each `verify` entry: select files by `paths` globs (section 4.4 semantics, relative to root, excluding `.git/`), apply the regex per line; report per entry; an unreadable file is `verify_error` (error), distinct from no-match |
| `duplicate_pending` | info | scratch state holds ids that resolve to no record (pruned automatically) |

### 4.13 Skills that are agent-facing versus human-facing

`decide` and `lint` are for the agent and the owner alike. `ratify`, `reject`, `init` are for the owner. Nothing technical prevents the agent from invoking them (section 9, R3); the deny rule on the attestation file and the `via` tag are the guards in this run.

## 5. Git hooks installed by `/scribe:init` and the CI check

All three git hooks are installed as executable Python shim files (P12, no bash):

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

The shim runs under the system `python3` (3.10 is enough for the shim; the plugin code itself runs under uv's 3.12). If `uv` is missing the hook prints one line and exits 0 (fail open). `scribe git-hook <name>` entrypoints exit 0 on every failure in this run (all three are advisory per README 10.4, `commit-msg` is warn only for now). `PLUGIN_ROOT` is `Path(scribe.__file__).resolve().parents[2]` at init time, so it points at whatever checkout or plugin install ran `init`.

### 5.1 `prepare-commit-msg`

Arguments: `<msg-file> [<source> [<sha>]]`. Behaviour:

1. Exit 0 without changes when `source` is `merge`, `squash`, or `commit` with a `sha` (amend and `-c`/`-C`: the trailers already there are kept; new ones are still added, see step 5), or when `SCRIBE_SKIP_HOOKS=1`.
2. Repo root = `git rev-parse --show-toplevel`; no store, exit 0.
3. Staged paths: `git diff --cached --name-only --diff-filter=ACMR`, POSIX relative.
4. Candidate decision ids, deduplicated, in this order:
   a. Every staged path under `docs/decisions/D-*.md`: the record's own id (this is how a commit that adds or updates a record carries its trailer, and how the three hand-written records get theirs).
   b. Every id in `pending_decisions` of every session in scratch state (all sessions, because the commit may be made by a different session than the one that decided) whose record exists and whose `affects` is either empty or matches at least one staged path (README 10.4: select only decisions whose `affects` overlap the staged paths so stale ids cannot satisfy validation; empty `affects` is treated as "no scope claim", included, and consumed by `post-commit`).
5. For each id: `git interpret-trailers --in-place --if-exists addIfDifferent --trailer "Decision: <alias> <ulid>" <msg-file>` (trailer format P6: alias for humans reading `git log`, ULID as the identity; the lookup accepts either token alone for hand-written trailers).
6. `Session:` trailer: if the message already has a `Claude-Session:` or `Session:` trailer, skip. Else pick the session in scratch state with the latest `last_prompt_at` (or `started_at`) and add `--trailer "Session: <session_id>"`. If scratch state has no session, skip.
7. Never fail the commit: any exception is logged to `.claude/scribe/hook-errors.log`, exit 0.

Interaction with `/commit` and the `Co-Authored-By` / `Claude-Session` trailers the owner's workflow already adds: `interpret-trailers` appends after existing trailers; `addIfDifferent` prevents duplicates when the hook runs twice.

### 5.2 `commit-msg` (warn only in this run)

Argument: `<msg-file>`. Reads trailers from the file with `git interpret-trailers --parse`. Checks, each printing `scribe: warning: ...` to stderr:

1. Every `Decision:` value resolves (by ULID, by alias, or both; if both are present and disagree, warn `alias/ulid mismatch`).
2. Each resolved record passes `validate` (errors listed).
3. A referenced record has `review_state: rejected`.
4. Staged paths match the `affects` of at least one active record and the message carries no `Decision:` trailer at all (`governed paths changed without a decision link`).
5. A staged record has `review_state != unreviewed` without an attestation (this is the "agent ratified itself" tell).
6. A staged record has `review_state: unreviewed` and `supersedes` a ratified record: print `scribe: notice: <alias> supersedes ratified <alias>; the CI check will block merge until it is reviewed` (README 10.4: the local hook only warns for this case).

Exit 0 always in this run. A later run flips checks 1, 2 and 5 to exit 1 (`SCRIBE_COMMIT_MSG=enforce` is honoured already, tests use it).

### 5.3 `post-commit`

No arguments. Behaviour:

1. Guard: `SCRIBE_SKIP_HOOKS=1` or the environment variable `SCRIBE_IN_POST_COMMIT=1` (set by the hook itself before touching git) exits 0, so an accidental nested commit cannot recurse.
2. `sha = git rev-parse HEAD` (12 chars stored), trailers from `git log -1 --format=%(trailers:key=Decision,valueonly)`, changed paths from `git diff-tree --no-commit-id --name-only -r HEAD` (for the root commit use `git show --name-only --format= HEAD`).
3. For each resolved record: `code_paths` = changed paths not under `docs/decisions/`. If `code_paths` is non-empty: append `{commit: sha, paths: code_paths}` to `implementation_links` unless a link with that sha exists (idempotent under amend), history `link_added`; if `effective_state == proposed`, set `implemented` with history (P15: a commit that only adds or edits the record itself does not implement it). If `code_paths` is empty, do nothing to the record.
4. Save records (the change lands in the next commit, by design: README 10.4), regenerate `INDEX.md`, remove the consumed ids from every session's `pending_decisions`.
5. Print `scribe: linked <n> record(s) to <sha>; run git add docs/decisions to include the backlinks in your next commit` to stderr when n > 0. Exit 0 always.

Amend and rebase: SHAs change and the stale link stays in the record. `scribe relink [--since <ref>]` (T15) walks `git log --format=%H` (or since a ref), parses trailers, and rebuilds every record's `implementation_links` from scratch: links whose commit is still reachable are kept, links whose commit is gone are dropped, missing ones added; one history entry `relinked` per changed record. `scribe lint` suggests `relink` when a link's commit is unreachable. No `post-rewrite` hook in this run (section 9, R5).

### 5.4 CI check: `scribe check` and `scribe-check.yml`

`scribe check --base <ref>` exit 1 (with reasons on stdout) when any of these hold for records added or modified between `<ref>` and `HEAD` (`git diff --name-only <ref>...HEAD -- docs/decisions/`), else exit 0 with `scribe check: ok`:

1. A changed record has `review_state: unreviewed` and its `supersedes` resolves to a record whose `review_state` is `ratified` in the base tree or in HEAD (P10: scope is records introduced or modified in the branch, so a pre-existing case on main does not fail every PR; the owner's branch protection makes this the merge gate, A11).
2. A changed record fails `validate` (including `unattested_review_state`).
3. `INDEX.md` is stale (`index --check`).
4. `RATIFICATIONS.jsonl` lost or altered a line present in the base (append-only check: base content must be a prefix of HEAD content).

Ordinary unreviewed records do not fail the check (README 10.4).

Workflow dropped by `init` at `.github/workflows/scribe-check.yml`:

```yaml
name: scribe-check
on:
  pull_request:
jobs:
  scribe-check:
    runs-on: ubuntu-latest
    env:
      SCRIBE_SOURCE: git+https://github.com/OWNER/scribe@v0.1.0   # edit once the scribe repo exists (P11)
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: astral-sh/setup-uv@v6        # tag UNVERIFIED, use the latest major
      - run: uvx --from "$SCRIBE_SOURCE" scribe check --base "origin/${{ github.base_ref }}"
```

Until the scribe repository is on GitHub, `SCRIBE_SOURCE` cannot resolve; the workflow file is still dropped so the owner can wire branch protection to the job name `scribe-check`, and the same command runs locally as `uv run --project ~/scribe scribe check --base origin/main`. Alternative considered and rejected for now: vendoring a standalone checker script into the target repo (duplicate code that drifts).

### 5.5 `scribe init [--force] [--hooks-dir <path>]`

1. Root = `git rev-parse --show-toplevel`; refuse outside a repo.
2. Hooks directory: `git rev-parse --git-path hooks` (correct inside linked worktrees, where hooks live in the main `.git`). If `git config core.hooksPath` is set (husky, lefthook, pre-commit) and `--hooks-dir` was not given: print the path and the manual chaining line (`uv run --project <PLUGIN_ROOT> scribe git-hook <name> "$@"`), install nothing into hooks, exit 1. With `--hooks-dir`, install there.
3. For each of `prepare-commit-msg`, `commit-msg`, `post-commit`: if the file does not exist, write the shim, `chmod 0o755`. If it exists and contains the marker `# scribe-managed`, overwrite. If it exists without the marker: skip with `scribe: existing <name> hook kept; use --force to replace (a backup <name>.pre-scribe is written)`; with `--force`, rename the old file to `<name>.pre-scribe` and write the shim. Exit code 0 unless a foreign hook was skipped (exit 1, so the owner notices).
4. `.gitignore`: append `.claude/scribe/` if not present (create the file if missing).
5. `.github/workflows/scribe-check.yml`: write if missing or scribe-managed (first line comment `# scribe-managed v1`); otherwise skip unless `--force`.
6. `.claude/settings.json`: read (create `{}` if missing), ensure `permissions.deny` contains `Edit(docs/decisions/RATIFICATIONS.jsonl)` and `Write(docs/decisions/RATIFICATIONS.jsonl)` (syntax UNVERIFIED), write back with 2-space indent preserving other keys. Skip with a message if the file is not valid JSON.
7. `docs/decisions/`: create if missing, with an empty `RATIFICATIONS.jsonl` and a generated `INDEX.md`.
8. Print a summary of every path written, kept, or skipped, and the two follow-ups: commit the new files; add branch protection requiring the `scribe-check` job.
9. Idempotent: a second run changes nothing and prints `unchanged` for each path.

## 6. Task list for the implementer

Each task is self-contained given this plan and the repo. "AT" = acceptance test, run from `/home/alfakentavr/scribe`. Size: S under 1 hour, M 1 to 3 hours, L over 3 hours for one gpt-5.6-sol subagent. Tasks are ordered so `uv run pytest` is green after each one. Every task adds its tests under `tests/` and, when it makes a non-trivial choice the plan left open, appends a `P` item to `AUTONOMOUS_DECISIONS_09_08_2026.md`.

### T1 Project skeleton (S)
Files: `pyproject.toml`, `.python-version`, `uv.lock`, `src/scribe/__init__.py`, `__main__.py`, `cli.py` (subparser scaffold, `--version` prints `scribe 0.1.0 (<resolved plugin root>)`), `tests/conftest.py` (fixtures `tmp_repo`, `run_cli`), `tests/test_cli.py`, `.gitignore` update, `README.md` stub (title, one-paragraph purpose, install line).
Behaviour: `pyproject.toml` with `[project] name = "scribe"`, `version = "0.1.0"`, `requires-python = ">=3.11"`, `dependencies = ["pyyaml>=6.0"]`, `[dependency-groups] dev = ["pytest>=8"]`, `[project.scripts] scribe = "scribe.cli:main"`, `[build-system]` hatchling or setuptools with `src` layout, `[tool.pytest.ini_options] testpaths = ["tests"]`. `uv lock` produces `uv.lock` (network needed once; if unavailable, log it and leave the lock for step 5).
AT: `uv run scribe --version` prints `scribe 0.1.0 (/home/alfakentavr/scribe)`; `uv run pytest -q` reports 1 passed.
Deps: none.

### T2 ULID, front matter, schema, validator (M)
Files: `src/scribe/ulid.py`, `frontmatter.py`, `schema.py`, `record.py`, `store.py` (minimal: iterate and resolve), `cli.py` (`validate`), `tests/test_ulid.py`, `test_frontmatter.py`, `test_schema.py`, `tests/fixtures/records/{valid_minimal.md, bad_ulid.md, missing_evidence_quote.md, unknown_key.md, ratified_without_attestation.md}`.
Behaviour: sections 3.1 to 3.4, 3.6, 3.7 (attestation lookup), 4.5. `Record.apply_change` implemented here with history append; `body_sha256` here.
AT: `uv run scribe validate docs/decisions` prints `3 records, 0 errors, 0 warnings` (the hand-written records and `RATIFICATIONS.jsonl` already exist; if the validator disagrees with them, the implementer fixes the validator or reports the record defect in the decisions file, never edits the records' bodies); `uv run scribe validate tests/fixtures/records/bad_ulid.md` exits 1 with `invalid_ulid`; `uv run pytest -q` green.
Deps: T1.

### T3 Repo root, store, affects matcher (S)
Files: `src/scribe/store.py` (full), `gitutil.py` (toplevel, staged paths), `matching.py`, `tests/test_matching.py` (table-driven, at least 20 cases including `**`, basename patterns, negation, backslash normalization, outside-repo path).
AT: `uv run pytest tests/test_matching.py -q` green; `uv run python -c "from scribe.matching import matches; assert matches('src/**', 'src/a/b.py'); assert not matches('src/*.py', 'src/a/b.py'); assert matches('*.sql', 'db/x.sql')"`.
Deps: T2.

### T4 INDEX.md generator (M)
Files: `src/scribe/index.py`, `cli.py` (`index`, `index --check`), `tests/test_index.py` (fixture store with one supersedes-ratified case, one implemented unreviewed, one proposed, one rejected, one expired), `docs/decisions/INDEX.md` (generated, committed).
Behaviour: section 3.5.
AT: `uv run scribe index && uv run scribe index --check` exits 0; `docs/decisions/INDEX.md` contains `## Review queue (0)` and `## Active decisions (3)` with the three aliases; the test asserts the `[supersedes ratified]` line is first in the queue.
Deps: T2, T3.

### T5 Reverse lookup (S)
Files: `src/scribe/lookup.py`, `gitutil.py` (trailer parsing via `git interpret-trailers --parse` and `git log --format=%(trailers:...)`), `cli.py` (`lookup`), `tests/test_lookup.py` (tmp repo, commit with `Decision:` trailer in alias-only, ulid-only, and both forms).
Behaviour: section 4.6.
AT: in the test repo, `scribe lookup <sha>` prints the record alias; `scribe lookup <alias>` prints the commit; unknown token exits 1.
Deps: T2, T3.

### T6 Plugin manifest, hooks.json, launcher, session hooks, scratch state (M)
Files: `.claude-plugin/plugin.json`, `hooks/hooks.json` (all events of sections 4.3, 4.4, 4.7, 4.8 registered now; the edit and gate commands may point at entrypoints that T7 and T14 fill, so T6 ships them as no-op `run_advisory` stubs that exit 0), `src/scribe/hooks/launcher.py`, `session_start.py`, `user_prompt_submit.py`, `state.py`, `cli.py` (`hook <event>` dispatch), `tests/fixtures/hooks/{session_start.json, user_prompt_submit.json, malformed.txt}`, `tests/test_hook_launcher.py`, `test_hook_session.py`.
Behaviour: sections 4.1 to 4.3. `plugin.json`: `{"name": "scribe", "version": "0.1.0", "description": "Records agent decisions, links them to code, injects them before edits, queues them for human ratification.", "author": {"name": "Nikita Boguslavskii"}}` (extra keys UNVERIFIED, keep to these).
AT: `python3 -m json.tool .claude-plugin/plugin.json hooks/hooks.json` both succeed; `cat tests/fixtures/hooks/user_prompt_submit.json | uv run scribe hook user-prompt-submit` exits 0 with empty stdout and `.claude/scribe/state.json` gains the session; `printf 'garbage' | uv run scribe hook session-start` exits 0 silently; every command string in hooks.json starts with `uv run --frozen --project "${CLAUDE_PLUGIN_ROOT}" scribe hook ` (asserted by a test).
Deps: T1, T3.

### T7 PreToolUse injection hook (M)
Files: `src/scribe/hooks/pre_tool_use_edit.py`, `tests/fixtures/hooks/{pre_tool_use_edit_match.json, pre_tool_use_edit_nomatch.json, pre_tool_use_write_outside_repo.json}`, `tests/test_hook_injection.py`, `tests/test_timing.py`.
Behaviour: section 4.4.
AT: with the fixture pointing at `<tmp_repo>/src/scribe/index.py` and the three real records copied into the tmp store, stdout is a JSON object whose `additionalContext` contains `D-260908-unreviewed-may-supersede-ratified` and the sentence `These are retrieval candidates`; the no-match fixture gives empty stdout; both exit 0; `test_timing.py` generates 100 records and asserts wall time of the subprocess under 1.0 s on a warm venv (skip with a clear reason if `uv` is absent).
Deps: T6, T3.

### T8 `scribe new` and the decide skill (M)
Files: `src/scribe/newrecord.py`, `templates/record_template.md`, `cli.py` (`new`), `skills/decide/SKILL.md`, `tests/test_new.py`, `tests/fixtures/new_spec.json`.
Behaviour: section 4.9.
AT: `uv run scribe new --spec tests/fixtures/new_spec.json --register --session test-session` inside a tmp repo creates `docs/decisions/D-<today>-<slug>.md` that passes `validate`, regenerates `INDEX.md` with the alias in the review queue, and `state.json` lists the ULID under `sessions.test-session.pending_decisions`; running the same spec twice yields `<slug>-2`.
Deps: T2, T4, T6.

### T9 Ratify and reject (M)
Files: `src/scribe/ratify.py`, `cli.py` (`ratify`, `reject`), `skills/ratify/SKILL.md`, `skills/reject/SKILL.md`, `tests/test_ratify.py`.
Behaviour: section 4.10 and validator rule 6 end to end.
AT: in a tmp repo with an unreviewed record, `uv run scribe ratify <alias> --by @tester --note t` sets `review_state: ratified`, appends 3 history entries and one JSONL line; `validate` passes; then hand-editing another record to `review_state: ratified` without an attestation makes `validate` exit 1 with `unattested_review_state`; `ratify` on an already ratified record exits 1.
Deps: T2, T4.

### T10 Git hooks: prepare-commit-msg, commit-msg, post-commit (L)
Files: `src/scribe/githooks/{prepare_commit_msg.py, commit_msg.py, post_commit.py}`, `cli.py` (`git-hook <name>`), `gitutil.py` (interpret-trailers, diff-tree), `tests/test_githooks.py`.
Behaviour: sections 5.1 to 5.3. Tests install the entrypoints directly as hook files pointing at the test's own interpreter (`sys.executable -m scribe git-hook <name>`), so they do not need the shim or `uv` at test time.
AT: in a tmp repo: (a) commit a new record file: the commit message gains `Decision: <alias> <ulid>`; (b) register a pending id with `affects: src/**`, stage `src/x.py`, commit: trailer added, `post-commit` sets `effective_state: implemented`, adds one `implementation_links` item, removes the pending id; (c) stage a `.md` outside `affects`, commit: no trailer; (d) `git commit --amend --no-edit`: no duplicate trailer, no duplicate link; (e) message with `Claude-Session:` present: no `Session:` added; (f) `commit-msg` with an unknown decision prints `scribe: warning` to stderr and the commit succeeds; with `SCRIBE_COMMIT_MSG=enforce` it fails.
Deps: T5, T6 (state), T9 (attestation check in commit-msg).

### T11 `scribe init` and the init skill (M)
Files: `src/scribe/init_repo.py`, `templates/githook_shim.py`, `templates/scribe-check.yml`, `cli.py` (`init`), `skills/init/SKILL.md`, `tests/test_init.py`.
Behaviour: section 5.5 and the shim in section 5.
AT: in a tmp repo, `uv run scribe init` writes three executable hooks containing `# scribe-managed`, appends `.claude/scribe/` to `.gitignore`, writes the workflow and `.claude/settings.json` with the two deny rules; a second run prints `unchanged` for every path and changes no file (compare mtimes or hashes); with a pre-existing foreign `commit-msg` the run exits 1 and keeps it, `--force` replaces it and leaves `commit-msg.pre-scribe`; with `core.hooksPath` set the run exits 1 with the chaining instructions; the installed shim, executed with `PLUGIN_ROOT` set to the repo, runs the real hook (one end-to-end commit).
Deps: T10.

### T12 CI check (M)
Files: `src/scribe/check.py`, `cli.py` (`check`), `tests/test_check.py`.
Behaviour: section 5.4.
AT: tmp repo: `main` has a ratified, attested record A; branch `feat` adds unreviewed record B with `supersedes: <A alias>` and regenerates INDEX; `uv run scribe check --base main` exits 1 and prints `B supersedes ratified A`; after `scribe ratify B`, exit 0; a branch adding a plain unreviewed record exits 0; a branch that deletes a line from `RATIFICATIONS.jsonl` exits 1.
Deps: T4, T9.

### T13 Lint and the lint skill (M)
Files: `src/scribe/lint.py`, `cli.py` (`lint`), `skills/lint/SKILL.md`, `tests/test_lint.py`.
Behaviour: section 4.12.
AT: fixtures trigger each rule once and the test asserts the code; `uv run scribe lint` on this repo exits 0 once T4's INDEX exists and the three records' `verify` entries pass (they reference source files created by T4, T12, T14, so run this AT again after T14: until then `verify_failed` for `SCRIBE_GATES` is expected and the test for the real repo is marked to run only after T14); `--expire` on a 40-day-old proposed fixture sets `expired` with a history entry.
Deps: T4, T5, T9.

### T14 Phase 3 gate scaffolds (M)
Files: `src/scribe/policy.py`, `hooks/pre_tool_use_gate.py`, `hooks/reconcile.py`, `tests/fixtures/hooks/{gate_bash_force_push.json, gate_bash_safe.json, gate_exit_plan_mode.json, task_completed.json, stop.json, stop_active.json}`, `tests/test_hook_gate.py`.
Behaviour: sections 4.7, 4.8.
AT: force-push fixture: exit 0, `gate-log.jsonl` gains a `deny` line; same with `SCRIBE_GATES=enforce`: exit 2, stderr contains `irreversible-action denylist`; `git push --force-with-lease` fixture: allow; ExitPlanMode fixture mentioning `add package` with empty pending decisions: `deny` logged, exit 0; `stop_active.json` (`stop_hook_active: true`): exit 0, no log line; `uv run scribe lint` on this repo now exits 0 (A13's `verify` entry finds `SCRIBE_GATES`).
Deps: T6.

### T15 Relink, marketplace, own CI, README, dogfood init (M)
Files: `src/scribe/relink.py`, `cli.py` (`relink`), `tests/test_relink.py`, `.claude-plugin/marketplace.json` (`{"name": "scribe", "owner": {"name": "Nikita Boguslavskii"}, "plugins": [{"name": "scribe", "source": "./", "description": "..."}]}`, key set UNVERIFIED), `.github/workflows/ci.yml` (checkout, setup-uv, `uv sync --frozen`, `uv run pytest -q`), `README.md` (full: install with `claude --plugin-dir ~/scribe` then `/reload-plugins`, CLI table, record format summary linking `docs/build/01-plan.md` section 3, denylist, fail-open policy, Windows caveats), then run `uv run scribe init` on this repo (writes `.git/hooks/*`, `.claude/settings.json`, `.github/workflows/scribe-check.yml`, `.gitignore` line).
AT: `uv run pytest -q` green; `python3 -m json.tool .claude-plugin/marketplace.json`; `ls -l .git/hooks/prepare-commit-msg` shows the scribe shim; `uv run scribe check --base HEAD~1` exits 0; `uv run scribe relink` on a tmp repo after `git commit --amend` replaces the stale sha and adds one `relinked` history entry.
Deps: T10, T11, T12.

### T16 Deferred tests, timing, final sweep (S)
Files: `tests/test_deferred_worktrees.py` (one test with `@pytest.mark.skip(reason="deferred: two-worktree supersede test, enable before turning any gate to enforce")` whose body already contains the scenario of section 7.4 so it can be un-skipped later), `tests/test_timing.py` (extend: SessionStart under 2 s warm), `README.md` (test section), `AUTONOMOUS_DECISIONS_09_08_2026.md` (implementer's P items consolidated).
AT: `uv run pytest -q` prints `N passed, 1 skipped`; `uv run scribe lint` exits 0; `uv run scribe index --check` exits 0; `git status --short` shows only intended files (the `.venv/`, `.claude/scribe/` are ignored).
Deps: all.

## 7. Test strategy

1. Layout: `tests/` flat, one file per module as listed in section 2, fixtures under `tests/fixtures/`. `tests/conftest.py` provides `tmp_repo` (a `git init`ed temp dir with `user.name`, `user.email`, `commit.gpgsign=false`, `core.hooksPath` unset, a `docs/decisions/` with the three real records copied in and their `RATIFICATIONS.jsonl`), `run_cli(args, cwd, env)` (invokes `scribe.cli.main` in-process for speed and captures stdout, stderr, exit code), `run_hook(event, payload_dict, cwd, env)` (subprocess `sys.executable -m scribe hook <event>` with the JSON on stdin, returns `(code, stdout, stderr)`; subprocess rather than in-process so exit codes and the launcher's crash handling are exercised for real), and `write_record(store, **overrides)` that builds a valid record from a template so each test changes only the field under test.
2. Hooks are tested by feeding stdin JSON fixtures and asserting stdout (parsed as JSON when non-empty), stderr and exit code. Every hook has at least: a happy path, a malformed stdin case (exit 0, empty stdout), and a missing-store case (exit 0, empty stdout). Gates additionally run with `SCRIBE_GATES=enforce` to prove the exit 2 path exists.
3. Git hooks are tested with real `git` in `tmp_repo`, installing the entrypoints as hook files that call `sys.executable -m scribe git-hook <name>` (no `uv`, no shim), plus one shim test in T11 that sets `PLUGIN_ROOT` to the repo and requires `uv` on PATH (skipped if absent).
4. Deferred: two-worktree supersede test (T16 stub). Scenario: worktree A ratifies record X on `main`; worktree B (branch `feat`) writes record Y with `supersedes: X` via `scribe new`, commits; `scribe index` in B shows Y at the top of the review queue with `[supersedes ratified]` and X under Retired; `scribe check --base main` in B exits 1; merging `feat` into `main` in A after `scribe ratify Y` passes `check`; the PreToolUse injection for a path in X's `affects` returns Y, not X, in B and still X in A before the merge. Enable before any gate is switched to enforce.
5. Timing: `tests/test_timing.py` asserts the injection subprocess completes under 1.0 s with 100 records on a warm venv, and prints the measured time so step 5 can record it.
6. Single command for everything: `uv run pytest` (equivalently `uv run pytest -q` for terse output). CI runs the same in `.github/workflows/ci.yml`. No test touches the network or the user's home directory; `HOME` is pointed at a temp dir in `conftest.py` for hook tests so `~/.claude` is never read.

## 8. Dogfooding

1. The three hand-written records in `docs/decisions/` are scribe's first ledger; they are `review_state: ratified` (owner decisions of 2026-09-08, attested in `RATIFICATIONS.jsonl` with `via: hand-written`) and `effective_state: proposed` until code lands.
2. Mapping to implementing tasks, so the right commits carry the right trailers: A10 (`D-260908-unreviewed-may-supersede-ratified`) is implemented by T4 (review queue ordering and marker) and T12 (CI check); A13 (`D-260908-one-way-door-defer-not-stop`) by T14 (shadow-mode denylist gate) and T8 (decide skill's one-way-door instructions); A12 (`D-260908-verbatim-quote-is-the-evidence`) by T2 (validator requires the Evidence blockquote) and T8 (template and skill quote the decisive turn).
3. How the links get filled: the pipeline commits through the `/commit` skill in the main session (brief: owner authorised autonomous commits of intermediate stages). For commits made before T11 lands, the committer adds the trailer by hand in the message: `Decision: D-260908-verbatim-quote-is-the-evidence 01M21BVB05VVF1XV54Y66AWV6E` (the ULIDs are in section 8 item 6). After T15 runs `scribe init` on this repo, `prepare-commit-msg` adds trailers automatically for staged records and pending ids, and `post-commit` writes `implementation_links` and flips `effective_state` to `implemented`. For the earlier hand-trailed commits, step 5 runs `uv run scribe relink` once, which rebuilds the links from git history.
4. During implementation, before T8 exists, the implementer logs decisions as P items in `AUTONOMOUS_DECISIONS_09_08_2026.md` (dated, contemporaneous). From T8 on, design-shaping choices (a new field, a changed enum, a behaviour the plan left open) are recorded with `uv run scribe new --spec ...` as `decided_by: agent`, `review_state: unreviewed`, quoting the plan line or the P item as Evidence (a pointer to a contemporaneous note is honest evidence; inventing a rationale afterwards is not). Step 5 reviews the queue with `/scribe:lint` and the owner ratifies or rejects.
5. Step 5 also runs `/scribe:decide` once on the repo with the plugin loaded via `claude --plugin-dir ~/scribe`, which is the only end-to-end check of `${CLAUDE_PLUGIN_ROOT}`, skill invocation, and hook registration in this run.
6. ULIDs of the three records: A10 `01M21BV91NZSW1HMJ127KZAA5J`, A13 `01M21BVA0X8D5FZCRZNX848569`, A12 `01M21BVB05VVF1XV54Y66AWV6E`.

## 9. Risks and open questions (defaults chosen)

R1. Hook output shape. `additionalContext` for PreToolUse (P19), SessionStart output shape, stdin field names, `timeout` units, `${CLAUDE_PLUGIN_ROOT}` inside skill Bash commands: all UNVERIFIED. Default: implement as specified, isolate every assumption in one module (`hooks/launcher.py` and `hooks/pre_tool_use_edit.py`), and let step 5's `claude --plugin-dir` run be the check. If PreToolUse ignores `additionalContext`, the fallback is plain stdout and a P item; the design still holds because retrieval is advisory.

R2. Cold start of `uv run` exceeding the edit-path budget on the first call after install or after a `uv.lock` change. Default: SessionStart pays the cost (120 s timeout), edit hooks have a 3 s hook timeout plus a 700 ms internal deadline. Residual: the very first edit in a session that skipped SessionStart may get no injection once. Accepted.

R3. Human-only ratification is not enforceable in-process: an agent can run `scribe ratify` through Bash. Defaults: deny rules on Edit and Write of `RATIFICATIONS.jsonl`, the `via: claude-code` tag when `CLAUDECODE` is set (UNVERIFIED), the attestation check that makes a front-matter-only ratification invalid, and the skills' wording. Open question for the owner (batched, not blocking): whether to add `Bash(*scribe ratify*)` and `Bash(*scribe reject*)` deny rules, which would also block the human-typed `/scribe:ratify` skill if slash commands go through the same permission check (UNVERIFIED).

R4. Scratch state under two sessions in one worktree and under `/batch` worktrees. Default: worktree-local file, keyed by session id, locked writes, `prepare-commit-msg` reads all sessions and filters by `affects` overlap, `post-commit` consumes ids. Residual: a decision with empty `affects` attaches to the next commit from any session in that worktree. Accepted; lint reports it (`duplicate_pending` is the nearest signal), and the README tells users to fill `affects`.

R5. Amend and rebase change SHAs; `post-commit` records the pre-rebase sha. Default: `scribe relink` rebuilds from trailers; lint flags unreachable link commits. No `post-rewrite` hook in this run (one more hook to install and test). Batched question: install `post-rewrite` in a later run.

R6. The `INDEX.md` and `implementation_links` writes from `post-commit` land in the next commit, so a branch's last commit always leaves the tree dirty by one generated file. Default: accept (README 10.4 says so); `scribe check` verifies `INDEX.md` freshness in CI so a forgotten regeneration is caught before merge, not silently.

R7. CI check installation: `uvx --from git+...` needs a public or token-accessible scribe repository, which does not exist yet and must not be created without asking. Default: workflow dropped with a placeholder `SCRIBE_SOURCE`; local `scribe check` is the interim gate. Batched question for the owner: create the GitHub repo and tag `v0.1.0`, or prefer vendoring.

R8. The ExitPlanMode policy uses keyword matching on the plan text, which will produce false positives (any plan that says "interface"). Default: shadow mode only, log and measure; the keyword list lives in `policy.py` for tuning. Not a blocker because it never denies in this run.

R9. Body immutability is checked against `--base` by lint, not by the validator, so a rewrite that reaches `main` without CI is invisible afterwards. Default: `scribe check` runs lint's `immutable_changed` and `history_rewritten` against the PR base in CI (add to T12 if time allows; otherwise a P item). Owner's branch protection makes it bite.

R10. Windows. Python shims with a `#!/usr/bin/env python3` line depend on Git for Windows' bash finding `python3`; hooks.json commands assume a POSIX-ish shell for `"${CLAUDE_PLUGIN_ROOT}"` expansion. Default: no Windows work in this run beyond avoiding bash and backslashes; README lists the two known gaps.

R11. One-way-door records: with the gate in shadow mode, "never act without ratification" is enforced only by the skill's instructions and the owner's existing autonomous-mode rule, exactly the status quo the owner described as producing no blockers so far. Default: accept for this run; the gate-log gives the frequency data the owner asked for before deciding to enforce.

R12. PyYAML is the only runtime dependency (P2). Its C accelerator is optional; the pure-Python path costs about 30 ms to import and parses a front matter block in well under a millisecond, which fits the budget. Alternative rejected: a hand-written YAML subset parser (fragile on nested flow mappings in `history`).
