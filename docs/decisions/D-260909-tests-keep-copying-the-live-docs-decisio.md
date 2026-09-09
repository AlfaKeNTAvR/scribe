---
id: 01M23XZP08PK2M4VCJHZCPS7YC
alias: D-260909-tests-keep-copying-the-live-docs-decisio
title: Tests keep copying the live docs/decisions ledger as their fixture; a synthetic fixture set and an isolated timing-test purge wait for the first unrelated breakage
date: '2026-09-09'
schema_version: 1
task_refs: []
review_state: unreviewed
effective_state: proposed
decided_by: agent-recommended
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
- {type: path, pattern: tests/conftest.py}
- {type: path, pattern: tests/test_timing.py}
- {type: path, pattern: tests/fixtures/**}
implementation_links: []
tags:
- tests
- fixtures
- dogfooding
- deferred
- codex-finding
reversibility: two-way-door
blast_radius: component
regret_when: A new dogfood record in docs/decisions breaks tests that count or name the seed records, or the timing test's bytecode purge touches the real checkout.
review: '2026-12-08'
verify:
- {id: conftest-pins-seed-records, engine: grep, pattern: SEED_RECORD_ALIASES, paths: [tests/conftest.py], expect: match, severity: warning}
supersedes: null
relates_to: []
history:
- {at: '2026-09-09T20:33:09Z', event: proposed, by: claude-code, session: session_01A6tVoZuuWqu56QxEqtAjRw}
---

# Tests keep copying the live docs/decisions ledger as their fixture; a synthetic fixture set and an isolated timing-test purge wait for the first unrelated breakage

> In the context of the Codex validation finding V23 (the suite copies the live ledger into its fixtures, so dogfooding can break unrelated tests, and the timing test purges bytecode in the real tree), facing the choice between rewriting the fixtures now or after v0.1.0, I decided to defer the rewrite and record the coupling, to achieve a v0.1.0 whose tests are the ones that validated the code, accepting that each new dogfood record may need a test count adjusted, which is why the first breakage of that kind triggers the rewrite.

## Question

Should the test suite stop copying docs/decisions (three seed records, the ledger and INDEX.md) into its fixtures and instead use stable synthetic records under tests/fixtures, and should test_timing.py purge bytecode from a temporary copy rather than the checkout? Codex rated this minor (V23), effort M. The V1 half of V23 (hook tests that never exercised uv startup failure) was fixed by tests/test_supervise.py.

## Criteria

- Dogfooding scribe on its own repository must not break tests that have nothing to do with the new record.
- The suite must not modify the real checkout (bytecode purge).
- The tests that validated today's 44 commits stay green through the rewrite.

## Constraints and assumptions

- The live ledger is the only realistic fixture with attestations, relinked history and implementation_links; synthetic fixtures would have to reproduce that shape.
- Records written by this same deferral batch (V7, V13, V23, and the rebase post-commit finding) are the first dogfood records after the seeds and are the immediate test of this coupling.
- Assumption filled in by the agent: tests that assert on record counts or seed aliases are few enough that adjusting them per new record costs less than the rewrite, until proven otherwise.

## Options considered

| Option | For | Against | Evidence | Why rejected |
|---|---|---|---|---|
| Defer the fixture rewrite; pin the fixture copy to the three seed records by alias (and to their attestation lines) so later dogfood records never enter it; rewrite at the first breakage the pinning cannot absorb | No test churn before v0.1.0; keeps the realistic fixture; a five-line filter in conftest | The fixture never sees a record shape newer than the seeds; the timing test keeps purging in the checkout | docs/build/06-validation-triage.md Batch C; tests/conftest.py; the first four dogfood records turned test_session_start_registers_session_and_is_quiet_with_empty_queue red on 2026-09-09 | chosen |
| Rewrite now: freeze three synthetic records under tests/fixtures with a matching ledger, point conftest at them, copy the tree for the timing purge | Decouples dogfooding from the suite for good | Effort M; the synthetic ledger must carry valid attestation hashes and relink history, so it is generated code, and any schema change means regenerating it | docs/build/04b-codex-validation.md V23 | Effort not justified before the coupling has actually bitten; deferred, not rejected |
| Keep copying the live ledger but pin the copy to a fixed git revision (git show <rev>:docs/decisions/...) | Cheap; stable | Tests then validate a ledger that drifts from the schema and writers as they evolve; a stale ledger hides regressions | reasoning | Trades one coupling for a silent one |

## Decision

tests/conftest.py copies only the three seed records, pinned by alias in SEED_RECORD_ALIASES, and only the attestation lines that belong to them; every later record in docs/decisions (unreviewed or ratified) stays out of the fixture. test_timing.py keeps its current purge for v0.1.0. The first breakage that this pinning cannot absorb (a schema change the seeds do not exercise, or a test that needs a newer record shape) triggers the synthetic-fixture rewrite (effort M) and the temp-copy purge together.

## Consequences

- Positive: no test churn before the tag; fixtures stay realistic; dogfooding cannot turn the suite red through the ledger copy.
- Negative: the fixture is frozen at the seed records' shape; a writer change that only shows on newer records is not exercised by the copied ledger.
- Requires: the pinning lands in the same commit as these records; any test that wants a newer record builds it itself.
- Measure: number of fixture edits caused by new records after the pinning; any before the review date triggers the rewrite early.

## Evidence

> Go ahead

- Owner (Nikita Boguslavskii) to Claude Fable 5.1, Claude Code session session_01A6tVoZuuWqu56QxEqtAjRw, 2026-09-09, approving the triage order of work in docs/build/06-validation-triage.md.
- docs/build/04b-codex-validation.md, finding V23 (Codex gpt-6-astra, 2026-09-08 21:51).
- docs/build/06-validation-triage.md, section Batch C, and the note that the V1 half of V23 is done in tests/test_supervise.py.
