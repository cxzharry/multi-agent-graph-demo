# Live Runtime Recovery Evaluation Plan

## Run configuration

- Gate: PROCEED
- Intent: DELIVER
- Target: 8
- Target minimum: 8
- Maximum iterations: 1
- Artifact root: `plans/meta-harness-2026-08-02-live-runtime-recovery`

## Sprint

1. Bind to integration generation 4, the P7 live-runtime finding, and accepted
   publisher/launcher generation-5 receipts.
2. Evaluate imperative Herdr compatibility, explicit replacement safety,
   sequence/store compatibility, lifecycle contracts, and the exact full matrix.
3. Stop on any command failure or score below 8; otherwise record SUCCESS and
   commit only this new evidence directory.

## Parallelization Strategy

Implementation parallelism: Sequential

Reason: P2 and P3 already produced accepted, complementary runtime fixes; P5
owns their ordered integration and combined verification.

- Can parallelize: no
- Implementation lanes: none; accepted P2 g5 and P3 g5 are immutable inputs
- Sequential dependencies: validate receipts, integrate P2, integrate P3, lock
  rubric, verify combined candidate, score, commit evidence
- Verification: publisher and launcher Python suites, full Vitest, production
  build, browser smoke, and diff check
- Recommended Phase 3 Agent Split Gate input: Local only, because P7 supplied
  the routed finding and live runtime/pane operations are prohibited

## Stop routing

Any failed check or criterion below 8 returns an exact finding to P1. P5 does
not edit product code, install, push, deliver, or operate live panes.
