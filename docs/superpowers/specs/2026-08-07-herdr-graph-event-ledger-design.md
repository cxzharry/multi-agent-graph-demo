# Herdr Graph Event Ledger and Truthful Live Workflow Design

**Date:** 2026-08-07  
**Status:** Approved design; implementation not started

## Problem

The current live-session graph has regressed against the intended product:

- it maps Herdr agent `done` directly to node `PASSED`, so a live P1
  controller can appear completed;
- it intentionally publishes `edges: []`, so a live run cannot show dispatch,
  artifact handoff, integration, review, or rework relationships;
- it removes workers when their panes disappear, so the current run loses its
  completed workflow;
- it cannot represent flexible workflows unless an exact custom topology was
  authored in advance.

This is a source-model problem, not a rendering-only bug. Agent liveness, task
outcome, and workflow relationships must have separate authoritative sources.

## Approved Product Outcome

The viewer must show a truthful, top-down graph of agent assignments:

1. P1 Orchestrator is the top node and remains `RUNNING` while the controller
   session is alive.
2. Parallel implementation agents are aligned on the same rank.
3. The primary workflow shows actual artifact handoffs, for example
   `P2/P3/P4 -> P5 Integration -> P6 Independent QC`.
4. P1 retains all orchestration authority. Its currently active dispatch or
   reroute is shown as one dashed control edge, not as a permanent P1-to-all
   ownership star.
5. A failed gate shows a visible return loop from the reviewer or QC agent to
   the remediation owner, followed by the new handoff through integration and
   independent QC.
6. Only agent assignments are nodes. Tasks, artifacts, gates, and events are
   labels, badges, edges, or timeline entries, never standalone nodes.
7. Each node displays a role name and a compact `P2`-style slot badge. It does
   not display `P2 - lane 2`.
8. Agent liveness and work result are separate. A finished worker may display
   `OFFLINE + PASS`; a reworking worker may display `RUNNING + REWORK`.
9. Completed worker nodes and their workflow edges remain visible until the
   run reaches a terminal state.
10. Historical edges remain visible but muted. The current path is highlighted
    and shows recent activity time.

## Source-of-Truth Architecture

### 1. Workspace-local live observer

The existing publisher continues to read Herdr's current workspace-local agent
state. It is authoritative only for agent liveness:

- `RUNNING`: the bound agent is actively working;
- `IDLE`: the bound agent exists but is waiting;
- `OFFLINE`: an assignment existed in this run but its agent is no longer
  observed;
- `STALE`: observation freshness has exceeded the allowed window.

P1 is special: while the exact controller session exists in the workspace, its
node is `RUNNING`, even if Herdr transiently reports the conversational agent as
`done` between controller turns. `PASSED` is never a liveness value.

No cross-workspace agent is queried, adopted, or merged.

### 2. Run-local flow journal

Invoking `herdr-graph-viewer` creates or reuses an append-only event journal
bound to the exact `workspace_id + run_id`. The journal is authoritative for
workflow relationships and current control activity.

The minimum event envelope is:

```json
{
  "schemaVersion": "role-graph-event/v1",
  "eventId": "stable-id",
  "workspaceId": "wK",
  "runId": "run-id",
  "at": "2026-08-07T09:47:00Z",
  "kind": "ARTIFACT_HANDOFF",
  "sourceAssignmentId": "implementation-ui:g1",
  "targetAssignmentId": "integration:g1",
  "laneId": "integration",
  "generation": 1,
  "artifactIdentity": {"commit": "...", "tree": "..."}
}
```

Supported semantic transitions are deliberately small:

- `CONTROL_DISPATCH`: P1 dispatches or reroutes one agent assignment;
- `ARTIFACT_HANDOFF`: one agent's accepted output becomes another agent's
  input;
- `ASSIGNMENT_RESULT`: an assignment records `PASS`, `FAIL`, `BLOCKED`, or
  `SKIPPED` separately from liveness;
- `REWORK_ROUTE`: a reviewer or QC finding returns to one remediation owner;
- `CONTROLLER_RECOVERED`: a replacement controller continues the same run;
- `RUN_TERMINAL`: the run finishes and freezes its current projection.

Events are explicit facts. The system must not infer workflow edges from P
numbers, role names, timestamps, pane positions, or status order.

### 3. Optional P1 emitter

After the viewer is invoked in a P1 session, the graph-viewer skill exposes a
local emitter and instructs the current controller to record the semantic
transition alongside the orchestration action it already performs. The emitter
belongs to `herdr-graph-viewer`; the installed `herdr-orchestrator` skill is not
modified or overwritten.

The emitter records only decisions P1 already knows: dispatch, accepted output,
integration handoff, review handoff, finding route, recovery, and terminal run.
Workers do not coordinate downstream workers directly. For example, P2 reports
completion to P1, P1 dispatches P5, and the workflow journal records P2's output
as an artifact handoff to P5.

When the viewer is not active, there is no journal write and no graph-viewer
behavior in the orchestration path. Emit failure is fail-open for orchestration:
the dispatch continues, while the viewer reports degraded telemetry and the
timestamp of the last valid event.

### 4. Flexible non-orchestrator flows

The event contract is independent of fixed P2-P9 workflow rules. A Herdr
session that does not use `herdr-orchestrator` may emit the same explicit
assignment and handoff events after invoking `herdr-graph-viewer`. It does not
need a custom manifest or a brainstorming step.

If a session emits no relationship event, the viewer shows truthful live agent
nodes and an explicit `relationships not yet observed` notice. It never guesses
an edge.

Invoking the viewer midway through a session starts recording from the current
controller-known state. Existing authoritative receipts may seed assignment
results, but the projector does not fabricate unrecorded historical handoffs.

### 5. Projection

The projector merges three independent sources:

| Concern | Authoritative source |
| --- | --- |
| Agent liveness and freshness | Current workspace Herdr observation |
| Workflow and current control edge | Run-local flow journal |
| PASS/FAIL/BLOCKED result | Valid receipt or explicit gate/result event |

An ordinary assignment node is keyed by run-local assignment identity, normally
`lane_id + generation`, and carries its bound agent session separately. This
allows one P slot to cover several roles over a run without conflating their
history. P1 is one stable Orchestrator node whose controller generation may
advance during recovery.

The projection retains assignment nodes through run termination. Repeated
handoffs on the same relationship update occurrence count and latest timestamp
instead of creating overlapping duplicate edges.

## Approved Visual Contract

The approved direction is option A from the visual brainstorming session:

- P1 is centered at the top.
- Same-depth assignments share a horizontal rank.
- Forward artifact links are straight, top-to-bottom links.
- The active artifact edge is highlighted; historical artifact edges are
  muted.
- Only the currently active P1 dispatch or reroute is drawn as a dashed control
  edge.
- A rework route uses a distinct failure color and the outer graph gutter so it
  is readable as a loop without crossing the main path.
- Each card contains role, P badge, liveness, result badge, and last-activity
  recency.
- The event timeline contains absolute timestamps and readable semantic text,
  such as `09:47 P1 dispatched P4`.

The renderer derives rank from the observed artifact dependency graph, not from
the numeric P slot. P labels communicate assignment, not topology.

## Recovery and Error Handling

- Reject journal events whose workspace or run does not exactly match the
  selected graph.
- Deduplicate stable event IDs. Older generations remain in history but cannot
  replace the current path.
- A pane move preserves the node because pane ID is not assignment identity.
- A closed pane changes the assignment to `OFFLINE` and keeps its node and
  edges until run termination.
- Controller recovery increments the Orchestrator controller generation and
  emits `CONTROLLER_RECOVERED`; it does not add a second P1 node.
- Publisher or viewer restart reloads the journal and reconstructs the same
  projection.
- Malformed journal data leaves the last valid snapshot intact and displays
  `TELEMETRY DEGRADED` with the last valid timestamp.
- Telemetry failure never blocks P1 dispatch, integration, review, QC, receipt
  validation, or delivery.

## Performance Contract

- Event append is local O(1) work and occurs only on a semantic transition.
- Additional event-write overhead is below 10 ms per orchestration transition.
- No raw prompt or terminal log scanning is added.
- No journal heartbeat is written, and unchanged polls cause no snapshot churn.
- The current snapshot contains the current projection, aggregated edges, and
  a bounded recent timeline; the append-only run journal remains the recovery
  source.
- With the viewer not invoked, graph-event overhead is zero.
- The frozen Superpowers baselines remain unchanged: Compact 152 seconds and
  Multi-module 1009 seconds. The latest accepted Herdr references remain
  Compact 143 seconds and Multi-module 776 seconds, both passing quality gates.

## Scope and Compatibility

Implementation stays in the separate `multi-agent-graph-demo` repository and
its `herdr-graph-viewer` skill subtree. Final installation synchronizes only:

- `/Users/haido/.codex/skills/herdr-graph-viewer`;
- the Claude graph-viewer skill, which must resolve to the same reviewed
  installation.

It must not overwrite or modify:

- `/Users/haido/.codex/skills/herdr-orchestrator`;
- Superpowers writing-plans integrations;
- frozen benchmark artifacts;
- another Herdr workspace or run.

The viewer remains manually invoked. No automatic startup or global hook is
added.

## Non-goals

- Showing raw prompt text, tool calls, token usage, or terminal logs.
- Inferring workflow relationships from passive observation.
- Making workers coordinate integration or QC without P1.
- Adding task, artifact, or gate nodes.
- Replacing authored custom manifests for users who intentionally supply one.
- Changing Herdr itself or another installed skill.

## Locked Verification

### Unit and protocol

1. Separate liveness from assignment result.
2. Keep P1 `RUNNING` while the exact controller session is alive.
3. Enforce exact workspace/run identity, event dedupe, and generation ordering.
4. Retain offline assignments until terminal run state.
5. Aggregate repeat handoffs without duplicate overlapping edges.
6. Preserve authored custom topology behavior.

### Recovery

1. Pane move preserves node identity.
2. Pane close retains an `OFFLINE` node.
3. Viewer and publisher restart reconstruct the same graph.
4. Controller recovery retains one P1 and advances its controller generation.
5. Malformed events retain the last valid snapshot and expose degraded status.

### Live browser acceptance

On the real remediation run, within two publisher intervals:

1. P1 is visibly `RUNNING`.
2. The active worker is visibly `RUNNING` with a recent timestamp.
3. P2-P4 implementation assignments are aligned on one rank.
4. The graph is not a permanent P1-to-all star.
5. The current dashed P1 control edge and actual artifact edges are visible.
6. Closed implementation panes remain `OFFLINE + PASS`.
7. The actual flow reaches `implementation -> P5 -> P6`.

An isolated deterministic QC canary must produce a real finding and visibly
route `P6 -> remediation owner -> P5 -> P6`. A separate non-orchestrator Herdr
canary must create an explicit A-to-B handoff without a custom manifest.

### Performance and regression

1. Measure event append below 10 ms per transition.
2. Run a compact viewer-on canary and compare it with the unchanged frozen
   Compact baseline of 152 seconds and accepted Herdr reference of 143 seconds;
   all quality gates must pass.
3. Run the smallest meaningful unit suites, build, browser smoke, launcher
   tests, and skill validation.
4. Perform contract-focused code review, exact-candidate integration, and
   independent QC.
5. Verify source/install parity for Codex and Claude and verify that the
   installed `herdr-orchestrator` identity did not change.

## Meta-harness Rubric

Run `Intent: IMPROVE` with locked criteria and iterate until all criteria pass:

- truthful liveness and result semantics;
- event-backed workflow and rework relationships;
- approved option-A visual contract;
- exact workspace isolation and recovery;
- flexible non-orchestrator flow support;
- bounded overhead and no other-skill regression;
- real live-browser evidence on the exact candidate.

Passing fixtures without the real live-browser graph is insufficient.
