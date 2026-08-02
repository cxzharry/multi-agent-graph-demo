# Herdr Space-Aware Graph Selector Implementation Plan

> **For Herdr delivery:** REQUIRED SUB-SKILL: Use
> `herdr-orchestrator` only after this plan is approved.

**Goal:** Make every graph selector option start with the live Herdr space name
so runs from different spaces are immediately distinguishable.

**Architecture:** Resolve the selected workspace label once in the launcher,
pass it as immutable publisher identity, persist it as optional snapshot
`spaceName`, and format selector labels from `spaceName · title`. Existing
snapshots fall back to `scopeId`; scope/run remain the only selection keys.

**Tech Stack:** Python 3 publisher/launcher, Node.js snapshot store and protocol,
React/TypeScript UI, Vitest, unittest, Playwright browser smoke.

---

## File Map

- `adapters/herdr/publisher.py`: accept and emit the exact space name.
- `adapters/herdr/test_publisher.py`: publisher RED/GREEN coverage.
- `skills/herdr-graph-viewer/scripts/start_viewer.py`: resolve the selected
  Herdr workspace label before pane mutation and bind it to publisher reuse.
- `skills/herdr-graph-viewer/scripts/test_start_viewer.py`: launcher label,
  propagation, reuse, and failure tests.
- `shared/role-graph.js`: validate optional `spaceName`.
- `tests/protocol.test.js`: protocol compatibility tests.
- `server/graph-store.js`: include `spaceName` in saved graph summaries.
- `tests/store.test.js`, `tests/server.test.js`: summary/API coverage.
- `src/graph/types.ts`: expose optional `spaceName` in snapshot and summary.
- `src/graph/useLiveGraph.ts`: provide the selector label formatter and retain
  `spaceName` after SSE updates.
- `src/graph/layout.test.ts`: formatter preference and fallback coverage.
- `src/main.tsx`: render the formatter instead of opaque IDs.
- `tests/browser-smoke.mjs`: prove two spaces are distinguishable.

## Herdr Delivery Contract

- `contract_id`: `herdr-graph-viewer-space-selector-20260802`
- Delivery mode: Standard because this is visible UI/browser behavior and
  requires independent review.
- All lanes use generation `1`, the same Herdr workspace, and the same approved
  spec/plan identity.
- P1 is controller-only. P1 does not edit, test, integrate, review, commit,
  push, or run browser QC.
- P2 owns `publisher_space_name`.
- P3 owns `selector_protocol_ui`.
- P4 owns `launcher_space_resolution`.
- P5 owns `integration` after P2-P4 PASS receipts.
- P6 owns independent contract/code review after P5.
- P7 owns functional test/build/browser QC after P6 PASS.
- P8 owns selector readability/design QC after P5.
- P9 owns user-persona discrimination QC after P5.
- No lane may edit `/Users/haido/herdr-orchestrator` or its installed skill.
- P5 alone syncs `/Users/haido/.codex/skills/herdr-graph-viewer`, commits the
  integrated candidate, and pushes after all required gates pass.

### Task 1: Publisher Space Identity — P2

**Owned paths:**

- `adapters/herdr/publisher.py`
- `adapters/herdr/test_publisher.py`

**Prerequisites:** Approved spec and plan; no implementation receipt.

- [ ] Add a failing publisher test that calls `build_snapshot` with
  `space_name="herdr-orchestrator"` and expects
  `snapshot["spaceName"] == "herdr-orchestrator"`.
- [ ] Run `python3 -B -m unittest adapters.herdr.test_publisher` and confirm the
  new test fails because the argument/field does not exist.
- [ ] Add required `space_name` propagation through `build_snapshot`,
  `publish_if_changed`, CLI parsing, and the watch loop. Reject empty names.
- [ ] Re-run `python3 -B -m unittest adapters.herdr.test_publisher`; expect all
  publisher tests to pass.
- [ ] Commit only the owned paths with
  `git commit -m "feat: publish Herdr space names"`.
- [ ] Write the terminal receipt:

```bash
python3 -B /Users/haido/.codex/skills/herdr-orchestrator/scripts/write_lane_receipt.py \
  --control-state "$HERDR_CONTROL_STATE" --lane publisher_space_name \
  --status PASS --check 'publisher unit tests=pass' \
  --output "commit=$(git rev-parse HEAD)"
```

### Task 2: Protocol, Store, and Selector Label — P3

**Owned paths:**

- `shared/role-graph.js`
- `tests/protocol.test.js`
- `server/graph-store.js`
- `tests/store.test.js`
- `tests/server.test.js`
- `src/graph/types.ts`
- `src/graph/useLiveGraph.ts`
- `src/graph/layout.test.ts`
- `src/main.tsx`
- `tests/browser-smoke.mjs`

**Prerequisites:** Approved spec and plan; independent from Task 1.

- [ ] Add failing tests proving optional non-empty `spaceName` is accepted,
  malformed `spaceName` is rejected, summaries retain it, and
  `graphOptionLabel` returns `spaceName · title` with `scopeId · title` fallback.
- [ ] Add a failing browser-smoke assertion for distinct options
  `herdr-orchestrator · Herdr graph viewer hardening` and
  `car-edge · Herdr standard delivery`.
- [ ] Run `npm test -- --run`; confirm the focused assertions fail for missing
  validation, summary propagation, and formatter behavior.
- [ ] Implement the optional protocol field, summary propagation, typed
  formatter, SSE summary retention, and selector rendering. Do not change URL
  identity or graph metadata.
- [ ] Run `npm test -- --run`; expect all Vitest suites to pass.
- [ ] Commit only the owned paths with
  `git commit -m "feat: label graphs by Herdr space"`.
- [ ] Write the terminal receipt:

```bash
python3 -B /Users/haido/.codex/skills/herdr-orchestrator/scripts/write_lane_receipt.py \
  --control-state "$HERDR_CONTROL_STATE" --lane selector_protocol_ui \
  --status PASS --check 'web tests=pass' \
  --output "commit=$(git rev-parse HEAD)"
```

### Task 3: Launcher Space Resolution — P4

**Owned paths:**

- `skills/herdr-graph-viewer/scripts/start_viewer.py`
- `skills/herdr-graph-viewer/scripts/test_start_viewer.py`

**Prerequisites:** Approved spec and plan; independent from Tasks 1-2.

- [ ] Add failing tests for exact `workspace_id` selection from
  `herdr workspace list`, non-empty label validation before `_split_pane`,
  `--space-name` command propagation, and publisher reuse matching the same
  space name.
- [ ] Run
  `python3 -B skills/herdr-graph-viewer/scripts/test_start_viewer.py`; confirm
  the new tests fail for the missing resolver/argument.
- [ ] Implement one workspace-label resolver, call it after state validation but
  before any server/publisher pane mutation, pass `--space-name`, include it in
  exact publisher identity, and return `space_name` in launcher JSON.
- [ ] Re-run the launcher test command; expect all launcher tests to pass.
- [ ] Commit only the owned paths with
  `git commit -m "feat: resolve Herdr space labels"`.
- [ ] Write the terminal receipt:

```bash
python3 -B /Users/haido/.codex/skills/herdr-orchestrator/scripts/write_lane_receipt.py \
  --control-state "$HERDR_CONTROL_STATE" --lane launcher_space_resolution \
  --status PASS --check 'launcher unit tests=pass' \
  --output "commit=$(git rev-parse HEAD)"
```

### Task 4: Integration and Required Gates — P5-P9

**Prerequisites:** Current-generation PASS receipts for Tasks 1-3.

- [ ] P5 integrates the three commits without changing worker-owned behavior,
  resolves only integration conflicts, and runs:

```bash
python3 -B -m unittest adapters.herdr.test_publisher
python3 -B skills/herdr-graph-viewer/scripts/test_start_viewer.py
npm test -- --run
npm run build
git diff --check
```

- [ ] P6 independently reviews the integrated diff against the design,
  workspace isolation, exact selection identity, backward compatibility, and
  no-pane-mutation-on-label-error contracts. Any finding routes to its owning
  lane and affected gates rerun.
- [ ] P8 confirms selector labels lead with readable, distinct space names and
  do not reintroduce the opaque-ID-first problem.
- [ ] P9 confirms a user can distinguish `herdr-orchestrator` from `car-edge`
  without interpreting `wK` or `wP`.
- [ ] P7 runs final functional QC:

```bash
node tests/browser-smoke.mjs
python3 -B -m unittest adapters.herdr.test_publisher
python3 -B skills/herdr-graph-viewer/scripts/test_start_viewer.py
npm test -- --run
npm run build
```

- [ ] P5 syncs the installed skill and verifies parity:

```bash
rsync -a --delete skills/herdr-graph-viewer/ /Users/haido/.codex/skills/herdr-graph-viewer/
diff -ru skills/herdr-graph-viewer /Users/haido/.codex/skills/herdr-graph-viewer
```

- [ ] P5 commits any integration-only changes, verifies
  `HEAD == main == origin/main` after push, and records a PASS receipt with the
  delivered commit, test outputs, build, browser smoke, and parity evidence.

## Acceptance

- The selector visibly renders the two expected space-first examples.
- Existing snapshots without `spaceName` render `scopeId · title`.
- Exact scope/run selection, SSE filtering, and persisted reload are unchanged.
- Missing live workspace labels fail before pane mutation.
- Publisher, launcher, protocol, store, server, frontend, build, browser smoke,
  P6 review, P8 design, P9 persona, installed parity, commit, and push gates pass.
