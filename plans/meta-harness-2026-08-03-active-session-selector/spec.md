# Active Session Selector Meta-Harness Spec

Deliver the approved design in
`docs/superpowers/specs/2026-08-03-herdr-active-session-selector-design.md`.
The evaluator must prove that fresh workspace-local presence, not persisted P1
status, determines Active membership; historical graphs remain exact and
readable; compact labels distinguish spaces without opaque IDs; and launcher,
publisher, pane, and workspace boundaries do not regress.

## Testable Behaviors

- Two fresh publishers from two spaces produce exactly two Active options.
- A publisher missing for more than six seconds moves its graph to History.
- A working current P1 renders `RUNNING`; a completed historical P1 renders
  `DONE`.
- Heartbeats do not append snapshot ledger records.
- An exact historical URL never silently selects a different graph.

## Parallelization Strategy

- Can parallelize: yes.
- Implementation lanes: P2 session publisher/presence client; P3 server,
  protocol, store, and selector UI; P4 launcher and installed-skill source.
- Sequential dependencies: P5 integrates the three lane commits; P6 review
  precedes P7 final functional QC; all gates precede installed-skill sync/push.
- Verification: focused tests per lane, then full unittest/Vitest/build/browser
  smoke and independent functional/layout/persona review.
- Recommended Phase 3 Agent Split Gate input: Spawn through Herdr Standard,
  because file ownership is disjoint and integration is receipt-gated.
