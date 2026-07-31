import assert from 'node:assert/strict';
import {mkdir, mkdtemp, readFile, rm} from 'node:fs/promises';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import {spawn} from 'node:child_process';

import {chromium} from 'playwright';

const repositoryRoot = path.resolve(import.meta.dirname, '..');
const artifactsDirectory = path.join(repositoryRoot, 'artifacts');
const screenshotPath = path.join(
  artifactsDirectory,
  'live-role-graph-browser-smoke.png',
);

async function readFixture(name) {
  return JSON.parse(
    await readFile(path.join(repositoryRoot, 'fixtures', name), 'utf8'),
  );
}

async function reservePort() {
  const server = net.createServer();
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  const address = server.address();
  assert.ok(address && typeof address === 'object');
  const {port} = address;
  await new Promise(resolve => server.close(resolve));
  return port;
}

async function waitForServer(baseUrl) {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    try {
      const response = await fetch(`${baseUrl}/api/graphs`);
      if (response.ok) return;
    } catch {
      // The server is still starting.
    }
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error('Timed out waiting for the role graph server');
}

async function postSnapshot(baseUrl, snapshot) {
  const response = await fetch(`${baseUrl}/api/snapshots`, {
    method: 'POST',
    headers: {'content-type': 'application/json'},
    body: JSON.stringify(snapshot),
  });
  assert.equal(response.status, 202, await response.text());
}

async function waitForNodeCount(page, count) {
  await page.waitForFunction(
    expected =>
      document.querySelectorAll('[data-testid="role-node"]').length === expected,
    count,
  );
}

async function nodeBox(page, nodeId) {
  const box = await page.locator(`[data-node-id="${nodeId}"]`).boundingBox();
  assert.ok(box, `Expected a visible node for ${nodeId}`);
  return box;
}

const temporaryDirectory = await mkdtemp(
  path.join(os.tmpdir(), 'role-graph-browser-smoke-'),
);
const dataFile = path.join(temporaryDirectory, 'snapshots.jsonl');
const port = await reservePort();
const baseUrl = `http://127.0.0.1:${port}`;
const serverProcess = spawn(process.execPath, ['server.js'], {
  cwd: repositoryRoot,
  env: {
    ...process.env,
    HOST: '127.0.0.1',
    PORT: String(port),
    ROLE_GRAPH_DATA_FILE: dataFile,
  },
  stdio: ['ignore', 'pipe', 'pipe'],
});
let serverOutput = '';
serverProcess.stdout.on('data', chunk => {
  serverOutput += chunk;
});
serverProcess.stderr.on('data', chunk => {
  serverOutput += chunk;
});

let browser;
try {
  await waitForServer(baseUrl);
  browser = await chromium.launch({headless: true});
  const page = await browser.newPage({viewport: {width: 1440, height: 1000}});

  await page.goto(baseUrl);
  await page.locator('[data-testid="empty-state"]').waitFor();

  const compact = await readFixture('compact.json');
  const branched = await readFixture('branched-loop.json');
  await postSnapshot(baseUrl, compact);
  await postSnapshot(baseUrl, branched);

  await page.reload();
  await waitForNodeCount(page, branched.nodes.length);

  const selector = page.locator('[data-testid="graph-selector"]');
  await selector.selectOption(
    new URLSearchParams({
      scopeId: compact.scopeId,
      runId: compact.runId,
    }).toString(),
  );
  await waitForNodeCount(page, compact.nodes.length);
  assert.equal(await page.locator('[data-testid="feedback-edge"]').count(), 0);

  await page.reload();
  await waitForNodeCount(page, compact.nodes.length);

  await selector.selectOption(
    new URLSearchParams({
      scopeId: branched.scopeId,
      runId: branched.runId,
    }).toString(),
  );
  await waitForNodeCount(page, branched.nodes.length);

  const implementationBoxes = await Promise.all([
    nodeBox(page, 'implementation-a'),
    nodeBox(page, 'implementation-b'),
    nodeBox(page, 'implementation-c'),
  ]);
  assert.ok(
    implementationBoxes.every(
      box => Math.abs(box.y - implementationBoxes[0].y) < 1,
    ),
    'Explicit parallel roles must share one horizontal layer',
  );

  const orchestratorBox = await nodeBox(page, 'orchestration');
  const otherBoxes = await Promise.all(
    branched.nodes
      .filter(node => node.id !== 'orchestration')
      .map(node => nodeBox(page, node.id)),
  );
  assert.ok(
    otherBoxes.every(box => orchestratorBox.y < box.y),
    'The orchestration role must be above every downstream role',
  );
  assert.equal(await page.locator('[data-testid="feedback-edge"]').count(), 1);

  const liveUpdate = structuredClone(branched);
  liveUpdate.sequence = 2;
  liveUpdate.generatedAt = '2026-07-31T10:06:00Z';
  liveUpdate.nodes = liveUpdate.nodes.map(node =>
    node.id === 'functional-qc'
      ? {...node, status: 'retrying', task: 'Re-run live update verification'}
      : node,
  );
  liveUpdate.events = [
    ...liveUpdate.events,
    {
      id: 'functional-retry',
      timestamp: liveUpdate.generatedAt,
      nodeId: 'functional-qc',
      type: 'retry',
      message: 'Functional verification is running again',
    },
  ];
  await postSnapshot(baseUrl, liveUpdate);
  await page.waitForFunction(
    () =>
      document.querySelector('[data-node-id="functional-qc"]')?.getAttribute(
        'data-status',
      ) === 'retrying',
  );

  await mkdir(artifactsDirectory, {recursive: true});
  await page.screenshot({path: screenshotPath, fullPage: true});
  console.log(`Browser smoke passed. Screenshot: ${screenshotPath}`);
} catch (error) {
  error.message = `${error.message}\nServer output:\n${serverOutput}`;
  throw error;
} finally {
  await browser?.close();
  serverProcess.kill('SIGTERM');
  await Promise.race([
    new Promise(resolve => serverProcess.once('exit', resolve)),
    new Promise(resolve => setTimeout(resolve, 2000)),
  ]);
  await rm(temporaryDirectory, {recursive: true, force: true});
}
