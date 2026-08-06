# Independent Meta-Harness Evaluation

Verdict: SUCCESS

Candidate: `800e6e34fcba015b63a3289769c9b7832c34f36a`
Tree: `c4fe3cccfe7693f97d28f55e3ae8c5df925ec811`
Rubric: `plans/meta-harness-2026-08-05-observed-graph/rubric.json`

## Scores

| Criterion | Score | Evidence summary |
| --- | ---: | --- |
| event_correctness | 9.3 | Bounded `ObservationLedger` emits timestamped lifecycle events for observed/status/assignee/generation/removal changes; 70 focused Python tests passed. |
| relationship_truthfulness | 9.4 | Session and synthetic snapshots emit zero edges/failure policies; custom manifests preserve authored edges and failure loops; browser smoke asserts the observed-topology notice and custom-topology behavior. |
| runtime_efficiency | 8.8 | Existing poll loops are reused, unchanged snapshots do not publish, and retained event history is bounded; no fresh profiler was run. |
| compatibility_isolation | 9.1 | Changed path scope is narrow, sibling skills remain untouched, launcher/workspace isolation tests passed, and receipts are identity-bound. |
| live_operator_evidence | 8.9 | Fresh browser smoke passed with screenshot sha256 `a5a46ccad7086829fc134290536cb705e41f494e3162c4bf68d13fced2c757a7`; design/persona receipts add real-browser and operator-language evidence. |

Weighted score: 9.15
Minimum criterion score: 8.8
Target: 8.5

## Hard Gates

- Candidate identity: PASS. `git rev-parse HEAD` and `HEAD^{tree}` match the requested immutable tuple.
- Required receipts: PASS. Read `integration-g3`, `independent_review-g3`, `functional_qc-g1`, `design_qc-g1`, and `persona_qc-g1` from the exact wK run; all are PASS and candidate-bound.
- Scope: PASS. No product/source/skill files were edited by this evaluator; only plan evidence artifacts were created.
- Verification: PASS. Focused Python, launcher, Vitest, build, browser smoke, evidence-schema validation, and `git diff --check` passed.

## Evidence Commands

- `python3 -B -m unittest adapters.herdr.test_observed_events adapters.herdr.test_session_publisher adapters.herdr.test_publisher`: PASS, 70 tests.
- `python3 -B skills/herdr-graph-viewer/scripts/test_start_viewer.py`: PASS, 48 tests.
- `npm test -- --run src/graph/layout.test.ts tests/protocol.test.js tests/store.test.js`: PASS, 3 files / 37 tests.
- `npm run build`: PASS.
- `node tests/browser-smoke.mjs`: PASS, screenshot generated at `artifacts/live-role-graph-browser-smoke.png`.
- Inline evidence schema and plan requirements validation: PASS.
- `git diff --check`: PASS.

## Remaining Limitations

I did not generate a new long-duration live wK control-pane capture in this evaluator turn. The live/operator score is based on immutable wK receipts plus fresh local browser smoke against the requested candidate.

The worktree has a pre-existing untracked `node_modules` directory; it was not modified or committed.
