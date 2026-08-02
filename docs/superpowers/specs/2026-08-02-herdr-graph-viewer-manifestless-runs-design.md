# Herdr Graph Viewer Manifestless Runs Design

**Date:** 2026-08-02
**Status:** Approved direction; awaiting written-spec review

## Problem

`$herdr-graph-viewer` currently requires a role-graph manifest selected through
`--manifest`, `run.role_graph_manifest`, or a run-local
`role-graph-manifest.json`. A valid P1 run that has only
`workspace-state.json` therefore fails with `missing_manifest` even though the
ledger contains enough information to display live agents, lanes, tasks, and
statuses.

The viewer and orchestrator are intentionally separate:

- `$herdr-orchestrator` owns orchestration and `workspace-state.json`;
- `$herdr-graph-viewer` is optional, explicitly invoked, and read-only with
  respect to orchestration;
- invoking either skill must not implicitly invoke or configure the other.

Making the orchestrator emit viewer files would couple the two skills. Making
the viewer maintain a generated manifest file would introduce state/manifest
skew, locking, cleanup, and generated-file precedence problems.

## Goals

1. Invoking `$herdr-graph-viewer` for any valid P1 ledger starts or reuses a
   graph without manual manifest setup.
2. Existing custom manifests retain precedence and exact authored topology.
3. Manifestless runs reflect new lanes and reassignment at the same ledger
   revision that contains them.
4. The viewer never writes to the orchestrator run directory or ledger.
5. Synthetic topology never invents dependencies, gate order, or failure
   loops that are absent from the ledger.
6. The launcher does not create viewer panes underneath P1 or close panes.
7. Existing protocol, workspace isolation, custom-manifest behavior, process
   reuse, and quality gates do not regress.

## Non-goals

- Changing `$herdr-orchestrator`, its installed skill, or its runtime schema.
- Generating or caching `role-graph-manifest.json` automatically.
- Inferring an arbitrary workflow DAG from lane names, P-slot numbers, or fixed
  Herdr roles.
- Adding a manifest export command before a concrete need exists.
- Streaming raw agent activity or installing a global hook.
- Changing the `role-graph/v1` wire schema or viewer server.

## Architecture

### Ownership boundary

The orchestrator remains the sole writer of `workspace-state.json`. The viewer
launcher selects that ledger, and the publisher reads it. No viewer process
modifies the ledger, its run directory, receipts, panes containing agents, or
orchestration state.

When no custom manifest exists, the publisher derives a manifest-shaped object
in memory from the same parsed state object used to build the snapshot. The
object is never serialized to disk.

This keeps one consistency boundary:

```text
atomic workspace-state.json revision
              |
              v
       one publisher read
              |
      +-------+--------+
      |                |
synthetic topology   live status/events
      |                |
      +-------+--------+
              |
       role-graph snapshot
```

### Manifest selection

The launcher uses the following precedence:

1. explicit `--manifest`;
2. `run.role_graph_manifest`;
3. run-local `role-graph-manifest.json`;
4. synthetic mode.

The first three are custom mode and preserve current behavior. If a custom
source is explicitly configured but missing, unreadable, malformed, or invalid,
launch fails clearly. The launcher must not silently replace a broken custom
topology with a synthetic graph.

Only the absence of every custom source selects synthetic mode. The publisher
CLI represents the two modes as mutually exclusive arguments:

```text
--manifest /absolute/path/to/manifest.json
--synthesize
```

### Synthetic operational graph

Synthetic mode produces a live operational view, not an inferred delivery
flow. Its title identifies it as an automatic operational graph while keeping
the existing wire schema unchanged.

The graph contains:

- one Orchestrator node sourced from P1;
- one logical node for each lane supersession chain;
- a control edge from P1 to every logical lane node;
- no inferred lane-to-lane handoff edges;
- no inferred failure policies.

Each logical lane node exposes the latest lane's role/task label, assignee slot,
status, and generation. Ordering and generated identifiers are deterministic so
the same state produces the same snapshot.

Because `workspace-state.json` does not encode dependency edges, synthetic mode
does not claim to show integration order, gate sequencing, or return loops. A
custom manifest remains the mechanism for those exact semantics.

### Lane reassignment

Reassignment creates a new lane whose `supersedes` field points to its
predecessor. The publisher builds a predecessor-to-successor index once per
state revision.

For a valid chain:

- the earliest predecessor is the logical lane identity;
- the unique latest successor supplies current state, generation, assignee, and
  task;
- all events referring to any chain member map to the same rendered node;
- superseded generations do not appear as duplicate active agents.

A custom node sourced from any member of the chain resolves to the same latest
successor, so authored placement survives reassignment.

A branch or cycle in `supersedes` is invalid ledger data. One-shot publishing
fails with an exact error. Watch mode reports the error, retains the last valid
snapshot, and retries on subsequent polls without looping or mutating state.

### Dynamic lanes with custom topology

Custom topology is authoritative for every node and edge it declares. A newly
registered lane that is not part of any authored source or supersession chain
must still remain observable.

The publisher appends each unmapped logical lane as a deterministic live-addition
node. If the custom graph contains exactly one node sourced from slot P1, the
publisher connects P1 to the live addition with a control edge. Otherwise it
adds the node without inventing a relationship. It does not insert the lane into
authored integration, review, QC, delivery, or failure routes.

Once a later custom manifest maps that lane, the live-addition projection
disappears and the authored node takes precedence.

### Process identity and mode changes

A publisher reuse key is:

```text
(workspace_id, absolute_state_path, mode)
```

Custom mode includes the absolute manifest path in `mode`; synthetic mode uses
the literal `synthetic`. Re-invoking the same key reuses the healthy publisher.

If the selected run changes between synthetic and custom mode, the launcher
stops only the old viewer-owned publisher process and starts the replacement in
the same viewer pane. It never closes, moves, or focuses the pane and never sends
input to an agent pane. This prevents duplicate publishers for one state while
allowing a custom manifest to take effect after a synthetic launch.

### Pane layout

On a cold launch, the viewer creates a right-side process rail:

1. the server pane is split to the right of P1;
2. the publisher pane is split below the server inside that right-side rail.

Neither pane is created below P1. The launcher preserves user focus, reuses
healthy panes, and never closes panes. Pane placement is a separate implementation
commit and test boundary from manifestless selection even when delivered in the
same release.

## Error behavior

| Condition | Result |
|---|---|
| No custom manifest exists | Start in synthetic mode |
| Explicit/configured custom path is missing | Fail with a custom-manifest error |
| Custom JSON/schema is invalid | Fail; never fall back silently |
| State belongs to another workspace | Refuse launch/publish |
| Supersession branch or cycle | Keep last valid live snapshot and report exact error |
| Unknown custom lane source | Preserve current pending behavior unless a valid successor resolves it |
| Viewer network/server failure | Report without mutating or blocking orchestration |

## Compatibility

- Custom-manifest selection order is unchanged; synthetic mode only replaces
  the terminal `missing_manifest` case.
- `role-graph/v1` and the server validation contract are unchanged.
- Publisher remains read-only and snapshot-driven.
- Scope/run filtering, ledger event order, timeline timestamps, failure-route
  rendering, reload hydration, and unknown graph selection remain unchanged.
- The installed `$herdr-graph-viewer` skill is synchronized only after source
  verification and independent QC.

## Implementation boundaries

Only the graph viewer repo changes:

- `skills/herdr-graph-viewer/scripts/start_viewer.py` for selection, argv/process
  matching, mode replacement, and right-side pane layout;
- `adapters/herdr/publisher.py` for deterministic synthesis, supersession
  resolution, event mapping, and unmapped live additions;
- their existing unit tests;
- `skills/herdr-graph-viewer/SKILL.md` for the manifestless-run contract.

The server, frontend protocol types, and every file in `herdr-orchestrator` stay
unchanged unless a failing compatibility test proves a narrower required edit
and the user approves that scope expansion.

## Verification

The implementation must prove:

1. a valid state without a manifest launches successfully in synthetic mode;
2. the same state produces byte-equivalent graph content across repeated builds;
3. a lane registered at revision N appears in snapshot sequence N;
4. a valid reassignment chain remains one logical node and maps all chain events;
5. supersession cycles and branches fail safely;
6. custom selection precedence and authored topology remain unchanged;
7. broken custom manifests fail instead of falling back;
8. unmapped custom-run lanes appear only as live additions;
9. publisher AST/read-only guards still pass;
10. repeated launch reuses the correct server/publisher and mode changes do not
    create duplicates;
11. cold launch places both viewer processes in a right-side rail, never below
    P1;
12. unit tests, build, browser smoke, health identity, workspace/run isolation,
    installed/source parity, and independent review/QC pass.

## Acceptance criteria

- A P1 session with only `workspace-state.json` opens a useful live graph when
  `$herdr-graph-viewer` is invoked.
- No automatic manifest or cache file is created.
- The orchestrator remains unaware of viewer invocation.
- Dynamic work and reassignment cannot disappear from the graph.
- Synthetic mode communicates only relationships proven by the ledger.
- Exact flow relationships and failure loops remain available through optional
  custom manifests.
- No viewer pane obscures P1 from below, and no pane is automatically closed.
