# Provenance Recovery Evaluation Plan

## Run configuration

- Gate: PROCEED
- Intent: DELIVER
- Target: 8
- Target minimum: 8
- Maximum iterations: 1
- Artifact root: `plans/meta-harness-2026-08-02-provenance-recovery`

## Sprint

1. Bind to integration generation 8, independent review generation-7 finding,
   and accepted persona UI generation-2 receipt.
2. Evaluate provenance-keyed internal hiding, authored auto-shaped identity
   visibility, retained synthetic readability, and the exact full matrix.
3. Stop on any command failure or score below 8; otherwise record SUCCESS,
   emit a trace, and commit only this new evidence directory.

## Parallelization Strategy

Implementation parallelism: Sequential

Reason: P5 integrates one accepted four-file provenance fix and evaluates one
shared browser/runtime candidate.

- Can parallelize: no
- Implementation lanes: none; accepted persona UI g2 is an immutable input
- Sequential dependencies: validate tuple and receipts, validate preimage,
  integrate the fix, lock rubric, verify candidate, score, emit trace, commit
  evidence
- Verification: publisher and launcher Python suites, full Vitest, production
  build, browser smoke, and diff check
- Recommended Phase 3 Agent Split Gate input: Local only, because this is an
  order-dependent fix-forward and P5 must not self-review as P6

## Stop routing

Any failed check or criterion below 8 returns an exact finding to P1. P5 does
not edit product code beyond the accepted commit, install, synchronize, push,
deliver, modify Herdr Orchestrator, close panes, operate live panes, or perform
P6 review.
