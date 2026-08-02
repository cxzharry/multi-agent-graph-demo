# Meta-Harness Report: Manifestless Viewer Integration

## Outcome

SUCCESS in iteration 2 of 2. Final composite score: `8.4`; every locked
criterion is at least target `8` and remains above minimum `7`. Iteration 1 was
reclassified after P6 found an authored/generated control-edge ID collision;
the accepted publisher fix-forward closes that finding in iteration 2.

## Integrated inputs

| Accepted commit | Integration commit | Purpose |
|---|---|---|
| `97c7ca5badb39dd89b26ba5dc73369babfef1cf4` | `fc1e524f2415709a02d70508aff800f188c1aefa` | Synthetic operational graph |
| `96affc46bf5f65139f53f24385dca30d4382a731` | `6452e0863c14ff63379fdba155a3edb360f6c2ba` | Projection hardening |
| `cd2ca2cd0a9eb68ad8ccc99e5a19710710d0acf5` | `d16b39bb053de32a8e35c2624b5dc667fe2625a4` | Collision-free live IDs |
| `14b4bec642314c18ca8393631513f8fddf6bc45e` | `b8c6d5e56811fbbdf393117cb6da630c20e82d6b` | Manifestless launcher and pane rail |
| `116ae64a1c6ef47808ae02d7d0853bda91c6e3e5` | `1ebbfb56c7c5ad923fe2871563506daf559c0d8a` | Strict custom-manifest validation |
| `68c3bbf9b787cb378ce638cd7d1c35239a79072c` | `f2ab5c246b1b4bfa3e5d2f08de69818dedc5174b` | Task and layer validation parity |
| `81aab03259bc4fdbd1c2e381e400810e72543289` | `2b90126bde97d5809dacc20e7666cd6c32a264a9` | Collision-free live control-edge IDs |

## Routed iteration-1 failure

P6 showed that a generated live control edge used its preferred ID without
checking authored edge IDs. An authored edge with the same ID therefore caused
a duplicate in the projected `role-graph/v1` snapshot. Iteration 1 records
`projection_integrity=7` and composite `7.8`, classified as an implementation
failure routed to `publisher_projection`.

Iteration 2 reserves every authored edge ID before allocating generated IDs.
Suffix selection is deterministic, authored edge values remain unchanged, and
the regression test asserts repeated-build equality, authored-edge retention,
generated/authored ID inequality, global edge-ID uniqueness, and validation by
the real shared protocol validator.

## Verification

- Publisher unittest: 29 passed.
- Launcher tests: 30 passed.
- Vitest: 4 files, 35 tests passed.
- Production TypeScript/Vite build: passed.
- Browser smoke: passed; no error was reported; 11-role scale `1.034`.
- `git diff --check`: passed with no output.

The worktree had no `node_modules`, and installation was prohibited. The exact
Node checks used the source checkout's existing dependency tree only after
`package.json` and `package-lock.json` compared byte-for-byte. A temporary
symlink exposed it to the worktree and was removed automatically after checks.

## Locked scores

| Criterion | Score | Evidence focus |
|---|---:|---|
| `manifestless_correctness` | 8 | Synthetic selection, null manifest, exact sequence readiness |
| `projection_integrity` | 9 | Authored IDs preserved; deterministic generated edge allocation and protocol uniqueness |
| `isolation_and_readonly` | 8 | Workspace rejection, AST guard, no agent-pane replacement |
| `launcher_lifecycle` | 8 | Exact mode reuse, same-pane replacement, right rail, locking |
| `backward_compatibility` | 9 | Shared node allocator behavior, protocol test, full matrix, browser smoke |

## Frozen comparison and scope

Recorded frozen Superpowers references remain Compact `152s` and Multi-module
`1009s`. They were compared as plan metadata only and were neither rerun nor
edited. No installation, push, delivery, or pane operation occurred; P7-P9
gates remain downstream.
