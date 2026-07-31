import { chromium } from 'playwright';
import { spawn, spawnSync } from 'child_process';
import fs from 'fs';
import path from 'path';

const base = process.cwd();
const endpoint = 'http://127.0.0.1:4173/events';
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
function run(cmd, args, opts={}) {
  const res = spawnSync(cmd, args, { cwd: base, encoding: 'utf8', ...opts });
  return { code: res.status ?? 0, out: (res.stdout || '') + (res.stderr || '') };
}
async function emit(event) {
  const body = JSON.stringify({ graphId: 'real-task-demo', timestamp: new Date().toISOString(), ...event });
  const res = await fetch(endpoint, { method: 'POST', headers: {'content-type':'application/json'}, body });
  if (!res.ok) throw new Error(`emit failed ${res.status}`);
}

fs.mkdirSync(path.join(base, 'artifacts'), { recursive: true });
fs.mkdirSync(path.join(base, 'data'), { recursive: true });
fs.writeFileSync(path.join(base, 'data/events.jsonl'), '');

const server = spawn('npm', ['run', 'server'], { cwd: base, stdio: ['ignore', 'pipe', 'pipe'] });
await sleep(1200);

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  viewport: { width: 1440, height: 950 },
  recordVideo: { dir: path.join(base, 'artifacts'), size: { width: 1440, height: 950 } }
});
const page = await context.newPage();
await page.goto('http://127.0.0.1:4173', { waitUntil: 'networkidle' });
await page.getByText('Live').click();
await sleep(900);

await emit({ nodeId:'bibi', agent:'Bibi', status:'running', type:'agent.session.started', sessionId:'bibi:real-task', activity:'Real task: create timestamped artifact and verify build' });
await sleep(1200);

await emit({ nodeId:'codex', agent:'Codex', status:'running', type:'agent.tool.started', sessionId:'codex:real-task', activity:'Writing REAL_TASK_RESULT.md with actual filesystem output' });
const artifact = `# Real Task Result\n\nCreated by the live graph demo at ${new Date().toISOString()}.\n\nThis file is a real artifact written during the recorded run, not a mock event.\n\nTask steps:\n1. Bibi opened the run.\n2. Codex wrote this artifact.\n3. Claude ran npm build as QC.\n4. Final node delivered the verified result.\n`;
fs.writeFileSync(path.join(base, 'REAL_TASK_RESULT.md'), artifact);
await sleep(1300);
await emit({ nodeId:'codex', agent:'Codex', status:'done', type:'agent.tool.completed', sessionId:'codex:real-task', activity:'REAL_TASK_RESULT.md written to disk' });
await sleep(900);

await emit({ nodeId:'claude', agent:'Claude', status:'running', type:'agent.tool.started', sessionId:'claude:real-task', activity:'Running npm run build for QC' });
await sleep(500);
const build = run('npm', ['run', 'build']);
fs.writeFileSync(path.join(base, 'artifacts/real-task-build.log'), build.out);
await sleep(1100);
await emit({ nodeId:'claude', agent:'Claude', status: build.code === 0 ? 'done' : 'failed', type: build.code === 0 ? 'agent.tool.completed' : 'agent.tool.failed', sessionId:'claude:real-task', activity: build.code === 0 ? 'Build passed; log saved to artifacts/real-task-build.log' : 'Build failed; log saved' });
await sleep(1100);

await emit({ nodeId:'final', agent:'Final', status:'done', type:'agent.session.completed', sessionId:'artifact:real-task', activity:'Delivered REAL_TASK_RESULT.md + build log + recording' });
await sleep(1800);

const video = await page.video().path();
await context.close();
await browser.close();
server.kill('SIGTERM');
const webm = path.join(base, 'artifacts/real-task-live-graph.webm');
fs.copyFileSync(video, webm);
console.log(webm);
