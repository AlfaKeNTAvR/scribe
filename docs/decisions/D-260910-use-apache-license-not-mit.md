---
id: 01M24MZGXR0BE7T3M9EQRAYJVB
alias: D-260910-use-apache-license-not-mit
title: scribe ships under Apache-2.0 with a NOTICE file rather than MIT, because the patent grant and the contribution terms are what a company's legal review looks for in a governance tool
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
- {type: path, pattern: LICENSE}
- {type: path, pattern: NOTICE}
- {type: path, pattern: .claude-plugin/marketplace.json}
implementation_links: []
tags:
- license
- publication
- governance
reversibility: one-way-door
blast_radius: org
regret_when: Contributors or users say the Apache ceremony (NOTICE, changed-file notices) is friction they will not carry, or the project stays single-author so the patent grant never earns its length.
review: '2027-03-10'
verify:
- {id: license-file-is-apache, engine: grep, pattern: Apache License, paths: [LICENSE], expect: match, severity: error}
- {id: manifest-declares-license, engine: grep, pattern: Apache-2.0, paths: [.claude-plugin/marketplace.json], expect: match, severity: error}
supersedes: null
relates_to: []
history:
- {at: '2026-09-10T03:15:01Z', event: proposed, by: claude-code, session: session_01A6tVoZuuWqu56QxEqtAjRw}
---

# scribe ships under Apache-2.0 with a NOTICE file rather than MIT, because the patent grant and the contribution terms are what a company's legal review looks for in a governance tool

> In the context of publishing scribe as a public Claude Code plugin that teams would install to govern their own decisions, facing a repository with no LICENSE at all, which leaves installers no right to use what they install, I decided to ship Apache-2.0 with a NOTICE file to achieve a permissive license that carries an explicit patent grant and contribution terms a corporate legal review accepts without a conversation, accepting a 202 line license file and the NOTICE convention instead of MIT's twenty lines, which is why both plugin manifests and pyproject.toml declare the SPDX identifier.

## Question

Which license should the public repository carry, given that it had none and that the intended audience is teams inside companies?

## Criteria

- Permissive enough that a company can adopt the tool without a policy exception.
- Explicit about patents, since the tool is published by an individual and may take outside contributions.
- Recognised by GitHub and by the plugin manifests, so the SPDX identifier can be declared.
- No copyleft obligation on repositories that merely use the tool.

## Constraints and assumptions

- The repository was already public with no LICENSE, so every installer was working under all rights reserved.
- The owner first said MIT, then asked which license is best for open source, and chose Apache-2.0 from three options.
- Apache-2.0 asks for a NOTICE file and for changed files to carry a notice; MIT asks for neither.
- A license change later needs the agreement of every contributor, which is why this is a one-way door while the project is still single-author.

## Options considered

| Option | For | Against | Evidence | Why rejected |
|---|---|---|---|---|
| Apache-2.0 with a NOTICE file | Permissive like MIT, plus an explicit patent grant and contribution terms; the default corporate legal teams accept without questions | 202 lines instead of 20, and the NOTICE and changed-file conventions to keep | the owner's selection among three options, 2026-09-10 | chosen |
| MIT | Shortest and most familiar permissive license, the norm for Claude Code plugins | No explicit patent grant, so a contributor could in theory assert a patent against users | the same three-option question; the owner's first instinct was MIT | Owner asked what is best for open source and chose the patent grant |
| GPL-3.0 | Derivative works must stay open, protecting the project from closed forks | Most companies forbid adopting GPL tooling, which is exactly the audience for a team governance tool | the same three-option question | It would cut off the intended audience |

## Decision

The repository carries the verbatim Apache License 2.0 text as LICENSE and a NOTICE file naming Nikita Boguslavskii as the 2026 copyright holder. The SPDX identifier Apache-2.0 is declared in .claude-plugin/marketplace.json, .claude-plugin/plugin.json and pyproject.toml. The MIT text written earlier in the same session is discarded before any commit, so no release ever carried it.

## Consequences

- Positive: anyone installing from the public marketplace has a clear grant, including patents, and a company can adopt it without a policy exception.
- Negative: contributors inherit the NOTICE and changed-file conventions, and relicensing later needs every contributor's agreement.
- Requires: new source files may carry the standard Apache header; the NOTICE file stays accurate as authorship changes.
- Measure: whether an outside contribution or a company adoption arrives without a licensing question.

## Evidence

> Actually, what is the best for opensource?

- Owner (Nikita Boguslavskii) to Claude Opus 5, Claude Code session session_01A6tVoZuuWqu56QxEqtAjRw, 2026-09-10, immediately after saying: Let's do MIT licence.
- The owner then selected Apache-2.0 from a three-option question offering Apache-2.0, MIT and GPL-3.0.
- https://www.apache.org/licenses/LICENSE-2.0.txt, the text fetched into LICENSE.
