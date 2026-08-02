# Cold Query Order Recovery Evaluation Spec

## Bound inputs

- Contract: `herdr-graph-viewer-manifestless-20260802`
- Integration generation: `6`
- Integration session: `019fc149-9da6-7c40-9425-36663c6e2b51`
- Starting commit: `3fd3d3c70a1d9d90628cdd726e09d4f0e1917b54`
- Starting tree: `e18e32836f64e69631b3ddc03a3b98c38ee5225f`
- Accepted launcher fix: `ed8c349e14560acd5cdac6de86ea8f0de791e9ed`
- Integrated launcher fix: `71bc0311cbcba972bfd5472e9f84ba6d88b79594`
- Integrated product tree: `cd494490f2ac6af7b73a0e3d4cb26a1d13272a92`
- Routed input: P6 finding `p6-cold-query-before-mutation`

## Testable behaviors

1. With a cold viewer port, empty or malformed pane-list output fails before
   any pane split, rename, run, or send-keys command.
2. With a cold viewer port, empty or malformed pane process-info output fails
   before any pane split, rename, run, or send-keys command.
3. With a reused viewer, empty or malformed pane-list and pane process-info
   output also fails before any pane mutation.
4. Successful imperative pane run and pane send-keys still accept empty stdout;
   valid JSON queries parse, nonzero failures remain errors, and pane split
   still requires a concrete pane result.
5. Selected-ledger P1 anchoring, pane isolation, exact publisher reuse,
   same-state replacement, stale-pane recovery, locking, bounded calls,
   no-focus, and no-close contracts remain unchanged.

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

All prior histories must remain byte-identical. Frozen Superpowers Compact
`152s` and Multi-module `1009s` are comparison-only metadata and are neither
rerun nor altered.

## Scope

This run writes only its own plan directory. No live panes, pane closure,
installation, push, delivery, Herdr Orchestrator modification, or baseline
mutation is allowed.
