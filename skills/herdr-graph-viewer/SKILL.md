---
name: herdr-graph-viewer
description: Use when the user explicitly invokes `$herdr-graph-viewer`, asks to visualize the active Herdr P1 run, or requests the localhost role graph for the current Herdr workspace.
---

# Herdr Graph Viewer

## Overview

Open the current P1 control run or Herdr session as a live, read-only localhost graph. Keep visualization optional: never install a global hook or change `herdr-orchestrator`.

## Start or reuse the viewer

Run:

```bash
python3 -B /Users/haido/.codex/skills/herdr-graph-viewer/scripts/start_viewer.py
```

The launcher must run inside Herdr. It resolves only the current workspace and current P1 pane plus full agent session ID. When an exact control state matches both values, it starts or reuses one publisher watcher for that state and topology mode. When none matches, it starts or reuses the exact workspace-local session publisher. It computes deterministic publisher and viewer content fingerprints: current runtimes use the fast reuse path, while stale or unmanaged same-scope runtimes are transparently stopped with a bounded wait and restarted in their existing ordinary panes. It verifies fingerprint-bound server health and a current snapshot, then prints JSON containing `url`, `mode`, absolute `flowJournal`, `emitCommand`, fingerprint evidence, and `reused`/`replaced` flags.

Session mode is a supported fallback, not an error. Its full P1 session ID is the hidden run identity; the selector presents the fresh heartbeat under **Active** with the compact name `current`. Persisted runs without fresh presence remain under **History**. Exact `scopeId + runId` values remain visible as graph metadata and routing identity.

Custom topology keeps this precedence: explicit `--manifest`, `run.role_graph_manifest`, then a run-local `role-graph-manifest.json`. When none exists, the publisher deterministically derives an operational graph in memory from the selected `workspace-state.json`. It writes no manifest or cache file and invents no handoff, dependency, gate, or failure edges. A configured custom path that is missing or invalid remains an error; never replace it with the synthetic graph.

Return the URL as a clickable link. Do not open a browser tab unless the user explicitly asks; then run `open '<url>'` after the launcher succeeds.

## Record real workflow events

After the launcher returns `status: ready`, the current P1 may record real semantic transitions. Copy the returned `emitCommand` prefix exactly; the prefix below illustrates a ready result for workspace `wK` and run `run-1`. Replace that whole prefix with the returned value, then append the event-specific arguments.

Control dispatch from P1 to an implementation assignment:

```bash
python3 -B /absolute/installed/herdr-graph-viewer/scripts/emit_event.py --journal /absolute/runs/wK/viewer/flow-events/run-1.jsonl --workspace-id wK --run-id run-1 \
  --event-id evt-dispatch-p3-g1 --at 2026-08-07T12:00:00Z \
  --kind CONTROL_DISPATCH --generation 1 \
  --source '{"id":"orchestrator:g1","role":"Orchestrator","slot":"P1","task":"Route approved work"}' \
  --target '{"id":"launcher-emitter:g1","role":"Implementation","slot":"P3","task":"Implement launcher and emitter"}'
```

Artifact handoff from implementation to integration:

```bash
python3 -B /absolute/installed/herdr-graph-viewer/scripts/emit_event.py --journal /absolute/runs/wK/viewer/flow-events/run-1.jsonl --workspace-id wK --run-id run-1 \
  --event-id evt-handoff-p3-p5-g1 --at 2026-08-07T12:20:00Z \
  --kind ARTIFACT_HANDOFF --generation 1 \
  --source '{"id":"launcher-emitter:g1","role":"Implementation","slot":"P3","task":"Implement launcher and emitter"}' \
  --target '{"id":"integration:g1","role":"Integration","slot":"P5","task":"Integrate accepted lanes"}' \
  --artifact '{"commit":"0123456789abcdef","tree":"fedcba9876543210"}'
```

Assignment result reported to P1:

```bash
python3 -B /absolute/installed/herdr-graph-viewer/scripts/emit_event.py --journal /absolute/runs/wK/viewer/flow-events/run-1.jsonl --workspace-id wK --run-id run-1 \
  --event-id evt-result-p3-g1 --at 2026-08-07T12:21:00Z \
  --kind ASSIGNMENT_RESULT --generation 1 \
  --assignment '{"id":"launcher-emitter:g1","role":"Implementation","slot":"P3","task":"Implement launcher and emitter"}' \
  --result PASS --reason 'Owned acceptance matrix passed'
```

Rework routed from independent review to the owning assignment:

```bash
python3 -B /absolute/installed/herdr-graph-viewer/scripts/emit_event.py --journal /absolute/runs/wK/viewer/flow-events/run-1.jsonl --workspace-id wK --run-id run-1 \
  --event-id evt-rework-p6-p3-g1 --at 2026-08-07T12:30:00Z \
  --kind REWORK_ROUTE --generation 1 \
  --source '{"id":"independent-review:g1","role":"Independent Review","slot":"P6","task":"Review immutable candidate"}' \
  --target '{"id":"launcher-emitter:g1","role":"Implementation","slot":"P3","task":"Resolve launcher finding"}' \
  --reason 'Publisher reuse did not bind the exact journal'
```

Workers report results to P1 and never dispatch downstream agents directly. P1 records the dispatch, handoff, result, or rework event only after that transition actually occurs; it does not infer future edges.

Event recording is optional and invoke-time only:

- **Viewer not invoked:** no event command runs and there is zero event-recording overhead.
- A journal or telemetry failure never blocks work; report it to P1 and continue the underlying workflow.
- A non-orchestrator A-to-B flow uses the same assignment and event contract.
- No manifest or brainstorming is required to record a real transition.
- Never add a global hook, scan a raw log, or edit/install `herdr-orchestrator` to capture events.

## Select an exact control state

Use `--state` when the caller explicitly wants one control-state run. The supplied path remains exact and does not fall back to another state:

```bash
python3 -B /Users/haido/.codex/skills/herdr-graph-viewer/scripts/start_viewer.py \
  --state /absolute/path/to/workspace-state.json
```

Use `--manifest /absolute/path/to/manifest.json` when the selected flow supplies a custom role graph. Otherwise the launcher uses `run.role_graph_manifest`, a run-local `role-graph-manifest.json`, or the deterministic in-memory operational graph in that order.

## Guardrails

- Never inspect, publish, prompt, move, or dispatch into another Herdr workspace.
- Never modify or sync the viewer repo, `herdr-orchestrator`, or its installed skill.
- Never close panes. Server and publisher are ordinary command panes, not agents.
- Reuse a server only when health advertises `space-name-summary`, `session-presence`, and the current viewer fingerprint. Skip unrelated or incompatible services without stopping them.
- Reuse control publishers by exact state, topology mode, and publisher fingerprint, and session publishers by exact workspace, space name, P1 pane, P1 session, endpoint, and fingerprint. Treat legacy/manual processes without a launcher fingerprint as stale, not reusable.
- Replace only same-scope ordinary viewer panes in the current workspace. Stop stale publishers before stale servers, confirm each pane returns to its shell, then start the server before the publisher. Never stack a replacement over an unconfirmed process.
- On cold launch, place the server right of P1 and the publisher below the server in that right-side rail. Preserve focus and never create either process below P1.
- Do not install hooks or stream raw tool activity. The explicit journal contains semantic transitions only; control and session publishers continue to read exact workspace-local state.

## Observed vs declared topology

- **Liveness and results are separate.** Publishers observe current agent presence while explicit journal events record assignment outcomes. A completed assignment can remain visible and offline with its result.
- **Relationships require events or a declared topology.** Session and synthetic flows never guess workflow edges. Explicit journal events add only observed dispatch, artifact handoff, result, and rework facts; without those facts the viewer reports that relationships are unavailable or empty.
- **Custom manifests remain the only exact topology source.** A declared manifest keeps its authored nodes, edges, gates, and failure loops byte-for-byte and shows no observed-topology notice.
- Startup stays explicit and invoke-only: no global hook is installed and the viewer never starts itself. Direct/manual publisher and server processes remain diagnostic `unmanaged` runtimes and cannot satisfy launcher readiness.

## Verification

Before reporting success, require launcher status `ready`, the expected `mode`, an exact workspace/run match, current publisher/viewer fingerprints, and a verified snapshot. Report whether server and publisher were started, replaced, or reused.
