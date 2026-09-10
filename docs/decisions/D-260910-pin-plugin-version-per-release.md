---
id: 01M24R3T3FVP5QQWZBKG2QPVY5
alias: D-260910-pin-plugin-version-per-release
title: Every published change bumps an explicit semantic version in all four manifests, patch for a fix and minor for a new skill, because Claude Code never fetches an unmoved version
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
- {type: path, pattern: .claude-plugin/marketplace.json}
- {type: path, pattern: .claude-plugin/plugin.json}
- {type: path, pattern: pyproject.toml}
- {type: path, pattern: src/scribe/__init__.py}
implementation_links: []
tags:
- release
- versioning
- marketplace
- install
reversibility: two-way-door
blast_radius: component
regret_when: Releases go out with an unbumped version more than once, or the four manifests drift despite the test, or a consumer needs a version scheme this one cannot express.
review: '2027-03-10'
verify:
- {id: manifest-versions-agree-test, engine: grep, pattern: test_every_manifest_states_the_same_version, paths: [tests/test_hook_launcher.py], expect: match, severity: error}
- {id: readme-has-release-checklist, engine: grep, pattern: '## Releasing', paths: [README.md], expect: match, severity: warning}
supersedes: null
relates_to: []
history:
- {at: '2026-09-10T04:09:47Z', event: proposed, by: claude-code, session: session_01A6tVoZuuWqu56QxEqtAjRw}
---

# Every published change bumps an explicit semantic version in all four manifests, patch for a fix and minor for a new skill, because Claude Code never fetches an unmoved version

> In the context of a plugin installed from a GitHub marketplace and cached per version, facing an owner who updated the marketplace and restarted and still did not see a skill that had been on main for an hour, I decided to keep an explicit semantic version and bump it on every published change, patch for a fix and minor for a new command or skill, to achieve installs that update when something ships and a number a human can name, accepting a release step that is easy to forget, which is why a test fails the build when the four manifests disagree and the README carries a release checklist.

## Question

How should the plugin be versioned so that an installed copy picks up a published change, and how big should the bump be for a small fix?

## Criteria

- An installed copy fetches new files whenever something is published.
- The version is readable, so a user and a bug report can name it.
- The four places that state a version cannot drift apart silently.
- The rule is short enough to follow without looking it up.

## Constraints and assumptions

- Claude Code resolves the version from plugin.json first, then the marketplace entry, then the git commit sha, and only fetches when the resolved version differs from the cached one; an explicit version that does not move means no fetch, whatever the repository does (documentation checked 2026-09-10).
- Installed plugins live under a per-version cache directory, so a restart alone changes nothing.
- The version appears in src/scribe/__init__.py, pyproject.toml, .claude-plugin/plugin.json and .claude-plugin/marketplace.json, and uv.lock records it too.
- Below 1.0 a minor bump may break things, which suits a record format still in motion.

## Options considered

| Option | For | Against | Evidence | Why rejected |
|---|---|---|---|---|
| Explicit semantic version, bumped on every published change: patch for a fix, minor for a new command or skill | Readable and citable; updates reach users; the pre-1.0 range allows breaking changes in a minor bump | A release step that is easy to forget, and forgetting it is silent for the user | the owner's question about 0.1.1 for small fixes; the failed 0.1.0 update on Windows | chosen |
| Omit the version so the git commit sha becomes the version | Every commit updates automatically, nothing to remember | No readable version anywhere, so no user can say which build they have and no record can name a release | the version resolution order in the plugin documentation, checked 2026-09-10 | Loses the human-facing number, and every commit on main would become a release |
| Bump only for features and leave fixes unnumbered | Fewer releases to think about | This is exactly the failure that prompted the question: a shipped fix that never reaches an installed copy | the doctor skill sitting on main while an installed 0.1.0 stayed unchanged | A fix nobody receives is not a fix |

## Decision

The version is semantic and explicit. A published change bumps it: patch (0.2.1) for a fix or a documentation change, minor (0.3.0) for a new command, skill or hook, and the pre-1.0 range keeps breaking changes at minor. All four sites move together, guarded by test_every_manifest_states_the_same_version, and uv.lock is re-locked. The README carries the checklist under Releasing. Whether a git tag accompanies each release is the owner's call and is not part of this decision.

## Consequences

- Positive: an installed copy sees every published change; a user can name the version they run.
- Negative: one more step per release, and skipping it fails silently for users, not for the build.
- Requires: the release checklist stays next to the install instructions; a future automated release would fold the bump into one command.
- Measure: how many published changes reach an installed copy without a manual reinstall.

## Evidence

> I am wondering if for small fixes we should go 0.1.1 etc

- Owner (Nikita Boguslavskii) to Claude Opus 5, Claude Code session session_01A6tVoZuuWqu56QxEqtAjRw, 2026-09-10, after a Windows install failed to pick up the doctor skill.
- Claude Code plugin marketplace documentation, fetched 2026-09-10 by the claude-code-guide subagent: version resolution order and the per-version cache.
- AUTONOMOUS_DECISIONS_09_08_2026.md, entry M27.
