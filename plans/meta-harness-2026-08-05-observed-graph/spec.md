# Meta-harness Spec: Observed Graph Truthfulness

Source design: `docs/superpowers/specs/2026-08-05-herdr-graph-observed-events-design.md`

Improve `herdr-graph-viewer` so session and manifestless control runs publish
immediate bounded lifecycle events and never fabricate workflow edges. Preserve
custom manifest topology, workspace isolation, explicit startup, existing
presence behavior, and every sibling skill byte-for-byte.

Testable behavior: a fresh session snapshot contains at least one timestamped
event per current node and zero edges; a custom branched-loop snapshot retains
its authored forward and return routes.

