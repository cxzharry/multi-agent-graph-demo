# Meta-Harness Report: P1 Anchor Recovery

## Outcome

SUCCESS in iteration 1. Composite score: `8.6`; every locked criterion is at
least `8`. P6 generation-2 finding `p6-right-of-p1-anchor` is resolved by the
accepted launcher g4 fix.

## Product integration

- Accepted commit: `277e360e31a51594149f020280be6b27b7909078`
- Integrated commit: `67ec076cefc6f67b9eb8efa793f00cd50a433438`
- Integrated tree: `9a8fa322842a93a8a79aeda85f0184a23ffed633`
- Changed paths: `start_viewer.py` and `test_start_viewer.py` only

The launcher resolves P1 from the selected state before manifest, port, pane,
or process discovery. Cold launches split the server right of that P1 and the
publisher below the server. Reused-server recovery splits the missing publisher
right of that same P1. A missing P1 binding fails before Herdr pane operations.

## Verification

- Publisher unittest: 29 passed.
- Launcher tests: 31 passed.
- Vitest: 4 files, 35 tests passed.
- Production TypeScript/Vite build: passed.
- Browser smoke: passed with 11-role scale `1.034` and no reported error.
- `git diff --check`: passed with no output.

No dependencies were installed. After byte-identical `package.json` and
`package-lock.json` checks, the source checkout's existing `node_modules` was
exposed through a temporary symlink and removed by shell trap.

## Locked scores

| Criterion | Score | Evidence focus |
|---|---:|---|
| `selected_ledger_p1_anchoring` | 9 | Cold and reused-server non-P1 invocation, missing binding guard |
| `pane_isolation_no_below_p1` | 9 | Exact right-side rail, down only from server, no-focus |
| `launcher_lifecycle_reuse` | 8 | Exact reuse, replacement, locking, concurrency |
| `backward_compatibility` | 8 | Manifest modes, workspace isolation, publisher/frontend regression |
| `full_integration_quality` | 9 | All six commands and real browser smoke pass |

## Audit and frozen comparison

The earlier `plans/meta-harness-2026-08-02-manifestless-viewer` history remains
bound to audit tree `e5614096f9b89dc28f0256979ac0fac564cc8add` and is not edited by
this run. Frozen Compact `152s` and Multi-module `1009s` are comparison-only
metadata and were neither rerun nor altered.

No installation, push, delivery, or live-pane operation occurred.
