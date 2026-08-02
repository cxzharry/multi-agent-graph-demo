# Meta-Harness Report: Manifestless Viewer Integration

## Outcome

SUCCESS in iteration 1 of at most 2. Composite score: `8.2`; every locked
criterion met target `8` and remained above minimum `7`. No product finding or
P5 correction was produced.

## Integrated inputs

| Accepted commit | Integration commit | Purpose |
|---|---|---|
| `97c7ca5badb39dd89b26ba5dc73369babfef1cf4` | `fc1e524f2415709a02d70508aff800f188c1aefa` | Synthetic operational graph |
| `96affc46bf5f65139f53f24385dca30d4382a731` | `6452e0863c14ff63379fdba155a3edb360f6c2ba` | Projection hardening |
| `cd2ca2cd0a9eb68ad8ccc99e5a19710710d0acf5` | `d16b39bb053de32a8e35c2624b5dc667fe2625a4` | Collision-free live IDs |
| `14b4bec642314c18ca8393631513f8fddf6bc45e` | `b8c6d5e56811fbbdf393117cb6da630c20e82d6b` | Manifestless launcher and pane rail |
| `116ae64a1c6ef47808ae02d7d0853bda91c6e3e5` | `1ebbfb56c7c5ad923fe2871563506daf559c0d8a` | Strict custom-manifest validation |
| `68c3bbf9b787cb378ce638cd7d1c35239a79072c` | `f2ab5c246b1b4bfa3e5d2f08de69818dedc5174b` | Task and layer validation parity |

## Verification

- Publisher unittest: 28 passed.
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
| `projection_integrity` | 9 | Determinism, reassignment, dynamic lanes, collision and invalid-chain safety |
| `isolation_and_readonly` | 8 | Workspace rejection, AST guard, no agent-pane replacement |
| `launcher_lifecycle` | 8 | Exact mode reuse, same-pane replacement, right rail, locking |
| `backward_compatibility` | 8 | Custom precedence/validation, protocol tests, build, browser smoke |

## Frozen comparison and scope

Recorded frozen Superpowers references remain Compact `152s` and Multi-module
`1009s`. They were compared as plan metadata only and were neither rerun nor
edited. No installation, push, delivery, pane closure, or P6-P9 action occurred.
