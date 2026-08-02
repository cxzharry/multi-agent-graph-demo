# Herdr Graph Viewer Manifestless Runs Implementation Plan

> **For Herdr delivery:** REQUIRED SUB-SKILL: Use
> `herdr-orchestrator` only after this plan is approved.

**Goal:** Make `$herdr-graph-viewer` open every valid P1 ledger without manual
manifest setup while preserving custom graphs, dynamic work, reassignment,
workspace isolation, and non-obscuring pane placement.

**Architecture:** The launcher preserves custom-manifest precedence and selects
`--synthesize` only when no custom source exists. The publisher derives an
operational manifest in memory from the same atomic state read used for the
snapshot, coalesces reassignment chains, and appends unmapped custom-run lanes
without inventing workflow dependencies. Viewer processes stay in a right-side
rail and are reused by exact state/mode identity.

**Tech Stack:** Python 3 standard library and `unittest`, Herdr CLI, Node.js,
React 19, TypeScript, Vite, Vitest, Playwright, Git worktrees.

---

## Locked Inputs

- Approved design:
  `docs/superpowers/specs/2026-08-02-herdr-graph-viewer-manifestless-runs-design.md`
- Design SHA-256:
  `41b5edfead872215af5030d099501a71e063b918169b4eac8822b6c9374203b8`
- Repository: `/Users/haido/multi-agent-graph-demo`
- Execution base: `3d6d45d9570e512d7765cef7e7b572e0ccb03fc5`
- Remote base before delivery: `b86bbe9b2d2ddace5453fc1efb822c02f80c3684`
- Read-only orchestrator source: `/Users/haido/herdr-orchestrator` at `7874aa2`
- Installed viewer skill: `/Users/haido/.codex/skills/herdr-graph-viewer`
- Frozen references, comparison only: Superpowers `152s`/`1009s`; latest
  Herdr `143s`/`776s`, both PASS. Never rerun or modify them.

This changes only the optional viewer, so orchestration timing is not a gate.
Prove instead that the orchestrator repo, installed orchestrator skill, and
frozen benchmark files are untouched.

## Success Criteria

1. No-manifest launch selects synthetic mode, not `missing_manifest`.
2. Custom precedence and invalid-custom failure behavior remain exact.
3. Synthetic output is deterministic and contains every logical lane.
4. Reassignment is one current node with events from every generation.
5. Custom topology stays authored; only genuinely unmapped work is appended.
6. Topology and status come from one parsed state revision.
7. Repeated launch reuses exact mode; mode replacement creates no duplicate.
8. Cold viewer processes occupy a right-side rail, never below P1.
9. Python suites, build, browser smoke, live smoke, Meta-Harness, P6 review,
   P7 functional QC, P8 layout QC, and P9 persona QC pass.
10. Installed viewer skill equals accepted source and normal push succeeds.

## File Ownership

| Path | Responsibility | Owner |
|---|---|---|
| `adapters/herdr/publisher.py` | Synthesis, supersession, additions, CLI | P2 |
| `adapters/herdr/test_publisher.py` | Projection and read-only tests | P2 |
| `skills/herdr-graph-viewer/scripts/start_viewer.py` | Selection, reuse, pane rail | P3 |
| `skills/herdr-graph-viewer/scripts/test_start_viewer.py` | Launcher/layout tests | P3 |
| `skills/herdr-graph-viewer/SKILL.md` | Manifestless user contract | P3 |

P2 and P3 may run concurrently. They must not edit each other's paths, server,
frontend, orchestrator, installed skills, benchmarks, or unrelated files.

## Task 1: Publisher In-Memory Projection

**Lane:** `publisher_projection`
**Owner:** P2

- [ ] **Step 1: Write failing synthesis tests**

Add this import and equivalent tests to `adapters/herdr/test_publisher.py`:

```python
from adapters.herdr.publisher import synthesize_manifest


def test_synthetic_manifest_is_deterministic_and_only_claims_control_edges(self):
    state = fixture_state()
    state["lanes"]["implementation_a"].update(
        {"lane_id": "implementation_a", "role": "Implementation", "slot": "P2"}
    )
    first = synthesize_manifest(state)
    second = synthesize_manifest(copy.deepcopy(state))

    self.assertEqual(first, second)
    self.assertEqual([], first["failurePolicies"])
    self.assertTrue(first["title"].startswith("Auto operational view"))
    self.assertEqual(
        {("orchestrator", node["id"]) for node in first["nodes"][1:]},
        {(edge["source"], edge["target"]) for edge in first["edges"]},
    )


def test_synthetic_snapshot_contains_lane_added_at_current_revision(self):
    state = fixture_state()
    state["revision"] = 43
    state["lanes"]["late_task"] = {
        "lane_id": "late_task", "role": "Follow-up", "slot": "P3",
        "state": "ACTIVE", "generation": 1,
        "task_summary": "Handle late task",
    }
    snapshot = build_snapshot(state, synthesize_manifest(state), "wK")

    self.assertEqual(43, snapshot["sequence"])
    self.assertIn("Handle late task", {node["task"] for node in snapshot["nodes"]})
```

Run the two named tests. Expected: FAIL because `synthesize_manifest` is absent.

- [ ] **Step 2: Implement strict supersession chains**

Add this pure helper to `adapters/herdr/publisher.py`:

```python
def _lane_chains(state: dict) -> tuple[list[str], dict[str, str], dict[str, list[str]]]:
    lanes = state.get("lanes", {})
    successors: dict[str, list[str]] = {}
    non_roots: set[str] = set()
    for lane_id, lane in lanes.items():
        predecessor = lane.get("supersedes")
        if predecessor is None:
            continue
        if predecessor not in lanes:
            raise PublisherError(f"lane {lane_id} supersedes unknown lane {predecessor}")
        successors.setdefault(predecessor, []).append(lane_id)
        non_roots.add(lane_id)

    roots = sorted(set(lanes) - non_roots)
    member_to_tip: dict[str, str] = {}
    root_to_members: dict[str, list[str]] = {}
    visited_all: set[str] = set()
    for root in roots:
        current = root
        members = [root]
        seen = {root}
        while current in successors:
            choices = sorted(successors[current])
            if len(choices) != 1:
                raise PublisherError(
                    f"lane {current} has multiple supersession successors: {', '.join(choices)}"
                )
            current = choices[0]
            if current in seen:
                raise PublisherError(f"supersession cycle includes lane {current}")
            seen.add(current)
            members.append(current)
        for member in members:
            member_to_tip[member] = current
        root_to_members[root] = members
        visited_all.update(members)
    if visited_all != set(lanes):
        unresolved = ", ".join(sorted(set(lanes) - visited_all))
        raise PublisherError(f"supersession cycle includes lanes: {unresolved}")
    return roots, member_to_tip, root_to_members
```

Branches and cycles fail exactly. Never select an arbitrary successor or add
warning fields to `role-graph/v1`.

- [ ] **Step 3: Implement deterministic synthesis**

Add `_lane_definition(root, tip, lane, layer, prefix)` and:

```python
def synthesize_manifest(state: dict) -> dict:
    run_id = state.get("run", {}).get("contract_id")
    if not isinstance(run_id, str) or not run_id:
        raise PublisherError("run.contract_id is required")
    roots, member_to_tip, _ = _lane_chains(state)
    lanes = state.get("lanes", {})
    nodes = [{
        "id": "orchestrator", "role": "Orchestrator", "assignee": "P1",
        "layer": 0, "task": state.get("slots", {}).get("P1", {}).get(
            "task_summary", "Route ready work"
        ),
        "source": {"type": "slot", "id": "P1"},
    }]
    for root in roots:
        tip = member_to_tip[root]
        nodes.append(_lane_definition(root, tip, lanes[tip], 1, "auto"))
    return {
        "schemaVersion": "herdr-role-graph-manifest/v1",
        "flowId": "auto-operational",
        "title": f"Auto operational view — {run_id}",
        "nodes": nodes,
        "edges": [{
            "id": f"control-{node['id']}", "source": "orchestrator",
            "target": node["id"], "kind": "forward", "status": "active",
        } for node in nodes[1:]],
        "failurePolicies": [],
    }
```

Role/task/assignee come only from the latest lane. Fall back to a humanized root
ID, empty task, and empty assignee; never infer a P slot from lane order.

- [ ] **Step 4: Write failing reassignment and custom-addition tests**

Add tests equivalent to:

```python
def test_custom_node_tracks_reassignment_tip_and_chain_events(self):
    state = fixture_state()
    state["lanes"]["implementation_a"]["state"] = "SUPERSEDED"
    state["lanes"]["implementation_a_reassigned_g2"] = {
        "lane_id": "implementation_a_reassigned_g2",
        "supersedes": "implementation_a", "state": "ACTIVE",
        "generation": 2, "slot": "P3", "task_summary": "Build adapter",
    }
    state["events"].append({
        "cursor": 61, "event_id": "event-g2", "kind": "LANE_PROGRESS",
        "lane_id": "implementation_a_reassigned_g2", "generation": 2,
    })
    snapshot = build_snapshot(state, fixture_manifest(), "wK")
    node = next(item for item in snapshot["nodes"] if item["id"] == "implementation-a")

    self.assertEqual("running", node["status"])
    self.assertEqual(2, node["generation"])
    self.assertEqual("implementation-a", snapshot["events"][-1]["nodeId"])


def test_custom_manifest_appends_only_unmapped_logical_lane(self):
    state = fixture_state()
    state["lanes"]["late_task"] = {
        "lane_id": "late_task", "role": "Follow-up", "slot": "P4",
        "state": "ACTIVE", "generation": 1,
    }
    snapshot = build_snapshot(state, fixture_manifest(), "wK")
    additions = [node for node in snapshot["nodes"] if node["id"].startswith("live-")]

    self.assertEqual(["P4"], [node["assignee"] for node in additions])
    self.assertEqual(1, sum(
        edge["target"] == additions[0]["id"] for edge in snapshot["edges"]
    ))
```

Add branch/cycle tests asserting `PublisherError` contains implicated IDs and
network publishing is not called. Run them and confirm RED.

- [ ] **Step 5: Materialize custom manifests and events**

Implement `_materialize_manifest(state, manifest)` returning:

```python
tuple[dict, dict[str, str]]  # deep-copied manifest, lane_id -> rendered node_id
```

Rewrite valid lane sources to their chain tip, map every chain member to the
authored node, and append only unmapped roots. Add a P1 control edge only when
exactly one authored node sources slot P1. Update `build_snapshot`, failure route
resolution, and `_events` to use the materialized copy and complete event map.
Do not mutate the state or supplied manifest.

- [ ] **Step 6: Add mutually exclusive publisher modes**

Change `publish_if_changed` to accept `manifest_path: Path | None` plus
keyword-only `synthesize: bool = False`. Require exactly one mode:

```python
if synthesize == (manifest_path is not None):
    raise PublisherError("select exactly one of manifest_path or synthesize")
manifest = synthesize_manifest(state) if synthesize else _read_json(manifest_path)
```

Use an argparse mutually exclusive group requiring `--manifest PATH` or
`--synthesize`. Preserve watch retry behavior and remove the duplicate parser
constructor while editing `_parser`.

- [ ] **Step 7: Verify and commit P2**

Run:

```bash
python3 -B -m unittest adapters.herdr.test_publisher
git diff --check
git add adapters/herdr/publisher.py adapters/herdr/test_publisher.py
git commit -m "feat: synthesize operational Herdr graphs"
```

Expected: all publisher and AST read-only tests PASS. Record SHA/tree and a
canonical immutable receipt.

## Task 2: Launcher Selection, Reuse, and Pane Rail

**Lane:** `launcher_manifestless`
**Owner:** P3

- [ ] **Step 1: Write failing selection-mode tests**

Replace the old terminal missing-manifest test and add:

```python
def test_selects_synthetic_only_when_no_custom_source_exists(self):
    launcher = self.require_launcher()
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        state = self.write_state(
            root, "current", workspace="w1", pane="w1:p1", run_id="current-run"
        )
        selected = launcher._load_state(state, "w1")
        self.assertEqual(
            launcher.ManifestSelection("synthetic", None),
            launcher._resolve_manifest(selected, None),
        )


def test_configured_missing_manifest_fails_instead_of_synthesizing(self):
    launcher = self.require_launcher()
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        state = self.write_state(
            root, "current", workspace="w1", pane="w1:p1", run_id="current-run",
            role_graph_manifest=str(root / "missing.json"),
        )
        with self.assertRaises(launcher.LauncherError) as raised:
            launcher._resolve_manifest(launcher._load_state(state, "w1"), None)
        self.assertEqual("missing_manifest", raised.exception.code)
```

Retain tests for explicit, state-configured, relative, and run-local manifests.
Run the named tests directly through `test_start_viewer.py`; expect RED.

- [ ] **Step 2: Implement explicit selection precedence**

Add:

```python
class ManifestSelection(NamedTuple):
    mode: str
    path: Path | None
```

Change `_resolve_manifest(selected, explicit)` to return custom selection for:
explicit path, `run.role_graph_manifest`, then run-local file. Validate each
selected custom path immediately. Return `ManifestSelection("synthetic", None)`
only when all three sources are absent. Never fall back from a broken custom
source.

- [ ] **Step 3: Write failing exact-mode process tests**

```python
def test_publisher_match_requires_exact_topology_mode(self):
    launcher = self.require_launcher()
    target = "/tmp/current/workspace-state.json"
    endpoint = "http://127.0.0.1:4173/api/snapshots"
    process = {"foreground_processes": [{"cmdline": (
        "python3 -B adapters/herdr/publisher.py "
        f"--state {target} --synthesize --workspace-id w1 "
        f"--endpoint {endpoint} --watch"
    )}]}

    self.assertTrue(launcher.publisher_matches(
        process, target, launcher.ManifestSelection("synthetic", None),
        "w1", endpoint, True,
    ))
    self.assertFalse(launcher.publisher_matches(
        process, target,
        launcher.ManifestSelection("custom", Path("/tmp/manifest.json")),
        "w1", endpoint, True,
    ))
```

Also add a mode-switch test proving the old viewer publisher receives `ctrl+c`,
the same pane receives the replacement command, and no new publisher pane opens.

- [ ] **Step 4: Implement mode identity and replacement**

`publisher_matches` and `_find_publisher` must compare publisher path, state,
workspace, endpoint, watch flag, and exactly one of `--synthesize` or an exact
absolute `--manifest` path. Add `_find_publisher_for_state` to locate a
viewer-owned publisher for the same state/workspace/endpoint with another mode.

On mode change, send `ctrl+c` only to that ordinary viewer publisher pane, then
run the replacement command in the same pane. Never close/move/focus a pane,
target an agent, or cross workspace boundaries.

- [ ] **Step 5: Write failing right-side rail tests**

Record complete `pane split` argv in the cold-start test. Assert the first split
anchors P1 with `--direction right`, the second anchors the new server pane with
`--direction down`, both include exact ratio/cwd/`--no-focus`, and no call splits
P1 downward. Do not use wildcard assertions.

- [ ] **Step 6: Implement the right-side rail**

Generalize:

```python
def _split_pane(
    anchor_pane: str, cwd: Path, label: str, *, direction: str, ratio: str
) -> str:
    response = _herdr(
        "pane", "split", "--pane", anchor_pane,
        "--direction", direction, "--ratio", ratio,
        "--cwd", str(cwd), "--no-focus",
    )
    pane_id = (_result_value(response, "pane") or {}).get("pane_id")
    if not isinstance(pane_id, str):
        raise LauncherError("herdr_error", "pane split returned no pane_id")
    _herdr("pane", "rename", pane_id, label)
    return pane_id
```

Cold launch: server right of P1, publisher down from server. If server is reused
and publisher absent, split publisher right of P1. Reuse healthy panes first.

- [ ] **Step 7: Emit topology mode and update skill contract**

Build exactly one publisher fragment:

```python
topology_args = (
    ["--synthesize"]
    if selection.mode == "synthetic"
    else ["--manifest", str(selection.path)]
)
```

Shell-quote every value. Launcher JSON adds `mode` and sets `manifest` to the
absolute custom path or null. Update `SKILL.md` to state that missing custom
topology derives deterministically from state in memory, writes no manifest,
and invents no handoff/dependency/failure edges. Preserve explicit invocation,
no hooks, read-only isolation, and no product pane closure.

- [ ] **Step 8: Verify and commit P3**

```bash
python3 -B skills/herdr-graph-viewer/scripts/test_start_viewer.py
git diff --check
git add skills/herdr-graph-viewer/scripts/start_viewer.py
git add skills/herdr-graph-viewer/scripts/test_start_viewer.py
git add skills/herdr-graph-viewer/SKILL.md
git commit -m "feat: launch manifestless Herdr graphs"
```

Expected: launcher tests PASS, including custom precedence, exact mode reuse,
concurrent launch, bounded timeouts, readiness, replacement, and layout. Record
SHA/tree and a canonical immutable receipt.

## Task 3: P5 Integration and Meta-Harness

**Lane:** `integration`
**Owner:** P5
**Prerequisites:** accepted P2 and P3 receipts

- [ ] **Step 1: Integrate accepted commits only**

Re-read control state and validate receipt tuple identity immediately before
integration. Apply P2 then P3 through normal forward commits. Do not edit worker
paths except to resolve an actual conflict or integration failure; record such a
fix in a new P5 commit.

- [ ] **Step 2: Run narrow and repository checks**

```bash
python3 -B -m unittest adapters.herdr.test_publisher
python3 -B skills/herdr-graph-viewer/scripts/test_start_viewer.py
npm test -- --run
npm run build
node tests/browser-smoke.mjs
git diff --check
```

Expected: all PASS, browser reports no console/page errors, and diff check emits
nothing.

- [ ] **Step 3: Run Meta-Harness with a locked rubric**

Use `$meta-harness` with `Intent: DELIVER`, `target=8`, `target_min=7`, and
`max-iter=2`. Store artifacts under:

```text
plans/meta-harness-2026-08-02-manifestless-viewer/
```

Lock five criteria:

1. `manifestless_correctness`: no-manifest launch reaches exact ready snapshot;
2. `projection_integrity`: dynamic/reassigned work stays visible without
   invented flow semantics;
3. `isolation_and_readonly`: exact workspace only and no ledger/agent mutation;
4. `launcher_lifecycle`: reuse, replacement, and right-side placement;
5. `backward_compatibility`: custom graphs, protocol, build, and smoke.

If any score is below 8, write evidence-backed feedback and route only the
failed concern through P1 to its owner. P5 integrates the fix-forward commit and
reruns the smallest affected checks. Never change the locked rubric.

- [ ] **Step 4: Commit evidence and receipt**

If no product correction is needed, do not manufacture one. Commit the complete
Meta-Harness artifacts as one evidence commit:

```bash
git add plans/meta-harness-2026-08-02-manifestless-viewer
git commit -m "test: evaluate manifestless viewer delivery"
```

Write and validate the P5 integration receipt against current control state.

## Task 4: Independent Review and QC

### P6 Independent Review

P6 is mandatory and read-only except for its external receipt. Bind review to
the integrated SHA/tree and current tuple.

- Trace every changed line to approved spec/plan.
- Confirm no orchestrator, server/schema, benchmark, or unrelated changes.
- Review deterministic IDs/order and absence of invented workflow edges.
- Review roots/tips, missing predecessor, branch, cycle, event mapping, and
  custom live additions.
- Review shell quoting, exact argv identity, locking, replacement, and no pane
  closure/cross-workspace action.
- Rerun both Python suites, Vitest, build, browser smoke, and diff check.
- Return PASS or file/line findings; receipt only after fresh PASS.

### P7 Functional QC

P7 is applicable. In the same Herdr workspace, create a temporary explicit state
fixture with current workspace ID, unique run ID, P1 binding, at least two active
lanes, and no manifest source. Invoke launcher with `--state` and verify:

- result is `ready`, mode `synthetic`, manifest null;
- health fingerprint, scope, run, and sequence are exact;
- adding a lane and incrementing revision adds a node at that sequence;
- no `role-graph-manifest.json` is created;
- foreign-workspace state is refused;
- repeated invocation reuses server and publisher.

Remove only P7's temporary fixture directory; do not close panes.

### P8 Layout QC

P8 is applicable. Record `herdr pane layout` before and after cold test launch:

- P1 retains vertical extent and focus;
- server is right of P1;
- publisher is below server inside the right rail;
- neither viewer pane lies below P1;
- no pane is closed, moved cross-workspace, or focused automatically.

Receipt evidence includes measured pane rectangles.

### P9 Persona QC

P9 is applicable. Invoke `$herdr-graph-viewer` from the manifestless same-
workspace fixture. Verify clickable URL, automatic operational title, current
task/assignee/generation/time/status, no invented gate loop, dynamic refresh,
and no setup instructions or duplicate processes.

## Task 5: Installation and Delivery

**Owner:** P5
**Prerequisites:** Meta-Harness SUCCESS and P6/P7/P8/P9 PASS

- [ ] **Step 1: Sync only the installed viewer skill**

```bash
rsync -a --delete skills/herdr-graph-viewer/ /Users/haido/.codex/skills/herdr-graph-viewer/
diff -ru skills/herdr-graph-viewer /Users/haido/.codex/skills/herdr-graph-viewer
python3 -B /Users/haido/.codex/skills/herdr-graph-viewer/scripts/test_start_viewer.py
```

Expected: parity diff empty and installed tests PASS. Never touch installed
`herdr-orchestrator`.

- [ ] **Step 2: Verify protected state and push normally**

```bash
git diff --check
git status --short --branch
git -C /Users/haido/herdr-orchestrator status --short --branch
git push origin main
git rev-parse HEAD
git rev-parse origin/main
git ls-remote origin refs/heads/main
```

Expected: only approved committed viewer changes, no task-related orchestrator
changes, and local/remote main identities equal. Never reset, rebase, or force.

- [ ] **Step 3: Record terminal delivery**

Write and validate P5 delivery receipt with accepted source SHA/tree, installed
parity, verification matrix, Meta-Harness outcome, P6-P9 receipts, and remote
SHA. P1 responds only after terminal delivery or a real blocker.

## Herdr Delivery Contract

```yaml
herdr_delivery:
  backend: herdr
  contract_id: herdr-graph-viewer-manifestless-20260802
  generation: 1
  approved_input:
    spec: docs/superpowers/specs/2026-08-02-herdr-graph-viewer-manifestless-runs-design.md
    spec_sha256: 41b5edfead872215af5030d099501a71e063b918169b4eac8822b6c9374203b8
    plan: docs/superpowers/plans/2026-08-02-herdr-graph-viewer-manifestless-runs.md
  controller:
    slot: P1
    role: orchestration-only
    prohibited: [implementation, tests, integration, review, commit, push, install]
  repository:
    root: /Users/haido/multi-agent-graph-demo
    base_sha: 3d6d45d9570e512d7765cef7e7b572e0ccb03fc5
  workspace:
    dispatch_boundary: current Herdr workspace only
    pane_policy:
      - reuse healthy panes first
      - close only task-created confirmed-unused panes when a new pane is needed
      - never close protected user panes
      - product launcher never closes panes
  lanes:
    - lane_id: publisher_projection
      contract_id: herdr-graph-viewer-manifestless-20260802
      generation: 1
      role: implementation
      eligible_slots: [P2, P3, P4]
      owned_paths:
        - adapters/herdr/publisher.py
        - adapters/herdr/test_publisher.py
      prerequisites: []
      acceptance:
        - python3 -B -m unittest adapters.herdr.test_publisher
      terminal_receipt:
        command: python3 -B /Users/haido/herdr-orchestrator/scripts/write_lane_receipt.py
        validation: python3 -B /Users/haido/herdr-orchestrator/scripts/validate_lane_receipt.py
        output_artifact: commit SHA and tree SHA
    - lane_id: launcher_manifestless
      contract_id: herdr-graph-viewer-manifestless-20260802
      generation: 1
      role: implementation
      eligible_slots: [P2, P3, P4]
      owned_paths:
        - skills/herdr-graph-viewer/scripts/start_viewer.py
        - skills/herdr-graph-viewer/scripts/test_start_viewer.py
        - skills/herdr-graph-viewer/SKILL.md
      prerequisites: []
      acceptance:
        - python3 -B skills/herdr-graph-viewer/scripts/test_start_viewer.py
      terminal_receipt:
        command: python3 -B /Users/haido/herdr-orchestrator/scripts/write_lane_receipt.py
        validation: python3 -B /Users/haido/herdr-orchestrator/scripts/validate_lane_receipt.py
        output_artifact: commit SHA and tree SHA
    - lane_id: integration
      contract_id: herdr-graph-viewer-manifestless-20260802
      generation: 1
      role: integration
      eligible_slots: [P5]
      owned_paths:
        - integration branch
        - plans/meta-harness-2026-08-02-manifestless-viewer/**
      prerequisites: [publisher_projection, launcher_manifestless]
      acceptance:
        - both Python suites PASS
        - npm test -- --run
        - npm run build
        - node tests/browser-smoke.mjs
        - Meta-Harness SUCCESS at target 8
      terminal_receipt:
        command: python3 -B /Users/haido/herdr-orchestrator/scripts/write_lane_receipt.py
        validation: python3 -B /Users/haido/herdr-orchestrator/scripts/validate_lane_receipt.py
        output_artifact: integrated SHA and tree
    - lane_id: independent_review
      contract_id: herdr-graph-viewer-manifestless-20260802
      generation: 1
      role: integration-reviewer
      eligible_slots: [P6]
      owned_paths: []
      prerequisites: [integration]
      acceptance: [rule review PASS, verification matrix PASS]
      terminal_receipt:
        command: python3 -B /Users/haido/herdr-orchestrator/scripts/write_lane_receipt.py
        validation: python3 -B /Users/haido/herdr-orchestrator/scripts/validate_lane_receipt.py
        output_artifact: review evidence
    - lane_id: functional_qc
      contract_id: herdr-graph-viewer-manifestless-20260802
      generation: 1
      role: qc
      eligible_slots: [P7]
      owned_paths: []
      prerequisites: [independent_review]
      acceptance: [manifestless live launch PASS, dynamic revision PASS, isolation PASS]
      terminal_receipt:
        command: python3 -B /Users/haido/herdr-orchestrator/scripts/write_lane_receipt.py
        validation: python3 -B /Users/haido/herdr-orchestrator/scripts/validate_lane_receipt.py
        output_artifact: functional evidence
    - lane_id: layout_qc
      contract_id: herdr-graph-viewer-manifestless-20260802
      generation: 1
      role: designer
      eligible_slots: [P8]
      owned_paths: []
      prerequisites: [independent_review]
      acceptance: [right-side geometry PASS, P1 focus and extent preserved]
      terminal_receipt:
        command: python3 -B /Users/haido/herdr-orchestrator/scripts/write_lane_receipt.py
        validation: python3 -B /Users/haido/herdr-orchestrator/scripts/validate_lane_receipt.py
        output_artifact: layout evidence
    - lane_id: persona_qc
      contract_id: herdr-graph-viewer-manifestless-20260802
      generation: 1
      role: persona
      eligible_slots: [P9]
      owned_paths: []
      prerequisites: [independent_review]
      acceptance: [skill invocation PASS, dynamic refresh and reuse PASS]
      terminal_receipt:
        command: python3 -B /Users/haido/herdr-orchestrator/scripts/write_lane_receipt.py
        validation: python3 -B /Users/haido/herdr-orchestrator/scripts/validate_lane_receipt.py
        output_artifact: persona evidence
    - lane_id: delivery
      contract_id: herdr-graph-viewer-manifestless-20260802
      generation: 1
      role: integration
      eligible_slots: [P5]
      owned_paths:
        - /Users/haido/.codex/skills/herdr-graph-viewer/**
        - refs/heads/main
      prerequisites: [independent_review, functional_qc, layout_qc, persona_qc]
      acceptance: [installed parity, installed tests PASS, remote identity exact]
      terminal_receipt:
        command: python3 -B /Users/haido/herdr-orchestrator/scripts/write_lane_receipt.py
        validation: python3 -B /Users/haido/herdr-orchestrator/scripts/validate_lane_receipt.py
        output_artifact: parity and remote SHA
  review_matrix:
    P6: {applicable: true, focus: [contract, correctness, readonly, isolation]}
    P7: {applicable: true, focus: [live_launch, dynamic_revision, reuse, errors]}
    P8: {applicable: true, focus: [pane_geometry, focus_preservation]}
    P9: {applicable: true, focus: [invocation, clarity, operational_truthfulness]}
  deployment:
    target: local installed viewer skill and origin/main
    topology: source acceptance -> installed sync -> parity -> normal push
    force_operations: prohibited
  evidence:
    run_root: /Users/haido/.codex/herdr-runs/<workspace_id>/herdr-graph-viewer-manifestless-20260802
    receipts: immutable JSON under run_root/receipts
    meta_harness: plans/meta-harness-2026-08-02-manifestless-viewer
    final_identity: source SHA, tree SHA, installed parity, remote SHA
```

## Plan Self-Review

- Every approved requirement maps to a task and acceptance check.
- P2/P3 ownership is disjoint; P5 alone integrates, installs, and pushes.
- Synthetic mode writes no manifest and invents no workflow/failure edges.
- Invalid custom sources, lanes, supersession, events, and mode changes have
  explicit tests and errors.
- Pane geometry has a distinct test/commit boundary.
- P6-P9 applicability and evidence are explicit.
- No live pane/session/lease IDs are bound in this plan.
- Frozen baselines are referenced but never rerun or modified.
- No placeholders, server/schema changes, or automatic export remain.
