# Live Runtime Recovery Evaluation Spec

## Bound inputs

- Contract: `herdr-graph-viewer-manifestless-20260802`
- Integration generation: `4`
- Starting commit: `50ba34e6a01f59693fecb5f0624517aecd879f66`
- Starting tree: `006398bbe32dff060d6c50ffc5f6faefad4ad1da`
- Accepted publisher fix: `a73cf68d4c6ab3f98ec3d94ad171dc7249f63f7f`
- Integrated publisher fix: `cabc6db17549816c1081b38d39ea0d2ba8c3e272`
- Accepted launcher fix: `9ee0c4226076c1975b69223180c34b503684fc9c`
- Integrated launcher fix: `84ed920c0ab45b2a764207abbd59374b76b56a5c`
- Integrated product tree: `3b6d9492b8790c6bab2d6a32ff18f9c8da6296dc`
- Routed input: P7 finding `p7-live-runtime-cold-and-mode-replacement`

## Testable behaviors

1. Successful imperative Herdr commands may return empty stdout; JSON query
   responses still parse, and pane split still requires a concrete pane ID.
2. `--replace-current` adds the replacement header only to the publisher's
   first POST and is selected only when the launcher stops a mismatched
   same-state ordinary publisher.
3. Explicit replacement accepts only an equal current sequence. Default equal,
   explicit lower, and default lower sequences remain stale conflicts.
4. Equal replacement is appended durably and remains current after store
   hydration; default monotonic ordering and multi-graph isolation remain exact.
5. Cold publisher creation, healthy exact reuse, selected-ledger P1 anchoring,
   no agent-pane reuse, no pane closure, and concurrent launch locking remain
   unchanged.

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

Both prior histories must remain byte-identical. Frozen Compact `152s` and
Multi-module `1009s` are comparison-only metadata and are neither rerun nor
altered.

## Scope

This run writes only its own plan directory. No live panes, installation, push,
delivery, or baseline mutation is allowed.
