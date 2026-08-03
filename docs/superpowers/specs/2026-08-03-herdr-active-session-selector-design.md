# Herdr Active Session Selector Design

## Status

Approved on 2026-08-03. The user selected **Active + history** and retains the
standing instruction to auto-approve the implementation plan.

## Problem

The selector currently lists persisted graph runs as if they were live Herdr
sessions. The live ledger on port 4174 contains three historical snapshots, but
none represents either P1 agent currently working in workspaces `wK` and `wP`.
The options also use full titles, so they are longer than the identity a user
needs while switching sessions.

Adding a status word to the existing options is insufficient: it would label
the three saved snapshots correctly, but the two current P1 sessions would
still be absent.

## User Experience

The selector has two groups:

- **Active** contains workspace-local session publishers whose presence
  heartbeat is fresh.
- **History** contains persisted graph snapshots without fresh presence.

Options use compact, explicit labels:

- `LIVE · car-edge · current`
- `LIVE · herdr-orchestrator · current`
- `DONE · herdr-orchestrator · space-selector`
- `DONE · herdr-orchestrator · viewer-hardening`

The exact `scopeId` and `runId` remain the routing identity and stay visible in
graph metadata. A URL that selects a historical run continues to select that
exact run. With no requested selection, the first active session wins.

## Architecture

### Workspace-local session mode

The launcher first looks for a control state whose controller pane **and agent
session ID** match the current P1. An explicit `--state` still selects the exact
state supplied by the caller.

When no current control state matches, the launcher starts session mode instead
of selecting an old state by pane ID or failing because historical states are
ambiguous. A new lightweight publisher polls `herdr agent list`, filters records
to the current workspace, and emits a graph containing only those agents. The
current P1 is the orchestrator node; other agents are direct children. It never
reads, prompts, moves, or dispatches into another workspace.

The session run ID is derived from the full current P1 session ID and remains
stable for routing. Its persisted short name is `current`.

### Presence without ledger churn

Snapshot publication remains immutable and occurs only when agent topology or
status changes. A separate authenticated `POST /api/presence` heartbeat updates
an in-memory presence registry and never appends to the JSONL snapshot ledger.
Presence expires after six seconds; publishers heartbeat every two seconds.
Server restart clears presence until publishers reconnect.

The existing control-state publisher also heartbeats while its selected run is
active. A completed control run does not remain active merely because an old
publisher process still exists.

The viewer health response advertises a new `session-presence` capability. The
launcher reuses only servers that support both `space-name-summary` and
`session-presence`, leaving older servers untouched.

### Summary status and short names

Snapshots gain an optional non-empty `shortName`. Existing control-state runs
derive a compact fallback by removing a terminal date and retaining at most the
last two run-ID segments. Session mode emits `current` directly.

`GET /api/graphs` derives historical status from the P1/orchestrator node and
merges fresh presence by exact `scopeId` and `runId`. It returns `isLive`,
`runStatus`, and `shortName`, sorted with active sessions first and history by
recency. When any snapshot or presence record supplies a space name, summaries
in that same scope may reuse it for display only; selection identity never
changes.

## Boundaries

- Viewer startup remains explicit; no global hook or automatic browser launch.
- No raw tool activity, prompt text, or command stream is published.
- No Herdr CLI calls occur in the browser or viewer server.
- Session publishers inspect only their own `workspace_id`.
- No dispatch, pane close, or mutation of `herdr-orchestrator` is allowed.
- Historical snapshots remain readable and are not rewritten or deleted.
- Existing explicit control-state and custom-manifest flows remain supported.

## Failure Handling

- If the current pane has no usable P1 session identity, session mode fails
  before pane mutation.
- A malformed presence payload returns HTTP 400 and does not affect snapshots.
- A stopped publisher naturally disappears from Active after the TTL and its
  last snapshot remains in History.
- A dead or incompatible viewer server is skipped without being stopped.
- Exact URL selection never falls back to another graph.

## Verification

- Launcher tests prove pane-and-session state matching, stale-state rejection,
  session-mode fallback, exact workspace binding, and capability negotiation.
- Session publisher tests prove workspace filtering, agent-only graphs, stable
  run identity, status changes, snapshot deduplication, and heartbeats.
- Server tests prove presence TTL, no JSONL heartbeat writes, summary status,
  scope-name enrichment, and active-first ordering.
- Frontend tests prove Active/History grouping, compact labels, exact routing,
  and active-first default selection.
- Browser smoke publishes two active spaces plus historical runs and verifies
  the exact compact labels and current P1 statuses.
- Independent review and functional, layout, and persona QC must pass before
  syncing the installed `herdr-graph-viewer` skill and pushing `main`.
