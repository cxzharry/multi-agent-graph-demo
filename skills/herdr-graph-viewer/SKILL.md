---
name: herdr-graph-viewer
description: Use when the user explicitly invokes `$herdr-graph-viewer`, asks to visualize the active Herdr P1 run, or requests the localhost role graph for the current Herdr workspace.
---

# Herdr Graph Viewer

## Overview

Open the selected P1 orchestration ledger as a live, read-only localhost graph. Keep visualization optional: never install a global hook or change `herdr-orchestrator`.

## Start or reuse the viewer

Run:

```bash
python3 -B /Users/haido/.codex/skills/herdr-graph-viewer/scripts/start_viewer.py
```

The launcher must run inside Herdr. It resolves only the current workspace, selects the run bound to the current P1 pane when possible, starts or reuses the viewer server, starts one publisher watcher for the exact state file and topology mode, verifies the snapshot, and prints JSON containing `url`.

Custom topology keeps this precedence: explicit `--manifest`, `run.role_graph_manifest`, then a run-local `role-graph-manifest.json`. When none exists, the publisher deterministically derives an operational graph in memory from the selected `workspace-state.json`. It writes no manifest or cache file and invents no handoff, dependency, gate, or failure edges. A configured custom path that is missing or invalid remains an error; never replace it with the synthetic graph.

Return the URL as a clickable link. Do not open a browser tab unless the user explicitly asks; then run `open '<url>'` after the launcher succeeds.

## Resolve selection errors

If the launcher returns `ambiguous_run`, show the candidate state paths and ask which run to use. Rerun with the exact selection:

```bash
python3 -B /Users/haido/.codex/skills/herdr-graph-viewer/scripts/start_viewer.py \
  --state /absolute/path/to/workspace-state.json
```

Use `--manifest /absolute/path/to/manifest.json` when the selected flow supplies a custom role graph. Otherwise the launcher uses `run.role_graph_manifest`, a run-local `role-graph-manifest.json`, or the deterministic in-memory operational graph in that order.

## Guardrails

- Never inspect, publish, prompt, move, or dispatch into another Herdr workspace.
- Never modify or sync the viewer repo, `herdr-orchestrator`, or its installed skill.
- Never close panes. Server and publisher are ordinary command panes, not agents.
- Reuse healthy processes by exact state and topology mode; replace only a mismatched viewer-owned publisher in the same ordinary pane.
- On cold launch, place the server right of P1 and the publisher below the server in that right-side rail. Preserve focus and never create either process below P1.
- Do not install hooks or stream raw tool activity. Publish only `workspace-state.json` revisions.
- If no state exists, report that P1 must create its control state before visualization can start.

## Verification

Before reporting success, require launcher status `ready`, an exact workspace/run match, and a verified snapshot sequence. Report whether server and publisher were started or reused.
