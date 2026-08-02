# P1 Anchor Recovery Evaluation Plan

## Run configuration

- Gate: PROCEED
- Intent: DELIVER
- Target: 8
- Target minimum: 8
- Maximum iterations: 1
- Artifact root: `plans/meta-harness-2026-08-02-p1-anchor-recovery`

## Sprint

1. Bind to integration generation 3, the P6 `p6-right-of-p1-anchor`
   finding, and accepted launcher g4.
2. Evaluate selected-ledger P1 anchoring, pane isolation, lifecycle reuse,
   compatibility, and the exact full integration matrix.
3. Stop on any criterion below 8 or any failed check; otherwise record SUCCESS
   and commit only this new evidence directory.

## Parallelization Strategy

Implementation parallelism: Sequential

Reason: P3 already produced one accepted two-file correction; P5 owns its
single-candidate integration and verification.

- Can parallelize: no
- Implementation lanes: none; accepted launcher g4 is the only product input
- Sequential dependencies: validate receipt, cherry-pick fix, lock rubric,
  verify candidate, score, commit evidence
- Verification: launcher and publisher Python suites, Vitest, build, browser
  smoke, and diff check
- Recommended Phase 3 Agent Split Gate input: Local only, because P6 supplied
  the routed finding and live P7-P9 gates remain downstream

## Stop routing

Any failed command or score below 8 is reported to P1 without product edits,
installation, delivery, or live-pane operations.
