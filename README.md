# Multi-Agent Graph Demo

A portable React Flow + Node.js demo for viewing a realtime multi-agent execution graph.

It shows a compact graph:

User task / Bibi orchestrator -> Codex implementation -> Claude QC/test -> Final delivery

The graph can run in two modes:

- Replay mode: built-in animation for demo/pitch videos.
- Live mode: listens to real hook events over Server-Sent Events (SSE) and updates node status/activity in realtime.

## What this includes

- React + Vite + TypeScript frontend
- React Flow graph UI
- Node.js event server, no Express required
- POST /events hook ingestion endpoint
- GET /stream SSE realtime endpoint
- JSONL event persistence at data/events.jsonl
- Hook emitter script for Claude/Codex/OpenClaw wrappers
- Simulated multi-agent run
- Real-task recording script
- MP4 conversion script using npm-installed ffmpeg
- Screenshot fallback script

## Requirements

Required:

- Node.js 20+ recommended
- npm

Optional for recording video/screenshots:

- Playwright browser dependencies. On Ubuntu/Debian you can usually run:

```bash
sudo npx playwright install-deps chromium
npx playwright install chromium
```

If you cannot use sudo, see “No-sudo browser libs workaround” below.

## Install

```bash
git clone <your-repo-url> multi-agent-graph-demo
cd multi-agent-graph-demo
npm install
npm run build
```

If you are copying this folder manually, copy the entire folder except `node_modules` if you want a clean install.

## Run the demo server

```bash
npm run server
```

Open:

```text
http://127.0.0.1:4173
```

Use the UI buttons:

- Replay: canned animation
- Live: listens to real events from /stream
- Play/Pause/Reset: replay controls

## Send live events

In another terminal:

```bash
npm run simulate
```

This emits a real sequence into POST /events:

Bibi running -> Codex running -> Codex done -> Claude running -> Claude done -> Final done

View stored events:

```bash
curl http://127.0.0.1:4173/events
```

## Emit a single hook event

```bash
node hooks/emit-event.js '{
  "nodeId": "codex",
  "status": "running",
  "activity": "Editing React Flow UI",
  "sessionId": "codex:pane-01",
  "type": "agent.tool.started"
}'
```

Event schema:

```json
{
  "graphId": "demo-run-1",
  "nodeId": "codex",
  "type": "agent.tool.started",
  "status": "running",
  "activity": "Editing React Flow UI",
  "sessionId": "codex:pane-01",
  "agent": "Codex",
  "label": "Codex",
  "timestamp": "2026-07-31T00:00:00.000Z",
  "payload": {}
}
```

Important fields:

- nodeId: one of bibi, codex, claude, final
- status: pending, running, waiting, done, failed
- activity: short text shown inside the node
- sessionId: the real agent/session identifier
- type: lifecycle/tool event name

## Integrating with Claude Code / Codex / OpenClaw hooks

At each lifecycle boundary, call `hooks/emit-event.js`.

Examples of useful hook points:

- session started
- task delegated
- tool started
- tool completed
- tool failed
- agent waiting on child sessions
- session completed
- session failed

Example wrapper call:

```bash
GRAPH_ENDPOINT=http://127.0.0.1:4173/events \
node hooks/emit-event.js "{\"nodeId\":\"claude\",\"status\":\"running\",\"activity\":\"Running tests\",\"sessionId\":\"claude:abc123\",\"type\":\"agent.tool.started\"}"
```

For OpenClaw/Hermes, the best integration points are:

1. Orchestrator/delegate_task start: create/update parent node and edge context.
2. Subagent session creation: update the child agent node with sessionId.
3. Tool wrapper/MCP boundary: update current activity.
4. Join/aggregate result: mark child done/failed and parent waiting/running.

## Record a video of the live graph

Install Playwright browser first:

```bash
npx playwright install chromium
```

Then:

```bash
npm run record
```

Output:

```text
artifacts/live-graph-demo.webm
```

Convert to MP4:

```bash
npm run convert:mp4
```

Output:

```text
artifacts/live-graph-demo.mp4
```

## Record a real task

This script performs a small real task while recording:

- writes REAL_TASK_RESULT.md
- runs npm run build
- saves artifacts/real-task-build.log
- records the graph and converts to MP4 manually if needed

```bash
npm run record:real
node scripts/convert-mp4.mjs artifacts/real-task-live-graph.webm artifacts/real-task-live-graph.mp4
```

Output:

```text
artifacts/real-task-live-graph.mp4
REAL_TASK_RESULT.md
artifacts/real-task-build.log
```

## Screenshot

Static fallback screenshot, no browser needed:

```bash
npm run screenshot:fallback
```

Output:

```text
artifacts/static-graph-screenshot.svg
```

## No-sudo browser libs workaround

If Playwright/Chromium fails with missing libs such as `libnspr4.so` and you cannot use sudo, you can locally download and extract the required Debian packages:

```bash
mkdir -p artifacts/browser-libs
cd artifacts/browser-libs
apt-get download libnspr4
apt-get download libnss3
apt-get download libasound2t64 || apt-get download libasound2
python3 - <<'PY'
import glob, subprocess
for deb in glob.glob('*.deb'):
    subprocess.run(['dpkg-deb','-x',deb,'.'], check=True)
PY
cd ../..
```

Run Playwright scripts with:

```bash
LIBDIR="$PWD/artifacts/browser-libs/usr/lib/x86_64-linux-gnu"
LD_LIBRARY_PATH="$LIBDIR:${LD_LIBRARY_PATH:-}" npm run record
```

## NPM scripts

- npm run dev: Vite dev server
- npm run build: TypeScript + Vite production build
- npm run server: Node event server + static dist server on port 4173
- npm run simulate: emit a sample multi-agent event sequence
- npm run record: record Live mode demo to WebM
- npm run record:real: perform a small real task and record it
- npm run convert:mp4: convert artifacts/live-graph-demo.webm to MP4
- npm run screenshot:fallback: generate static SVG screenshot

## Files to know

- src/main.tsx: React Flow UI and live/replay logic
- src/style.css: dark visual styling
- server.js: event ingestion, SSE, static serving
- hooks/emit-event.js: hook emitter
- scripts/simulate-run.js: demo event simulation
- scripts/record-demo.mjs: Playwright recording
- scripts/record-real-task.mjs: real task recording
- scripts/convert-mp4.mjs: MP4 conversion
- scripts/render-static-graph-svg.js: static screenshot fallback

## Packaging notes

Do not commit/copy these if you want a clean repo:

- node_modules/
- dist/
- data/events.jsonl
- artifacts/browser-libs/
- large generated videos under artifacts/

Keep source scripts and README.
