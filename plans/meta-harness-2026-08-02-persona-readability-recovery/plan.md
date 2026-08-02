# Persona Readability Recovery Evaluation Plan

## Run configuration

- Gate: PROCEED
- Intent: DELIVER
- Target: 8
- Target minimum: 8
- Maximum iterations: 1
- Artifact root: `plans/meta-harness-2026-08-02-persona-readability-recovery`

## Sprint

1. Bind to integration generation 7 and the accepted publisher generation-6
   and persona UI generation-1 receipts.
2. Evaluate live lane-to-P identity, meaningful deterministic snapshot time,
   timestamp normalization, role-first compact nodes, retained graph contracts,
   and the exact full matrix.
3. Stop on any command failure or score below 8; otherwise record SUCCESS and
   commit only this new evidence directory.

## Parallelization Strategy

Implementation parallelism: Sequential

Reason: The two accepted lanes are immutable inputs and P5 owns their ordered
integration plus one shared browser/runtime evaluation of the combined result.

- Can parallelize: no
- Implementation lanes: none; accepted publisher g6 and persona UI g1 commits
  are immutable inputs
- Sequential dependencies: validate both receipts and preimages, integrate the
  publisher, integrate the persona UI, lock rubric, verify combined candidate,
  score, emit trace, commit evidence
- Verification: publisher and launcher Python suites, full Vitest, production
  build, browser smoke, and diff check
- Recommended Phase 3 Agent Split Gate input: Local only, because evaluation
  uses one combined candidate and live pane operations are prohibited

## Stop routing

Any failed check or criterion below 8 returns an exact finding to P1. P5 does
not edit product code, install, sync, push, deliver, modify Herdr Orchestrator,
close panes, or operate live panes.
