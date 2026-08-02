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
const newAtEventTime = '2026-07-31T10:05:09Z';
const newAtEventLabel = formatSmokeTimestamp(newAtEventTime);

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

async function viewportReadability(page, nodeId) {
  return page.evaluate(id => {
    const viewport = document.querySelector('.react-flow__viewport');
    const node = document.querySelector(`[data-node-id="${id}"]`);
    assertElement(viewport, 'React Flow viewport');
    assertElement(node, `role node ${id}`);

    const transform = new DOMMatrixReadOnly(getComputedStyle(viewport).transform);
    const scale = Math.abs(transform.a);
    const roleTitle = node.querySelector('h3');
    const task = node.querySelector('.role-task');
    const status = node.querySelector('.role-status');
    assertElement(roleTitle, 'role title');
    assertElement(task, 'role task');
    assertElement(status, 'role status');

    return {
      scale,
      roleTitle: Number.parseFloat(getComputedStyle(roleTitle).fontSize) * scale,
      task: Number.parseFloat(getComputedStyle(task).fontSize) * scale,
      status: Number.parseFloat(getComputedStyle(status).fontSize) * scale,
    };

    function assertElement(value, label) {
      if (!(value instanceof Element)) throw new Error(`Missing ${label}`);
    }
  }, nodeId);
}

async function statusVisualState(page) {
  return page.evaluate(() => {
    const statusOrder = [
      'running',
      'retrying',
      'passed',
      'pending',
      'failed',
    ];
    const state = {};
    for (const status of statusOrder) {
      const node = document.querySelector(`[data-status="${status}"]`);
      assertElement(node, `${status} role node`);
      const dot = node.querySelector('.status-dot');
      assertElement(dot, `${status} status dot`);
      const styles = getComputedStyle(node);
      const dotStyles = getComputedStyle(dot);
      state[status] = {
        borderColor: styles.borderColor,
        backgroundColor: styles.backgroundColor,
        boxShadow: styles.boxShadow,
        dotBackgroundColor: dotStyles.backgroundColor,
        dotBoxShadow: dotStyles.boxShadow,
      };
    }
    return state;

    function assertElement(value, label) {
      if (!(value instanceof Element)) throw new Error(`Missing ${label}`);
    }
  });
}

function assertInside(inner, outer, label) {
  assert.ok(
    inner.x >= outer.x &&
      inner.y >= outer.y &&
      inner.x + inner.width <= outer.x + outer.width &&
      inner.y + inner.height <= outer.y + outer.height,
    `${label} must be visible in the initial graph viewport`,
  );
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
  const recentEpochMilliseconds = Math.floor(Date.now() / 1000) * 1000;
  const recentEpochSeconds = recentEpochMilliseconds / 1000;
  const recentIsoTime = new Date(recentEpochMilliseconds).toISOString();
  const recentClockLabel = formatSmokeTimestamp(recentEpochMilliseconds);
  const generatedNodeId = `auto-${Buffer.from('publisher_projection').toString('hex')}`;
  const persona = {
    ...structuredClone(compact),
    flowId: 'auto-operational',
    scopeId: 'persona:ui',
    runId: 'role-assignee-timestamps',
    generatedAt: recentIsoTime,
    title: 'Persona UI contract',
    nodes: [
      {
        id: generatedNodeId,
        role: 'Publisher',
        assignee: 'P5',
        layer: 0,
        status: 'running',
        task: 'Publisher Projection',
        generation: 1,
      },
      {
        id: 'authored-review',
        role: 'Review',
        assignee: 'P5',
        layer: 1,
        status: 'pending',
        task: 'Check authored decision quality',
        generation: 1,
      },
    ],
    edges: [
      {
        id: 'publisher-to-review',
        source: generatedNodeId,
        target: 'authored-review',
        kind: 'forward',
        status: 'active',
      },
    ],
    events: [
      {
        id: 'epoch-seconds-event',
        at: recentEpochSeconds,
        nodeId: generatedNodeId,
        message: 'Epoch seconds event',
      },
      {
        id: 'epoch-milliseconds-event',
        at: recentEpochMilliseconds,
        nodeId: 'authored-review',
        message: 'Epoch milliseconds event',
      },
      {
        id: 'iso-event',
        at: recentIsoTime,
        nodeId: 'authored-review',
        message: 'ISO event',
      },
    ],
  };
  const customPersona = {
    ...structuredClone(persona),
    flowId: 'authored-custom',
    scopeId: 'persona:custom',
    runId: 'authored-auto-id',
    generatedAt: new Date(recentEpochMilliseconds - 1000).toISOString(),
    title: 'Authored auto ID contract',
    nodes: [
      {
        id: generatedNodeId,
        role: 'Publisher',
        assignee: 'P5',
        layer: 0,
        status: 'running',
        task: 'Publisher Projection',
        generation: 1,
      },
    ],
    edges: [],
    events: [],
  };
  await postSnapshot(baseUrl, compact);
  await postSnapshot(baseUrl, customPersona);
  await postSnapshot(baseUrl, persona);
  const atTimelineSnapshot = structuredClone(branched);
  atTimelineSnapshot.events = [
    {
      id: 'old-at-event',
      at: newAtEventTime,
      nodeId: 'implementation-a',
      type: 'lane_done',
      message: 'Older at event',
    },
    {
      id: 'new-at-event',
      at: newAtEventTime,
      nodeId: 'correction-owner',
      type: 'retry',
      message: 'Newest at event',
    },
  ];
  await postSnapshot(baseUrl, atTimelineSnapshot);

  const missingSelection = {
    scopeId: 'portfolio:missing',
    runId: 'unknown-run',
  };
  await page.goto(
    `${baseUrl}/?${new URLSearchParams(missingSelection).toString()}`,
  );
  await page
    .locator('[data-testid="empty-state"]')
    .getByText('Graph not found')
    .waitFor();
  assert.equal(await page.locator('[data-testid="role-node"]').count(), 0);
  const missingUrl = new URL(page.url());
  assert.equal(missingUrl.searchParams.get('scopeId'), missingSelection.scopeId);
  assert.equal(missingUrl.searchParams.get('runId'), missingSelection.runId);

  await page.goto(baseUrl);
  await waitForNodeCount(page, persona.nodes.length);

  const selector = page.locator('[data-testid="graph-selector"]');
  await selector.selectOption(
    new URLSearchParams({
      scopeId: compact.scopeId,
      runId: compact.runId,
    }).toString(),
  );
  await waitForNodeCount(page, compact.nodes.length);
  assert.equal(await page.locator('[data-testid="feedback-edge"]').count(), 0);
  const compactPanel = await page.locator('.graph-panel').boundingBox();
  assert.ok(compactPanel);
  for (const node of compact.nodes) {
    assertInside(await nodeBox(page, node.id), compactPanel, `Compact ${node.role}`);
  }

  await page.reload();
  await waitForNodeCount(page, compact.nodes.length);

  await selector.selectOption(
    new URLSearchParams({
      scopeId: customPersona.scopeId,
      runId: customPersona.runId,
    }).toString(),
  );
  await waitForNodeCount(page, customPersona.nodes.length);
  const authoredAutoNode = page.locator(`[data-node-id="${generatedNodeId}"]`);
  assert.equal(await authoredAutoNode.locator('.role-task').count(), 1);
  assert.equal(await authoredAutoNode.locator('.role-id').count(), 1);
  assert.equal(
    await authoredAutoNode.locator('.role-task').textContent(),
    'Publisher Projection',
  );
  assert.equal(
    await authoredAutoNode.locator('.role-id').textContent(),
    generatedNodeId,
  );

  await selector.selectOption(
    new URLSearchParams({
      scopeId: persona.scopeId,
      runId: persona.runId,
    }).toString(),
  );
  await waitForNodeCount(page, persona.nodes.length);
  const generatedNode = page.locator(`[data-node-id="${generatedNodeId}"]`);
  const authoredNode = page.locator('[data-node-id="authored-review"]');
  assert.equal(await generatedNode.locator('h3').textContent(), 'Publisher');
  assert.equal(await authoredNode.locator('h3').textContent(), 'Review');
  assert.equal(await generatedNode.locator('.assignee-chip').textContent(), 'P5');
  assert.equal(await authoredNode.locator('.assignee-chip').textContent(), 'P5');
  assert.equal(await generatedNode.locator('.role-task').count(), 0);
  assert.equal(await generatedNode.locator('.role-id').count(), 0);
  assert.equal(
    await authoredNode.locator('.role-task').textContent(),
    'Check authored decision quality',
  );
  assert.equal(await authoredNode.locator('.role-id').textContent(), 'authored-review');
  const generatedNodeText = await generatedNode.innerText();
  assert.ok(!generatedNodeText.includes(generatedNodeId));
  assert.ok(!generatedNodeText.includes('Publisher Projection'));
  const personaText = await page.locator('.viewer-layout').innerText();
  assert.ok(!personaText.includes(String(recentEpochSeconds)));
  assert.ok(!personaText.includes(String(recentEpochMilliseconds)));
  const personaTimelineMeta = await page
    .locator('.timeline-item small')
    .allTextContents();
  assert.equal(personaTimelineMeta.length, 3);
  assert.ok(
    personaTimelineMeta.every(value => value.includes(recentClockLabel)),
    `All timestamp forms must render as ${recentClockLabel}: ${personaTimelineMeta.join(', ')}`,
  );
  await page.locator('.snapshot-time').getByText(recentClockLabel).waitFor();

  await selector.selectOption(
    new URLSearchParams({
      scopeId: branched.scopeId,
      runId: branched.runId,
    }).toString(),
  );
  await waitForNodeCount(page, branched.nodes.length);
  await page.evaluate(
    () =>
      new Promise(resolve =>
        requestAnimationFrame(() => requestAnimationFrame(resolve)),
      ),
  );

  const readability = await viewportReadability(page, 'orchestration');
  console.log(`Initial 11-role React Flow scale: ${readability.scale.toFixed(3)}`);
  assert.ok(
    readability.roleTitle >= 12,
    `Role title effective size ${readability.roleTitle.toFixed(2)}px is below 12px`,
  );
  assert.ok(
    readability.task >= 10,
    `Task effective size ${readability.task.toFixed(2)}px is below 10px`,
  );
  assert.ok(
    readability.status >= 8,
    `Status effective size ${readability.status.toFixed(2)}px is below 8px`,
  );

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
  const graphPanel = await page.locator('.graph-panel').boundingBox();
  assert.ok(graphPanel);
  assertInside(orchestratorBox, graphPanel, 'Orchestration role');
  await page.locator('.failure-summary').waitFor();
  assert.equal(await page.locator('.react-flow__controls-zoomin').count(), 1);
  assert.equal(await page.locator('.react-flow__controls-zoomout').count(), 1);
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
  const firstTimelineItem = page.locator('.timeline-item').first();
  await expectTimelineText(firstTimelineItem, 'Newest at event');
  await expectTimelineText(firstTimelineItem, newAtEventLabel);
  await expectTimelineText(page.locator('.timeline-item').nth(1), 'Older at event');
  await expectTimelineText(page.locator('.timeline-item').nth(1), newAtEventLabel);
  const timelineMessages = await page
    .locator('.timeline-item p')
    .evaluateAll(items => items.map(item => item.textContent?.trim()));
  assert.deepEqual(timelineMessages.slice(0, 2), [
    'Newest at event',
    'Older at event',
  ]);
  const statusStyles = await statusVisualState(page);
  assert.notEqual(
    statusStyles.passed.borderColor,
    statusStyles.running.borderColor,
    'Passed nodes must not use active running border color',
  );
  assert.notEqual(
    statusStyles.passed.dotBackgroundColor,
    statusStyles.running.dotBackgroundColor,
    'Passed nodes must not use active running dot color',
  );
  assert.notEqual(
    statusStyles.retrying.dotBackgroundColor,
    statusStyles.running.dotBackgroundColor,
    'Retrying and running nodes must remain visually distinct',
  );
  assert.notEqual(
    statusStyles.running.dotBoxShadow,
    'none',
    'Running nodes must keep an active glow',
  );
  assert.notEqual(
    statusStyles.retrying.dotBoxShadow,
    'none',
    'Retrying nodes must keep an active glow',
  );
  assert.equal(
    statusStyles.passed.dotBoxShadow,
    'none',
    'Passed nodes must not use active glow',
  );
  assert.notEqual(
    statusStyles.pending.backgroundColor,
    statusStyles.running.backgroundColor,
    'Pending nodes must look visually inactive',
  );
  assert.notEqual(
    statusStyles.failed.borderColor,
    statusStyles.running.borderColor,
    'Failed nodes must not use active running border color',
  );
  const forwardPaths = await page
    .locator('.forward-edge .react-flow__edge-path')
    .evaluateAll(paths => paths.map(path => path.getAttribute('d') || ''));
  assert.ok(forwardPaths.length > 0);
  assert.ok(
    forwardPaths.every(
      path => !/[CQ]/.test(path) && (path.match(/L/g) || []).length === 1,
    ),
    'Every forward edge must remain a single straight segment',
  );
  const feedbackBox = await page
    .locator('[data-testid="feedback-edge"]')
    .boundingBox();
  assert.ok(feedbackBox);
  const rightmostNode = Math.max(
    ...[...otherBoxes, orchestratorBox].map(box => box.x + box.width),
  );
  assert.ok(feedbackBox.x + feedbackBox.width > rightmostNode);

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

async function expectTimelineText(locator, text) {
  await locator.getByText(text).waitFor();
}

function formatSmokeTimestamp(value) {
  return new Intl.DateTimeFormat(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(typeof value === 'number' ? value : Date.parse(value));
}
