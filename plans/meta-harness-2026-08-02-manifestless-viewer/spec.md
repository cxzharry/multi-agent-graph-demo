# Manifestless Viewer Delivery Evaluation Spec

## Bound inputs

- Contract: `herdr-graph-viewer-manifestless-20260802`
- Integration generation: `1`
- Integration base: `00bb64448f664857a6e9c68cb3216d457c85c004`
- Publisher accepted tip: `cd2ca2cd0a9eb68ad8ccc99e5a19710710d0acf5`
- Launcher accepted tip: `68c3bbf9b787cb378ce638cd7d1c35239a79072c`
- Approved plan SHA-256:
  `edb2464cb163a6ab4b6c96d39a444d9dd50fdaa1f2c9de1385e1e49fd2ddb507`

## Testable behaviors

1. A valid state with no custom manifest selects synthetic topology and can
   produce an exact current-revision snapshot.
2. Dynamic lanes and reassignment chains remain visible without inferred
   lane-to-lane flow or failure semantics.
3. Publisher and launcher preserve exact workspace isolation and do not write
   orchestration state or act on agent panes.
4. Publisher reuse is exact by mode; mode replacement reuses the viewer-owned
   pane; cold placement forms a right-side rail.
5. Custom manifests retain precedence and validation while protocol tests,
   production build, and browser smoke remain green.

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

The approved plan records Compact `152s` and Multi-module `1009s`. These values
are comparison-only: this run neither edits nor reruns frozen baselines, and
orchestration timing is not a product gate for this optional viewer change.

## Scope

Evaluation may write only this plan directory. Product corrections are not made
by P5: a finding stops the run for P1 routing. Installation, push, pane closure,
and delivery are outside this gate.
