# Meta-Harness Report: Live Runtime Recovery

## Outcome

SUCCESS in iteration 1. Composite score: `8.8`; every locked criterion is at
least `8`. P7 finding `p7-live-runtime-cold-and-mode-replacement` is resolved by
the accepted publisher and launcher generation-5 fixes.

## Product integration

| Accepted commit | Integration commit | Purpose |
|---|---|---|
| `a73cf68d4c6ab3f98ec3d94ad171dc7249f63f7f` | `cabc6db17549816c1081b38d39ea0d2ba8c3e272` | Explicit equal-sequence replacement |
| `9ee0c4226076c1975b69223180c34b503684fc9c` | `84ed920c0ab45b2a764207abbd59374b76b56a5c` | Imperative Herdr and mode replacement |

Integrated product tree: `3b6d9492b8790c6bab2d6a32ff18f9c8da6296dc`.

The publisher emits `X-Role-Graph-Replace-Current: true` only when explicitly
started with `--replace-current`, and clears the mode after its first successful
publish. The launcher adds that flag only after stopping a mismatched same-state
ordinary publisher. Cold/new publishers omit it.

The store accepts explicit replacement only when the incoming sequence equals
the current sequence. Default equal, default lower, and explicit lower inputs
remain stale conflicts. Appended equal replacements remain current after
restart hydration.

Successful imperative Herdr calls may return empty stdout. JSON query responses
remain parsed, nonzero exits remain errors, and pane splitting still requires a
concrete pane ID.

## Verification

- Publisher unittest: 31 passed.
- Launcher tests: 35 passed.
- Vitest: 4 files, 37 tests passed.
- Production TypeScript/Vite build: passed.
- Browser smoke: passed with 11-role scale `1.034` and no reported error.
- `git diff --check`: passed with no output.

The worktree already contained dependencies and the package files matched the
source checkout byte-for-byte. No install or dependency-link mutation occurred.

## Locked scores

| Criterion | Score | Evidence focus |
|---|---:|---|
| `real_herdr_imperative_compatibility` | 9 | Empty imperative success; strict query/split contracts |
| `explicit_mode_replacement_safety` | 9 | Header and first POST; mismatch-only launcher flag |
| `sequence_store_backward_compatibility` | 9 | Equal-only explicit replacement; lower/default conflicts; hydration |
| `pane_process_lifecycle_contracts` | 8 | P1 anchor, exact reuse, isolation, locking, no-close |
| `full_integration_quality` | 9 | All six commands and browser smoke pass |

## Audit and frozen comparison

Prior harness trees remain byte-identical:

- Manifestless viewer: `e5614096f9b89dc28f0256979ac0fac564cc8add`
- P1 anchor recovery: `b43deffeb76a4c23d357c74c516237d3690de6fb`

Frozen Compact `152s` and Multi-module `1009s` are comparison-only metadata and
were neither rerun nor altered.

No live-pane operation, installation, push, or delivery occurred.
