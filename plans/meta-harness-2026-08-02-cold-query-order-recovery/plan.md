# Cold Query Order Recovery Evaluation Plan

## Run configuration

- Gate: PROCEED
- Intent: DELIVER
- Target: 8
- Target minimum: 8
- Maximum iterations: 1
- Artifact root: `plans/meta-harness-2026-08-02-cold-query-order-recovery`

## Sprint

1. Bind to integration generation 6, P6 finding
   `p6-cold-query-before-mutation`, and accepted launcher generation-7 receipt.
2. Evaluate cold and reused publisher-discovery query failures before every
   pane mutation, retained imperative/query behavior, lifecycle contracts, and
   the exact full matrix.
3. Stop on any command failure or score below 8; otherwise record SUCCESS and
   commit only this new evidence directory.

## Parallelization Strategy

Implementation parallelism: Sequential

Reason: P3 supplied one accepted launcher correction and P5 owns its exact
integration, order-sensitive evaluation, and receipt binding.

- Can parallelize: no
- Implementation lanes: none; accepted P3 generation 7 is an immutable input
- Sequential dependencies: validate tuple and receipt, integrate the fix, lock
  the rubric, verify cold and reused query order, score, commit evidence
- Verification: focused protocol assertions plus publisher and launcher Python
  suites, full Vitest, production build, browser smoke, and diff check
- Recommended Phase 3 Agent Split Gate input: Local only, because P6 supplied
  the routed finding and live pane operations are prohibited

## Stop routing

Any failed check or criterion below 8 returns an exact finding to P1. P5 does
not edit product code, install, push, deliver, modify Herdr Orchestrator, close
panes, or operate live panes.
