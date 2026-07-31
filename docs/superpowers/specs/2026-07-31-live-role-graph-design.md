# Live Role Graph Design

**Status:** Approved direction, pending implementation-plan approval

**Date:** 2026-07-31

## Goal

Provide a local, read-only visualization that lets a user see the current
multi-agent orchestration state while P1 continues coordinating work.

The graph must place the orchestrator at the top, move forward work downward,
keep parallel roles on the same horizontal layer, and show an active failure
return as a loop. Nodes represent logical agent roles. A compact assignee chip,
such as `P5`, shows which Herdr slot currently covers the role; one slot may
cover multiple roles.

The viewer must support arbitrary role graphs. Herdr is one producer of the
protocol, not a hard-coded UI mode.

## Product Boundary

One repository owns the deliverable:

- `/Users/haido/multi-agent-graph-demo` owns the generic viewer, local snapshot
  API, and source adapters.

`/Users/haido/herdr-orchestrator` and the installed
`/Users/haido/.codex/skills/herdr-orchestrator` tree are read-only input
contracts. The visualization project does not add, edit, install, or sync files
in either location.

The viewer never dispatches agents, mutates orchestration state, writes
receipts, or closes panes. Its Herdr adapter never becomes part of P1's
controller loop. It runs as an independent sidecar from the viewer repository
and may be stopped without affecting delivery.

## User Experience

The page has three persistent regions:

1. A header with connection state and a scope/run selector.
2. A top-down graph canvas.
3. A compact event timeline for recent state transitions and loop activity.

On first load, the page fetches the latest snapshot for the selected scope and
run. It then listens for newer snapshots over server-sent events. Reloading the
browser must not lose the last known graph.

Forward links are direct straight connections. Active return links use a
straight-segment feedback gutter outside the forward graph, so the loop does
not cross through unrelated nodes.

The Live view shows:

- every logical role in the current flow;
- its current assignee chip, such as `P1`, `P5`, or a generic agent label;
- its current task and status;
- all forward dependencies;
- only the currently active failure return;
- recent events and the failure reason.

Potential failure policies are data in the snapshot but are not drawn until
active. A future Failure Map view may expose every policy without changing the
protocol.

## Generic Snapshot Protocol

The protocol is an immutable full snapshot. The browser does not rebuild
orchestration state from events.

```json
{
  "schemaVersion": "role-graph/v1",
  "scopeId": "herdr:wK",
  "runId": "role-graph-live-viewer-20260731",
  "sequence": 42,
  "generatedAt": "2026-07-31T10:15:00Z",
  "title": "Live role graph",
  "nodes": [
    {
      "id": "orchestrator",
      "role": "Orchestrator",
      "assignee": "P1",
      "layer": 0,
      "status": "running",
      "task": "Route ready work",
      "generation": 1
    }
  ],
  "edges": [
    {
      "id": "orchestrator-to-implementation",
      "source": "orchestrator",
      "target": "implementation",
      "kind": "forward",
      "status": "active"
    }
  ],
  "failurePolicies": [
    {
      "gateNodeId": "functional-qc",
      "returnToNodeId": "correction-owner",
      "ownerNodeId": "correction-owner",
      "resumeNodeId": "integration",
      "rerunNodeIds": ["integration", "independent-qc", "functional-qc"],
      "excludedNodeIds": ["implementation"]
    }
  ],
  "activeFailureRoute": null,
  "events": []
}
```

Required node statuses are `pending`, `running`, `passed`, `failed`,
`blocked`, `retrying`, `stale`, and `skipped`.

`layer` is optional. When present, equal layers are laid out horizontally. When
absent, the viewer derives layers from forward dependencies. Return edges never
participate in forward layout.

`resumeNodeId` is the first role that receives the corrected generation.
`rerunNodeIds` is the ordered set of roles that must rerun from that point
through the failed gate. `activeFailureRoute` repeats the selected policy
fields and adds `reason` and `generation`. This keeps the renderer deterministic
and avoids policy inference in the browser.

## Local API

The viewer server exposes:

- `POST /api/snapshots` to validate, persist, and broadcast a full snapshot;
- `GET /api/graphs` to list known scope/run pairs;
- `GET /api/snapshot?scopeId=...&runId=...` to hydrate the latest snapshot;
- `GET /api/stream?scopeId=...&runId=...` for filtered server-sent events.

Snapshots are keyed by the exact `(scopeId, runId)` pair. A new sequence must
be greater than the stored sequence for that key. The append-only JSONL file
supports restart hydration.

If `ROLE_GRAPH_INGEST_TOKEN` is set, POST requests require a matching bearer
token. Read endpoints remain local read-only endpoints.

## Herdr Role-Graph Manifest

The Herdr sidecar accepts a manifest rather than embedding one fixed workflow:

```json
{
  "schemaVersion": "herdr-role-graph-manifest/v1",
  "flowId": "standard-delivery",
  "title": "Herdr standard delivery",
  "nodes": [
    {
      "id": "orchestrator",
      "role": "Orchestrator",
      "assignee": "P1",
      "layer": 0,
      "source": {"type": "slot", "id": "P1"}
    },
    {
      "id": "integration",
      "role": "Integration",
      "assignee": "P5",
      "layer": 3,
      "source": {"type": "lane", "id": "integration"}
    }
  ],
  "edges": [],
  "failurePolicies": []
}
```

The publisher requires `--workspace-id` and refuses a state file whose
`workspace_id` differs. It reads only the supplied file and manifest. It does
not discover or combine other workspaces.

For each manifest node, the sidecar reads either one named slot or one named
lane. Lane state wins over slot state. Multiple logical roles may display the
same assignee chip. A lane in `FINDING` activates the matching failure policy;
the publisher supplies the complete active route to the viewer.

The sidecar supports one-shot and watch modes. Watch mode publishes only when
the workspace revision changes and uses bounded polling. Viewer/network failure
is reported without mutating or blocking Herdr.

## Layout and Rendering

The viewer removes return edges before layout. It uses a top-to-bottom Dagre
layout for forward dependencies and honors explicit layers by adding invisible
rank constraints. Nodes in one layer share the same vertical coordinate.

Forward edges use React Flow's straight path. Active return edges use a custom
polyline:

```text
source -> feedback gutter -> target row -> target
```

The gutter is placed beyond the graph bounds. This keeps the normal flow
readable and makes the loop direction unambiguous.

## Failure and Recovery Behavior

- Unknown or invalid snapshots return HTTP 400 and are not persisted.
- Stale sequences return HTTP 409 and are not broadcast.
- A missing selected graph shows an empty state, not demo agents.
- SSE reconnect triggers a fresh snapshot hydration.
- A stale, moved, or replaced Herdr pane remains a node with `stale` or current
  ledger status; it cannot freeze the UI.
- Publisher failure cannot stop P1, dispatch, integration, or QC.
- No viewer path contains a command that starts, closes, moves, or prompts an
  agent.

## Acceptance Criteria

1. The UI contains no hard-coded Bibi, Codex, Claude, Final, P1-P9 workflow, or
   fixed node aliases.
2. Two fixtures with different graph shapes render without source changes.
3. The orchestrator is at the top and explicit parallel layers align.
4. Forward relationships are visible as straight links.
5. An active gate failure renders a return loop through the feedback gutter.
6. Scope/run selection never mixes events or snapshots.
7. Browser reload hydrates the last persisted graph.
8. One Herdr live-state fixture produces a valid generic snapshot.
9. The same assignee can appear on multiple role nodes.
10. The publisher performs no Herdr mutation or agent command.
