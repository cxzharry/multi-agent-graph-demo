# Query Strictness Recovery Evaluation Spec

## Bound inputs

- Contract: `herdr-graph-viewer-manifestless-20260802`
- Integration generation: `5`
- Integration session: `019fc149-9da6-7c40-9425-36663c6e2b51`
- Starting commit: `92c409bc1281a1290f1de74c3f75821cf846baf5`
- Starting tree: `6ee855f6b529f29f9c017e16ce9c62c6d6230279`
- Accepted launcher fix: `7053eb89af5eda199df514daf56f0a38be73adfd`
- Integrated launcher fix: `b64c61a8af7bc79d0062173b18fcee5c57e5897a`
- Integrated product tree: `8ffd9aea123958f384941130cc7799fadfc10cce`
- Routed input: P6 finding `p6-empty-query-strictness`

## Testable behaviors

1. Successful Herdr queries such as pane list and pane process-info reject empty
   stdout as an invalid response instead of treating it as an empty object.
2. Empty query output stops launcher execution before pane split, rename, run,
   send-keys, or any other pane mutation.
3. Successful imperative pane run and pane send-keys commands continue to
   accept empty stdout.
4. Non-empty JSON query parsing, nonzero command failures, required pane split
   results, stale-pane retry behavior, selected-ledger P1 anchoring, pane
   isolation, exact reuse, replacement, locking, and no-close contracts remain
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
- `plans/meta-harness-2026-08-02-live-runtime-recovery` audit tree:
  `f22266db22dd1eab9b7495455a2de29e90f8fe37`

All prior histories must remain byte-identical. Frozen Superpowers Compact
`152s` and Multi-module `1009s` are comparison-only metadata and are neither
rerun nor altered.

## Scope

This run writes only its own plan directory. No live panes, installation, push,
delivery, Herdr Orchestrator modification, or baseline mutation is allowed.
