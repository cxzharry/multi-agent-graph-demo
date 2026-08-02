# Meta-Harness Report: Cold Query Order Recovery

## Outcome

SUCCESS in iteration 1. Composite score: `8.8`; every locked criterion is at
least `8`. P6 finding `p6-cold-query-before-mutation` is resolved by the
accepted launcher generation-7 fix.

## Product integration

| Accepted commit | Integration commit | Purpose |
|---|---|---|
| `ed8c349e14560acd5cdac6de86ea8f0de791e9ed` | `71bc0311cbcba972bfd5472e9f84ba6d88b79594` | Validate publisher discovery before every pane mutation |

Integrated product tree: `cd494490f2ac6af7b73a0e3d4cb26a1d13272a92`.

Exact and same-state publisher discovery now completes before cold server pane
creation. Empty or malformed pane-list and process-info output therefore fails
before split, rename, run, or send-keys for both cold and reused viewers.

The launcher suite directly covers all four cold empty/malformed query cases
and both reused empty cases. The focused evaluator ran the same exact-command
protocol helper for both reused malformed cases; each stopped before mutation.

Successful imperative pane run and pane send-keys still accept empty stdout.
Valid JSON queries parse, nonzero exits remain errors, and pane splitting still
requires a concrete pane ID.

## Verification

- Publisher unittest: 31 passed.
- Launcher tests: 41 passed.
- Focused reused malformed protocol assertions: 2 passed.
- Vitest: 4 files, 37 tests passed.
- Production TypeScript/Vite build: passed.
- Browser smoke: passed with 11-role scale `1.034` and no reported error.
- `git diff --check`: passed with no output.

The worktree already contained a real dependency directory and the package
files matched the source checkout byte-for-byte. No install or dependency-link
mutation occurred.

## Locked scores

| Criterion | Score | Evidence focus |
|---|---:|---|
| `cold_query_failures_before_mutation` | 9 | Cold empty/malformed list and process query traces |
| `reused_query_failures_before_mutation` | 9 | Reused empty/malformed list and process query traces |
| `imperative_query_protocol_compatibility` | 9 | Empty imperative success; strict JSON, exit, and split behavior |
| `launcher_lifecycle_contracts` | 8 | P1 anchor, reuse, isolation, replacement, stale recovery, locking, no-close |
| `full_integration_quality_and_audit` | 9 | Full matrix and every prior harness subtree preserved |

## Audit and frozen comparison

Prior harness trees remain byte-identical:

- Manifestless viewer: `e5614096f9b89dc28f0256979ac0fac564cc8add`
- P1 anchor recovery: `b43deffeb76a4c23d357c74c516237d3690de6fb`
- Live runtime recovery: `f22266db22dd1eab9b7495455a2de29e90f8fe37`
- Superseded query strictness: `3236642651c3f9418df0655f83c318d926ef6c4b`

Frozen Superpowers Compact `152s` and Multi-module `1009s` are comparison-only
metadata and were neither rerun nor altered.

No live-pane operation, pane closure, installation, push, delivery, or Herdr
Orchestrator modification occurred.
