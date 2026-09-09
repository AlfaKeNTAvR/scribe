# scribe

Scribe records agent decisions, links them to code, injects them before edits,
and keeps a review queue for human ratification. It ships as a Claude Code
plugin (skills and hooks) plus a Python CLI, and installs its own git hooks
into a target repository through `scribe init`.

This document is plain and factual: what each piece does, what it does not
do, and where it can fail quietly. Full behavioural spec:
`docs/build/03-plan-v2.md` (referenced below as "the plan").

## Install

Local development, from this checkout:

```
claude --plugin-dir ~/scribe
```

then, inside a running Claude Code session, run `/reload-plugins` to pick up
changes without restarting.

Once scribe is published to a marketplace, install it the normal way (`/plugin
marketplace add <source>` then `/plugin install scribe`) and re-run the
install after any version bump: third-party plugins do not auto-update.

Installing the plugin gives you the five skills and the Claude Code hooks
(`hooks/hooks.json`). It does **not** touch any git repository. To add
scribe's git hooks, CI check and config to a project, run `scribe init` inside
that project's repository (see below).

## CLI reference

Every subcommand is `uv run scribe <command> ...` from this checkout (or
`scribe <command> ...` once the console script is on PATH inside a `uv`
environment that has scribe installed).

| Command | What it does |
|---|---|
| `validate [paths...]` | Validates one or more decision records (or every record under `docs/decisions` with no argument) against the schema in the plan, section 3. |
| `index [path]` | Regenerates `docs/decisions/INDEX.md`. `--check` exits 1 instead of writing when the file on disk is stale. |
| `lookup <token>` | Reverse lookup: a commit-ish shows the records its `Decision:` trailers name; a ULID or alias shows the commits and `implementation_links` for that record. |
| `new --spec <file>` | Writes a new decision record from a JSON spec (used by `/scribe:decide`). `--register` adds the new id to a session's pending decisions so the next commit picks it up. |
| `ratify <alias-or-ulid> [note]` | Records a human ratification verdict: appends to `RATIFICATIONS.jsonl`, updates the record, runs supersession reconciliation. |
| `reject <alias-or-ulid> [note]` | Same as `ratify`, verdict `rejected`. |
| `check --base <ref> [--allow-dirty]` | The CI merge gate: fails a pull request that introduces or depends on an unreviewed record superseding a ratified one, or that breaks the append-only or immutability rules. Deleting a record that was present at the base ref also fails the check (`record_deleted`); retire it with `expired` or `backtracked` instead. Refuses to run when `docs/decisions` has uncommitted changes (they could mask or fake the committed result), unless `--allow-dirty` is given. |
| `lint` | Store-wide rules over every record: stale index, immutable-field changes, unattested review states, expired proposals, `verify` entries, and more (plan section 4.12). |
| `init [--force] [--hooks-dir DIR] [--ci-source SPEC]` | Installs the git hook shims (`prepare-commit-msg`, `commit-msg`, `post-commit`, `post-rewrite`), `.claude/scribe/config.json`, the `RATIFICATIONS.jsonl` deny rule in `.claude/settings.json`, and (with `--ci-source`) the `scribe-check.yml` workflow, into the current repository. |
| `relink` | Rebuilds every record's `implementation_links` from git history: reachable linked commits are kept and refreshed, unreachable ones (post-amend, post-rebase) are dropped, missing ones are added. No range option; always looks at the whole history. `git commit --amend` and `git rebase` already trigger this automatically through the `post-rewrite` hook; run it by hand for a history rewritten somewhere the hook never ran, for example on another clone. |
| `hook <event>` | Entry point for a Claude Code hook; reads the event payload as JSON on stdin. Not meant to be run by hand. |
| `git-hook <name> [args...]` | Entry point for a git hook (`prepare-commit-msg`, `commit-msg`, `post-commit`, `post-rewrite`); this is what the shims `scribe init` writes actually call. Not meant to be run by hand. |
| `--version` | Prints the installed scribe version and the path it was loaded from. |

## Record format

Decision records live at `docs/decisions/D-<slug>.md`: YAML front matter plus
a fixed body (Question, Criteria, Constraints and assumptions, Options
considered, Decision, Consequences, Evidence, and an optional Attempted and
failed section). The full field table, the immutable versus mutable key
split, history entry shape, and the body rules are the plan, sections 3.1
through 3.6. `docs/decisions/INDEX.md` (section 3.5) is generated, never
hand-edited.

Never edit a record's body by hand after its first commit: the body is
immutable, and every change to a mutable field (`review_state`,
`effective_state`, `ratified_by`, `ratified_at`, `implementation_links`,
`supersedes`, `history`) must go through a scribe command so it appends a
history entry. Never edit `docs/decisions/RATIFICATIONS.jsonl` by hand either;
see the ratification model below.

`verify` entries (run by `scribe lint` only) support two engines: `grep`
(`{pattern, paths}`, a regex checked against files selected by glob) and
`pytest` (`{target}`, a pytest node id or path run with `uv run --frozen
pytest -q -x <target>` from the repository root, gated on that repository
having a `pyproject.toml` that names pytest; bounded by a timeout, 60 seconds
by default and overridable with `SCRIBE_VERIFY_TIMEOUT`). `jsonpath` is named
on this allowlist but not implemented in this release.

## Ratification model

`docs/decisions/RATIFICATIONS.jsonl` is committed and append only, one JSON
object per line:

```json
{"id": "01M21BV91NZSW1HMJ127KZAA5J", "alias": "D-260908-unreviewed-may-supersede-ratified", "verdict": "ratified", "by": "@nikita", "at": "2026-09-08T20:37:41Z", "body_sha256": "<hex>", "via": "hand-written", "note": "Interview answer A10"}
```

`verdict` in `ratified`, `rejected`; `via` in `skill`, `cli`, `hand-written`,
set from the CLI flag `--via` (default `cli`; the skills pass `--via skill`).
The latest line for an `id` is authoritative. Validator rule 6 makes a
record's `review_state` worthless without a matching line, so editing a
record alone cannot ratify it.

What this file is and is not: `scribe init` adds
`Edit(/docs/decisions/RATIFICATIONS.jsonl)` to `permissions.deny` in the
target repo's `.claude/settings.json`; the leading `/` anchors at the
session's primary working directory, not the repository root, and an `Edit`
rule also covers the `Write` tool (Claude Code 2.1.228 or later; `Write(...)`
path rules are accepted but never consulted, so none is written). This blocks
the agent's file tools, but only for a session started at the repository
root: live testing showed that no project settings (`.claude/settings.json`
or `settings.local.json`, whatever path form the rule uses, `/relative`,
`**/any-depth`, or `//absolute`) load when Claude Code starts in a
subdirectory of the repository, so the deny rule is silently inactive for
those sessions. `scribe init` and the SessionStart hook both print a
reminder to start Claude at the repository root; for a session that must
start below it, add `Edit(**/docs/decisions/RATIFICATIONS.jsonl)` to your own
user-level settings instead, since a user-level rule is not anchored to the
project's settings source. None of this blocks a subprocess: an agent could
run `scribe ratify` through Bash. In this release, human-only ratification is
by construction of the skills (`/scribe:ratify` and `/scribe:reject` carry
`disable-model-invocation: true`), not by proof; the attestation line records
who ran the verdict and through which path (`via`).

## Denylist

The `PreToolUse` gate on `Bash|PowerShell` matches commands against a fixed
set of irreversible-action rules (`src/scribe/policy.py`): force-pushing,
force-deleting a branch, `git reset --hard` against a remote-tracking branch,
`rm -rf` outside the worktree, running a database migration (alembic, prisma,
flyway), `terraform apply`/`destroy`, `kubectl apply`/`delete`, `helm
install`/`upgrade`, `docker push`, publishing a package (npm/pnpm/yarn,
cargo, twine, `uv publish`), creating a GitHub release, merging a GitHub pull
request, and writing HTTP requests (curl/wget/http with a write method or a
request body). A decision record can also declare its own `affects` entry of
`{type: action, pattern: <rule-name>}` to tie a rule to a specific decision.

## Fail-open policy

Every Claude Code hook this plugin registers is advisory or shadow-mode by
default:

- The `SessionStart`, `UserPromptSubmit` and `PreToolUse Edit|Write`
  (injection) hooks are advisory: any internal failure is caught, logged to
  `.claude/scribe/hook-errors.log`, and the hook exits 0. A broken hook never
  blocks an edit.
- The `PreToolUse ExitPlanMode`/`Bash|PowerShell` gate and the
  `TaskCompleted`/`Stop` reconcile hooks run in shadow mode: they compute a
  verdict, log it to `.claude/scribe/gate-log.jsonl`, and still exit 0. They
  only start blocking once a repository's `.claude/scribe/config.json` sets
  `SCRIBE_GATES: enforce`; `scribe init` never sets this itself.
- The git hooks (`prepare-commit-msg`, `commit-msg`, `post-commit`,
  `post-rewrite`) never fail a commit, amend or rebase in this release:
  exceptions are logged and the hook exits 0. `commit-msg` prints warnings by
  default (`SCRIBE_COMMIT_MSG: warn`); an `enforce` value in the same config
  file turns three of its checks fatal. `post-rewrite` runs the same relink
  as `scribe relink` after `git commit --amend` and `git rebase`, so
  implementation links stay current across a rewrite without a manual step;
  it shares the V8 ledger lock with the other three writers, so a lock
  timeout prints one line and writes nothing, same as `post-commit`.
- `uv` itself is covered too. Every registered hook command and every git
  shim runs `uv run ... scribe` through `hooks/supervise.py`, a stdlib-only
  Python script (system `python3`, 3.8 or newer). If uv cannot start (missing
  binary, locked or read-only cache, stale `uv.lock`) or the application
  crashes, the supervisor prints one `scribe: <hook> skipped (...)` line to
  stderr and exits 0, so Claude Code never sees the exit 2 that would deny a
  tool call and git never sees a failed hook. Only a deliberate refusal (a
  gate in `enforce` mode, `commit-msg` under `SCRIBE_COMMIT_MSG: enforce`)
  is passed through: the supervisor gives that invocation a random token and
  accepts only the matching `[scribe-deny <token>]` stderr line, then forces
  the documented blocking exit code. Registered hooks use `python3 -I -S`;
  installed git shims re-exec themselves with those flags before loading the
  supervisor.

## Config file

`.claude/scribe/config.json`, written once by `scribe init` and never
overwritten again after that (a hand edit is never clobbered):

```json
{"version": 1, "SCRIBE_GATES": "shadow", "SCRIBE_COMMIT_MSG": "warn"}
```

`SCRIBE_GATES` is `shadow` (default) or `enforce`. `SCRIBE_COMMIT_MSG` is
`warn` (default) or `enforce`. The file is git-ignored (`scribe init` adds
`.claude/scribe/` to `.gitignore`), so these switches are local to a clone and
can never be flipped by an inherited environment variable.

## Windows caveats

Windows is best effort by construction (Python via `uv`, forward-slash paths,
exec-form hooks, no bash), not tested against a real Windows machine in this
release:

- **Shim and hook interpreter**: the git hook shims `scribe init` writes use
  `#!/usr/bin/env python3` on POSIX and `#!/usr/bin/env python` on Windows
  (`os.name == "nt"` at init time); both import `hooks/supervise.py` from the
  plugin root and wait for uv through `subprocess.run`, so nothing depends on
  `execvp`. `scribe init` refuses to install anything if `uv` or the shim
  interpreter is not on PATH. The Claude Code hooks in `hooks/hooks.json`
  are registered as `python3 -I -S <plugin>/hooks/supervise.py ...`; a Windows
  machine whose interpreter is only reachable as `python` needs that command
  name changed, which has not been tried.
- **Lock adapter untested**: the scratch-state file lock
  (`src/scribe/state.py`) uses `fcntl.flock` on POSIX and `msvcrt.locking` on
  Windows. The Windows branch is exercised only against a faked `msvcrt`
  module in unit tests, never against real Windows file locking.
- **PowerShell tool matcher**: the `Bash|PowerShell` gate's denylist patterns
  (`src/scribe/policy.py`) are written and tested against bash-style command
  strings. They also match the equivalent PowerShell spellings the rules
  anticipate (`npm.cmd`, `-X`/`--request`, and so on), but the matcher itself
  has not been run against a live PowerShell session.

## Tests

Run the suite from this repository:

```sh
uv run pytest -q
```

The suite has exactly three skips, all in `tests/test_deferred.py`:

| Test | Deferred behaviour | When to enable |
|---|---|---|
| `test_two_worktree_supersede` | Two real worktrees ratify X, propose Y superseding X, retrieve their own active decision, and merge after Y is ratified. The complete scenario is executable but skipped. | Before turning any gate to `enforce`. |
| `test_commit_msg_runs_verify_on_staged_content` | Run referenced records' `verify` entries against staged content in `commit-msg`. | After 14 days of dogfooding `scribe lint` with zero `verify_error`; implement the staged-content runner and replace the assertion stub, then remove the skip. |
| `test_check_runs_verify_on_committed_content` | Run changed records' `verify` entries against committed content in `scribe check`. | After the same 14-day, zero-`verify_error` period; implement the committed-content runner and replace the assertion stub, then remove the skip. |

`tests/test_timing.py` measures the complete injection subprocess through
the registered command, `python3 -I -S <checkout>/hooks/supervise.py hook
pre-tool-use-edit` (which runs `uv run --frozen --project <checkout> scribe
hook pre-tool-use-edit`), with
100 generated records plus the three seed records. It prints `warm median`
for three runs (must be below 1.0 s) and `bytecode-cold` after removing
`src/**/__pycache__` and setting `PYTHONDONTWRITEBYTECODE=1` (must be below
2.0 s). Missing `uv` or `python3` fails the test. Run it alone with
`uv run pytest -q -s tests/test_timing.py`.

The edit hook also has a 700 ms internal processing deadline and a 1 s
Claude Code timeout. A fresh-venv cold start is not measured; SessionStart's
120 s timeout absorbs initial startup. Tests use temporary repositories;
git hook tests make commits there, never in this checkout.
