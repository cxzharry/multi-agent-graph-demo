# Read-Only Herdr Adapter

The optional Herdr adapter is a sidecar owned by this viewer repository. It
converts one explicitly selected Herdr workspace state into a complete
`role-graph/v1` snapshot and posts that snapshot to the local viewer.

It does not dispatch agents, write receipts, mutate a workspace, discover other
workspaces, or start, move, prompt, or close panes. Stopping the adapter has no
effect on Herdr delivery.

## Start the local viewer

```bash
cd /Users/haido/multi-agent-graph-demo
npm ci
npm run build
npm run server
```

The viewer listens at `http://127.0.0.1:4173` and persists snapshots to
`data/snapshots.jsonl` unless `ROLE_GRAPH_DATA_FILE` is set.

For an isolated local data file:

```bash
ROLE_GRAPH_DATA_FILE=/absolute/path/to/snapshots.jsonl npm run server
```

## Publish one selected workspace

```bash
cd /Users/haido/multi-agent-graph-demo
python3 -B adapters/herdr/publisher.py \
  --state /absolute/path/to/workspace-state.json \
  --manifest adapters/herdr/manifests/standard.json \
  --workspace-id wK \
  --endpoint http://127.0.0.1:4173/api/snapshots \
  --watch
```

The publisher refuses a state file whose `workspace_id` does not exactly match
`--workspace-id`. The viewer scope becomes `herdr:wK`, and the run ID comes
from `run.contract_id` in the supplied state.

Without `--watch`, the command publishes once and exits. Watch mode polls at a
bounded interval and publishes only when the workspace revision changes:

```bash
python3 -B adapters/herdr/publisher.py \
  --state /absolute/path/to/workspace-state.json \
  --manifest adapters/herdr/manifests/standard.json \
  --workspace-id wK \
  --endpoint http://127.0.0.1:4173/api/snapshots \
  --watch \
  --interval 2
```

If the viewer requires an ingest token, pass it without storing it in source:

```bash
python3 -B adapters/herdr/publisher.py \
  --state /absolute/path/to/workspace-state.json \
  --manifest adapters/herdr/manifests/standard.json \
  --workspace-id wK \
  --endpoint http://127.0.0.1:4173/api/snapshots \
  --token "$ROLE_GRAPH_INGEST_TOKEN"
```

## Inspect the published graph

Open:

```text
http://127.0.0.1:4173/?scopeId=herdr%3AwK&runId=role-graph-live-viewer-20260731
```

Or inspect the local API:

```bash
curl 'http://127.0.0.1:4173/api/snapshot?scopeId=herdr%3AwK&runId=role-graph-live-viewer-20260731'
```

The manifest maps logical roles to named slots or lanes. Lane state takes
precedence over slot state, and one assignee such as P5 may appear on several
logical roles. A lane in `FINDING` activates the matching failure policy and
includes the complete return route in the snapshot.
