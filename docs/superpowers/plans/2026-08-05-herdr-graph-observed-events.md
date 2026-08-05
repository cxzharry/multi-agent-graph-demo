# Herdr Graph Observed Events Implementation Plan

> **For Herdr delivery:** REQUIRED SUB-SKILL: Use
> `herdr-orchestrator` only after this plan is approved.

**Goal:** Make every live graph show bounded lifecycle activity immediately while never drawing relationships that the selected source cannot prove.

**Architecture:** A shared Python transition ledger turns existing publisher polling into timestamped lifecycle events. Session and synthetic control publishers emit node layers without fabricated edges, while the React UI labels those flows as observed topology; custom manifests remain authoritative and unchanged.

**Tech Stack:** Python 3.10+ stdlib, unittest, React 19, TypeScript, Vitest, Playwright, immutable `role-graph/v1` snapshots.

---

## File Map

- Create `adapters/herdr/observed_events.py`: bounded transition ledger shared by both publishers.
- Create `adapters/herdr/test_observed_events.py`: deterministic event, ordering, removal, and retention tests.
- Modify `adapters/herdr/session_publisher.py`: emit initial and changed lifecycle events; remove unproven control edges.
- Modify `adapters/herdr/test_session_publisher.py`: RED/GREEN coverage for useful initial snapshots and deduplication.
- Modify `adapters/herdr/publisher.py`: remove synthetic control edges and merge bounded observed events in watch publication.
- Modify `adapters/herdr/test_publisher.py`: truthfulness and custom-topology regression coverage.
- Modify `src/main.tsx`: render an observed-topology notice only for session/synthetic flows.
- Modify `src/style.css`: compact, restrained notice styling.
- Modify `src/graph/layout.test.ts`: prove two-layer disconnected topology remains aligned.
- Modify `tests/browser-smoke.mjs`: verify notice/event visibility, zero observed edges, and custom-loop preservation.
- Modify `skills/herdr-graph-viewer/SKILL.md`: document lifecycle-only events and truthful relationship fallback.
- Modify `README.md`: describe observed versus declared topology.

## Parallelization Strategy

Implementation parallelism: Parallel lanes

Reason: publisher logic/tests and frontend/skill presentation use disjoint owned paths and can be integrated deterministically.

- **Can parallelize:** yes.
- **Lane P2 — publisher observation:** owns only `adapters/herdr/observed_events.py`, `adapters/herdr/test_observed_events.py`, `adapters/herdr/session_publisher.py`, `adapters/herdr/test_session_publisher.py`, `adapters/herdr/publisher.py`, and `adapters/herdr/test_publisher.py`.
- **Lane P3 — viewer truthfulness:** owns only `src/main.tsx`, `src/style.css`, `src/graph/layout.test.ts`, `tests/browser-smoke.mjs`, `skills/herdr-graph-viewer/SKILL.md`, and `README.md`.
- **Sequential dependencies:** P5 integrates P2 then P3, runs the combined suite, and creates one immutable candidate. P6 and applicable QC lanes inspect that exact candidate.
- **Per-lane verification:** P2 runs three Python unittest modules plus AST/read-only guards already contained in publisher tests. P3 runs Vitest, build, and browser smoke against protocol-valid fixtures.
- **Final verification:** full Python suite, full Vitest suite, build, browser smoke, launcher tests, skill validation, exact installed/source parity, Git diff check, and live current-workspace launch.
- **Recommended Phase 3 Agent Split Gate input:** Spawn — two disjoint implementation lanes plus independent integration/review/QC are safe and required by Herdr.

### Task 1: Shared bounded transition ledger

**Files:**
- Create: `adapters/herdr/observed_events.py`
- Create: `adapters/herdr/test_observed_events.py`

- [ ] **Step 1: Write failing tests for initial observation and no-op polling**

Define tests using the public API below:

```python
ledger = ObservationLedger(limit=4)
events = ledger.observe(nodes, observed_at="2026-08-05T10:00:00Z")
self.assertEqual(["NODE_OBSERVED", "NODE_OBSERVED"], [e["kind"] for e in events])
self.assertEqual([], ledger.observe(nodes, observed_at="2026-08-05T10:00:02Z"))
```

Also assert every event has `id`, `at`, `nodeId`, `kind`, and `message`; generation is included only when the node supplies an integer generation.

- [ ] **Step 2: Run RED**

Run: `python3 -B -m unittest adapters.herdr.test_observed_events -v`

Expected: FAIL because `adapters.herdr.observed_events` does not exist.

- [ ] **Step 3: Implement the minimal ledger**

Expose this focused interface:

```python
class ObservationLedger:
    def __init__(self, limit: int = 64): ...
    def observe(self, nodes: list[dict], observed_at: str | None = None) -> list[dict]: ...
    @property
    def events(self) -> list[dict]: ...
```

Projection identity is node `id`; compared fields are `status`, `assignee`, and `generation`. Sort nodes by ID before comparison. Generate monotonic `observed-000001` IDs and UTC `Z` timestamps. Retain only `limit` events.

- [ ] **Step 4: Add RED tests for transitions, removal, and retention**

Assert one exact event for `NODE_STATUS_CHANGED`, `NODE_ASSIGNEE_CHANGED`, and `NODE_REMOVED`; two simultaneous changes are ordered by node ID and event kind; a limit of four retains exactly the last four events.

- [ ] **Step 5: Make the edge cases GREEN**

Reject a non-positive limit and malformed node IDs with `ObservationError`. Return deep copies from `events` so callers cannot mutate ledger state.

- [ ] **Step 6: Verify and commit**

Run: `python3 -B -m unittest adapters.herdr.test_observed_events -v`

Expected: all tests PASS.

Commit: `feat: observe bounded agent lifecycle events`

### Task 2: Session and control publisher integration

**Files:**
- Modify: `adapters/herdr/session_publisher.py`
- Modify: `adapters/herdr/test_session_publisher.py`
- Modify: `adapters/herdr/publisher.py`
- Modify: `adapters/herdr/test_publisher.py`

- [ ] **Step 1: Write failing session tests**

Update the session snapshot test to assert:

```python
self.assertEqual([], snapshot["edges"])
self.assertEqual(len(snapshot["nodes"]), len(snapshot["events"]))
self.assertTrue(all(event["at"].endswith("Z") for event in snapshot["events"]))
```

Use an injected `ObservationLedger` and fixed `observed_at` to prove one status change appends one event while reordered/unchanged agent input publishes nothing.

- [ ] **Step 2: Run session RED**

Run: `python3 -B -m unittest adapters.herdr.test_session_publisher -v`

Expected: FAIL because the current snapshot has direct P1 edges and no events.

- [ ] **Step 3: Integrate the ledger into session mode**

`main()` creates one `ObservationLedger`. `publish_if_changed()` builds nodes first, calls `ledger.observe()`, and publishes the ledger's bounded history. `build_session_snapshot()` accepts optional `ledger` and `observed_at` keyword arguments for deterministic tests. Keep `layer: 0` for P1 and `layer: 1` for other agents, but return `edges: []`, `failurePolicies: []`, and `activeFailureRoute: None`.

- [ ] **Step 4: Write failing synthetic/control tests**

Assert `synthesize_manifest(state)["edges"] == []` and `failurePolicies == []`. Add a watch-publication test with a shared ledger that proves revision 1 emits initial events, revision 2 appends exactly one status event, and a repeated revision does not publish.

Add a custom-manifest regression that compares authored `edges` and `failurePolicies` before and after observer integration.

- [ ] **Step 5: Run control RED**

Run: `python3 -B -m unittest adapters.herdr.test_publisher -v`

Expected: FAIL because synthetic mode still fabricates P1 control edges and control publication does not retain observations.

- [ ] **Step 6: Integrate the ledger into control watch mode**

Keep `build_snapshot()` deterministic and preserve authored state events. Extend `publish_if_changed()` with an optional ledger and fixed observation time for tests; after building the snapshot, append newly observed lifecycle events, cap the combined event list, and advance `generatedAt` to the newest valid event. `main()` owns one ledger for the watcher lifetime. A repeated revision returns before observation or publication.

- [ ] **Step 7: Run the full backend lane verification**

Run:

```bash
python3 -B -m unittest \
  adapters.herdr.test_observed_events \
  adapters.herdr.test_session_publisher \
  adapters.herdr.test_publisher -v
```

Expected: all tests PASS; existing workspace isolation, parser, supersession, custom-manifest, heartbeat, and read-only tests remain green.

- [ ] **Step 8: Commit**

Commit: `feat: publish truthful observed graph activity`

### Task 3: Viewer provenance notice and browser behavior

**Files:**
- Modify: `src/main.tsx`
- Modify: `src/style.css`
- Modify: `src/graph/layout.test.ts`
- Modify: `tests/browser-smoke.mjs`
- Modify: `skills/herdr-graph-viewer/SKILL.md`
- Modify: `README.md`

- [ ] **Step 1: Write failing frontend/layout tests**

Add a disconnected snapshot layout test with P1 at layer 0 and three agents at layer 1. Assert P1 is above the agents, all agents share the same Y coordinate, and `forwardEdges` is empty.

Extend browser smoke with an `auto-operational` snapshot containing zero edges and timestamped observed events. Assert:

```javascript
assert.equal(await page.locator('.forward-edge').count(), 0);
await page.getByTestId('relationship-notice').waitFor();
assert.match(await page.getByTestId('relationship-notice').innerText(), /relationships unavailable/i);
assert.ok(await page.locator('.timeline-item').count() > 0);
```

Then select the existing authored branched-loop fixture and assert the notice disappears while forward and feedback edges remain visible.

- [ ] **Step 2: Run RED**

Run:

```bash
npm test -- --run
npm run build
node tests/browser-smoke.mjs
```

Expected: unit/build remain diagnostic; browser smoke FAILS because no relationship notice exists and the current synthetic fixture still carries an edge.

- [ ] **Step 3: Add the restrained notice**

Compute:

```typescript
const observedTopology =
  snapshot?.flowId === 'auto-operational' || snapshot?.flowId === 'live-session';
```

Render one compact `data-testid="relationship-notice"` block inside the graph panel when true. The copy is exactly `Observed topology — relationships unavailable` with one short explanatory line. Do not alter custom flow rendering or the `role-graph/v1` type.

- [ ] **Step 4: Document the runtime contract**

Update the skill and README to state:

- session/synthetic events are bounded lifecycle observations, not raw activity;
- session/synthetic relationships are unavailable and therefore unconnected;
- custom manifests remain the only exact topology source;
- startup stays explicit and no global hook is installed.

- [ ] **Step 5: Run GREEN and commit**

Run:

```bash
npm test -- --run
npm run build
node tests/browser-smoke.mjs
```

Expected: all PASS and the smoke screenshot shows initial events, no synthetic lines, and intact custom loops.

Commit: `feat: label observed graph topology truthfully`

### Task 4: Integration, adversarial verification, and delivery

**Files:**
- Modify only when a failing in-scope test proves a required correction.
- Create meta-harness evidence under `plans/meta-harness-2026-08-05-observed-graph/`.

- [ ] **Step 1: Integrate exact lane commits**

P5 verifies each lane receipt and cherry-picks P2 before P3 into the integration worktree. Reject overlapping paths or uncommitted worker changes.

- [ ] **Step 2: Run the smallest full candidate matrix**

```bash
python3 -B -m unittest discover -s adapters/herdr -p 'test_*.py' -v
python3 -B -m unittest skills.herdr-graph-viewer.scripts.test_start_viewer -v
npm test -- --run
npm run build
node tests/browser-smoke.mjs
git diff --check HEAD^ HEAD
```

Expected: every command exits 0.

- [ ] **Step 3: Run live current-workspace verification**

From the current Herdr workspace, invoke the repository launcher or installed candidate in an isolated candidate path. Require `status: ready`, exact `workspace_id`, verified snapshot, non-empty events, zero edges in session mode, and publisher/server reuse on the second invocation. Never inspect another workspace.

- [ ] **Step 4: Independent review and applicable QC**

P6 checks exact candidate/tree, contract isolation, boundedness, no fabricated relationships, custom topology preservation, and test evidence. P7 repeats functional/runtime checks. P8 verifies top-down alignment, notice readability, no synthetic lines, and custom loop geometry. P9 verifies the operator can distinguish observed versus declared topology and event recency.

- [ ] **Step 5: Meta-harness failure routing**

Score all locked criteria. If any score is below 8.5, write `feedback/iter-N.json` and `state/state-N.json`, classify the failure, and route only the targeted concern into the next generation. Stop only on SUCCESS or the 120-minute budget.

- [ ] **Step 6: Sync only the installed viewer skill**

After P6/P7/P8/P9 PASS, synchronize the reviewed `skills/herdr-graph-viewer/` subtree to `/Users/haido/.codex/skills/herdr-graph-viewer/`. Compare an exact relative-path SHA-256 manifest. Do not touch any sibling skill directory.

- [ ] **Step 7: Commit evidence and push**

Write `outcome.json`, report, and trace; commit final evidence; fast-forward `main`; push without force; verify local HEAD, `origin/main`, and remote ref match.

## Herdr Delivery Contract

```yaml
contract_id: herdr-graph-observer-truth-20260805
mode: Standard
risk: medium
mode_reason: >-
  The change crosses Python publisher behavior, persistent snapshots, React UI,
  browser smoke, installed skill delivery, and visible relationship semantics;
  Compact is not eligible.
review_applicability:
  P7_functional_performance_qc: applicable
  P8_design_layout_qc: applicable
  P9_persona_qc: applicable
lanes:
  - lane_id: publisher_observation
    slot: P2
    generation: 1
    owned_paths:
      - adapters/herdr/observed_events.py
      - adapters/herdr/test_observed_events.py
      - adapters/herdr/session_publisher.py
      - adapters/herdr/test_session_publisher.py
      - adapters/herdr/publisher.py
      - adapters/herdr/test_publisher.py
    prerequisites: [approved_spec, approved_plan]
    acceptance:
      - python3 -B -m unittest adapters.herdr.test_observed_events adapters.herdr.test_session_publisher adapters.herdr.test_publisher -v
    terminal_receipt: functional
  - lane_id: viewer_truthfulness
    slot: P3
    generation: 1
    owned_paths:
      - src/main.tsx
      - src/style.css
      - src/graph/layout.test.ts
      - tests/browser-smoke.mjs
      - skills/herdr-graph-viewer/SKILL.md
      - README.md
    prerequisites: [approved_spec, approved_plan]
    acceptance:
      - npm test -- --run
      - npm run build
      - node tests/browser-smoke.mjs
    terminal_receipt: functional
  - lane_id: integration
    slot: P5
    generation: 1
    owned_paths: [integration_candidate]
    prerequisites: [publisher_observation, viewer_truthfulness]
    acceptance: [full_candidate_matrix]
    terminal_receipt: integration
  - lane_id: independent_review
    slot: P6
    generation: 1
    owned_paths: [read_only_candidate_review]
    prerequisites: [integration]
    acceptance: [contract_review, regression_review]
    terminal_receipt: review
  - lane_id: functional_qc
    slot: P7
    generation: 1
    owned_paths: [read_only_functional_qc]
    prerequisites: [integration]
    acceptance: [runtime_matrix, isolation_checks]
    terminal_receipt: functional_performance_qc
  - lane_id: design_qc
    slot: P8
    generation: 1
    owned_paths: [read_only_visual_qc]
    prerequisites: [integration]
    acceptance: [browser_layout_qc]
    terminal_receipt: design_qc
  - lane_id: persona_qc
    slot: P9
    generation: 1
    owned_paths: [read_only_operator_qc]
    prerequisites: [integration]
    acceptance: [operator_comprehension_qc]
    terminal_receipt: persona_qc
deployment_topology:
  source_repo: /Users/haido/multi-agent-graph-demo
  installed_target: /Users/haido/.codex/skills/herdr-graph-viewer
  forbidden_targets:
    - /Users/haido/herdr-orchestrator
    - /Users/haido/.codex/skills/herdr-orchestrator
    - /Users/haido/.codex/skills/writing-plans
    - /Users/haido/.agents/skills/writing-plans
evidence:
  - exact lane receipts
  - exact integration candidate and tree
  - locked meta-harness feedback and outcome
  - independent P6 and P7-P9 PASS receipts
  - installed/source SHA-256 parity
```

