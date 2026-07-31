import { chromium } from 'playwright';
import { spawn } from 'child_process';
import fs from 'fs';
import path from 'path';

const base = process.cwd();
fs.mkdirSync(path.join(base, 'artifacts'), { recursive: true });
const server = spawn('npm', ['run', 'server'], { cwd: base, stdio: ['ignore', 'pipe', 'pipe'] });
await new Promise(r => setTimeout(r, 1200));
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  viewport: { width: 1440, height: 950 },
  recordVideo: { dir: path.join(base, 'artifacts'), size: { width: 1440, height: 950 } }
});
const page = await context.newPage();
await page.goto('http://127.0.0.1:4173', { waitUntil: 'networkidle' });
await page.getByText('Live').click();
await page.waitForTimeout(700);
const sim = spawn('npm', ['run', 'simulate'], { cwd: base, stdio: ['ignore', 'pipe', 'pipe'] });
await new Promise(resolve => sim.on('close', resolve));
await page.waitForTimeout(2200);
const video = await page.video().path();
await context.close();
await browser.close();
server.kill('SIGTERM');
const out = path.join(base, 'artifacts', 'live-graph-demo.webm');
fs.copyFileSync(video, out);
console.log(out);
