# Query Strictness Recovery Evaluation Plan

## Run configuration

- Gate: PROCEED
- Intent: DELIVER
- Target: 8
- Target minimum: 8
- Maximum iterations: 1
- Artifact root: `plans/meta-harness-2026-08-02-query-strictness-recovery`

## Sprint

1. Bind to integration generation 5, P6 finding
   `p6-empty-query-strictness`, and accepted launcher generation-6 receipt.
2. Evaluate strict empty-query rejection, failure-before-mutation behavior,
   preserved empty imperative success, launcher compatibility, and the exact
   full matrix.
3. Stop on any command failure or score below 8; otherwise record SUCCESS and
   commit only this new evidence directory.

## Parallelization Strategy

Implementation parallelism: Sequential

Reason: P3 supplied one accepted launcher correction and P5 owns its exact
integration, evaluation, and receipt binding.

- Can parallelize: no
- Implementation lanes: none; accepted P3 generation 6 is an immutable input
- Sequential dependencies: validate tuple and receipt, integrate the fix, lock
  the rubric, verify the candidate, score, commit evidence
- Verification: publisher and launcher Python suites, full Vitest, production
  build, browser smoke, and diff check
- Recommended Phase 3 Agent Split Gate input: Local only, because P6 supplied
  the routed finding and live pane operations are prohibited

## Stop routing

Any failed check or criterion below 8 returns an exact finding to P1. P5 does
not edit product code, install, push, deliver, modify Herdr Orchestrator, or
operate live panes.
