# Provenance Recovery Evaluation Spec

## Bound inputs

- Contract: `herdr-graph-viewer-manifestless-20260802`
- Integration generation: `8`
- Integration session: `019fc149-9da6-7c40-9425-36663c6e2b51`
- Starting commit: `7910d8098d3959db74e7b5a1fe6444c92f561c18`
- Starting tree: `cf7fa22b775deb0b11f1c04d529dba6c46d84d0e`
- Independent review finding: `p6-authored-auto-id-provenance`
- Finding receipt: `independent_review-g7.json`
- Accepted persona UI fix: `d6e42ca20d1f1d7b09a63739765d79a61681a29c`
- Integrated persona UI fix: `368cf74f71645578aa5ef2dbc6b9810c0bf75b25`
- Integrated product tree: `90313cf2902098293ce17251d0abf394c9e10f91`

## Testable behaviors

1. Generated-internal hiding is enabled only when the snapshot has the exact
   `auto-operational` flow provenance, never from node ID shape alone.
2. A custom authored node whose ID is the same auto-hex form as a synthesized
   node keeps its complete authored ID and authored task visible.
3. The equivalent auto-operational synthetic node continues to hide its
   generated auto ID and redundant decoded lane-label task.
4. Role-first headings, compact accessible P chips, seconds/ms/ISO timestamp
   rendering, meaningful deterministic `generatedAt`, and lane-to-P mapping
   remain correct.
5. Authored custom manifests, loop fixture, top-down same-row layout, straight
   links, selection, live updates, launcher lifecycle, workspace isolation,
   no-close behavior, and runtime/browser contracts remain unchanged.

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

- `plans/meta-harness-2026-08-02-manifestless-viewer`:
  `e5614096f9b89dc28f0256979ac0fac564cc8add`
- `plans/meta-harness-2026-08-02-p1-anchor-recovery`:
  `b43deffeb76a4c23d357c74c516237d3690de6fb`
- `plans/meta-harness-2026-08-02-live-runtime-recovery`:
  `f22266db22dd1eab9b7495455a2de29e90f8fe37`
- `plans/meta-harness-2026-08-02-query-strictness-recovery`:
  `3236642651c3f9418df0655f83c318d926ef6c4b`
- `plans/meta-harness-2026-08-02-cold-query-order-recovery`:
  `53189bc2bd72067cf169ee84906cc94e32fc0239`
- `plans/meta-harness-2026-08-02-persona-readability-recovery`:
  `01c03937108feeda155d0f2c464abcd80d82f01a`

All prior histories must remain byte-identical. Frozen Superpowers Compact
`152s` and Multi-module `1009s` are comparison-only metadata and are neither
rerun nor altered.

## Scope

This run writes only its own plan directory. No baseline, prior harness, live
pane, source main, installed skill, or Herdr Orchestrator mutation is allowed.
