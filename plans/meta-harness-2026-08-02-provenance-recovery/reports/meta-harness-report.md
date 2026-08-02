# Meta-Harness Report: Provenance Recovery

## Outcome

SUCCESS in iteration 1. Composite score: `8.8`; every locked criterion is at
least `8`. P6 finding `p6-authored-auto-id-provenance` is resolved by the
accepted persona UI generation-2 fix.

## Product integration

| Accepted commit | Integration commit | Purpose |
|---|---|---|
| `d6e42ca20d1f1d7b09a63739765d79a61681a29c` | `368cf74f71645578aa5ef2dbc6b9810c0bf75b25` | Key synthetic display hiding to trustworthy flow provenance |

Integrated product tree: `90313cf2902098293ce17251d0abf394c9e10f91`.

Node display data is now marked synthetic only when the snapshot has the exact
`auto-operational` flow provenance. Node ID prefixes and decoded task text no
longer establish provenance by themselves.

Browser smoke publishes an authored custom snapshot and a synthetic snapshot
with the same auto-hex node ID and matching task. The authored snapshot retains
the full authored ID and task. The synthetic snapshot hides both generated
internals while preserving the role-first Publisher heading and compact P5
assignee chip.

## Verification

- Publisher unittest: 34 passed.
- Launcher tests: 41 passed.
- Vitest: 4 files, 37 tests passed.
- Production TypeScript/Vite build: passed.
- Browser smoke: authored/synthetic provenance plus persona, custom loop/layout,
  and runtime assertions passed with 11-role scale `1.034`.
- `git diff --check`: passed with no output.

The worktree already contained a real dependency directory and package files
matched the source checkout byte-for-byte. No installation, synchronization,
or dependency-link mutation occurred.

## Locked scores

| Criterion | Score | Evidence focus |
|---|---:|---|
| `provenance_keyed_hiding` | 9 | Exact auto-operational flow provenance only |
| `authored_auto_id_visibility` | 9 | Same auto-hex ID/task remains fully authored and visible |
| `synthetic_internal_readability` | 9 | Generated internals hidden; role and P chip retained |
| `retained_persona_time_identity_contracts` | 9 | Lane identity, deterministic time, normalized display, accessibility |
| `retained_custom_layout_runtime_quality` | 8 | Full matrix, custom/loop/layout/runtime, launcher lifecycle, audit preservation |

## Audit and frozen comparison

All six prior Meta-Harness subtrees remain byte-identical. Frozen Superpowers
Compact `152s` and Multi-module `1009s` are comparison-only metadata and were
neither rerun nor altered.

No live-pane operation, pane closure, installation, synchronization, push,
delivery, source-main mutation, P6 self-review, or Herdr Orchestrator
modification occurred.
