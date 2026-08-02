# Meta-Harness Report: End-to-End Provenance Recovery

## Outcome

SUCCESS in iteration 1. Composite score: `8.8`; every locked criterion is at
least `8`. P6 finding `p6-end-to-end-flow-provenance` is resolved by the
accepted publisher generation-7 and persona UI generation-3 fixes.

The prior provenance-recovery score of `8.8` is preserved as audit history but
superseded because it lacked real publisher evidence.

## Product integration

| Accepted commit | Integration commit | Purpose |
|---|---|---|
| `e957827c11d17f9fdd84c5ac3d11ff5425b688af` | `4cdcbdf70b6d9ee50755b2e2a3c76ccf8352b5b5` | Carry exact manifest flowId into snapshots |
| `dda3b0d60dcf3adfc99df18b3fe789f002b80e95` | `67366a7a486773dd168f2bbff5c3472703ea5617` | Hide all synthetic internals solely from provenance |

Integrated product tree: `4a6a47fcb06739fc62a24f026d58344015e3f031`.

## Producer-to-UI proof

A fresh direct probe called `synthesize_manifest` and `build_snapshot`:

- Synthetic manifest and snapshot both returned `auto-operational`.
- Authored manifest and snapshot both returned `custom/Authored Flow:v2`.

The UI consumes that exact snapshot field and sets synthetic data only for
exact `auto-operational`. RoleNode hides task and ID solely from the trusted
synthetic boolean; it has no prefix or decoding heuristic.

Browser smoke proves the same auto-hex and opaque ID/task pairs are fully
visible for `authored-custom` and fully hidden for `auto-operational`, while
role headings and compact P chips remain visible.

## Verification

- Direct producer flowId probe: 2 passed.
- Producer-to-UI contract-stitch assertion: passed.
- Publisher unittest: 36 passed.
- Launcher tests: 41 passed.
- Vitest: 4 files, 37 tests passed.
- Production TypeScript/Vite build: passed.
- Browser smoke: passed with 11-role scale `1.034`.
- `git diff --check`: passed with no output.

## Locked scores

| Criterion | Score |
|---|---:|
| `real_producer_flow_provenance` | 9 |
| `exact_ui_provenance_consumption` | 9 |
| `shape_independent_synthetic_hiding` | 9 |
| `authored_identical_content_visibility` | 9 |
| `retained_full_integration_and_audit` | 8 |

## Audit and boundaries

All seven prior Meta-Harness subtrees remain byte-identical. Frozen Compact
`152s` and Multi-module `1009s` were comparison-only and were neither rerun nor
altered. No installation, synchronization, push, source-main mutation, live
pane operation, pane closure, P6 self-review, delivery, or Herdr Orchestrator
modification occurred.
