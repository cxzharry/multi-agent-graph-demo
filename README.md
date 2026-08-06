# Live Role Graph Viewer

A standalone local viewer for immutable `role-graph/v1` snapshots. It renders
arbitrary top-down role graphs, keeps parallel roles aligned, persists the
latest snapshot for each scope/run pair, and streams live updates over
server-sent events.

The viewer is read-only. It does not dispatch agents, mutate orchestration
state, write Herdr receipts, or control panes.

## Requirements

- Node.js 20 or newer
- npm
- Python 3.10 or newer for the optional Herdr adapter
- Playwright Chromium for browser smoke checks

## Install and run

```bash
npm ci
npm run build
npm run server
```

Open `http://127.0.0.1:4173`.

By default, snapshots are persisted to `data/snapshots.jsonl`. To use a
different local file:

```bash
ROLE_GRAPH_DATA_FILE=/absolute/path/to/snapshots.jsonl npm run server
```

If `ROLE_GRAPH_INGEST_TOKEN` is set, snapshot POST requests require the same
bearer token. Read endpoints remain local and read-only.

## Publish a snapshot

The server exposes:

- `GET /api/health`
- `POST /api/snapshots`
- `GET /api/graphs`
- `GET /api/snapshot?scopeId=...&runId=...`
- `GET /api/stream?scopeId=...&runId=...`

`GET /api/health` identifies this viewer exactly:

```json
{"service":"herdr-role-graph-viewer","schemaVersion":"role-graph/v1"}
```

Example:

```bash
curl \
  -H 'Content-Type: application/json' \
  --data @fixtures/compact.json \
  http://127.0.0.1:4173/api/snapshots
```

## Optional read-only Herdr adapter

The repository-local adapter maps one explicitly supplied Herdr
`workspace-state.json` and manifest to a generic snapshot. It reads only those
inputs and publishes to the viewer:

```bash
python3 -B adapters/herdr/publisher.py \
  --state /absolute/path/to/workspace-state.json \
  --manifest adapters/herdr/manifests/standard.json \
  --workspace-id wK \
  --endpoint http://127.0.0.1:4173/api/snapshots \
  --watch
```

The `--workspace-id` value must exactly match the state file. The adapter does
not discover other workspaces or modify Herdr state. See
[docs/herdr-adapter.md](docs/herdr-adapter.md) for details.

### Observed vs declared topology

The adapter reuses its existing two-second poll to emit bounded, timestamped
lifecycle events (`NODE_OBSERVED`, `NODE_STATUS_CHANGED`,
`NODE_ASSIGNEE_CHANGED`, `NODE_GENERATION_CHANGED`, `NODE_REMOVED`) for every
observed node — never raw prompt, command, tool, token, or log activity.
Unchanged polls publish nothing.

Session mode and the synthesized operational graph observe nodes and statuses
but have no trusted workflow-edge source, so they draw **no** edges: P1 stays in
layer 0, observed agents in layer 1, and the viewer shows an `Observed
topology — relationships unavailable` notice. A supplied custom manifest is the
only exact topology source; its authored edges, gates, and failure loops render
unchanged with no notice.

## Verification

```bash
npm test -- --run
npm run build
node tests/browser-smoke.mjs
python3 -B -m unittest adapters.herdr.test_publisher -v
```

The browser smoke writes its screenshot to `artifacts/browser-smoke.png`.

## Key paths

- `shared/role-graph.js` — runtime snapshot validation
- `server/graph-store.js` — append-only persistence and latest-snapshot index
- `server/app.js` — local HTTP API and filtered SSE
- `src/graph/` — generic layout, nodes, feedback edge, and live-data hook
- `fixtures/` — structurally different protocol examples
- `adapters/herdr/` — optional repository-local read-only publisher
- `docs/superpowers/` — approved design and implementation plan
- `plans/meta-harness-2026-07-31-live-role-graph-plan/` — approved planning evidence

Generated files such as `node_modules/`, `dist/`, local JSONL data, browser
evidence, and large media artifacts should remain untracked.
