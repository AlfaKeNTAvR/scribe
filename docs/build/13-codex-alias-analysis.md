# Codex alias analysis

## Existing aliases

- **Informative** - `D-260908-one-way-door-defer-not-stop` - 36 characters. Title: "One-way-door decisions are recorded as proposed and batched for the end of the run, never a hard stop, and the Bash denylist keeps the action denied until ratified." `decided_by: human`, `provenance.agent: claude-code`, hand-named. "one-way-door", "defer", and "not-stop" capture the subject, action, and contrast. No filler or cut.
- **Informative** - `D-260908-unreviewed-may-supersede-ratified` - 42 characters. Title: "An unreviewed agent record may supersede a ratified one, guarded by queue priority and a CI merge gate." `decided_by: human`, `provenance.agent: claude-code`, hand-named. Every word identifies the actors and verdict. No filler or cut.
- **Informative** - `D-260908-verbatim-quote-is-the-evidence` - 39 characters. Title: "The Evidence section quotes the decisive user turn verbatim; transcript pointers are kept but never relied on." `decided_by: human`, `provenance.agent: claude-code`, hand-named. "verbatim-quote" and "evidence" state the rule. "is-the" is grammatical glue but helps express the relationship. No cut.
- **Weak** - `D-260909-history-replay-validation-every-changed` - 48 characters. Title: "History replay validation (every changed mutable field must be explained by an appended history entry) is deferred until the CI check has run on real branches for a few weeks." `decided_by: agent-recommended`, `provenance.agent: claude-code`, generated. "history-replay-validation" identifies the topic, but "every-changed" is an incomplete qualifier and the decisive word "deferred" is lost. The cut falls before "mutable".
- **Weak** - `D-260909-post-commit-skips-its-backlink-write-whi` - 49 characters. Title: "post-commit skips its backlink write while a rebase is in progress and leaves the relink to post-rewrite, so replayed commits do not dirty docs/decisions mid-rebase." `decided_by: agent`, `provenance.agent: claude-code`, generated. "post-commit-skips-backlink-write" carries meaning, while "its" is filler. The cut lands inside "while", omitting the essential rebase condition.
- **Weak** - `D-260909-tests-keep-copying-the-live-docs-decisio` - 49 characters. Title: "Tests keep copying the live docs/decisions ledger as their fixture; a synthetic fixture set and an isolated timing-test purge wait for the first unrelated breakage." `decided_by: agent-recommended`, `provenance.agent: claude-code`, generated. It conveys continued copying, but omits the important seed pinning and deferral trigger. "the" is filler and the cut lands inside "decisions".
- **Useless** - `D-260909-the-git-hooks-keep-reading-records-and-a` - 49 characters. Title: "The git hooks keep reading records and attestations from the working tree, not from the staged index, until enforce mode ships or a false verdict is seen." `decided_by: agent-recommended`, `provenance.agent: claude-code`, generated. "git-hooks", "keep-reading", and "records" provide only a topic. "the" and "and" consume space, and the final "a" is the first letter of "attestations". The alias omits the actual choice between working tree and staged index.
- **Weak** - `D-260909-non-positive-width-height-or-radius-rais` - 49 characters. Title: "Non-positive width, height, or radius raises ValueError inline in each geometry function." `decided_by: human`, `provenance.agent: null`, hand-named playground seed. The dimensions and rejection behavior are recognizable, but "or" consumes space, "raises" is cut to "rais", and the inline implementation choice is absent.

## What the seeds do right

The three 2026-09-08 seeds summarize the decision instead of copying the beginning of its title. Each preserves the distinguishing nouns and the verdict or contrast: "defer-not-stop", "may-supersede", and "quote-is-evidence". They omit setup, articles, actors already implied by the record, and secondary safeguards. The playground seed is the exception: it resembles a mechanical title prefix and demonstrates why a character cut must happen after semantic compression and only at a word boundary.

## Fixed width

Keep a maximum width, not equal-length stored aliases. Current aliases are already 36 to 49 characters, a cut on a hyphen can produce 39 stem characters, and collision suffixes add length.

Alignment is useful in INDEX and, less strongly, in `scribe lookup`, where fields are compared across rows. The renderer should provide columns using a Markdown table or a monospace block. Padding ordinary Markdown source is ineffective because rendered HTML collapses spaces. Equal length adds little in file listings, where semantic prefixes matter more, or in `Decision:` trailers and git log, where aliases are tokens on separate lines. Injection also needs compact aliases because each line is capped at 220 characters, but equal width provides no benefit because the title follows immediately.

## Options

- **Agent-written slug field** - Best semantic quality and clean separation from the long title. It adds authoring work and needs validation because agents can still produce vague slugs.
- **Verdict-first template** - Require forms such as `defer-history-replay-check` or `read-hook-state-from-worktree`. This puts the decision before truncation and is easier to validate than subject-verb-object. A controlled verb list needs maintenance.
- **Derive from Decision text** - More likely to find the verdict than title-prefix slugification, but decision paragraphs contain context and implementation detail, so extraction remains heuristic.
- **Stopword stripping only** - Cheap and backward-compatible, but it cannot reorder words or recover a verdict occurring after character 40. Banning "keep" would actively remove a meaningful verdict.
- **Area plus action** - Forms such as `hooks-read-working-tree` improve browsing and grouping. Area vocabularies drift unless standardized, and the prefix consumes scarce space.
- **External naming patterns** - ADR sequence numbers and Jira keys provide excellent identity but little meaning. Conventional Commits offers the more useful lesson: a small category or scope followed by a concise imperative subject.

## Recommendation

Add a required agent-written `slug`, but define it as a 3 to 6 word verdict-first phrase, not subject-verb-object. The proposal's examples are imperative verb-object phrases already. Keep the 40-character maximum, reject mid-word truncation and collisions, retain the full title, and render INDEX as real columns rather than encoding alignment into identifiers. Do not use automatic stopword stripping as the normal path or ban "keep". If compatibility requires a fallback, derive candidates from the Decision section and fail with a suggested slug when no clear verdict fits, rather than silently accepting another weak title prefix.

## Migration

Aliases are immutable keys embedded in filenames, trailers, relationships, attestations, and lookup. Renaming them would break history, while deleting records triggers `record_deleted`. Leave ratified seeds and existing historical trailers alone.

The four unreviewed 2026-09-09 records offer a review-time choice: preferably accept their weak aliases as historical debt and improve only future records. If the owner considers readability critical before ratification, create new records with good aliases that supersede the old records, reject the old records, and use only the new aliases in future trailers. Do not rename or delete the old files, and do not rewrite existing commits. This preserves referential integrity but adds ledger noise, so it is justified only for the worst alias, especially `the-git-hooks-keep-reading-records-and-a`.

## Validation and skill wording

Validate `slug` as follows:

- Exactly 3 to 6 lowercase ASCII words separated by single hyphens.
- At most 40 characters, with no leading, trailing, or repeated hyphen.
- Characters match `^[a-z0-9]+(?:-[a-z0-9]+){2,5}$`.
- First word is an approved verdict verb such as `use`, `keep`, `defer`, `skip`, `allow`, `reject`, `require`, `pin`, `read`, `write`, or `validate`.
- Reject filler tokens `the`, `a`, `an`, `its`, `and`, `or`, `of`, `to`, and `in`. Do not reject `keep`.
- Reject an existing full alias collision and ask for a more specific slug instead of appending `-2`.
- Validate the final `D-YYMMDD-<slug>` independently against the alias schema.

Add this exact wording to `skills/decide/SKILL.md`:

> Add a required `slug` beside `title`. Write the slug as a 3 to 6 word, verdict-first summary of what was decided, not as the opening words of the title. Start with an action such as `use`, `keep`, `defer`, `skip`, `allow`, `reject`, `require`, or `pin`, then name the affected mechanism and distinguishing condition. Use only lowercase ASCII letters, digits, and single hyphens, with at most 40 characters. Omit articles, conjunctions, possessives, and setup words. Make the decision understandable without opening the record. Good: `defer-history-replay-check`, `skip-post-commit-during-rebase`, `pin-test-fixture-to-seeds`. Bad: `the-git-hooks-keep-reading-records`, `history-replay-validation-every-changed`.

Codex session ID: 01a0886e-b6c5-76a3-a396-868d3999abd2
Resume in Codex: codex resume 01a0886e-b6c5-76a3-a396-868d3999abd2
