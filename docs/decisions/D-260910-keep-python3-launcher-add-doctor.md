---
id: 01M24MZNGXZK9A5XEXM16NDSRT
alias: D-260910-keep-python3-launcher-add-doctor
title: Hook entries keep launching python3 and a new scribe doctor command reports a broken install, because hooks.json has no platform branch and making uv the launcher would undo the fail-open supervisor
date: '2026-09-10'
schema_version: 1
task_refs: []
review_state: unreviewed
effective_state: proposed
decided_by: human
recommended_by: claude-code
ratified_by: null
ratified_at: null
provenance:
  authored_by: agent-drafted
  agent: claude-code
  model: null
  session: session_01A6tVoZuuWqu56QxEqtAjRw
  prompt_ids: []
  trigger: user-prompt
  source_messages: []
affects:
- {type: path, pattern: hooks/hooks.json}
- {type: path, pattern: src/scribe/doctor.py}
- {type: path, pattern: src/scribe/cli.py}
implementation_links: []
tags:
- install
- hooks
- windows
- cli
reversibility: two-way-door
blast_radius: component
regret_when: Claude Code adds a platform branch or an interpreter placeholder to the hook schema, or Windows users report that doctor tells them what is wrong but the fix is still too manual.
review: '2026-12-09'
verify:
- {id: doctor-command-exists, engine: grep, pattern: doctor, paths: [src/scribe/cli.py], expect: match, severity: error}
- {id: hooks-still-launch-python3, engine: grep, pattern: python3, paths: [hooks/hooks.json], expect: match, severity: warning}
supersedes: null
relates_to: []
history:
- {at: '2026-09-10T03:15:05Z', event: proposed, by: claude-code, session: session_01A6tVoZuuWqu56QxEqtAjRw}
---

# Hook entries keep launching python3 and a new scribe doctor command reports a broken install, because hooks.json has no platform branch and making uv the launcher would undo the fail-open supervisor

> In the context of a Claude Code plugin whose seven hook entries launch the fail-open supervisor with the literal python3, facing a Windows install where that name usually resolves to nothing and the failure shows only as a non-blocking hook error line nobody reads, I decided to keep python3 and add a scribe doctor command that checks the interpreter, uv, the plugin root, the git hook shims, the settings file and the store, to achieve one loud place where a broken install is visible on every platform, accepting that Windows still needs a python3 on PATH, which is why the README names the two ways to provide one.

## Question

How should the plugin survive an install on a platform where the interpreter named in hooks.json does not exist, given that a hook that cannot launch fails quietly?

## Criteria

- Ubuntu, the platform the plugin is developed on, keeps working unchanged.
- A Windows user learns that scribe is not running, without reading a debug log.
- No regression of the fail-open guarantee: an infrastructure failure must never read as a deliberate denial.
- One command a user can run after installing, no manual JSON piping.

## Constraints and assumptions

- The hooks documentation, checked 2026-09-10, documents no platform conditional, no per-OS command and no environment placeholder in hooks.json beyond CLAUDE_PROJECT_DIR, CLAUDE_PLUGIN_ROOT and CLAUDE_PLUGIN_DATA.
- Exec form (a command plus args) resolves the command through PATH; Windows searches for .exe, .bat, .cmd and .ps1, so a POSIX shebang script cannot be the command there.
- hooks/supervise.py exists because uv exits 2 when it cannot start and Claude Code reads exit 2 from PreToolUse or UserPromptSubmit as a denial (Codex finding V1).
- A hook that cannot be launched at all is a non-blocking error: the transcript shows one hook error line and the action proceeds.

## Options considered

| Option | For | Against | Evidence | Why rejected |
|---|---|---|---|---|
| Keep python3 in hooks.json, add scribe doctor, document the Windows fix | Ubuntu unchanged; the failure becomes visible on demand on every platform; supervise.py keeps the fail-open guarantee | Windows still needs a python3 on PATH, provided by the Store Python or a python3.cmd shim; doctor is new surface to maintain | the hooks documentation checked 2026-09-10; hooks/supervise.py docstring | chosen |
| Make uv the hook command and let it run the supervisor | One binary name that exists on both platforms | uv exits 2 when it cannot start, and Claude Code reads exit 2 as a denial, so a locked cache would start denying edits again | hooks/supervise.py docstring, Codex finding V1 | It reintroduces the defect supervise.py was written to fix |
| Change the command to python | Works on a default Windows install | Ubuntu has no python binary unless python-is-python3 is installed, so it breaks the development platform | Ubuntu 22.04 default package set | Trades a Windows break for an Ubuntu break |
| Ship a platform-detecting wrapper as the hook command | One entry could pick the interpreter itself | The wrapper is either a shebang script, which Windows cannot exec, or a .cmd, which POSIX cannot exec; hooks.json cannot name two | exec form PATH rules in the hooks documentation | No single file is executable on both platforms |

## Decision

hooks/hooks.json keeps python3 in all seven entries. A new scribe doctor command reports one line per check: the hook interpreter (resolved through PATH, with the version it reports), uv, the plugin root and its hooks.json, the installed git hook shims and their interpreter, the settings deny rule, the decision store and whether INDEX.md is stale. It exits 1 if any check fails, 0 otherwise, and takes --json for machine output. The README install section names the Windows fix (Store Python, or a python3.cmd on PATH) and points at doctor.

## Consequences

- Positive: an install that silently does nothing can be diagnosed with one command instead of piping hook payloads by hand.
- Negative: doctor duplicates knowledge of what init writes, so the two drift if init changes and doctor does not.
- Requires: a Windows user still has to provide python3 themselves; the upstream gap is worth an issue against Claude Code.
- Measure: whether the next Windows install reports scribe working after following the README, without a debug log.

## Evidence

> What was your friction for installing this plug in? I can give it to another Claude, and we can fix it.

- Owner (Nikita Boguslavskii) to Claude Opus 5, Claude Code session session_01A6tVoZuuWqu56QxEqtAjRw, 2026-09-10, approving the batch with the single word Build after the four friction items were listed.
- The friction report from a Windows Claude Code session, pasted by the owner in the same session: hardcoded python3, undocumented local marketplace install, no self-check, tests that do not collect on Windows.
- Claude Code hooks documentation, fetched 2026-09-10 by the claude-code-guide subagent.
