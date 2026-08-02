# Manifestless Viewer Delivery Evaluation Plan

## Run configuration

- Gate: PROCEED
- Intent: DELIVER
- Target: 8
- Target minimum: 7
- Maximum iterations: 2
- Artifact root: `plans/meta-harness-2026-08-02-manifestless-viewer`

## Sprint

1. Bind the evaluation to the approved design, plan, integration base, accepted
   publisher tip, and accepted launcher tip.
2. Evaluate the integrated candidate with focused source review and the exact
   repository verification matrix.
3. Stop immediately on a product finding and route it through P1; otherwise
   record SUCCESS and commit the evidence as one forward integration commit.

## Parallelization Strategy

Implementation parallelism: Sequential

Reason: P2 and P3 already produced independently accepted histories; P5 owns
their ordered integration and a single final-candidate evaluation.

- Can parallelize: no
- Implementation lanes: none; accepted publisher and launcher lanes are inputs
- Sequential dependencies: validate receipts and histories, integrate publisher,
  integrate launcher, evaluate the combined candidate, commit evidence
- Verification: both Python suites, Vitest, build, browser smoke, and diff check
- Recommended Phase 3 Agent Split Gate input: Local only, because independent
  P6-P9 review and QC are downstream gates and must not be folded into P5

## Stop routing

Any score below 8 or any product test/review finding stops P5 integration and is
reported to P1 with exact evidence. The locked rubric is never changed.
