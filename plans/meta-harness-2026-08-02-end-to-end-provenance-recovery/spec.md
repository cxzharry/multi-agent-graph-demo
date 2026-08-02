# End-to-End Provenance Recovery Evaluation Spec

## Bound inputs

- Contract: `herdr-graph-viewer-manifestless-20260802`
- Integration generation: `9`
- Integration session: `019fc149-9da6-7c40-9425-36663c6e2b51`
- Starting commit: `49c21fb737c87e3f0c9a5ca939d06e5c129b5634`
- Starting tree: `a9fecf4b597b606665605659dbfe4ce08a89ef88`
- P6 finding: `p6-end-to-end-flow-provenance`
- Finding receipt: `independent_review-g8.json`
- Accepted publisher fix: `e957827c11d17f9fdd84c5ac3d11ff5425b688af`
- Integrated publisher fix: `4cdcbdf70b6d9ee50755b2e2a3c76ccf8352b5b5`
- Accepted persona UI fix: `dda3b0d60dcf3adfc99df18b3fe789f002b80e95`
- Integrated persona UI fix: `67366a7a486773dd168f2bbff5c3472703ea5617`
- Integrated product tree: `4a6a47fcb06739fc62a24f026d58344015e3f031`

## Testable behaviors

1. A real synthesized `auto-operational` manifest retains exact `flowId` through
   `build_snapshot`; an authored custom flow ID is also preserved verbatim.
2. The UI marks node render data synthetic only when the real snapshot flow ID
   is exactly `auto-operational`.
3. RoleNode hides both ID and task for every synthetic node, including opaque
   non-auto-shaped content, without ID-prefix or task-decoding heuristics.
4. Authored custom nodes with identical auto-hex and opaque ID/task pairs keep
   their complete authored ID and task visible.
5. Lane-to-P mapping, generated/time normalization, role-first P chips, custom
   manifests, loop/top-down/straight-link layout, selection, live updates,
   launcher lifecycle, workspace isolation, no-close, and runtime contracts
   remain unchanged.

## Exact producer probe

The evaluation directly calls `synthesize_manifest` and `build_snapshot` and
asserts:

```text
synthetic manifest flowId == synthetic snapshot flowId == auto-operational
authored manifest flowId == authored snapshot flowId == custom/Authored Flow:v2
```

## Exact verification matrix

```text
python3 -B -m unittest adapters.herdr.test_publisher
python3 -B skills/herdr-graph-viewer/scripts/test_start_viewer.py
npm test -- --run
npm run build
node tests/browser-smoke.mjs
git diff --check
```

## Audit boundaries

- `plans/meta-harness-2026-08-02-manifestless-viewer`: `e5614096f9b89dc28f0256979ac0fac564cc8add`
- `plans/meta-harness-2026-08-02-p1-anchor-recovery`: `b43deffeb76a4c23d357c74c516237d3690de6fb`
- `plans/meta-harness-2026-08-02-live-runtime-recovery`: `f22266db22dd1eab9b7495455a2de29e90f8fe37`
- `plans/meta-harness-2026-08-02-query-strictness-recovery`: `3236642651c3f9418df0655f83c318d926ef6c4b`
- `plans/meta-harness-2026-08-02-cold-query-order-recovery`: `53189bc2bd72067cf169ee84906cc94e32fc0239`
- `plans/meta-harness-2026-08-02-persona-readability-recovery`: `01c03937108feeda155d0f2c464abcd80d82f01a`
- `plans/meta-harness-2026-08-02-provenance-recovery`: `7c96047cca55128a681b5eadb257d6bf37fc79e4`

The g8 provenance-recovery score of `8.8` is preserved but superseded because
P6 proved it lacked a real producer contract. Every prior history remains
byte-identical. Frozen Superpowers Compact `152s` and Multi-module `1009s` are
comparison-only metadata and are neither rerun nor altered.

## Scope

This run writes only its own plan directory. No prior/frozen artifact, live
pane, source main, installed skill, or Herdr Orchestrator mutation is allowed.
