---
id: 01M249VWTCVC0NT2E0GEZMD95A
alias: D-260910-require-verdict-first-alias-slug
title: Every new record alias comes from a required, agent-written verdict-first slug (verb from an allowlist, 3 to 6 words, 40 characters, no filler), never from the title's opening words
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
- {type: path, pattern: src/scribe/newrecord.py}
- {type: path, pattern: skills/decide/SKILL.md}
implementation_links: []
tags:
- alias
- naming
- schema
- skill
reversibility: two-way-door
blast_radius: component
regret_when: Agents fail scribe new on the slug rule more than one time in five, or the verb allowlist blocks a real decision that no listed verb can express.
review: '2026-12-08'
verify:
- {id: slug-verb-allowlist-exists, engine: grep, pattern: SLUG_VERBS, paths: [src/scribe/newrecord.py], expect: match, severity: error}
- {id: skill-explains-slug, engine: grep, pattern: verdict-first, paths: [skills/decide/SKILL.md], expect: match, severity: warning}
supersedes: null
relates_to: []
history:
- {at: '2026-09-10T00:00:47Z', event: proposed, by: claude-code, session: session_01A6tVoZuuWqu56QxEqtAjRw}
---

# Every new record alias comes from a required, agent-written verdict-first slug (verb from an allowlist, 3 to 6 words, 40 characters, no filler), never from the title's opening words

> In the context of aliases being the name a human sees in INDEX.md, git trailers and file listings, facing five generated aliases that were the first 40 characters of a sentence (filler words, cut mid-word, no verdict) against three hand-named seeds that read as rulings, I decided to require an agent-written verdict-first slug validated by scribe new (verb allowlist first, 3 to 6 words, at most 40 characters, filler rejected, collisions refused) to achieve aliases that state the decision without opening the record and share one style over time, accepting a maintained verb list and a hard failure when the agent names badly, which is why the skill carries the rule and examples and the list lives in one constant.

## Question

How should the alias of a new decision record be formed so that it is informative in INDEX.md, commit trailers and file listings, given that the title is a long sentence and the previous generator took its first 40 characters?

## Criteria

- A reader learns what was decided from the alias alone.
- One style across records written by different agents over time.
- A fixed maximum width so aliases align in columns.
- Existing aliases and every reference to them stay valid.

## Constraints and assumptions

- Aliases are immutable keys: filenames, Decision trailers on commits, relates_to and supersedes references, attestation lines. Renaming or deleting a record fails scribe check (record_deleted), so the eight existing aliases stay as they are.
- Two independent analyses (docs/build/13-alias-analysis.md by a Fable subagent, docs/build/13-codex-alias-analysis.md by Codex gpt-5.6-sol) agreed on an agent-written slug and disagreed on strictness; the owner chose the strict variant.
- The stored alias schema (ALIAS_RE, 8 to 60 characters) is unchanged; the new rule applies to what scribe new accepts.

## Options considered

| Option | For | Against | Evidence | Why rejected |
|---|---|---|---|---|
| Strict: required slug, first word from a verb allowlist, filler tokens rejected, collision is an error asking for a more specific slug | Uniform verb-first reading; the verdict is always visible; no silent -2 suffixes | A maintained verb list; scribe new refuses a record when the agent names badly; two of the three seeds would not have passed | docs/build/13-codex-alias-analysis.md, Recommendation and Validation sections | chosen |
| Lenient: slug optional in the schema and mandatory in the skill, a derived fallback with a slug_derived warning, shape-only validation | Never blocks a record; accepts the seeds as written | Style drifts as agents skip the field; the fallback keeps producing title prefixes | docs/build/13-alias-analysis.md, Recommendation section | Owner: mostly thinking about the future, the style should match; the ordering can be changed later if the style is disliked |
| Keep the title-derived cut and only strip stopwords or cut at a word boundary | No new field, backward compatible | Cannot reorder words or surface a verdict that sits after character 40; the seeds show the verdict is what matters | the five 2026-09-09 aliases, for example the-git-hooks-keep-reading-records-and-a | Both analysts rated it insufficient |

## Decision

scribe new requires a slug in the spec: 3 to 6 lowercase words joined by single hyphens, at most 40 characters, first word from newrecord.SLUG_VERBS, none of the filler tokens (the, a, an, its, and, or, of, to, in), and no existing record with the same alias; the alias is D-YYMMDD-<slug> verbatim. The decide skill states the rule with good and bad examples. Title-derived slugs and -2 suffixing are removed. The eight existing aliases are left alone; the four unreviewed 2026-09-09 records keep theirs unless the owner rejects and re-records them.

## Consequences

- Positive: future aliases read as rulings in INDEX.md, trailers and listings, in one style.
- Negative: an agent that cannot find a listed verb has to pick the nearest one or the record fails; the verb list needs occasional additions.
- Requires: the skill wording stays in sync with SLUG_VERBS; playground templates carry a slug placeholder.
- Measure: count of scribe new failures on the slug rule per month, and whether any record needed a verb outside the list.

## Evidence

> I feel like maybe strict is a good option because I'm mostly thinking about the future. So we wanna... the style to match potentially. You know? So I think that's good. And just in case if we don't like the style, we can change the award ordering or something.

- Owner (Nikita Boguslavskii) to Claude Fable 5.1, Claude Code session session_01A6tVoZuuWqu56QxEqtAjRw, 2026-09-09 night, voice-transcribed (award ordering read as word ordering).
- docs/build/13-alias-analysis.md (Fable subagent) and docs/build/13-codex-alias-analysis.md (Codex gpt-5.6-sol), both 2026-09-09.
- docs/build/14-strict-slug.md, the implementation report.
