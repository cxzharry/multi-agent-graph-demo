# Meta-Harness Plan

Review:

`docs/superpowers/plans/2026-07-31-live-role-graph.md`

Implementation parallelism: Parallel lanes

Reason: protocol/server and the read-only adapter have disjoint files; frontend
depends on the shared protocol/dependency lane.

## Parallelization Strategy

- Can parallelize: yes
- Lane 1: snapshot protocol, persistence, local API, package dependencies
- Lane 2: generic graph UI and browser smoke after Lane 1
- Lane 3: repository-local read-only Herdr adapter
- Merge point: P5 integrates all three commits in the viewer repository
- Verification: focused lane checks, full integration suite, browser smoke,
  P6 review, and P7-P9 QC
- Recommended Phase 3 Agent Split Gate input: Spawn via Herdr after plan
  approval

