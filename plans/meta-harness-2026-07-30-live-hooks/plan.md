# Live Multi-Agent Graph Demo Spec

Gate: PROCEED — task is multi-step, multi-file, visual + runtime behavior, and requires iterative verification.
Intent: DELIVER
Mode: Auto recommended — internal routing. Use local controller for integration plus Claude/Codex sidecars where useful.

## Goal
Upgrade the React Flow visual demo into a runnable near-realtime multi-agent execution graph. It must accept hook events, update agent nodes live, and provide a screenshot-capable browser smoke path.

## Scope
- Keep graph compact: 4 nodes (Bibi, Codex, Claude, Final).
- Add a local Node server with POST /events, GET /events, GET /stream SSE, static Vite build serving.
- Add hook scripts that can be called by Claude/Codex/OpenClaw wrappers to emit JSON events.
- UI supports demo playback and live mode consuming SSE.
- Provide simulation script that emits a real Bibi → Codex → Claude → Final run.
- Fix screenshot environment enough to capture a browser screenshot.

## Parallelization Strategy
Can parallelize: yes.
Implementation lanes: (1) backend event server/scripts, (2) frontend live React Flow mode, (3) test/QC screenshot smoke.
Sequential dependencies: event schema first, final build after merge.
Verification: npm build, server API simulation, SSE/browser smoke, screenshot artifact.
Recommended Phase 3 Agent Split Gate input: Spawn sidecar reviewers/tests; controller integrates.

## Iteration 1 Plan
1. Install missing browser deps.
2. Add event server and hook scripts.
3. Upgrade UI live mode.
4. Build and run server.
5. Simulate hook events, browser smoke, screenshot.
