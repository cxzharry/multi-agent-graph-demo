# Herdr Graph Observed Events and Truthful Relationships Design

**Date:** 2026-08-05  
**Status:** Approved

## Problem

The graph viewer currently exposes two misleading fallbacks:

- session mode publishes `events: []`, so a live Herdr session can show no
  activity even while agents are working;
- manifestless control mode draws every lane as a direct child of P1, although
  `workspace-state.json` does not prove those relationships.

The renderer is displaying the published snapshot correctly. The missing
activity and false relationships originate in the publishers.

## Goals

1. A newly invoked viewer immediately shows timestamped lifecycle activity for
   every currently observed node.
2. Later topology, status, and assignee changes append ordered events without
   duplicates or ledger churn on unchanged polls.
3. Session and synthetic modes never claim workflow relationships that their
   sources cannot prove.
4. Custom manifests remain authoritative for exact edges, gates, and failure
   loops.
5. The work changes only the graph viewer repository and its installed
   `herdr-graph-viewer` snapshot; every other skill and Herdr orchestration
   contract remains unchanged.

## Non-goals

- Streaming prompt text, commands, tool calls, token usage, or raw agent logs.
- Installing global hooks or automatically starting the viewer.
- Inferring dependencies from P numbers, role names, timestamps, pane layout,
  or status order.
- Changing `herdr-orchestrator`, `writing-plans`, Superpowers, Herdr itself, or
  any other installed skill.
- Replacing custom manifests with generated topology.

## Chosen Architecture

### Observer-first lifecycle ledger

Both publishers use one small, deterministic transition ledger. It compares a
current node projection with the previous projection already held by the
publisher.

On the first observation it emits one lifecycle event per node, including the
node's current status. On later observations it emits events only for:

- a newly observed node;
- a status change;
- an assignee change;
- a node that disappears from the observed source.

Each event contains a stable event ID, UTC timestamp, node ID, generation when
available, kind, and human-readable message. The ledger retains only the most
recent bounded set of events. An unchanged poll emits no snapshot and no event.

The observer uses the polling loops that already run for presence and state
updates. It adds no new process, hook, polling interval, or cross-workspace
query.

### Publisher behavior

Session mode builds its current node projection from the already filtered
workspace-local result of `herdr agent list`. The first published snapshot is
therefore useful immediately rather than waiting for a future transition.

Control mode preserves authored `workspace-state.json.events` in their existing
order and adds observer events for lifecycle changes. Authored IDs remain
unchanged; observer IDs occupy a separate namespace. Repeated construction of
the same revision remains deterministic, and watch mode alone supplies wall
clock observation timestamps.

Publisher restart may seed its bounded observer history from the latest exact
`scopeId + runId` snapshot already stored by the viewer. Failure to retrieve a
seed is non-fatal and never changes workspace selection. A seed from another
scope or run is rejected.

### Truthful relationship modes

Relationship provenance has two states:

- **Declared:** a custom manifest supplies exact nodes, edges, gates, and
  failure policies. Existing behavior is preserved byte-for-byte except for
  lifecycle events that describe observed state.
- **Unavailable:** session or synthetic mode has nodes and statuses but no
  trusted workflow-edge source. P1 remains in layer 0 and observed agents or
  lanes remain in layer 1 for readable layout, but the publisher emits no
  edges or failure routes.

The frontend identifies the existing `live-session` and `auto-operational`
flows as observed topology. It displays a concise notice:

> Observed topology — relationships unavailable

The notice explains that an exact custom topology is required for workflow
edges. It must not appear for authored custom flows.

### Compatibility and isolation

The existing `role-graph/v1` schema remains unchanged. The design reuses
existing `flowId` provenance rather than adding a new wire field. Historical
snapshots remain readable, including old synthetic snapshots containing control
edges.

All changes stay within:

- `adapters/herdr/` publisher code and tests;
- `src/` graph presentation and tests;
- browser smoke coverage;
- `skills/herdr-graph-viewer/` documentation and launcher tests only when
  required by the verified behavior;
- this feature's design, plan, and meta-harness evidence.

The installed skill is synchronized only from the reviewed repository subtree
after all gates pass. Synchronization must not touch sibling skill directories.

## Error Handling

- A malformed current observation leaves the last valid snapshot intact and
  reports an exact publisher error.
- Seed retrieval failure starts a fresh bounded event ledger without blocking
  graph publication.
- A seed with mismatched scope or run is ignored or rejected, never merged.
- Unknown agent statuses continue to render as stale and still receive an
  initial observed event.
- Disappearing nodes produce one terminal observation event and are then absent
  from the current node set.

## Performance Contract

- Keep the existing two-second publisher interval.
- Perform one linear comparison over the selected nodes per changed poll.
- Retain a bounded event history; no unbounded in-memory or JSONL growth from
  unchanged polling.
- Presence heartbeats remain in memory and do not append snapshots.
- No raw session-log scan, prompt parsing, or recursive workspace discovery.

## Verification

TDD must prove:

1. session mode emits initial timestamped events for P1 and every current local
   agent;
2. one status transition emits exactly one new event and an unchanged poll
   emits none;
3. removal and assignee changes are represented once;
4. event ordering and retention are deterministic;
5. session and synthetic snapshots contain zero fabricated edges;
6. custom manifest edges, failure policies, and loops remain exact;
7. workspace filtering and exact `scopeId + runId` seed identity are enforced;
8. server persistence, SSE, Active/History presence, and historical URLs do not
   regress;
9. the UI notice appears only for observed topology;
10. unit tests, build, browser smoke, launcher tests, live current-workspace
    launch, independent review, and installed/source parity pass.

## Meta-harness Rubric

The run uses `Intent: IMPROVE`, `max-iter=until-pass`, and a 120-minute wall
clock budget. Success requires every locked criterion to score at least 8.5:

- event correctness and usefulness;
- relationship truthfulness;
- runtime efficiency and boundedness;
- compatibility and cross-skill isolation;
- live browser and current-workspace evidence.

