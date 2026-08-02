# End-to-End Provenance Recovery Evaluation Plan

## Run configuration

- Gate: PROCEED
- Intent: DELIVER
- Target: 8
- Target minimum: 8
- Maximum iterations: 1
- Artifact root: `plans/meta-harness-2026-08-02-end-to-end-provenance-recovery`

## Sprint

1. Bind to integration generation 9, P6 end-to-end provenance finding, and the
   accepted publisher generation-7 and persona UI generation-3 receipts.
2. Run a real `synthesize_manifest -> build_snapshot` producer probe, then
   evaluate the UI provenance consumer and full runtime matrix.
3. Stop on any command failure or score below 8; otherwise record SUCCESS,
   emit a trace, and commit only this new evidence directory.

## Parallelization Strategy

Implementation parallelism: Sequential

Reason: The disjoint accepted fixes form one producer-to-UI interface contract
and P5 must evaluate them on one combined candidate.

- Can parallelize: no
- Implementation lanes: none; accepted publisher g7 and persona UI g3 are
  immutable inputs
- Sequential dependencies: validate tuple and receipts, validate both
  preimages, integrate publisher, integrate persona UI, lock rubric, run real
  producer probe, run full matrix, score, emit trace, commit evidence
- Verification: direct producer assertion, publisher and launcher Python suites,
  full Vitest, production build, browser smoke, and diff check
- Recommended Phase 3 Agent Split Gate input: Local only, because proof must
  join producer output and UI consumption without P5 self-review as P6

## Stop routing

Any failed check or criterion below 8 returns an exact finding to P1. P5 does
not edit product code beyond accepted commits, install, synchronize, push,
deliver, modify source main or Herdr Orchestrator, close panes, operate live
panes, or perform P6 review.
