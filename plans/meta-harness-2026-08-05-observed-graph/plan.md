# Meta-harness Plan: Observed Graph Truthfulness

Implementation plan: `docs/superpowers/plans/2026-08-05-herdr-graph-observed-events.md`

Implementation parallelism: Parallel lanes

Reason: Python publisher and frontend/skill paths are disjoint until P5
integration.

## Parallelization Strategy

- Can parallelize: yes.
- Implementation lanes: P2 publisher observation; P3 viewer truthfulness.
- Sequential dependencies: P5 integrates P2 then P3; P6 and P7-P9 evaluate the
  same immutable candidate.
- Verification: lane-local RED/GREEN checks followed by the full Python,
  Vitest, build, browser, launcher, live-workspace, parity, and review matrix.
- Recommended Phase 3 Agent Split Gate input: Spawn, because owned paths do not
  overlap and independent review is mandatory.

