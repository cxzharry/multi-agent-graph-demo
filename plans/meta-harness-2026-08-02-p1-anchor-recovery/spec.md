# P1 Anchor Recovery Evaluation Spec

## Bound inputs

- Contract: `herdr-graph-viewer-manifestless-20260802`
- Integration generation: `3`
- Starting commit: `42a0f548da9d86825fc02ee2db5d4ff0ee17cd52`
- Starting tree: `7d1945a961a396c1aeb765b0fcb53fbe6efff421`
- Accepted launcher fix: `277e360e31a51594149f020280be6b27b7909078`
- Integrated launcher fix: `67ec076cefc6f67b9eb8efa793f00cd50a433438`
- Integrated product tree: `9a8fa322842a93a8a79aeda85f0184a23ffed633`
- Routed input: P6 generation-2 finding `p6-right-of-p1-anchor`
- Prior harness audit tree: `e5614096f9b89dc28f0256979ac0fac564cc8add`

## Testable behaviors

1. A cold launch invoked from a non-P1 pane anchors the server to the selected
   ledger's controller P1 with `--direction right`, then anchors the publisher
   below the server inside that right-side rail.
2. With a reused server and missing publisher, the publisher is split right of
   the selected ledger's P1, never right of or below the invoking non-P1 pane.
3. A selected ledger without a usable P1 pane binding fails before Herdr pane
   discovery, splitting, process replacement, or viewer probing.
4. Exact publisher reuse, mode replacement, locking, concurrency, workspace
   isolation, manifest precedence, and no-focus/no-close behavior remain intact.
5. Publisher projection, frontend protocol, production build, and browser smoke
   do not regress.

## Exact verification matrix

```text
python3 -B -m unittest adapters.herdr.test_publisher
python3 -B skills/herdr-graph-viewer/scripts/test_start_viewer.py
npm test -- --run
npm run build
node tests/browser-smoke.mjs
git diff --check
```

## Frozen comparison

Compact `152s` and Multi-module `1009s` are recorded comparison-only metadata.
They are neither rerun nor edited, and orchestration timing is not a gate for
this launcher correction.

## Scope

This follow-on run writes only its own plan directory. The existing
`plans/meta-harness-2026-08-02-manifestless-viewer` history must remain at its
captured tree identity. Installation, push, delivery, and live-pane operations
are prohibited.
