# Live Role Graph Implementation Plan

> **For Herdr delivery:** REQUIRED SUB-SKILL: Use `herdr-orchestrator` only
> after this plan is approved.

**Goal:** Turn `multi-agent-graph-demo` into a generic, persistent live role
graph viewer with a repository-local, read-only Herdr adapter that publishes the
current state of one selected workspace without changing P1 orchestration
behavior or the Herdr skill.

**Architecture:** The viewer accepts immutable `role-graph/v1` snapshots keyed
by scope and run, persists the latest snapshot, broadcasts updates through
filtered SSE, and renders arbitrary top-down role graphs. A separate Python
publisher reads one Herdr `workspace-state.json` plus a declarative role-graph
manifest, derives the current active failure route, and posts a complete
snapshot. The protocol boundary prevents Herdr-specific state logic from
entering the UI.

**Tech Stack:** React 19, TypeScript, Vite, React Flow, `@dagrejs/dagre` 3.0.0,
Node.js built-ins, Vitest 4.1.10, Playwright, Python 3 standard library,
`unittest`, Herdr, Git worktrees.

---

## Locked Inputs and Success Criteria

- Approved design:
  `docs/superpowers/specs/2026-07-31-live-role-graph-design.md`
- Viewer repository:
  `/Users/haido/multi-agent-graph-demo`
- Viewer base:
  `d68e267d787729d813b4d2a177f788f935bcbc81`
- Read-only Herdr source contract:
  `/Users/haido/herdr-orchestrator` at
  `7874aa2dd36fc46f1c4d902b5d744fa9601d858b`
- Protected installed Herdr skill:
  `/Users/haido/.codex/skills/herdr-orchestrator`
- Locked pre-existing viewer command:
  - `npm run server` -> `node server.js`
- Locked execution-backend helper:
  - `/Users/haido/herdr-orchestrator/scripts/write_lane_receipt.py` must exist
    before dispatch;
  - it may write only to the external Herdr run/receipt directory supplied by
    the controller, never to either protected Herdr tree.
- Dependency ownership:
  - `viewer_protocol_server` owns all `package.json` and lockfile changes,
    including `@dagrejs/dagre` 3.0.0 and Vitest 4.1.10;
  - Playwright already exists at viewer base and remains owned by that lane;
  - `viewer_frontend` consumes the integrated dependency commit and does not
    edit package metadata.
- Frozen benchmark references, comparison only:
  - Compact Superpowers: `152s`
  - Multi-module Superpowers: `1009s`
  - Latest Herdr Compact: `143s`, PASS
  - Latest Herdr Multi-module: `776s`, PASS

The delivery is complete only when:

1. the viewer renders two differently shaped fixtures without source changes;
2. API validation, persistence, scope isolation, stale-sequence rejection, and
   filtered SSE pass;
3. reload hydration and live update pass in a real browser;
4. explicit same-layer nodes are horizontally aligned;
5. forward edges are straight and an active failure loop uses the feedback
   gutter;
6. the Herdr publisher maps a real-format workspace fixture to the generic
   protocol and refuses a workspace mismatch;
7. publisher source contains no Herdr mutation, pane control, dispatch, prompt,
   or receipt-write command;
8. P5 integrates the viewer repository and records its exact commit identity;
9. P6 independently reviews protocol, isolation, read-only behavior, and
   regression risk;
10. P7 functional QC, P8 visual QC, and P9 persona QC pass;
11. the Herdr repository and installed skill remain byte-for-byte untouched;
12. the viewer repository advances through a normal commit and push with no
    force;
13. frozen benchmark files and baseline values remain unchanged.

## Non-Goals

- No public deployment.
- No graph editing UI.
- No P1 controller or Herdr repository changes.
- No automatic discovery across Herdr workspaces.
- No event-sourcing reducer in the browser.
- No all-policy Failure Map view in this delivery.
- No new orchestration roles, role renames, or pane lifecycle behavior.

## Protocol Contract

The runtime validator is the source of truth:

```js
export const SNAPSHOT_SCHEMA_VERSION = "role-graph/v1";
export const NODE_STATUSES = new Set([
  "pending",
  "running",
  "passed",
  "failed",
  "blocked",
  "retrying",
  "stale",
  "skipped",
]);
```

Every snapshot must contain:

```ts
type RoleGraphSnapshot = {
  schemaVersion: "role-graph/v1";
  scopeId: string;
  runId: string;
  sequence: number;
  generatedAt: string;
  title: string;
  nodes: RoleNode[];
  edges: RoleEdge[];
  failurePolicies: FailurePolicy[];
  activeFailureRoute: ActiveFailureRoute | null;
  events: GraphEvent[];
};
```

Validation rejects duplicate node/edge IDs, missing edge endpoints, invalid
status/kind values, malformed timestamps, negative sequences, and failure
routes that refer to unknown nodes.

## Target File Map

### `/Users/haido/multi-agent-graph-demo`

| Path | Responsibility |
|---|---|
| `shared/role-graph.js` | Runtime constants and snapshot validation |
| `server/graph-store.js` | Append-only persistence and latest-snapshot index |
| `server/app.js` | Local API and scope-filtered SSE |
| `server.js` | Thin process entrypoint |
| `src/graph/types.ts` | Browser protocol types |
| `src/graph/layout.ts` | Top-down forward layout |
| `src/graph/RoleNode.tsx` | Logical-role node with compact assignee chip |
| `src/graph/FeedbackEdge.tsx` | Active return route through outer gutter |
| `src/graph/useLiveGraph.ts` | Hydration, selection, SSE reconnect |
| `src/main.tsx` | Generic viewer shell |
| `src/style.css` | Graph, selector, states, timeline, responsive behavior |
| `tests/protocol.test.js` | Runtime validation |
| `tests/store.test.js` | Persistence and sequence ordering |
| `tests/server.test.js` | HTTP and stream isolation |
| `src/graph/layout.test.ts` | Layout and feedback route geometry |
| `tests/browser-smoke.mjs` | Hydration, selection, alignment, live loop smoke |
| `fixtures/compact.json` | Compact arbitrary-flow fixture |
| `fixtures/branched-loop.json` | Parallel roles plus active return fixture |

### `/Users/haido/multi-agent-graph-demo`

| Path | Responsibility |
|---|---|
| `adapters/herdr/publisher.py` | Pure mapping, validation, one-shot/watch publish |
| `adapters/herdr/test_publisher.py` | Mapping, failure-route, isolation, read-only tests |
| `adapters/herdr/manifests/standard.json` | Declarative standard Herdr role graph |
| `docs/herdr-adapter.md` | Local read-only connection guide |
| `README.md` | Short pointer to the optional viewer |

## Herdr Delivery Contract

```yaml
herdr_delivery:
  backend: herdr
  contract_id: role-graph-live-viewer-20260731
  generation: 1
  controller:
    slot: P1
    role: orchestration-only
    prohibited:
      - product implementation
      - product tests
      - integration
      - review
      - commit
      - push
  repository:
    root: /Users/haido/multi-agent-graph-demo
    base_sha: d68e267d787729d813b4d2a177f788f935bcbc81
  readonly_inputs:
    herdr_repository: /Users/haido/herdr-orchestrator
    herdr_base_sha: 7874aa2dd36fc46f1c4d902b5d744fa9601d858b
    installed_skill: /Users/haido/.codex/skills/herdr-orchestrator
  lanes:
    - lane_id: viewer_protocol_server
      contract_id: role-graph-live-viewer-20260731
      generation: 1
      role: implementation
      eligible_slots: [P2, P3, P4]
      owned_paths:
        - package.json
        - package-lock.json
        - shared/role-graph.js
        - server/graph-store.js
        - server/app.js
        - server.js
        - tests/protocol.test.js
        - tests/store.test.js
        - tests/server.test.js
      prerequisites: []
      acceptance:
        - npm test -- --run tests/protocol.test.js tests/store.test.js tests/server.test.js
      terminal_receipt:
        command: python3 -B /Users/haido/herdr-orchestrator/scripts/write_lane_receipt.py
        output_artifact: viewer commit SHA and tree SHA
    - lane_id: viewer_frontend
      contract_id: role-graph-live-viewer-20260731
      generation: 1
      role: implementation
      eligible_slots: [P2, P3, P4]
      owned_paths:
        - src/graph/types.ts
        - src/graph/layout.ts
        - src/graph/layout.test.ts
        - src/graph/RoleNode.tsx
        - src/graph/FeedbackEdge.tsx
        - src/graph/useLiveGraph.ts
        - src/main.tsx
        - src/style.css
        - fixtures/compact.json
        - fixtures/branched-loop.json
        - tests/browser-smoke.mjs
      prerequisites: [viewer_protocol_server]
      acceptance:
        - npm test -- --run src/graph/layout.test.ts
        - npm run build
        - node tests/browser-smoke.mjs
      terminal_receipt:
        command: python3 -B /Users/haido/herdr-orchestrator/scripts/write_lane_receipt.py
        output_artifact: viewer commit SHA and tree SHA
    - lane_id: herdr_readonly_publisher
      contract_id: role-graph-live-viewer-20260731
      generation: 1
      role: implementation
      eligible_slots: [P2, P3, P4]
      owned_paths:
        - adapters/herdr/__init__.py
        - adapters/herdr/publisher.py
        - adapters/herdr/test_publisher.py
        - adapters/herdr/manifests/standard.json
      prerequisites: []
      acceptance:
        - python3 -B -m unittest adapters.herdr.test_publisher -v
      terminal_receipt:
        command: python3 -B /Users/haido/herdr-orchestrator/scripts/write_lane_receipt.py
        output_artifact: viewer commit SHA and tree SHA
  integration:
    slot: P5
    prerequisites:
      - viewer_protocol_server
      - viewer_frontend
      - herdr_readonly_publisher
    responsibilities:
      - integrate all three viewer commits in prerequisite order
      - write README.md and docs/herdr-adapter.md
      - run the adapter-to-viewer live canary
      - record the exact viewer commit
      - prove the Herdr repository and installed skill were not modified
    acceptance:
      - cd /Users/haido/multi-agent-graph-demo && npm test -- --run
      - cd /Users/haido/multi-agent-graph-demo && npm run build
      - cd /Users/haido/multi-agent-graph-demo && python3 -B -m unittest adapters.herdr.test_publisher -v
      - browser smoke publishes a Herdr fixture and displays its active loop
  independent_review:
    slot: P6
    applicable: true
    blocking_checks:
      - snapshot validation and cross-scope isolation
      - no Herdr state mutation or agent command
      - no hard-coded workflow in viewer
      - P1 contract unchanged
      - frozen benchmark artifacts unchanged
      - no out-of-scope diff
  quality_control:
    P7:
      applicable: true
      role: functional-qc
      checks:
        - persistence and reload hydration
        - filtered live update
        - workspace mismatch refusal
        - same assignee on multiple roles
        - active gate failure loop
    P8:
      applicable: true
      role: visual-qc
      checks:
        - orchestrator at top
        - parallel roles horizontally aligned
        - direct forward links
        - feedback gutter avoids unrelated nodes
        - readable status and P chip
    P9:
      applicable: true
      role: persona-qc
      checks:
        - user can identify active role and next gate quickly
        - user can switch scope/run without mixed state
        - viewer exposes no mutation controls
  release:
    topology: standalone-local-viewer-plus-one-github-repository
    viewer_push: normal forward push, no force
    herdr_repository_update: prohibited
    installed_skill_update: prohibited
    public_deploy: not-applicable
```

## Task 1: Build the Viewer Protocol Validator

**Files:**

- Create: `/Users/haido/multi-agent-graph-demo/shared/role-graph.js`
- Create: `/Users/haido/multi-agent-graph-demo/tests/protocol.test.js`
- Modify: `/Users/haido/multi-agent-graph-demo/package.json`
- Modify: `/Users/haido/multi-agent-graph-demo/package-lock.json`

**Step 1: Add the failing protocol tests**

Cover:

- a valid compact snapshot;
- duplicate node IDs;
- edge to an unknown node;
- invalid node status;
- invalid return-edge kind;
- active route to an unknown node;
- malformed `generatedAt`;
- negative or fractional sequence.

**Step 2: Run the focused test and observe failure**

```bash
cd /Users/haido/multi-agent-graph-demo
npm test -- --run tests/protocol.test.js
```

Expected: FAIL because the validator does not exist.

**Step 3: Implement the smallest runtime validator**

Export:

```js
export function validateSnapshot(value) {
  // Return a normalized snapshot or throw SnapshotValidationError.
}

export function graphKey(scopeId, runId) {
  return `${encodeURIComponent(scopeId)}::${encodeURIComponent(runId)}`;
}
```

Do not add schema compilers, migration layers, compatibility aliases, or
Herdr-specific fields.

**Step 4: Install the lane-owned dependencies**

Pin:

```text
@dagrejs/dagre 3.0.0
vitest 4.1.10
```

Keep the existing Playwright dependency. Add `"test": "vitest"` and preserve
the existing `"server": "node server.js"` script.

**Step 5: Run the focused test**

Expected: PASS.

**Step 6: Commit and write the lane receipt**

Commit message:

```text
feat: validate generic role graph snapshots
```

## Task 2: Add Persistent Snapshot Storage and API

**Files:**

- Create: `/Users/haido/multi-agent-graph-demo/server/graph-store.js`
- Create: `/Users/haido/multi-agent-graph-demo/server/app.js`
- Modify: `/Users/haido/multi-agent-graph-demo/server.js`
- Create: `/Users/haido/multi-agent-graph-demo/tests/store.test.js`
- Create: `/Users/haido/multi-agent-graph-demo/tests/server.test.js`

**Step 1: Add failing storage tests**

Use a temporary directory. Verify:

- append and restart hydration;
- latest snapshot per `(scopeId, runId)`;
- increasing sequence only;
- two scopes with the same run ID remain separate;
- graph summaries are sorted by newest `generatedAt`.

**Step 2: Add failing HTTP tests**

Start `createApp()` on port `0`. Verify:

- POST returns 202 for a valid snapshot;
- invalid input returns 400;
- stale sequence returns 409;
- GET graph list and snapshot return only the requested key;
- two SSE clients receive only their selected scope/run;
- bearer auth is enforced only when the ingest token is configured.

**Step 3: Run focused tests and observe failure**

```bash
npm test -- --run tests/store.test.js tests/server.test.js
```

**Step 4: Implement storage and the thin HTTP adapter**

`GraphStore` owns JSONL reads/writes and latest indexing. `createApp()` owns
HTTP parsing, auth, and SSE subscriptions. Keep `server.js` to environment
parsing and `listen()`.

**Step 5: Run all lane tests**

```bash
npm test -- --run tests/protocol.test.js tests/store.test.js tests/server.test.js
```

Expected: PASS.

**Step 6: Commit and write the lane receipt**

Commit message:

```text
feat: persist and stream role graph snapshots
```

## Task 3: Implement Generic Layout and Graph Components

**Files:**

- Create: `/Users/haido/multi-agent-graph-demo/src/graph/types.ts`
- Create: `/Users/haido/multi-agent-graph-demo/src/graph/layout.ts`
- Create: `/Users/haido/multi-agent-graph-demo/src/graph/layout.test.ts`
- Create: `/Users/haido/multi-agent-graph-demo/src/graph/RoleNode.tsx`
- Create: `/Users/haido/multi-agent-graph-demo/src/graph/FeedbackEdge.tsx`

**Step 1: Add failing layout tests**

Verify:

- only `forward` edges enter Dagre;
- the lowest explicit layer has the smallest y coordinate;
- nodes sharing a layer share the same y coordinate;
- changing node IDs and graph shape does not require aliases;
- feedback gutter x is outside graph bounds;
- feedback path begins and ends at the correct nodes.

**Step 2: Run the focused test and observe failure**

```bash
npm test -- --run src/graph/layout.test.ts
```

**Step 3: Implement the layout**

Use `rankdir: "TB"`, stable sorting by node ID, fixed node dimensions, and
explicit layer constraints. Return `positionedNodes`, `forwardEdges`, and
`feedbackGutterX`.

**Step 4: Implement the components**

`RoleNode` renders role, assignee chip, task, status, and generation.
`FeedbackEdge` renders one SVG polyline through `feedbackGutterX`.

Do not render an assignee as the node's primary identity.

**Step 5: Run the test and build**

```bash
npm test -- --run src/graph/layout.test.ts
npm run build
```

Expected: PASS.

## Task 4: Replace the Hard-Coded Demo UI

**Files:**

- Create: `/Users/haido/multi-agent-graph-demo/src/graph/useLiveGraph.ts`
- Modify: `/Users/haido/multi-agent-graph-demo/src/main.tsx`
- Modify: `/Users/haido/multi-agent-graph-demo/src/style.css`
- Create: `/Users/haido/multi-agent-graph-demo/fixtures/compact.json`
- Create: `/Users/haido/multi-agent-graph-demo/fixtures/branched-loop.json`
- Create: `/Users/haido/multi-agent-graph-demo/tests/browser-smoke.mjs`

**Step 1: Add two structurally different fixtures**

The compact fixture is a three-node linear flow. The branched fixture includes
parallel implementation roles, P5 on multiple logical roles, independent QC,
functional QC, and one active return.

No fixture name may become a renderer condition.

**Step 2: Implement hydration and live selection**

`useLiveGraph`:

1. fetches `/api/graphs`;
2. selects the URL query key or newest graph;
3. hydrates `/api/snapshot`;
4. opens the filtered EventSource;
5. ignores any payload whose key differs;
6. rehydrates after reconnect.

**Step 3: Replace hard-coded nodes and aliases**

Remove `baseNodes`, `nodeAliases`, Bibi/Codex/Claude/Final assumptions, and
event-to-node inference. Render only validated snapshot data.

**Step 4: Implement the timeline and empty state**

The timeline shows recent events and the active failure reason. Empty state
explains how to publish a snapshot and contains no sample agents.

**Step 5: Add browser smoke**

The Playwright script must:

- start from an empty temporary data file;
- POST compact and branched fixtures;
- select each scope/run and assert the correct node count;
- reload and assert hydration;
- assert equal y coordinates for parallel roles;
- assert orchestrator y is above every other role;
- assert exactly one visible feedback edge;
- POST a higher sequence and assert live status update;
- save a screenshot artifact.

**Step 6: Run focused verification**

```bash
npm test -- --run
npm run build
node tests/browser-smoke.mjs
```

Expected: PASS.

**Step 7: Commit and write the lane receipt**

Commit message:

```text
feat: render live generic role graphs
```

## Task 5: Build the Repository-Local Read-Only Herdr Adapter

**Files:**

- Create: `adapters/herdr/__init__.py`
- Create: `adapters/herdr/publisher.py`
- Create: `adapters/herdr/test_publisher.py`
- Create: `adapters/herdr/manifests/standard.json`

**Step 1: Add failing pure-mapping tests**

Use temporary state and manifest fixtures. Verify:

- exact workspace match succeeds;
- mismatch fails before network access;
- slot and lane sources map to statuses;
- the same assignee maps to multiple roles;
- `FINDING` selects the matching failure policy;
- unknown lanes remain pending without inventing work;
- events are bounded and preserve ledger order;
- sequence equals workspace revision;
- scope ID is `herdr:<workspace_id>`;
- run ID comes from `run.contract_id`.

Import the module as:

```python
from adapters.herdr.publisher import build_snapshot
```

All focused and full-suite commands run from the viewer repository root.

**Step 2: Add a static read-only contract test**

Parse the publisher source and reject imports/calls for:

- `subprocess`;
- Herdr CLI;
- pane start/close/move/prompt;
- workspace-state mutation helpers;
- receipt writers.

Allow only file reads, JSON parsing, time, `urllib.request`, and bounded sleep
for watch mode.

**Step 3: Run focused tests and observe failure**

```bash
python3 -B -m unittest adapters.herdr.test_publisher -v
```

**Step 4: Implement pure functions first**

```python
def build_snapshot(state: dict, manifest: dict, workspace_id: str) -> dict:
    """Return one role-graph/v1 snapshot without I/O."""

def publish_snapshot(snapshot: dict, endpoint: str, token: str | None) -> None:
    """POST one immutable snapshot."""
```

Then add a CLI with `--state`, `--manifest`, `--workspace-id`, `--endpoint`,
`--watch`, and `--interval`. Watch mode publishes only when revision changes.

**Step 5: Add the standard manifest**

Use logical roles and assignee chips:

- Orchestrator — P1
- Implementation A/B/C — P2/P3/P4 on one layer
- Integration — P5
- Independent QC — P6
- Functional QC — P7
- Visual QC — P8
- Persona QC — P9
- Correction Owner — P5
- Delivery — P5

Include failure policies for every applicable gate, not only P7. Only a current
`FINDING` becomes `activeFailureRoute`.

**Step 6: Run focused and contract tests**

```bash
python3 -B -m unittest adapters.herdr.test_publisher -v
```

Expected: PASS.

**Step 7: Commit and write the lane receipt**

Commit message:

```text
feat: publish Herdr state as a role graph
```

## Task 6: Integrate the Standalone Viewer

**Owner:** P5 only

**Files:**

- Modify: `README.md`
- Create: `docs/herdr-adapter.md`

**Step 1: Verify receipts before integration**

Validate contract ID, lane ID, generation, session, input identity, output
commit, owned paths, and acceptance commands for all three implementation
lanes. Reject stale or dirty receipts.

**Step 2: Integrate viewer commits**

Merge/cherry-pick in dependency order:

1. `viewer_protocol_server`
2. `viewer_frontend`

Resolve only true integration conflicts. Do not rewrite lane-owned behavior.

**Step 3: Integrate the repository-local Herdr adapter**

Integrate `herdr_readonly_publisher` into the same viewer integration branch.
Confirm its diff contains only `adapters/herdr/**`.

**Step 4: Write the local guide**

Document:

```bash
cd /Users/haido/multi-agent-graph-demo
npm run build
npm run server

cd /Users/haido/multi-agent-graph-demo
python3 -B adapters/herdr/publisher.py \
  --state /absolute/path/to/workspace-state.json \
  --manifest adapters/herdr/manifests/standard.json \
  --workspace-id wK \
  --endpoint http://127.0.0.1:4173/api/snapshots \
  --watch
```

State that the viewer is optional and read-only.

**Step 5: Run the minimum full verification**

Viewer:

```bash
npm test -- --run
npm run build
node tests/browser-smoke.mjs
```

Repository-local Herdr adapter:

```bash
python3 -B -m unittest adapters.herdr.test_publisher -v
```

Adapter-to-viewer:

1. start the viewer against a temporary JSONL file;
2. publish a real-format Herdr fixture;
3. open the selected scope/run in Playwright;
4. assert role, assignee, status, relation, and active loop;
5. capture screenshot and API response evidence.

**Step 6: Compare frozen evidence without rerunning it**

Verify:

- `benchmarks/frozen-superpowers-v1.json` is byte-identical to Herdr base;
- the existing result
  `benchmarks/results/688c7a3d6b95b46a4870e9154c047e7bc8a86ecf.json`
  is unchanged;
- no benchmark command was invoked;
- the release note repeats `152s / 1009s` frozen and `143s / 776s` latest
  Herdr PASS only as comparison evidence.

**Step 7: Prove Herdr remained untouched**

Compare the tracked Herdr diff and installed-skill digest with the values
recorded before dispatch. Any change is release-blocking and must not be
silently reverted.

**Step 8: Produce integration receipts**

Record:

- viewer base, integrated commit, and tree SHA;
- unchanged Herdr tracked-tree SHA;
- unchanged installed-skill digest;
- protocol fixture SHA-256;
- full verification commands and exit codes;
- browser screenshot path.

## Task 7: Independent Review and QC

**Owner:** P6, then P7-P9

**Step 1: P6 independent review**

Review the integrated viewer diff against the approved spec and plan. Block on:

- UI-specific workflow branches;
- snapshot mixing across scope/run;
- publisher access outside the selected state;
- any Herdr mutation or agent command;
- P1/controller/watcher behavior changes;
- missing validation;
- missing test evidence;
- frozen artifact changes;
- unrelated files.

P6 writes a validator-clean review receipt. P1 only routes findings.

**Step 2: Route findings**

- Viewer backend/protocol findings return to `viewer_protocol_server`.
- Viewer layout/UI findings return to `viewer_frontend`.
- Herdr mapping/isolation findings return to `herdr_readonly_publisher`.
- Integration-only conflicts return to P5.

Every correction increments the affected lane generation and reruns that
lane's acceptance checks. P5 reintegrates; P6 rereviews.

**Step 3: P7 functional QC**

Run the browser smoke, restart hydration, SSE update, workspace mismatch, and
failure-loop scenarios independently.

**Step 4: P8 visual QC**

Inspect the screenshot at desktop and narrow viewport. Require:

- top-down hierarchy;
- horizontal parallel roles;
- straight forward links;
- clear outer feedback loop;
- legible role/status/task/P chip;
- no visual implication that P5 is a separate worker from its logical roles.

**Step 5: P9 persona QC**

From the orchestrator user perspective, confirm:

- current role and next gate are identifiable;
- active failure owner and return target are understandable;
- scope switching cannot show mixed runs;
- there is no control that can mutate an agent or pane.

## Task 8: Commit and Push the Standalone Viewer

**Owner:** P5 only after P6-P9 PASS

**Step 1: Reconfirm the protected Herdr boundaries**

Do not edit, sync, install, commit, or push anything in:

```text
/Users/haido/herdr-orchestrator
/Users/haido/.codex/skills/herdr-orchestrator
```

Do not edit or sync the external `writing-plans` copies under `~/.codex` or
`~/.agents`.

**Step 2: Commit integration documentation**

Use normal commits:

```text
docs: explain the local live role graph
```

**Step 3: Re-run release checks on final commits**

Run the viewer suite/build/browser smoke and Herdr full suite/contract verifier
from clean final trees. Confirm both worktrees are clean.

**Step 4: Push the viewer repository**

Fetch and verify ancestry before push. Push normal forward updates only. Never
force-push.

**Step 5: Record final delivery**

Report:

- final viewer commit SHA;
- pushed viewer branch;
- local viewer URL;
- exact publisher command;
- P6-P9 receipts;
- unchanged Herdr tracked-tree and installed-skill digest evidence;
- frozen/latest benchmark comparison;
- any intentionally deferred items.
