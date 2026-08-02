# Persona Readability Recovery Evaluation Spec

## Bound inputs

- Contract: `herdr-graph-viewer-manifestless-20260802`
- Integration generation: `7`
- Integration session: `019fc149-9da6-7c40-9425-36663c6e2b51`
- Starting commit: `d4ec085daa98359bea48c64810eee517fe58ed82`
- Starting tree: `d5516390dfcfedc6f1818f8321af79f8f3fdd9a7`
- Accepted publisher fix: `f3c9360cbad849707787f11a4058cceba9d8e974`
- Integrated publisher fix: `49e364b6ebc2c5e02b1322a76406440b2b58f3bf`
- Accepted persona UI fix: `780d984afdfb71ae58eabb141910ec63cd42340b`
- Integrated persona UI fix: `fd5128b7e8cb96df58cf351caf592d49586d6e2c`
- Integrated product tree: `c1c6aff006b0ac41c24db1d24928b2863ff603f6`
- Routed inputs: `layout_qc-g1.json` and `persona_qc-g1.json`

## Testable behaviors

1. Synthetic and materialized live lane nodes prefer the exact slot whose
   `lane_id` matches the lane tip, yielding compact P assignees such as P7-P9.
2. `generatedAt` is the latest valid normalized event time, supports epoch
   seconds, epoch milliseconds, and ISO values, and uses deterministic valid
   metadata or epoch fallback when events are invalid.
3. Snapshot generated time and timeline event times render in one readable
   local-clock format for seconds, milliseconds, and ISO inputs without raw
   epoch values.
4. Role remains the primary node heading, assignees render as exact compact P
   chips, generated IDs and redundant generated lane-label tasks are hidden,
   and authored IDs/tasks remain visible.
5. Custom authored manifests, loop fixtures, top-down layout, straight links,
   same-row roles, live updates, selection behavior, launcher lifecycle, and
   runtime/browser contracts remain unchanged.

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

- `plans/meta-harness-2026-08-02-manifestless-viewer` audit tree:
  `e5614096f9b89dc28f0256979ac0fac564cc8add`
- `plans/meta-harness-2026-08-02-p1-anchor-recovery` audit tree:
  `b43deffeb76a4c23d357c74c516237d3690de6fb`
- `plans/meta-harness-2026-08-02-live-runtime-recovery` audit tree:
  `f22266db22dd1eab9b7495455a2de29e90f8fe37`
- `plans/meta-harness-2026-08-02-query-strictness-recovery` audit tree:
  `3236642651c3f9418df0655f83c318d926ef6c4b`
- `plans/meta-harness-2026-08-02-cold-query-order-recovery` audit tree:
  `53189bc2bd72067cf169ee84906cc94e32fc0239`

All prior histories must remain byte-identical. Frozen Superpowers Compact
`152s` and Multi-module `1009s` are comparison-only metadata and are neither
rerun nor altered.

## Scope

This run writes only its own plan directory. No live panes, pane closure,
installation, synchronization, push, delivery, Herdr Orchestrator modification,
or baseline mutation is allowed.
