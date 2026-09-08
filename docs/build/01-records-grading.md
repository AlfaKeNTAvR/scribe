# DEMM grade of the three hand-written records

Written 2026-09-08 by the Fable 5.1 planner (step 1). Method: README section 12, Decision Evidence Maturity Model (arXiv 2605.04093). Four properties chosen in README section 15 ("who decided, what was rejected, which commit, was it verified"). Each cell is one of DEMM's evidence categories: `fully fillable` (the evidence exists and is in the record), `partially fillable` (the field exists, the evidence is incomplete or pending), `structurally unfillable` (the schema has no place for it), `opaque` (the record claims it but nothing lets a reader check). A record scores at its weakest property, not its average.

Records:

- R1 `D-260908-unreviewed-may-supersede-ratified` (A10)
- R2 `D-260908-one-way-door-defer-not-stop` (A13)
- R3 `D-260908-verbatim-quote-is-the-evidence` (A12)

## Grade table

| Property | R1 | R2 | R3 | Where the evidence lives |
|---|---|---|---|---|
| Who decided | fully fillable | fully fillable | fully fillable | `decided_by: human`, `ratified_by`, `ratified_at`, `history` ratified entries, the verbatim owner quote in `## Evidence`, and the attestation line in `RATIFICATIONS.jsonl` pinned to the body hash |
| What was rejected | fully fillable | fully fillable | fully fillable | `## Options considered` table: 3 rejected rows each with a `Why rejected` cell, one row `chosen`; R2 also names the earlier README rule it overrides (D9) |
| Which commit | partially fillable | partially fillable | partially fillable | `implementation_links` is empty and `effective_state: proposed` because no code exists yet; the `Decision:` trailer and `post-commit` hook (plan section 5) fill it once T4/T12 (R1), T8/T14 (R2), T2/T8 (R3) land. The field exists, so this is pending, not unfillable |
| Was it verified | partially fillable | partially fillable | partially fillable | Each record has `verify` entries (grep engine) that `scribe lint` runs; today they fail or are vacuous because the target files do not exist. R2's core claim ("never act without ratification") needs a runtime test of the Bash gate, which is shadow-only in this run; the deferred two-worktree test (plan 7.4) covers R1 |

Record level (weakest property): all three are `partially fillable` on "which commit" and "was it verified". DEMM level for the ledger as it stands: level 2, Process-attested (who decided and what was rejected are attested by the ratification process and the quote); it reaches level 3, Property-instrumented, when `post-commit` links land and `scribe lint` runs the `verify` entries green.

## Container-fallacy check

DEMM's warning is a complete-looking log that cannot say who authorized an action or whether it changed the target. Per record:

- Who authorized: answered by the quote plus attestation in all three. Not a container.
- Did it change the target: not yet answerable for any of the three (no implementation). The records say so explicitly (`effective_state: proposed`, empty links) rather than implying completion. Acceptable at step 1; becomes a defect if the links are still empty after step 5.

## Structurally unfillable check (README 15: "if any property is structurally unfillable by design, the schema needs a field, not more discipline")

- None of the four properties is structurally unfillable. Two near misses worth noting for the reviewer:
  1. Transcript pointers (`provenance.source_messages`) are empty in all three and will stay empty for hand-written records. By R3's own decision this is `opaque` for the pointer but `fully fillable` for the proof (the quote), so no schema change.
  2. "Was it verified" for a behavioural rule like R2 cannot be closed by a grep `verify` entry; it needs a test. The schema has no `verify` engine for "run this pytest node". Proposed default: do not add an engine now (the allowlist stays `grep`); record the test path in `## Evidence` when it exists and let lint's `verify_failed` stay a weak signal. Batched question for the owner: add `engine: pytest` with a node id in a later run.

## Next-morning recovery test (README 15 step 1)

Can a reader recover the choice, the alternatives and the implementing changes from the files and `git log` alone?

- Choice: yes, from the H1, the Y-statement and `## Decision`.
- Alternatives: yes, from `## Options considered`.
- Implementing changes: not yet; recoverable once commits carry `Decision: <alias> <ulid>` trailers (`git log --grep=<alias>`) and `post-commit` writes the links. Step 5 re-runs this check.
