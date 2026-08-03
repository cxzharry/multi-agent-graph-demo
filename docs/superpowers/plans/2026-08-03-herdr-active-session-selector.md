# Herdr Active Session Selector Implementation Plan

> **For Herdr delivery:** REQUIRED SUB-SKILL: Use
> `herdr-orchestrator` only after this plan is approved.

**Goal:** Show only genuinely live Herdr sessions in an Active selector group,
retain persisted runs as compact History entries, and make the current P1
status truthful across independently invoked workspaces.

**Architecture:** A workspace-local publisher owns Herdr discovery and sends
snapshot changes plus an in-memory presence heartbeat. The server merges
presence with persisted graph summaries using exact `scopeId + runId`
identity, while the frontend groups compact labels into Active and History.
The launcher binds control states by pane and session identity, otherwise it
uses session mode without inspecting another workspace.

**Tech Stack:** Python 3 launcher/publishers, Node.js HTTP/SSE server and JSONL
store, React/TypeScript, Vitest, unittest, Playwright browser smoke.

---

## File Map

- `adapters/herdr/session_publisher.py`: publish an agent-only graph for the
  exact current workspace and heartbeat its session presence.
- `adapters/herdr/test_session_publisher.py`: TDD coverage for workspace
  isolation, graph projection, identity, deduplication, and heartbeats.
- `adapters/herdr/publisher.py`: heartbeat active control-state runs without
  persisting heartbeat churn.
- `adapters/herdr/test_publisher.py`: control-state presence coverage.
- `shared/role-graph.js`: accept optional non-empty `shortName` snapshots.
- `server/presence-store.js`: validate and retain expiring in-memory presence.
- `server/graph-store.js`: merge live presence and compact status into graph
  summaries without rewriting the ledger.
- `server/app.js`: expose authenticated presence ingestion and advertise the
  `session-presence` capability.
- `tests/protocol.test.js`, `tests/store.test.js`, `tests/server.test.js`:
  protocol, TTL, ordering, status, and no-ledger-churn coverage.
- `src/graph/types.ts`: type `shortName`, `isLive`, and `runStatus`.
- `src/graph/useLiveGraph.ts`: exact selection, active-first default, and
  compact option labels.
- `src/main.tsx`: render native Active and History option groups.
- `src/graph/layout.test.ts`, `tests/browser-smoke.mjs`: selector behavior and
  two-live-space browser evidence.
- `skills/herdr-graph-viewer/scripts/start_viewer.py`: choose exact current
  control state or session mode and require presence-capable servers.
- `skills/herdr-graph-viewer/scripts/test_start_viewer.py`: launcher identity,
  capability, reuse, and fallback tests.
- `skills/herdr-graph-viewer/SKILL.md`: document optional session mode and the
  Active/History contract.
- `plans/meta-harness-2026-08-03-active-session-selector/*`: locked rubric,
  iteration evidence, outcome, and report.

## Meta-Harness Contract

- Gate: `PROCEED`; intent: `DELIVER`; target: `8`; target minimum: `7`;
  maximum iterations: `3`.
- Implementation parallelism: Parallel lanes.
- Reason: publisher, server/UI, and launcher have disjoint owned paths and a
  shared snapshot/presence contract that P5 can integrate deterministically.
- Rubric criteria: truthful liveness, workspace isolation, compact selector
  usability, backward compatibility, and operational efficiency.
- Success requires every criterion at least 8 with evidence from unit tests,
  build, browser smoke, independent review, and installed-skill parity.
- A failed criterion routes to its owning lane; the replacement generation
  must rerun every downstream gate bound to the changed artifact.

## Herdr Delivery Contract

- `contract_id`: `herdr-active-session-selector-20260803`
- Delivery mode: Standard because this changes protocol/schema, authenticated
  server behavior, visible UI, launcher behavior, and browser workflows.
- Base commit: `2d3abd7` on `/Users/haido/multi-agent-graph-demo/main`.
- All first-pass lanes use generation `1`; replacements increment only the
  affected lane generation.
- P1 is controller-only. P1 does not edit product code, run product tests,
  integrate, review, commit, push, deploy, close panes, or dispatch outside the
  current Herdr workspace.
- P2 owns `session_publisher_presence`.
- P3 owns `presence_summary_selector`.
- P4 owns `launcher_session_mode`.
- P5 owns `integration` after current-generation P2-P4 PASS receipts.
- P6 owns independent rule/contract/code review after P5.
- P7 owns functional test/build/browser QC after P6 PASS.
- P8 owns selector layout/readability QC after P5.
- P9 owns operator-persona QC after P5.
- No lane may edit `/Users/haido/herdr-orchestrator` or
  `/Users/haido/.codex/skills/herdr-orchestrator`.
- P5 alone syncs `/Users/haido/.codex/skills/herdr-graph-viewer`, commits the
  integrated candidate, and pushes after every required gate passes.

### Task 1: Workspace Session Publisher and Presence — P2

**Owned paths:**

- Create: `adapters/herdr/session_publisher.py`
- Create: `adapters/herdr/test_session_publisher.py`
- Modify: `adapters/herdr/publisher.py`
- Modify: `adapters/herdr/test_publisher.py`

**Prerequisites:** Approved spec and plan; independent from Tasks 2-3.

- [ ] Write failing tests for exact workspace filtering, P1-rooted agent-only
  projection, stable full-session run identity, `shortName="current"`, and
  status-change-only snapshot publication. The wished-for public interfaces
  are:

```python
agents = select_workspace_agents(raw_agents, workspace_id="wK")
snapshot = build_session_snapshot(
    agents=agents,
    workspace_id="wK",
    space_name="herdr-orchestrator",
    p1_session_id="019fb24f-f36f-7642-8679-5c6405fb3889",
    p1_pane_id="wK:p1",
    sequence=1,
)
heartbeat_presence(endpoint, token, snapshot)
```

- [ ] Run the focused RED checks and confirm failures are caused by the missing
  session publisher and control-run heartbeat:

```bash
python3 -B -m unittest adapters.herdr.test_session_publisher
python3 -B -m unittest adapters.herdr.test_publisher
```

- [ ] Implement the minimal session publisher. It must call `herdr agent list`,
  filter `workspace_id` exactly before projection, identify P1 by the supplied
  session and pane IDs, publish other local agents as direct children, and
  never call prompt, dispatch, move, close, or cross-workspace commands.
- [ ] Implement `POST /api/presence` heartbeats every two seconds while keeping
  snapshots change-driven. Control-state publisher heartbeats only while its
  selected run is active; terminal control runs stop heartbeating.
- [ ] Re-run both focused commands; expect all tests to pass with no network or
  real Herdr mutation.
- [ ] Commit only owned paths:

```bash
git add adapters/herdr/session_publisher.py \
  adapters/herdr/test_session_publisher.py \
  adapters/herdr/publisher.py adapters/herdr/test_publisher.py
git commit -m "feat: publish live Herdr session presence"
```

- [ ] Write the terminal receipt:

```bash
python3 -B /Users/haido/.codex/skills/herdr-orchestrator/scripts/write_lane_receipt.py \
  --control-state "$HERDR_CONTROL_STATE" --lane session_publisher_presence \
  --status PASS --check 'session and control publisher tests=pass' \
  --output "commit=$(git rev-parse HEAD)"
```

### Task 2: Presence Server and Active/History Selector — P3

**Owned paths:**

- Create: `server/presence-store.js`
- Modify: `shared/role-graph.js`
- Modify: `server/graph-store.js`
- Modify: `server/app.js`
- Modify: `tests/protocol.test.js`
- Modify: `tests/store.test.js`
- Modify: `tests/server.test.js`
- Modify: `src/graph/types.ts`
- Modify: `src/graph/useLiveGraph.ts`
- Modify: `src/main.tsx`
- Modify: `src/graph/layout.test.ts`
- Modify: `tests/browser-smoke.mjs`

**Prerequisites:** Approved spec and plan; independent from Tasks 1 and 3.

- [ ] Write failing tests for optional non-empty `shortName`, authenticated
  presence validation, a six-second injectable TTL, no JSONL writes on
  heartbeat, exact `(scopeId, runId)` liveness, derived P1 status, same-scope
  display-name enrichment, Active-first ordering, and compact fallback names.
  The required summary shape is:

```js
{
  scopeId: 'herdr:wK',
  runId: '019fb24f-f36f-7642-8679-5c6405fb3889',
  spaceName: 'herdr-orchestrator',
  shortName: 'current',
  isLive: true,
  runStatus: 'RUNNING'
}
```

- [ ] Write failing frontend/browser assertions for native `Active` and
  `History` groups and these exact compact labels:

```text
LIVE · car-edge · current
LIVE · herdr-orchestrator · current
DONE · herdr-orchestrator · space-selector
DONE · herdr-orchestrator · viewer-hardening
```

- [ ] Run `npm test -- --run`; confirm failures are specifically due to absent
  presence/summary/grouping behavior.
- [ ] Implement a small in-memory `PresenceStore` keyed by exact identity.
  `POST /api/presence` uses the existing ingest bearer token; malformed input
  returns 400. `/api/health` advertises both `space-name-summary` and
  `session-presence`.
- [ ] Extend graph summaries without mutating stored snapshots. Map P1 status
  to `RUNNING`, `DONE`, `FAILED`, or `PENDING`; sort fresh presence first and
  history by recency. Keep exact requested URL selection and default to the
  first live graph only when the URL has no requested identity.
- [ ] Render native `<optgroup label="Active">` and
  `<optgroup label="History">`. Preserve `scopeId + runId` as option value and
  retain SSE updates for the selected exact graph.
- [ ] Run `npm test -- --run`; expect all suites to pass.
- [ ] Commit only owned paths:

```bash
git add server/presence-store.js shared/role-graph.js server/graph-store.js \
  server/app.js tests/protocol.test.js tests/store.test.js \
  tests/server.test.js src/graph/types.ts src/graph/useLiveGraph.ts \
  src/main.tsx src/graph/layout.test.ts tests/browser-smoke.mjs
git commit -m "feat: group active and historical graph runs"
```

- [ ] Write the terminal receipt:

```bash
python3 -B /Users/haido/.codex/skills/herdr-orchestrator/scripts/write_lane_receipt.py \
  --control-state "$HERDR_CONTROL_STATE" --lane presence_summary_selector \
  --status PASS --check 'web tests=pass' \
  --output "commit=$(git rev-parse HEAD)"
```

### Task 3: Current Session Launcher Mode — P4

**Owned paths:**

- Modify: `skills/herdr-graph-viewer/scripts/start_viewer.py`
- Modify: `skills/herdr-graph-viewer/scripts/test_start_viewer.py`
- Modify: `skills/herdr-graph-viewer/SKILL.md`

**Prerequisites:** Approved spec and plan; independent from Tasks 1-2.

- [ ] Add failing tests proving state selection requires both current P1 pane
  and current agent session ID, stale states are rejected, no matching state
  selects session mode, explicit `--state` remains exact, and only a health
  response containing both capabilities is reusable.
- [ ] Add a failing launch test whose current workspace has no control state and
  assert the publisher command contains this exact identity binding:

```text
session_publisher.py --workspace-id wK --space-name herdr-orchestrator \
  --p1-session-id 019fb24f-f36f-7642-8679-5c6405fb3889 \
  --p1-pane-id wK:p1
```

- [ ] Run the launcher RED command and confirm failures are caused by pane-only
  matching and missing session mode:

```bash
python3 -B skills/herdr-graph-viewer/scripts/test_start_viewer.py
```

- [ ] Implement one current-P1 identity resolver before any pane mutation. In
  control mode, preserve the existing publisher command and manifest
  precedence. In session mode, use the full P1 session as hidden run identity,
  start/reuse only the exact local session publisher, and report `mode` in the
  launcher JSON.
- [ ] Require `space-name-summary` plus `session-presence` when scanning ports.
  Skip incompatible/dead servers without stopping them. Keep the existing
  right-side rail placement, focus restoration, and never-close-pane rules.
- [ ] Update the skill text so missing current control state is a supported
  session-mode path, while viewer invocation remains explicit and optional.
- [ ] Re-run the launcher test command; expect all tests to pass.
- [ ] Commit only owned paths:

```bash
git add skills/herdr-graph-viewer/scripts/start_viewer.py \
  skills/herdr-graph-viewer/scripts/test_start_viewer.py \
  skills/herdr-graph-viewer/SKILL.md
git commit -m "feat: launch viewer for the current Herdr session"
```

- [ ] Write the terminal receipt:

```bash
python3 -B /Users/haido/.codex/skills/herdr-orchestrator/scripts/write_lane_receipt.py \
  --control-state "$HERDR_CONTROL_STATE" --lane launcher_session_mode \
  --status PASS --check 'launcher and skill tests=pass' \
  --output "commit=$(git rev-parse HEAD)"
```

### Task 4: Integration, Meta-Harness Evaluation, and Delivery — P5-P9

**Prerequisites:** Current-generation PASS receipts for Tasks 1-3.

- [ ] P5 integrates only the accepted commits into a forward commit based on
  `2d3abd7`, resolves integration conflicts without expanding scope, and runs:

```bash
python3 -B -m unittest adapters.herdr.test_session_publisher
python3 -B -m unittest adapters.herdr.test_publisher
python3 -B skills/herdr-graph-viewer/scripts/test_start_viewer.py
npm test -- --run
npm run build
git diff --check
```

- [ ] P6 independently reviews the current integrated tuple against the design
  and all contracts: liveness is heartbeat-derived, completed control runs are
  not live, routing identity is exact, no cross-workspace inspection occurs,
  no pane closes, no old server is killed, heartbeats do not append ledger
  rows, and old flows remain readable. Findings return to the owning lane.
- [ ] P8 verifies native group order, compact labels, no truncation/overflow,
  and horizontal/vertical selector fit at desktop and narrow viewport sizes.
- [ ] P9 verifies an operator can identify which spaces are active, which runs
  are history, and which current P1 is working without interpreting opaque
  workspace or session IDs.
- [ ] P7 runs final functional QC against a fresh compatible server with two
  active-space fixtures plus history and records the URL and assertions:

```bash
node tests/browser-smoke.mjs
python3 -B -m unittest adapters.herdr.test_session_publisher
python3 -B -m unittest adapters.herdr.test_publisher
python3 -B skills/herdr-graph-viewer/scripts/test_start_viewer.py
npm test -- --run
npm run build
```

- [ ] P5 preserves the already locked rubric and writes
  `plans/meta-harness-2026-08-03-active-session-selector` feedback, state,
  outcome, and report artifacts from the actual gate evidence. SUCCESS is
  allowed only when all five criteria score at least 8.
- [ ] P5 syncs only the graph-viewer skill and verifies exact parity:

```bash
rsync -a --delete skills/herdr-graph-viewer/ \
  /Users/haido/.codex/skills/herdr-graph-viewer/
diff -ru skills/herdr-graph-viewer \
  /Users/haido/.codex/skills/herdr-graph-viewer
```

- [ ] P5 creates the final integration commit, pushes `main` normally, and
  proves the delivered tuple:

```bash
git status --short
git rev-parse HEAD
git rev-parse main
git rev-parse origin/main
```

## Acceptance

- Exactly the current workspace-local publishers with a heartbeat newer than
  six seconds appear in Active; stopped publishers age into History.
- P1 working status appears `RUNNING`, not `PASS`, and completed historical P1
  runs remain `DONE`.
- Selector labels are compact, grouped, space-first, and omit opaque IDs.
- Exact URL routing, historical readability, custom/control graph flows, SSE,
  focus restoration, right-side pane placement, and no-pane-close behavior do
  not regress.
- No publisher, launcher, server, or UI path inspects or dispatches into another
  Herdr workspace.
- Unit tests, build, browser smoke, P6 review, P7 functional QC, P8 layout QC,
  P9 persona QC, meta-harness rubric, installed parity, commit, and push gates
  all pass on the delivered commit.
