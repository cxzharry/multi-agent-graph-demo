# Meta-Harness Report: Query Strictness Recovery

## Outcome

SUCCESS in iteration 1. Composite score: `8.8`; every locked criterion is at
least `8`. P6 finding `p6-empty-query-strictness` is resolved by the accepted
launcher generation-6 fix.

## Product integration

| Accepted commit | Integration commit | Purpose |
|---|---|---|
| `7053eb89af5eda199df514daf56f0a38be73adfd` | `b64c61a8af7bc79d0062173b18fcee5c57e5897a` | Strict query output without imperative regression |

Integrated product tree: `8ffd9aea123958f384941130cc7799fadfc10cce`.

Successful pane list and pane process-info queries now reject empty stdout as
an invalid Herdr response. Both discovery paths re-raise invalid responses, so
the launcher cannot reinterpret them as stale panes and continue toward split,
rename, run, or send-keys. The protocol tests assert the exact command prefix
and prove no mutation command occurs.

Successful imperative pane run and pane send-keys commands still accept empty
stdout. Non-empty JSON queries remain parsed, nonzero exits remain errors, and
pane splitting still requires a concrete pane ID.

## Verification

- Publisher unittest: 31 passed.
- Launcher tests: 37 passed.
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
| `strict_empty_query_rejection` | 9 | Empty list/process query output fails; JSON still parses |
| `query_failure_no_mutation` | 9 | Exact command traces stop before every pane mutation |
| `empty_imperative_backward_compatibility` | 9 | Empty run/send-keys success; strict split/nonzero behavior |
| `launcher_lifecycle_backward_compatibility` | 8 | P1 anchor, reuse, isolation, replacement, stale handling, locking, no-close |
| `full_integration_quality` | 9 | Six commands, browser smoke, and prior harness preservation pass |

## Audit and frozen comparison

Prior harness trees remain byte-identical:

- Manifestless viewer: `e5614096f9b89dc28f0256979ac0fac564cc8add`
- P1 anchor recovery: `b43deffeb76a4c23d357c74c516237d3690de6fb`
- Live runtime recovery: `f22266db22dd1eab9b7495455a2de29e90f8fe37`

Frozen Superpowers Compact `152s` and Multi-module `1009s` are comparison-only
metadata and were neither rerun nor altered.

No live-pane operation, installation, push, delivery, or Herdr Orchestrator
modification occurred.
