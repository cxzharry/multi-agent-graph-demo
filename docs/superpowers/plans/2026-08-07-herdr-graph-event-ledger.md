# Herdr Graph Event Ledger Implementation Plan

> **For Herdr delivery:** REQUIRED SUB-SKILL: Use
> `herdr-orchestrator` only after this plan is approved.

**Goal:** Replace misleading status-only live graphs with a truthful, event-backed agent workflow that separates liveness from result, preserves completed assignments, and renders actual dispatch, artifact handoff, review, and rework relationships.

**Architecture:** A workspace/run-scoped append-only journal records explicit semantic transitions only while the viewer is active. Both publishers merge journal facts with their existing authoritative state and publish backward-compatible `role-graph/v1` snapshots. The frontend renders approved option A: P1 at the top, artifact flow as the primary topology, only the current P1 control edge dashed, and rework loops in the outer gutter.

**Tech Stack:** Python 3.10+ stdlib and unittest, Node.js 24 ESM, React 19, TypeScript, Vitest, Dagre, React Flow, Playwright, Herdr CLI.

---

## Approved Inputs

- Design: `docs/superpowers/specs/2026-08-07-herdr-graph-event-ledger-design.md`
- Design commit: `495d6ec8f54a1e9129f1e91902cb9c9197513a82`
- Source repository: `/Users/haido/multi-agent-graph-demo`
- Installed Codex target: `/Users/haido/.codex/skills/herdr-graph-viewer`
- Claude target: `/Users/haido/.claude/skills/herdr-graph-viewer`
- Forbidden target: `/Users/haido/.codex/skills/herdr-orchestrator`
- Frozen references, never rewritten or rerun as baselines: Compact 152 seconds; Multi-module 1009 seconds.
- Accepted Herdr references: Compact 143 seconds; Multi-module 776 seconds; both quality gates PASS.

## Locked File Ownership

### P2 — flow publisher

- Create `adapters/herdr/flow_journal.py` and `adapters/herdr/test_flow_journal.py`.
- Create `adapters/herdr/flow_projection.py` and `adapters/herdr/test_flow_projection.py`.
- Modify `adapters/herdr/publisher.py` and `adapters/herdr/test_publisher.py`.
- Modify `adapters/herdr/session_publisher.py` and `adapters/herdr/test_session_publisher.py`.

### P3 — launcher and emitter

- Create `skills/herdr-graph-viewer/scripts/emit_event.py` and `skills/herdr-graph-viewer/scripts/test_emit_event.py`.
- Modify `skills/herdr-graph-viewer/scripts/start_viewer.py` and `skills/herdr-graph-viewer/scripts/test_start_viewer.py`.
- Modify `skills/herdr-graph-viewer/SKILL.md` and `README.md`.

### P4 — protocol and visual graph

- Modify `shared/role-graph.js`, `tests/protocol.test.js`, and `src/graph/types.ts`.
- Modify `src/graph/RoleNode.tsx`, `src/graph/FeedbackEdge.tsx`, `src/graph/layout.ts`, `src/graph/layout.test.ts`, `src/graph/useLiveGraph.ts`, `src/main.tsx`, and `src/style.css`.
- Modify `tests/browser-smoke.mjs`.

P2/P3/P4 run concurrently with disjoint paths. P5 integrates in that order. P6 independently reviews one immutable candidate. P7/P8/P9 then run concurrently against that exact candidate. Findings return to the owning lane and every changed candidate repeats P5/P6 and applicable QC.

## Locked Data Contracts

`flow_journal.py` defines exactly:

```python
EVENT_SCHEMA_VERSION = "role-graph-event/v1"
EVENT_KINDS = {
    "CONTROL_DISPATCH",
    "ARTIFACT_HANDOFF",
    "ASSIGNMENT_RESULT",
    "REWORK_ROUTE",
    "CONTROLLER_RECOVERED",
    "RUN_TERMINAL",
}
RESULTS = {"PASS", "FAIL", "BLOCKED", "SKIPPED", "REWORK"}
```

Every event has `schemaVersion`, `eventId`, `workspaceId`, `runId`, `at`, `kind`, and a positive integer `generation`. Relationship events contain source and target assignment descriptors:

```python
{
    "id": "implementation-ui:g1",
    "role": "Implementation",
    "slot": "P2",
    "agentSessionId": "optional-live-session-id",
    "task": "Implement checkout UI",
}
```

Keep `schemaVersion: role-graph/v1`. New snapshot fields are optional:

```ts
type AgentLiveness = 'running' | 'idle' | 'offline' | 'stale';
type AssignmentResult = 'pass' | 'fail' | 'blocked' | 'skipped' | 'rework';
type RelationshipMode = 'declared' | 'event-backed' | 'unavailable';

type RoleNode = {
  liveness?: AgentLiveness;
  result?: AssignmentResult;
  lastActivityAt?: string;
};

type RoleEdge = {
  kind: 'forward' | 'return' | 'control';
  occurrenceCount?: number;
  lastEventAt?: string;
  reason?: string;
};
```

Legacy required fields stay required. New publishers set `liveness` and `result`; the UI uses them when present and preserves old snapshot rendering otherwise.

## Task 1: Build the exact run-local event journal

**Owner:** P2  
**Files:** Create `adapters/herdr/flow_journal.py`; create `adapters/herdr/test_flow_journal.py`.

- [ ] **Step 1: Write failing validation tests**

Cover one valid event for every kind. Reject missing identity, foreign workspace/run, unknown kind, malformed timestamp, non-positive generation, incomplete assignment descriptors, and unknown result.

```python
event = validate_event(value, workspace_id="wK", run_id="run-1")
self.assertEqual("evt-dispatch-p2-g1", event["eventId"])
```

- [ ] **Step 2: Run RED**

```bash
python3 -B -m unittest adapters.herdr.test_flow_journal -v
```

Expected: FAIL because `flow_journal` does not exist.

- [ ] **Step 3: Implement pure validation**

Implement `validate_event(value, *, workspace_id, run_id)` with defensive copy, strict exact identity, ISO-8601 validation, and kind-specific fields. Do not mutate caller data.

- [ ] **Step 4: Write failing append/read tests**

```python
journal = FlowJournal(path, workspace_id="wK", run_id="run-1")
journal.append(event)
journal.append(event)
reader = FlowJournalReader(path, workspace_id="wK", run_id="run-1")
self.assertEqual([event], reader.read_new())
self.assertEqual([], reader.read_new())
```

Also test two sequential writers, tied timestamps preserving append order, duplicate IDs projecting once, valid prefix plus malformed tail, and foreign identity rejection.

- [ ] **Step 5: Implement locked append and read**

Use an adjacent lock file and `fcntl.flock(LOCK_EX)`. `FlowJournal.append()` performs only one canonical compact JSONL append, flush, and `os.fsync`, so a fresh emitter process does not scan prior history. `FlowJournalReader.read_new()` retains its byte offset and seen event IDs, deduplicates first occurrence in ledger order, and parses only the appended suffix after initial hydration. A restarted reader performs one full recovery scan. A malformed tail raises `JournalError` without rewriting the file.

- [ ] **Step 6: Run GREEN, time, and commit**

```bash
python3 -B -m unittest adapters.herdr.test_flow_journal -v
git add adapters/herdr/flow_journal.py adapters/herdr/test_flow_journal.py
git commit -m "feat: add exact graph flow journal"
```

Append 200 unique temporary events and record median/p95/max. Median added append time must be below 10 ms.

## Task 2: Project truthful assignments and relationships

**Owner:** P2  
**Files:** Create `adapters/herdr/flow_projection.py`; create `adapters/herdr/test_flow_projection.py`.

- [ ] **Step 1: Write option-A RED tests**

Construct P1 dispatches to P2/P3/P4, implementation handoffs to P5, P5 to P6, a P6 finding to P4, and P4 rework to P5. Assert P1 running, completed workers offline plus pass, actual artifact pairs, exactly one active control edge, and one return pair.

```python
self.assertEqual([("orchestrator", "implementation-ui:g2")], active_control_pairs)
self.assertEqual([("independent-qc:g1", "implementation-ui:g2")], return_pairs)
```

- [ ] **Step 2: Write retention and recovery RED tests**

Prove missing live agents become offline without deletion, repeated handoffs increase `occurrenceCount`, stale generations cannot become current, and `CONTROLLER_RECOVERED` keeps node `orchestrator` while increasing generation.

- [ ] **Step 3: Run RED**

```bash
python3 -B -m unittest adapters.herdr.test_flow_projection -v
```

- [ ] **Step 4: Implement the deterministic projector**

```python
def project_flow(*, events, live_agents, p1_session_id, prior_nodes=None):
    """Return nodes, edges, activeFailureRoute, timeline, and telemetry."""
```

Seed P1 and observed agents; merge assignment descriptors by assignment ID; bind liveness by exact agent session; retain prior missing assignments as offline; apply result separately; keep only the newest active control edge; aggregate forward/return pairs; derive layers only from artifact edges; retain a bounded timeline in append order.

- [ ] **Step 5: Run GREEN and commit**

```bash
python3 -B -m unittest adapters.herdr.test_flow_projection -v
git add adapters/herdr/flow_projection.py adapters/herdr/test_flow_projection.py
git commit -m "feat: project event-backed agent workflows"
```

## Task 3: Integrate projection into both publishers

**Owner:** P2  
**Files:** Modify `adapters/herdr/publisher.py`, `adapters/herdr/test_publisher.py`, `adapters/herdr/session_publisher.py`, and `adapters/herdr/test_session_publisher.py`.

- [ ] **Step 1: Write session RED tests**

Add `--flow-journal`. With events, assert `relationshipMode: event-backed`, live P1 remains running even when Herdr reports done, a done live worker is idle plus pass, and a removed worker remains offline plus pass. Without a journal, preserve `unavailable` and legacy nodes.

- [ ] **Step 2: Write control RED tests**

For synthetic topology, overlay journal artifact/control/return edges and separate slot liveness from lane result. Map controller slot `ACTIVE` to running. For custom manifests, preserve authored topology byte-for-byte.

- [ ] **Step 3: Run RED**

```bash
python3 -B -m unittest adapters.herdr.test_flow_journal adapters.herdr.test_flow_projection adapters.herdr.test_session_publisher adapters.herdr.test_publisher -v
```

- [ ] **Step 4: Load exact journal fail-open**

Both publishers accept optional `--flow-journal`. Load only exact workspace/run events. Malformed data keeps the last valid snapshot and reports telemetry `{status: degraded, lastValidAt, reason}`. Publishers never repair the journal.

- [ ] **Step 5: Merge optional fields without snapshot churn**

Set liveness, result, activity, relationship mode, edge count/time/reason, and bounded timeline. Preserve legacy fields and unchanged-poll suppression.

- [ ] **Step 6: Run GREEN and commit**

```bash
python3 -B -m unittest discover -s adapters/herdr -p 'test_*.py' -v
git add adapters/herdr
git commit -m "feat: publish truthful live workflow relationships"
```

## Task 4: Add the explicit event emitter CLI

**Owner:** P3  
**Files:** Create `skills/herdr-graph-viewer/scripts/emit_event.py`; create `skills/herdr-graph-viewer/scripts/test_emit_event.py`.

- [ ] **Step 1: Write CLI RED tests**

Invoke `main(argv)` against a temporary journal. Cover every event kind, assignment JSON parsing, exact identity mismatch, missing fields, duplicate IDs projecting once through `FlowJournalReader`, and machine-readable output.

- [ ] **Step 2: Run RED**

```bash
python3 -B -m unittest skills/herdr-graph-viewer/scripts/test_emit_event.py -v
```

- [ ] **Step 3: Implement one small CLI**

Accept `--journal`, `--workspace-id`, `--run-id`, `--event-id`, `--at`, `--kind`, `--generation`, source/target/assignment JSON, `--result`, artifact JSON, and `--reason`. Import `FlowJournal`; do not duplicate validation. Print exactly one JSON object containing `status`, `eventId`, `appended`, and `elapsedMs`. Exit 0 for a valid new or duplicate event and 2 for validation/identity failure.

- [ ] **Step 4: Run GREEN and commit**

```bash
python3 -B -m unittest skills/herdr-graph-viewer/scripts/test_emit_event.py -v
git add skills/herdr-graph-viewer/scripts/emit_event.py skills/herdr-graph-viewer/scripts/test_emit_event.py
git commit -m "feat: add graph handoff event emitter"
```

## Task 5: Make launcher journal identity exact and reusable

**Owner:** P3  
**Files:** Modify `skills/herdr-graph-viewer/scripts/start_viewer.py`; modify `skills/herdr-graph-viewer/scripts/test_start_viewer.py`.

- [ ] **Step 1: Write journal path/output RED tests**

Assert the journal resolves below `runs_root / workspace_id / viewer / flow-events` with a collision-safe run filename. Launcher output must contain absolute `flowJournal` and an `emitCommand` prefix containing exact installed emitter, journal, workspace, and run values.

- [ ] **Step 2: Write publisher identity RED tests**

Both control and session publisher argv contain `--flow-journal`. Reuse requires the exact resolved path. A publisher for another journal is foreign/missing, not reusable and not stoppable. Existing same-scope stale replacement remains guarded.

- [ ] **Step 3: Write lifecycle RED tests**

Cover cold launch, current reuse, stale replacement, viewer restart preserving journal, and an invocation in another mocked workspace that cannot discover or mutate the first workspace journal or panes.

- [ ] **Step 4: Implement minimal launcher changes**

Create only the journal parent directory; do not emit a fake event. Pass the path to the publisher, include it in matching, and return emitter metadata. Preserve placement: server right of P1, publisher below that server in the right rail, never below P1.

- [ ] **Step 5: Run GREEN and commit**

```bash
python3 -B -m unittest skills/herdr-graph-viewer/scripts/test_start_viewer.py -v
git add skills/herdr-graph-viewer/scripts/start_viewer.py skills/herdr-graph-viewer/scripts/test_start_viewer.py
git commit -m "feat: launch exact run flow journals"
```

## Task 6: Document invoke-time event recording

**Owner:** P3  
**Files:** Modify `skills/herdr-graph-viewer/SKILL.md`; modify `README.md`.

- [ ] **Step 1: Add exact P1 examples**

After a ready launcher result, the current P1 records only real semantic transitions through returned `emitCommand`. Include complete control-dispatch, artifact-handoff, result, and rework-route commands. Workers still report to P1 and never dispatch downstream agents directly.

- [ ] **Step 2: Lock optional behavior**

Document: viewer not invoked means zero event command/overhead; telemetry failure never blocks work; non-orchestrator flows use the same contract; no manifest or brainstorming is required; no global hook, raw log scan, or installed orchestrator edit is allowed.

- [ ] **Step 3: Validate and commit**

```bash
python3 -B /Users/haido/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/herdr-graph-viewer
git add README.md skills/herdr-graph-viewer/SKILL.md
git commit -m "docs: explain event-backed graph workflows"
```

## Task 7: Extend the snapshot protocol compatibly

**Owner:** P4  
**Files:** Modify `shared/role-graph.js`, `tests/protocol.test.js`, and `src/graph/types.ts`.

- [ ] **Step 1: Write protocol RED tests**

Validate a complete event-backed snapshot. Reject unknown liveness/result/mode, control edges with unknown nodes, zero occurrence count, and malformed activity timestamps. Re-run legacy compact and branched snapshots unchanged.

- [ ] **Step 2: Run RED**

```bash
npm test -- --run tests/protocol.test.js
```

- [ ] **Step 3: Add optional validators and types**

Add liveness, result, and relationship-mode sets; add `control` to edge kinds. Validate optional fields only when present. Do not change the schema version or weaken existing required fields.

- [ ] **Step 4: Run GREEN and commit**

```bash
npm test -- --run tests/protocol.test.js
git add shared/role-graph.js tests/protocol.test.js src/graph/types.ts
git commit -m "feat: extend graph protocol for live workflow facts"
```

## Task 8: Render separate liveness, result, and recency

**Owner:** P4  
**Files:** Modify `src/graph/RoleNode.tsx`, `src/style.css`, and `tests/browser-smoke.mjs`.

- [ ] **Step 1: Write browser RED assertions**

Post P1 running, P2 offline plus pass, P4 running plus rework, and P6 offline plus fail. Assert visible labels, distinct badges, `data-liveness`, `data-result`, exact P-only badges, and relative/absolute time. Assert P1 never renders `PASSED`.

- [ ] **Step 2: Run RED**

```bash
npm run build
node tests/browser-smoke.mjs
```

- [ ] **Step 3: Implement minimal node rendering**

Use `data.liveness` as primary state when present and a deterministic legacy mapping otherwise. Render result separately. Preserve full accessible role/assignee text. Show relative recency on card and absolute time in title.

- [ ] **Step 4: Add scoped styles**

Only running glows. Idle/offline/stale remain distinct and non-active. Result badges must remain inside cards at desktop, tablet, and 390x844 mobile widths.

- [ ] **Step 5: Run GREEN and commit**

```bash
npm run build
node tests/browser-smoke.mjs
git add src/graph/RoleNode.tsx src/style.css tests/browser-smoke.mjs
git commit -m "feat: separate agent liveness from task results"
```

## Task 9: Render approved option-A relationships

**Owner:** P4  
**Files:** Modify `src/graph/FeedbackEdge.tsx`, `src/graph/layout.ts`, `src/graph/layout.test.ts`, `src/graph/useLiveGraph.ts`, `src/main.tsx`, `src/style.css`, and `tests/browser-smoke.mjs`.

- [ ] **Step 1: Write layout RED tests**

Assert P1 is top, parallel implementation nodes share Y, artifact edges determine depth, and control/return edges do not alter rank. Forward links are straight and return links use the outer gutter.

- [ ] **Step 2: Write browser RED assertions**

Require exactly one active dashed P1 edge; no permanent P1 star; P2/P3/P4 to P5 to P6 artifact flow; muted history; visible P6-to-owner loop; append-order timeline timestamps; event-backed empty notice; truthful unavailable legacy notice; unchanged custom topology.

- [ ] **Step 3: Implement relationship mapping**

Map forward to straight edges, control to straight dashed edges, and return to `FeedbackEdge`. Only active status animates. Use edge count/time/reason as labels or titles without adding non-agent nodes.

- [ ] **Step 4: Preserve selection and degraded telemetry**

Hydration/SSE continues to accept exact scope plus run only. Render `TELEMETRY DEGRADED` with last valid time without discarding the graph.

- [ ] **Step 5: Run GREEN and commit**

```bash
npm test -- --run
npm run build
node tests/browser-smoke.mjs
git add src shared tests
git commit -m "feat: render event-backed workflow and rework loops"
```

## Task 10: Integrate exact lane artifacts

**Owner:** P5  
**Prerequisites:** validator-clean current-generation PASS receipts for P2/P3/P4.

- [ ] **Step 1: Validate receipts and ownership**

Run `validate_lane_receipt.py` for each implementation lane. Reject stale generation, dirty worktree, wrong input identity, unowned paths, or missing RED/GREEN evidence.

- [ ] **Step 2: Integrate P2, P3, then P4**

Cherry-pick accepted commits into a clean worktree descending from this plan commit. Resolve only locked API/type mismatches. Never reset, rebase, force, or delete user worktrees.

- [ ] **Step 3: Run the full candidate matrix**

```bash
python3 -B -m unittest discover -s adapters/herdr -p 'test_*.py' -v
python3 -B -m unittest skills/herdr-graph-viewer/scripts/test_emit_event.py skills/herdr-graph-viewer/scripts/test_start_viewer.py -v
npm test -- --run
npm run build
node tests/browser-smoke.mjs
python3 -B /Users/haido/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/herdr-graph-viewer
git diff --check
```

- [ ] **Step 4: Commit candidate and receipt**

Record exact commit/tree, accepted lane commits, command results, and unchanged installed-orchestrator identity.

## Task 11: Independently review the candidate

**Owner:** P6  
**Prerequisite:** immutable P5 candidate.

- [ ] **Step 1: Bind review identity**

Verify exact commit/tree, clean tracked state, ancestor relation, and validator-clean P2/P3/P4/P5 receipts.

- [ ] **Step 2: Review adversarial contracts**

Check P1 controller-only behavior, exact workspace isolation, event identity, malformed-tail recovery, no guessed edges, custom-manifest compatibility, offline retention, generation ordering, active-only control edge, return loop, zero behavior when viewer is off, and forbidden-target protection.

- [ ] **Step 3: Re-run independent checks**

Run focused journal/projector/launcher/protocol tests, build, and browser smoke on the exact candidate. PASS requires `output_artifact == input_identity`; otherwise issue a candidate-bound finding.

## Task 12: Run concurrent live QC

**Owners:** P7 functional/performance, P8 design, P9 persona.  
**Prerequisite:** all inspect the same P6-approved candidate.

### P7 functional/performance

- [ ] Launch only in the current authorized workspace and verify exact journal/workspace/run plus current fingerprints.
- [ ] Exercise real dispatch, handoff, result, and reroute events; verify sequence, dedupe, restart recovery, offline retention, and cross-workspace isolation.
- [ ] Measure 200 appends and record median/p95/max; median must remain below 10 ms.
- [ ] Run compact viewer-on canary, compare with frozen 152 seconds and accepted Herdr 143 seconds, and require quality gates PASS. Never rerun or edit frozen baseline.

### P8 design

- [ ] Verify P1 top, applicable parallel workers same rank, straight artifact links, one active dashed P1 edge, muted history, outer-gutter loop, timestamps, and no clipping at desktop/tablet/390x844.
- [ ] Capture the real remediation run and deterministic loop. Fixture-only evidence is insufficient.

### P9 persona

- [ ] Verify an operator can distinguish RUNNING from PASS, find the current agent and time, follow implementation through P5/P6, and understand the return route.
- [ ] Verify a non-orchestrator canary emits A-to-B without manifest or brainstorming, while a no-event session shows no guessed relationship.

Each lane writes a generation-bound exact-candidate receipt.

## Task 13: Run meta-harness until locked success

**Owner:** P1 routes; P5 mutates candidates; evaluator remains independent.  
**Files:** Create `plans/meta-harness-2026-08-07-event-backed-live-graph/`.

- [ ] **Step 1: Lock rubric before evaluation**

Use `Intent: IMPROVE`, `max-iter: until-pass`, and 120-minute wall-clock budget. Criteria: liveness/result truth 20%; event-backed relationships 25%; option-A live visual 20%; recovery/isolation 15%; non-orchestrator flexibility 10%; performance/other-skill isolation 10%. Every score is at least 8.5, with hard floor 8.0 on truth, isolation, and live visual.

- [ ] **Step 2: Evaluate exact evidence**

Consume source diff, tests, live API snapshot, real screenshots, timing, compact comparison, receipts, and installed hashes. Do not accept fixture-only claims.

- [ ] **Step 3: Route failures and repeat gates**

Feedback includes exact criterion, evidence, owner, required rerun, and candidate. P1 routes to owner, advances generation, then repeats P5/P6/QC for every changed candidate.

- [ ] **Step 4: Stop only on success or budget**

Persist spec, rubric, state, feedback, trace, outcome, and report. Budget exhaustion is not success.

## Task 14: Deliver source and installed viewer skills

**Owner:** P5 after every current-generation gate PASS.

- [ ] **Step 1: Verify final identity**

Require P6/P7/P8/P9 PASS on one commit/tree, meta-harness SUCCESS, clean tracked tree, and no unreviewed product delta.

- [ ] **Step 2: Advance and push normally**

Fast-forward source main, push once, and prove HEAD/main/origin/main/remote main plus tree are identical. Never force, reset, or rebase.

- [ ] **Step 3: Sync graph-viewer only**

Mirror only `skills/herdr-graph-viewer/` to Codex. Preserve Claude symlink if it resolves to Codex; otherwise mirror only its exact graph-viewer directory. Compare SHA-256 manifests and run quick validation plus installed tests.

- [ ] **Step 4: Prove forbidden targets unchanged**

Compare before/after identities for installed `herdr-orchestrator` and Superpowers writing-plans integration.

- [ ] **Step 5: Verify installed runtime twice**

Invoke installed viewer twice in the authorized workspace. First may replace only stale same-scope runtime; second must reuse server, publisher, and journal. Verify live option-A output and do not close viewer panes.

## Herdr Delivery Contract

```yaml
contract_id: herdr-graph-event-ledger-20260807
mode: Standard
risk: high
mode_reason: >-
  Browser-visible workflow semantics, publisher projection, launcher identity,
  persistent telemetry, recovery, and installed-skill delivery make Compact
  ineligible.
review_applicability:
  P7_functional_performance_qc: applicable
  P8_design_layout_qc: applicable
  P9_persona_qc: applicable
lanes:
  - lane_id: flow_publisher
    slot: P2
    generation: 1
    owned_paths:
      - adapters/herdr/flow_journal.py
      - adapters/herdr/test_flow_journal.py
      - adapters/herdr/flow_projection.py
      - adapters/herdr/test_flow_projection.py
      - adapters/herdr/publisher.py
      - adapters/herdr/test_publisher.py
      - adapters/herdr/session_publisher.py
      - adapters/herdr/test_session_publisher.py
    prerequisites: [approved_spec, approved_plan]
    acceptance:
      - python3 -B -m unittest discover -s adapters/herdr -p 'test_*.py' -v
      - event_append_median_below_10ms
    terminal_receipt_command: >-
      python3 -B /Users/haido/herdr-orchestrator/scripts/write_lane_receipt.py
      --control-state "$CONTROL_STATE" --lane flow_publisher --status PASS
      --output-json "$OUTPUT_IDENTITY" --acceptance flow_publisher
      --check "adapter_matrix=pass" --check "event_timing=pass"
  - lane_id: launcher_emitter
    slot: P3
    generation: 1
    owned_paths:
      - skills/herdr-graph-viewer/scripts/emit_event.py
      - skills/herdr-graph-viewer/scripts/test_emit_event.py
      - skills/herdr-graph-viewer/scripts/start_viewer.py
      - skills/herdr-graph-viewer/scripts/test_start_viewer.py
      - skills/herdr-graph-viewer/SKILL.md
      - README.md
    prerequisites: [approved_spec, approved_plan]
    acceptance:
      - python3 -B -m unittest skills/herdr-graph-viewer/scripts/test_emit_event.py skills/herdr-graph-viewer/scripts/test_start_viewer.py -v
      - graph_viewer_skill_validation
    terminal_receipt_command: >-
      python3 -B /Users/haido/herdr-orchestrator/scripts/write_lane_receipt.py
      --control-state "$CONTROL_STATE" --lane launcher_emitter --status PASS
      --output-json "$OUTPUT_IDENTITY" --acceptance launcher_emitter
      --check "launcher_emitter_matrix=pass"
  - lane_id: protocol_visual
    slot: P4
    generation: 1
    owned_paths:
      - shared/role-graph.js
      - tests/protocol.test.js
      - src/graph/types.ts
      - src/graph/RoleNode.tsx
      - src/graph/FeedbackEdge.tsx
      - src/graph/layout.ts
      - src/graph/layout.test.ts
      - src/graph/useLiveGraph.ts
      - src/main.tsx
      - src/style.css
      - tests/browser-smoke.mjs
    prerequisites: [approved_spec, approved_plan]
    acceptance:
      - npm test -- --run
      - npm run build
      - node tests/browser-smoke.mjs
    terminal_receipt_command: >-
      python3 -B /Users/haido/herdr-orchestrator/scripts/write_lane_receipt.py
      --control-state "$CONTROL_STATE" --lane protocol_visual --status PASS
      --output-json "$OUTPUT_IDENTITY" --acceptance protocol_visual
      --check "frontend_matrix=pass" --check "option_a_browser=pass"
  - lane_id: integration
    slot: P5
    generation: 1
    owned_paths: []
    prerequisites: [flow_publisher, launcher_emitter, protocol_visual]
    acceptance: [full_candidate_matrix, receipt_validation, diff_check]
    terminal_receipt_command: >-
      python3 -B /Users/haido/herdr-orchestrator/scripts/write_lane_receipt.py
      --control-state "$CONTROL_STATE" --lane integration --status PASS
      --output-json "$OUTPUT_IDENTITY" --acceptance integration
      --check "full_candidate_matrix=pass"
  - lane_id: independent_review
    slot: P6
    generation: 1
    owned_paths: []
    prerequisites: [integration]
    acceptance: [candidate_identity, adversarial_contract_review]
    terminal_receipt_command: >-
      python3 -B /Users/haido/herdr-orchestrator/scripts/write_lane_receipt.py
      --control-state "$CONTROL_STATE" --lane independent_review --status PASS
      --output-json "$INPUT_IDENTITY" --acceptance independent_review
      --check "contract_review=pass"
  - lane_id: functional_performance_qc
    slot: P7
    generation: 1
    owned_paths: []
    prerequisites: [independent_review]
    acceptance: [live_runtime, recovery, isolation, event_timing, compact_comparison]
    terminal_receipt_command: >-
      python3 -B /Users/haido/herdr-orchestrator/scripts/write_lane_receipt.py
      --control-state "$CONTROL_STATE" --lane functional_performance_qc --status PASS
      --output-json "$INPUT_IDENTITY" --acceptance functional_performance_qc
      --check "functional_performance_qc=pass"
  - lane_id: design_qc
    slot: P8
    generation: 1
    owned_paths: []
    prerequisites: [independent_review]
    acceptance: [live_option_a_layout, responsive_graph, real_loop_evidence]
    terminal_receipt_command: >-
      python3 -B /Users/haido/herdr-orchestrator/scripts/write_lane_receipt.py
      --control-state "$CONTROL_STATE" --lane design_qc --status PASS
      --output-json "$INPUT_IDENTITY" --acceptance design_qc
      --check "design_qc=pass"
  - lane_id: persona_qc
    slot: P9
    generation: 1
    owned_paths: []
    prerequisites: [independent_review]
    acceptance: [operator_comprehension, non_orchestrator_canary, honest_empty_state]
    terminal_receipt_command: >-
      python3 -B /Users/haido/herdr-orchestrator/scripts/write_lane_receipt.py
      --control-state "$CONTROL_STATE" --lane persona_qc --status PASS
      --output-json "$INPUT_IDENTITY" --acceptance persona_qc
      --check "persona_qc=pass"
deployment_topology:
  source_repo: /Users/haido/multi-agent-graph-demo
  codex_installed_target: /Users/haido/.codex/skills/herdr-graph-viewer
  claude_installed_target: /Users/haido/.claude/skills/herdr-graph-viewer
  meta_harness_root: plans/meta-harness-2026-08-07-event-backed-live-graph
  forbidden_targets:
    - /Users/haido/.codex/skills/herdr-orchestrator
    - /Users/haido/.agents/skills/writing-plans
    - every Herdr workspace other than the caller workspace
evidence:
  required:
    - generation-bound receipts for every applicable lane
    - RED then GREEN evidence for P2 P3 P4
    - one immutable candidate for P6 P7 P8 P9
    - real live remediation graph matching approved option A
    - deterministic real finding and rework loop
    - non-orchestrator A-to-B canary without manifest
    - event timing and compact frozen-reference comparison
    - meta-harness SUCCESS with every criterion at least 8.5
    - source and installed SHA-256 parity
    - unchanged installed herdr-orchestrator identity
    - local main equals origin/main equals remote main
```
