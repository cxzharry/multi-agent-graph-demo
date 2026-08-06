# Herdr Graph Viewer Runtime Fingerprint Implementation Plan

> **For Herdr delivery:** REQUIRED SUB-SKILL: Use
> `herdr-orchestrator` only after this plan is approved.

**Goal:** Make an explicit `herdr-graph-viewer` invocation reuse only byte-current publisher and server processes, replacing stale runtimes in their existing panes without accepting stale snapshots.

**Architecture:** The launcher computes deterministic publisher and viewer content fingerprints. Publisher argv/snapshots and server argv/health expose those fingerprints; discovery classifies exact processes as reusable, stale, or missing, and a locked replacement transaction safely stops and restarts only stale components. Session publisher bootstrap preserves trustworthy bounded events and advances beyond the persisted sequence.

**Tech Stack:** Python 3.10+ stdlib and unittest, Node.js 24 ESM, React 19, TypeScript, Vitest, Playwright, Herdr CLI, immutable `role-graph/v1` snapshots.

---

## Approved Inputs

- Design: `docs/superpowers/specs/2026-08-07-herdr-graph-viewer-runtime-fingerprint-design.md`
- Design commit: `653b76dd4728624fca74d80a32d02e2c498cf754`
- Source repository: `/Users/haido/multi-agent-graph-demo`
- Installed Codex target: `/Users/haido/.codex/skills/herdr-graph-viewer`
- Claude target: `/Users/haido/.claude/skills/herdr-graph-viewer`
- Reported failure fixture: legacy session snapshot with eight inferred P1 edges, zero events, and a publisher process whose argv matches but whose loaded modules predate current source.

## File Map

- Modify `skills/herdr-graph-viewer/scripts/start_viewer.py`: calculate fingerprints, classify server/publisher processes, coordinate same-pane replacement, and require fingerprint-bound readiness.
- Modify `skills/herdr-graph-viewer/scripts/test_start_viewer.py`: fingerprint calculation, legacy discovery, replacement ordering, sequence floors, ambiguity, reuse, and concurrency tests.
- Modify `adapters/herdr/observed_events.py`: restore trustworthy bounded observed-event history.
- Modify `adapters/herdr/test_observed_events.py`: restoration, malformed history, bounds, and counter-continuity tests.
- Modify `adapters/herdr/publisher.py`: accept/publish runtime fingerprints and load an exact current snapshot.
- Modify `adapters/herdr/test_publisher.py`: fingerprint, replacement, seed identity, and unmanaged-mode tests.
- Modify `adapters/herdr/session_publisher.py`: fingerprint snapshots, seed sequence/history, and force one newer startup snapshot.
- Modify `adapters/herdr/test_session_publisher.py`: legacy migration and restart-continuity tests.
- Modify `server.js`: parse forwarded port/fingerprint arguments and retain direct-development defaults.
- Modify `server/app.js`: expose runtime fingerprint through health.
- Modify `tests/server.test.js`: health fingerprint and unmanaged compatibility tests.
- Modify `tests/browser-smoke.mjs`: assert the fingerprint-aware health contract without changing layout.
- Modify `README.md`: document current/stale/missing reuse and manual unmanaged mode.
- Modify `skills/herdr-graph-viewer/SKILL.md`: document automatic stale-runtime recovery on explicit invocation.
- Create `plans/meta-harness-2026-08-07-runtime-fingerprint/`: locked evaluation and evidence files.

## Parallelization Strategy

- **P2 publisher runtime:** owns only the six listed `adapters/herdr/` files.
- **P3 server runtime:** owns only `server.js`, `server/app.js`, and `tests/server.test.js`.
- **P4 launcher recovery:** owns launcher, launcher tests, browser smoke, README, and skill documentation.

P2/P3/P4 execute concurrently against fixed contracts in this plan. P5 integrates P2, P3, then P4. P6 reviews one immutable candidate. After P6 PASS, P7/P8/P9 run concurrently against the same candidate.

## Task 1: Deterministic launcher fingerprints

**Owner:** P4 launcher recovery

**Files:**
- Modify: `skills/herdr-graph-viewer/scripts/start_viewer.py`
- Modify: `skills/herdr-graph-viewer/scripts/test_start_viewer.py`

- [ ] **Step 1: Write failing publisher fingerprint tests**

Create a temporary repository containing four non-test adapter modules plus `test_publisher.py`. Assert:

```python
first = launcher.publisher_runtime_fingerprint(repo)
(repo / "README.md").write_text("docs changed", encoding="utf-8")
self.assertEqual(first, launcher.publisher_runtime_fingerprint(repo))
(repo / "adapters/herdr/observed_events.py").write_text(
    "EVENT_LIMIT = 65\n", encoding="utf-8"
)
self.assertNotEqual(first, launcher.publisher_runtime_fingerprint(repo))
```

Also prove a runtime helper rename changes the hash and `test_*.py` changes do not.

- [ ] **Step 2: Write failing viewer fingerprint tests**

Build a minimal viewer tree with server, shared, src, index, package/lock, Vite, and TypeScript inputs. Assert changes to those inputs change the hash while changes under `docs/`, `tests/`, `dist/`, and `node_modules/` do not.

- [ ] **Step 3: Run RED**

```bash
python3 -B -m unittest \
  skills.herdr-graph-viewer.scripts.test_start_viewer.RuntimeFingerprintTest -v
```

Expected: FAIL because the fingerprint APIs do not exist.

- [ ] **Step 4: Implement deterministic hashing**

```python
def _content_fingerprint(repo: Path, relative_paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for relative in sorted(relative_paths, key=lambda value: value.as_posix()):
        path = repo / relative
        if not path.is_file():
            raise LauncherError("missing_viewer", f"Missing runtime file: {path}")
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def publisher_runtime_fingerprint(repo: Path) -> str:
    adapter_root = repo / "adapters/herdr"
    paths = [
        path.relative_to(repo)
        for path in adapter_root.glob("*.py")
        if not path.name.startswith("test_")
    ]
    if not paths:
        raise LauncherError("missing_viewer", f"Missing publisher runtime: {adapter_root}")
    return _content_fingerprint(repo, paths)


def viewer_runtime_fingerprint(repo: Path) -> str:
    required = {
        Path("server.js"), Path("index.html"),
        Path("package.json"), Path("package-lock.json"),
    }
    patterns = (
        "server/**/*.js", "shared/**/*.js", "src/**/*.ts",
        "src/**/*.tsx", "src/**/*.css", "vite.config.*", "tsconfig*.json",
    )
    discovered = {
        path.relative_to(repo)
        for pattern in patterns
        for path in repo.glob(pattern)
        if path.is_file()
    }
    return _content_fingerprint(repo, list(required | discovered))
```

- [ ] **Step 5: Run GREEN**

Run the focused class and the full launcher suite. Expected: PASS. Commit after Task 4 so P4 never leaves call sites inconsistent.

## Task 2: Publisher fingerprint and restart continuity

**Owner:** P2 publisher runtime

**Files:**
- Modify: `adapters/herdr/observed_events.py`
- Modify: `adapters/herdr/test_observed_events.py`
- Modify: `adapters/herdr/publisher.py`
- Modify: `adapters/herdr/test_publisher.py`
- Modify: `adapters/herdr/session_publisher.py`
- Modify: `adapters/herdr/test_session_publisher.py`

- [ ] **Step 1: Write failing ledger restoration tests**

```python
ledger = ObservationLedger.restore(nodes, prior_events, limit=4)
self.assertEqual(prior_events, ledger.events)
events = ledger.observe(changed_nodes, observed_at="2026-08-07T01:00:00Z")
self.assertEqual("observed-000003", events[0]["id"])
self.assertEqual("NODE_STATUS_CHANGED", events[0]["kind"])
```

Empty, malformed, foreign-ID, or non-observed history must create a fresh ledger. More than `limit` valid events retains the newest suffix.

- [ ] **Step 2: Run ledger RED**

Run: `python3 -B -m unittest adapters.herdr.test_observed_events -v`

Expected: FAIL because `ObservationLedger.restore` does not exist.

- [ ] **Step 3: Implement strict bounded restoration**

```python
@classmethod
def restore(
    cls,
    nodes: list[dict],
    events: list[dict],
    limit: int = DEFAULT_LIMIT,
) -> "ObservationLedger":
    ledger = cls(limit)
    if not events:
        return ledger
    retained = copy.deepcopy(events[-limit:])
    counters = []
    for event in retained:
        event_id = event.get("id") if isinstance(event, dict) else None
        if not isinstance(event_id, str) or not event_id.startswith("observed-"):
            return cls(limit)
        suffix = event_id.removeprefix("observed-")
        if not suffix.isdigit():
            return cls(limit)
        counters.append(int(suffix))
    ledger._events = retained
    ledger._counter = max(counters)
    ledger._previous = ledger._project(nodes)
    return ledger
```

- [ ] **Step 4: Write failing publisher fingerprint tests**

For both modes assert `snapshot["publisherFingerprint"] == "publisher-sha"`. Test `--runtime-fingerprint publisher-sha`; omission must preserve direct/manual usage through `publisherFingerprint: "unmanaged"`.

Add exact current-snapshot loading tests for URL encoding, scope/run rejection, invalid JSON, timeout, and unavailable server.

- [ ] **Step 5: Write failing legacy migration test**

Seed sequence 111 with eight edges and zero events. Start with fingerprint `publisher-sha` and floor 112. Assert:

```python
self.assertEqual(112, snapshot["sequence"])
self.assertEqual("publisher-sha", snapshot["publisherFingerprint"])
self.assertEqual([], snapshot["edges"])
self.assertGreater(len(snapshot["events"]), 0)
```

With valid observed history, restart preserves history and appends only real later transitions.

- [ ] **Step 6: Run publisher RED**

```bash
python3 -B -m unittest \
  adapters.herdr.test_observed_events \
  adapters.herdr.test_session_publisher \
  adapters.herdr.test_publisher -v
```

Expected: FAIL on missing restoration, CLI, snapshot, loader, and sequence-floor behavior.

- [ ] **Step 7: Implement publisher contracts**

Add optional arguments:

```python
parser.add_argument("--runtime-fingerprint", default="unmanaged")
parser.add_argument("--sequence-floor", type=_positive_sequence, default=1)
```

Both snapshot builders add `publisherFingerprint`. The exact loader derives:

```python
query = urllib.parse.urlencode({"scopeId": scope_id, "runId": run_id})
snapshot_url = endpoint.removesuffix("/api/snapshots") + "/api/snapshot?" + query
```

Session startup restores only valid exact-run observed history, then publishes once at `max(sequence_floor, seed_sequence + 1)`. Later unchanged polls remain silent. Control mode retains authoritative revision and `--replace-current` behavior.

- [ ] **Step 8: Run GREEN and commit**

Run the three modules and full adapter discovery. Expected: PASS.

Commit: `feat: fingerprint graph publishers`

## Task 3: Viewer server fingerprint health

**Owner:** P3 server runtime

**Files:**
- Modify: `server.js`
- Modify: `server/app.js`
- Modify: `tests/server.test.js`

- [ ] **Step 1: Write failing health tests**

```javascript
const app = createApp({dataFile, runtimeFingerprint: 'viewer-sha'});
expect(await response.json()).toEqual({
  service: 'herdr-role-graph-viewer',
  schemaVersion: 'role-graph/v1',
  capabilities: ['space-name-summary', 'session-presence'],
  runtimeFingerprint: 'viewer-sha',
});
```

Also require `runtimeFingerprint: 'unmanaged'` when direct callers omit it.

- [ ] **Step 2: Run server RED**

Run: `npm test -- --run tests/server.test.js`

Expected: FAIL because health does not expose runtime identity.

- [ ] **Step 3: Implement CLI parsing and health propagation**

```javascript
function option(name, fallback) {
  const index = process.argv.indexOf(name);
  if (index === -1) return fallback;
  const value = process.argv[index + 1];
  if (!value || value.startsWith('--')) {
    throw new Error(`${name} requires a value`);
  }
  return value;
}

const PORT = Number(option('--port', process.env.PORT || 4173));
const RUNTIME_FINGERPRINT = option('--runtime-fingerprint', 'unmanaged');
```

Reject an invalid port or empty supplied fingerprint. Pass the fingerprint to `createApp()`, default it to `unmanaged`, and return it in health.

- [ ] **Step 4: Run GREEN and commit**

```bash
npm test -- --run tests/server.test.js
npm run build
```

Expected: PASS.

Commit: `feat: expose viewer runtime fingerprint`

## Task 4: Stale-process discovery and same-pane replacement

**Owner:** P4 launcher recovery

**Files:**
- Modify: `skills/herdr-graph-viewer/scripts/start_viewer.py`
- Modify: `skills/herdr-graph-viewer/scripts/test_start_viewer.py`
- Modify: `tests/browser-smoke.mjs`
- Modify: `README.md`
- Modify: `skills/herdr-graph-viewer/SKILL.md`

- [ ] **Step 1: Write failing process classification tests**

Introduce this result contract:

```python
@dataclass(frozen=True)
class ProcessMatch:
    pane_id: str | None
    status: str
```

Allowed statuses are `reusable`, `stale`, and `missing`. Prove exact publisher identity plus exact fingerprint is reusable; missing/different fingerprint is stale and returns the same pane; unrelated identity is missing. Prove viewer health is current only with the exact fingerprint, stale with missing/different fingerprint, and occupied for an unrelated service.

- [ ] **Step 2: Write failing legacy server mapping tests**

Require one ordinary current-workspace pane with label `graph-viewer-server`, exact repo cwd, and foreground `node server.js` to be the migration target. Zero candidates yields no target. Two candidates raise `LauncherError("ambiguous_stale_server", f"Multiple legacy graph-viewer-server panes in workspace {workspace_id}")` before any `send-keys`, split, or run.

- [ ] **Step 3: Write failing replacement ordering tests**

Against a stale publisher and stale server, record Herdr calls and assert:

```python
self.assertLess(
    calls.index(("pane", "send-keys", "publisher", "ctrl+c")),
    calls.index(("pane", "send-keys", "server", "ctrl+c")),
)
self.assertLess(
    calls.index(("pane", "run", "server", server_command)),
    calls.index(("pane", "run", "publisher", publisher_command)),
)
self.assertFalse(any(call[:2] == ("pane", "split") for call in calls))
```

The publisher command includes `--runtime-fingerprint` and session mode includes `--sequence-floor 112`. The server command forwards `--port` and `--runtime-fingerprint` through npm.

- [ ] **Step 4: Write failing readiness tests**

Return old session sequence 111 first, then 112 with the desired fingerprint. Require rejection of 111. Control-state replacement requires exact revision and desired fingerprint. Missing/wrong fingerprint times out as `publisher_start_failed`.

- [ ] **Step 5: Run launcher RED**

Run: `python3 -B -m unittest skills.herdr-graph-viewer.scripts.test_start_viewer -v`

Expected: FAIL on classification, migration, replacement, command, and readiness assertions.

- [ ] **Step 6: Implement discovery and bounded stop**

Replace boolean publisher matchers with `ProcessMatch`. Preserve exact identity matching, then compare `--runtime-fingerprint`. Scan only ordinary panes in the caller workspace.

```python
def _wait_for_shell(pane_id: str, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = _herdr("pane", "process-info", "--pane", pane_id)
        info = _result_value(response, "process_info") or {}
        if info.get("foreground_processes") == []:
            return
        time.sleep(0.1)
    raise LauncherError(
        "process_stop_failed", f"Pane {pane_id} did not return to its shell"
    )
```

Never run a replacement until the old process is confirmed stopped.

- [ ] **Step 7: Implement server selection and fingerprint readiness**

Compute both fingerprints once under the workspace lock. Reuse exact current health; migrate one unambiguous current-workspace stale server; otherwise skip stale/occupied ports and select a free port.

Extend `_wait_for_snapshot()` with `expected_publisher_fingerprint` and optional `minimum_sequence_exclusive`. Return only when scope/run/space, revision or sequence floor, and fingerprint all match.

- [ ] **Step 8: Preserve fast reuse and concurrency**

Update the concurrency test so two simultaneous invokes still produce one server and one publisher. The second returns both `reused` fields true and performs no stop, build, split, or snapshot append.

- [ ] **Step 9: Document and browser-test recovery**

README and skill docs state that invocation remains explicit, current runtimes reuse, stale runtimes replace in-place, unmanaged manual processes are diagnostic only, and no other workspace is mutated.

Browser smoke requires a non-empty health `runtimeFingerprint` while retaining top-down layout, zero observed edges, event recency, custom loops, and Active/History assertions.

- [ ] **Step 10: Run GREEN and commit**

```bash
python3 -B -m unittest skills.herdr-graph-viewer.scripts.test_start_viewer -v
npm test -- --run
npm run build
node tests/browser-smoke.mjs
git diff --check
```

Expected: PASS.

Commit: `feat: replace stale graph viewer runtimes`

## Task 5: Integration, independent gates, meta-harness, and delivery

**Owner:** P5 integration, P6 independent review, P7/P8/P9 QC

**Files:**
- Product files remain read-only unless a candidate-bound failing gate routes one exact finding to its owning lane in a new generation.
- Create evaluator evidence only under `plans/meta-harness-2026-08-07-runtime-fingerprint/`.

- [ ] **Step 1: Integrate receipt-clean lane commits**

P5 validates P2/P3/P4 receipts, verifies disjoint ownership, and cherry-picks P2, P3, then P4. Preserve untracked dependencies; never commit `node_modules`, `dist`, or smoke screenshots.

- [ ] **Step 2: Run the immutable-candidate matrix**

```bash
python3 -B -m unittest discover -s adapters/herdr -p 'test_*.py' -v
python3 -B -m unittest skills.herdr-graph-viewer.scripts.test_start_viewer -v
npm test -- --run
npm run build
node tests/browser-smoke.mjs
git diff --check 653b76dd4728624fca74d80a32d02e2c498cf754..HEAD
python3 -B /Users/haido/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/herdr-graph-viewer
```

Expected: all exit 0. Add one exact fixture probe showing legacy `8 edges / 0 events` input becomes a newer zero-edge snapshot with observed events and current fingerprint.

- [ ] **Step 3: Run independent review and concurrent QC**

P6 checks exact candidate/tree, ownership, stop-before-start ordering, sequence continuity, legacy compatibility, ambiguity fail-closed behavior, isolation, and custom topology regressions.

After P6 PASS, P7/P8/P9 inspect the same candidate concurrently:

- P7 repeats functional/runtime/concurrency and forbidden-cross-workspace checks.
- P8 runs browser smoke and verifies unchanged top-down layout, straight authored edges, zero observed edges, event recency, and custom loops.
- P9 verifies explicit invocation, reuse/replacement evidence, and `idle -> pending` independently from topology truth.

- [ ] **Step 4: Run locked meta-harness**

Lock target 8.5 and hard floor 8.0 for stale detection, replacement safety, snapshot/event continuity, unchanged-invocation efficiency, and browser/operator isolation. Write feedback, state, outcome, report, and trace. Route scores below 8.5 to the owning lane and next generation. Stop only on `SUCCESS` or budget.

- [ ] **Step 5: Deliver source and installed skills**

After all gates PASS:

1. Commit evaluator evidence only.
2. Fast-forward source `main`; never force or rebase user commits.
3. Push and prove local main, `origin/main`, and remote main are identical.
4. Mirror only `skills/herdr-graph-viewer/` to the Codex target.
5. Preserve the Claude symlink when it resolves to Codex; otherwise sync only its exact skill directory.
6. Compare exact SHA-256 manifests; run quick validation and installed launcher tests.
7. Invoke installed skill twice only in an authorized eligible caller workspace: first replaces stale fixture/runtime; second reuses both. Never inspect, stop, dispatch to, or close another workspace.

## Herdr Delivery Contract

```yaml
contract_id: herdr-graph-runtime-fingerprint-20260807
mode: Standard
risk: high
mode_reason: >-
  This changes Python and Node process identity, same-pane stop/start lifecycle,
  persistent sequence handling, health, browser evidence, and installed skills.
  Browser/runtime/process mutation makes Compact ineligible.
review_applicability:
  P7_functional_performance_qc: applicable
  P8_design_layout_qc: applicable
  P9_persona_qc: applicable
lanes:
  - lane_id: publisher_runtime
    slot: P2
    generation: 1
    owned_paths:
      - adapters/herdr/observed_events.py
      - adapters/herdr/test_observed_events.py
      - adapters/herdr/publisher.py
      - adapters/herdr/test_publisher.py
      - adapters/herdr/session_publisher.py
      - adapters/herdr/test_session_publisher.py
    prerequisites: [approved_spec, approved_plan]
    acceptance:
      - python3 -B -m unittest adapters.herdr.test_observed_events adapters.herdr.test_session_publisher adapters.herdr.test_publisher -v
    terminal_receipt_command: >-
      python3 -B /Users/haido/herdr-orchestrator/scripts/write_lane_receipt.py
      --control-state "$CONTROL_STATE" --lane publisher_runtime --status PASS
      --output-json "$OUTPUT_IDENTITY" --acceptance publisher_runtime
      --check "publisher_tests=pass"
  - lane_id: server_runtime
    slot: P3
    generation: 1
    owned_paths: [server.js, server/app.js, tests/server.test.js]
    prerequisites: [approved_spec, approved_plan]
    acceptance:
      - npm test -- --run tests/server.test.js
      - npm run build
    terminal_receipt_command: >-
      python3 -B /Users/haido/herdr-orchestrator/scripts/write_lane_receipt.py
      --control-state "$CONTROL_STATE" --lane server_runtime --status PASS
      --output-json "$OUTPUT_IDENTITY" --acceptance server_runtime
      --check "server_tests=pass"
  - lane_id: launcher_recovery
    slot: P4
    generation: 1
    owned_paths:
      - skills/herdr-graph-viewer/scripts/start_viewer.py
      - skills/herdr-graph-viewer/scripts/test_start_viewer.py
      - tests/browser-smoke.mjs
      - README.md
      - skills/herdr-graph-viewer/SKILL.md
    prerequisites: [approved_spec, approved_plan]
    acceptance:
      - python3 -B -m unittest skills.herdr-graph-viewer.scripts.test_start_viewer -v
      - npm test -- --run
      - npm run build
      - node tests/browser-smoke.mjs
    terminal_receipt_command: >-
      python3 -B /Users/haido/herdr-orchestrator/scripts/write_lane_receipt.py
      --control-state "$CONTROL_STATE" --lane launcher_recovery --status PASS
      --output-json "$OUTPUT_IDENTITY" --acceptance launcher_recovery
      --check "launcher_browser_matrix=pass"
  - lane_id: integration
    slot: P5
    generation: 1
    owned_paths: []
    prerequisites: [publisher_runtime, server_runtime, launcher_recovery]
    acceptance: [full_candidate_matrix, legacy_upgrade_probe, diff_check]
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
  - lane_id: functional_qc
    slot: P7
    generation: 1
    owned_paths: []
    prerequisites: [independent_review]
    acceptance: [runtime_matrix, concurrency, isolation]
    terminal_receipt_command: >-
      python3 -B /Users/haido/herdr-orchestrator/scripts/write_lane_receipt.py
      --control-state "$CONTROL_STATE" --lane functional_qc --status PASS
      --output-json "$INPUT_IDENTITY" --acceptance functional_qc
      --check "functional_qc=pass"
  - lane_id: design_qc
    slot: P8
    generation: 1
    owned_paths: []
    prerequisites: [independent_review]
    acceptance: [browser_layout, observed_relationships, custom_loops]
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
    acceptance: [operator_upgrade_flow, status_topology_distinction]
    terminal_receipt_command: >-
      python3 -B /Users/haido/herdr-orchestrator/scripts/write_lane_receipt.py
      --control-state "$CONTROL_STATE" --lane persona_qc --status PASS
      --output-json "$INPUT_IDENTITY" --acceptance persona_qc
      --check "persona_qc=pass"
deployment_topology:
  source_repo: /Users/haido/multi-agent-graph-demo
  codex_installed_target: /Users/haido/.codex/skills/herdr-graph-viewer
  claude_installed_target: /Users/haido/.claude/skills/herdr-graph-viewer
  meta_harness_root: plans/meta-harness-2026-08-07-runtime-fingerprint
  forbidden_targets:
    - /Users/haido/herdr-orchestrator
    - /Users/haido/.codex/skills/herdr-orchestrator
    - every Herdr workspace other than the caller workspace
evidence:
  required:
    - generation-bound receipts for every applicable lane
    - exact candidate commit and tree for P6/P7/P8/P9
    - RED then GREEN evidence for P2/P3/P4
    - full matrix and legacy upgrade fixture
    - meta-harness SUCCESS with every criterion at least 8.5
    - source/installed SHA-256 parity
    - local main equals origin/main equals remote main
```
