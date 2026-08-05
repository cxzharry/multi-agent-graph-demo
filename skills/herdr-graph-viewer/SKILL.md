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

The launcher must run inside Herdr. It resolves only the current workspace and current P1 pane plus full agent session ID. When an exact control state matches both values, it starts or reuses one publisher watcher for that state and topology mode. When none matches, it starts or reuses the exact workspace-local session publisher. It verifies the snapshot and prints JSON containing `url` and `mode`.

Session mode is a supported fallback, not an error. Its full P1 session ID is the hidden run identity; the selector presents the fresh heartbeat under **Active** with the compact name `current`. Persisted runs without fresh presence remain under **History**. Exact `scopeId + runId` values remain visible as graph metadata and routing identity.

Custom topology keeps this precedence: explicit `--manifest`, `run.role_graph_manifest`, then a run-local `role-graph-manifest.json`. When none exists, the publisher deterministically derives an operational graph in memory from the selected `workspace-state.json`. It writes no manifest or cache file and invents no handoff, dependency, gate, or failure edges. A configured custom path that is missing or invalid remains an error; never replace it with the synthetic graph.

Return the URL as a clickable link. Do not open a browser tab unless the user explicitly asks; then run `open '<url>'` after the launcher succeeds.

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
- Reuse a server only when health advertises both `space-name-summary` and `session-presence`; skip dead or incompatible servers without stopping them.
- Reuse control publishers by exact state and topology mode, and session publishers by exact workspace, space name, P1 pane, P1 session, and endpoint. Replace only a mismatched viewer-owned control publisher in the same ordinary pane.
- On cold launch, place the server right of P1 and the publisher below the server in that right-side rail. Preserve focus and never create either process below P1.
- Do not install hooks or stream raw tool activity. Control mode publishes `workspace-state.json` revisions; session mode publishes only workspace-local agent status and presence.

## Observed vs declared topology

- **Events are bounded lifecycle observations, not raw activity.** Both publishers reuse their existing two-second poll to diff node lifecycle and emit timestamped `NODE_OBSERVED`, `NODE_STATUS_CHANGED`, `NODE_ASSIGNEE_CHANGED`, and `NODE_REMOVED` events. A fresh graph shows one event per current node immediately; unchanged polls add nothing. No prompt, command, tool, token, or session-log activity is streamed, and history stays bounded.
- **Session and synthetic relationships are unavailable.** These flows observe nodes and statuses but have no trusted workflow-edge source, so they draw no edges, gates, or failure routes. P1 stays in layer 0 and observed agents in layer 1, and the viewer shows a concise `Observed topology — relationships unavailable` notice.
- **Custom manifests remain the only exact topology source.** A declared manifest keeps its authored nodes, edges, gates, and failure loops byte-for-byte and shows no observed-topology notice.
- Startup stays explicit: no global hook is installed and the viewer never starts itself.

## Verification

Before reporting success, require launcher status `ready`, the expected `mode`, an exact workspace/run match, and a verified snapshot. Report whether server and publisher were started or reused.
