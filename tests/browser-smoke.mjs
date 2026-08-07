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

async function postPresence(baseUrl, presence) {
  const response = await fetch(`${baseUrl}/api/presence`, {
    method: 'POST',
    headers: {'content-type': 'application/json'},
    body: JSON.stringify(presence),
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

async function responsiveVisualMetrics(page) {
  return page.evaluate(() => {
    const graphPanel = required('.graph-panel');
    const canvas = required('.react-flow');
    const viewport = required('.react-flow__viewport');
    const timelinePanel = required('.timeline-panel');
    const timelineList = required('.timeline-list');
    const graphMeta = required('.graph-meta');
    const relationshipNotice = document.querySelector('.relationship-notice');
    const transform = new DOMMatrixReadOnly(getComputedStyle(viewport).transform);
    const scale = Math.abs(transform.a);
    const bounds = element => {
      const rect = element.getBoundingClientRect();
      return {
        left: rect.left,
        right: rect.right,
        top: rect.top,
        bottom: rect.bottom,
        width: rect.width,
        height: rect.height,
      };
    };
    const nodes = [...document.querySelectorAll('[data-testid="role-node"]')];
    const timelineRows = [...document.querySelectorAll('.timeline-item')];

    return {
      viewportWidth: window.innerWidth,
      documentHeight: document.documentElement.scrollHeight,
      documentWidth: document.documentElement.scrollWidth,
      bodyWidth: document.body.scrollWidth,
      graphPanel: bounds(graphPanel),
      canvas: bounds(canvas),
      timelinePanel: bounds(timelinePanel),
      nodeBounds: nodes.map(node => bounds(node)),
      nodePositions: Object.fromEntries(
        nodes.map(node => [node.getAttribute('data-node-id'), bounds(node)]),
      ),
      roleTitleSizes: nodes.map(node => {
        const title = required('h3', node);
        return Number.parseFloat(getComputedStyle(title).fontSize) * scale;
      }),
      roleTitlesContained: nodes.every(node => {
        const title = required('h3', node);
        return (
          title.scrollWidth <= title.clientWidth + 1 &&
          title.scrollHeight <= title.clientHeight + 1
        );
      }),
      assigneeSizes: nodes.map(node => {
        const assignee = required('.assignee-chip', node);
        return Number.parseFloat(getComputedStyle(assignee).fontSize) * scale;
      }),
      statusSizes: nodes.map(node => {
        const status = required('.role-status', node);
        return Number.parseFloat(getComputedStyle(status).fontSize) * scale;
      }),
      assigneesContained: nodes.every(node => {
        const assignee = required('.assignee-chip', node);
        return (
          assignee.scrollWidth <= assignee.clientWidth + 1 &&
          assignee.scrollHeight <= assignee.clientHeight + 1
        );
      }),
      overlayOverlap: relationshipNotice
        ? overlapArea(bounds(graphMeta), bounds(relationshipNotice))
        : 0,
      timelineScrolls:
        timelineList.scrollHeight > timelineList.clientHeight + 1,
      timelineRowsContained: timelineRows.every(row => {
        const content = required(':scope > div:last-child', row);
        const metadata = required('small', row);
        return (
          content.scrollWidth <= content.clientWidth + 1 &&
          metadata.scrollWidth <= metadata.clientWidth + 1 &&
          bounds(metadata).right <= bounds(timelinePanel).right + 1
        );
      }),
    };

    function required(selector, root = document) {
      const element = root.querySelector(selector);
      if (!(element instanceof Element)) throw new Error(`Missing ${selector}`);
      return element;
    }

    function overlapArea(left, right) {
      return (
        Math.max(0, Math.min(left.right, right.right) - Math.max(left.left, right.left)) *
        Math.max(0, Math.min(left.bottom, right.bottom) - Math.max(left.top, right.top))
      );
    }
  });
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

async function selectedOptionLayout(page) {
  return page.locator('[data-testid="graph-selector"]').evaluate(select => {
    const styles = getComputedStyle(select);
    const context = document.createElement('canvas').getContext('2d');
    if (!context) throw new Error('Missing canvas text measurement context');
    context.font = `${styles.fontWeight} ${styles.fontSize} ${styles.fontFamily}`;
    const selectedLabel = select.selectedOptions[0]?.textContent?.trim() ?? '';
    const contentWidth =
      select.clientWidth -
      Number.parseFloat(styles.paddingLeft) -
      Number.parseFloat(styles.paddingRight);
    const bounds = element => {
      const rect = element.getBoundingClientRect();
      return {left: rect.left, right: rect.right};
    };
    const header = document.querySelector('.viewer-header');
    const controls = document.querySelector('.viewer-controls');
    if (!header || !controls) throw new Error('Missing viewer header controls');

    return {
      selectedLabel,
      textWidth: context.measureText(selectedLabel).width,
      contentWidth,
      viewportWidth: window.innerWidth,
      header: bounds(header),
      controls: bounds(controls),
      select: bounds(select),
    };
  });
}

const temporaryDirectory = await mkdtemp(
  path.join(os.tmpdir(), 'role-graph-browser-smoke-'),
);
const dataFile = path.join(temporaryDirectory, 'snapshots.jsonl');
const port = await reservePort();
const baseUrl = `http://127.0.0.1:${port}`;
const runtimeFingerprint = 'browser-smoke-runtime';
const serverProcess = spawn(
  process.execPath,
  [
    'server.js',
    '--port',
    String(port),
    '--runtime-fingerprint',
    runtimeFingerprint,
  ],
  {
    cwd: repositoryRoot,
    env: {
      ...process.env,
      HOST: '127.0.0.1',
      PORT: String(port),
      ROLE_GRAPH_DATA_FILE: dataFile,
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  },
);
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
  const healthResponse = await fetch(`${baseUrl}/api/health`);
  assert.equal(healthResponse.status, 200);
  const health = await healthResponse.json();
  assert.equal(health.runtimeFingerprint, runtimeFingerprint);
  browser = await chromium.launch({headless: true});
  const page = await browser.newPage({viewport: {width: 1440, height: 1000}});

  await page.goto(baseUrl);
  await page.locator('[data-testid="empty-state"]').waitFor();

  const compact = await readFixture('compact.json');
  const branched = await readFixture('branched-loop.json');
  compact.spaceName = 'car-edge';
  compact.shortName = 'current';
  compact.title = 'Herdr standard delivery';
  branched.spaceName = 'herdr-orchestrator';
  branched.title = 'Herdr graph viewer hardening';
  const recentEpochMilliseconds = Math.floor(Date.now() / 1000) * 1000;
  const recentEpochSeconds = recentEpochMilliseconds / 1000;
  const recentIsoTime = new Date(recentEpochMilliseconds).toISOString();
  const recentClockLabel = formatSmokeTimestamp(recentEpochMilliseconds);
  const generatedNodeId = `auto-${Buffer.from('publisher_projection').toString('hex')}`;
  const opaqueNodeId = 'publisher-runtime';
  const opaqueNodeTask = 'Coordinate publisher runtime';
  const persona = {
    ...structuredClone(compact),
    flowId: 'auto-operational',
    spaceName: undefined,
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
        id: opaqueNodeId,
        role: 'Review',
        assignee: 'P5',
        layer: 1,
        status: 'pending',
        task: opaqueNodeTask,
        generation: 1,
      },
    ],
    // Observed topology proves no fabricated relationships.
    edges: [],
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
        nodeId: opaqueNodeId,
        message: 'Epoch milliseconds event',
      },
      {
        id: 'iso-event',
        at: recentIsoTime,
        nodeId: opaqueNodeId,
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
      {
        id: opaqueNodeId,
        role: 'Review',
        assignee: 'P5',
        layer: 1,
        status: 'pending',
        task: opaqueNodeTask,
        generation: 1,
      },
    ],
    edges: [],
    events: [],
  };
  const mobileAssigneeFit = {
    ...structuredClone(persona),
    flowId: 'auto-operational',
    scopeId: 'herdr:wK',
    runId: 'mobile-assignee-fit',
    title: 'Mobile assignee fit',
    nodes: [
      {
        id: 'mobile-p1',
        role: 'Orchestrator',
        assignee: 'codex',
        layer: 0,
        status: 'running',
        task: 'Coordinate the current session',
        generation: 1,
      },
      {
        id: 'mobile-review',
        role: 'Independent Review',
        assignee: 'Unassigned',
        layer: 1,
        status: 'pending',
        task: 'Review the integrated candidate',
        generation: 1,
      },
    ],
    edges: [],
    events: [],
  };
  const selectorLayout = {
    ...structuredClone(compact),
    spaceName: 'herdr-orchestrator',
    shortName: undefined,
    scopeId: 'herdr:wK',
    runId: 'herdr-graph-viewer-space-selector-20260802',
    generatedAt: new Date(recentEpochMilliseconds - 2000).toISOString(),
    title:
      'Auto operational view — herdr-graph-viewer-space-selector-20260802',
  };
  selectorLayout.nodes[0] = {
    ...selectorLayout.nodes[0],
    assignee: 'P1',
    status: 'passed',
  };
  const activeHerdr = {
    ...structuredClone(compact),
    spaceName: 'herdr-orchestrator',
    scopeId: 'herdr:wK',
    runId: '019fc17a-c793-7cd3-8f0d-113ac80ae6ff',
    generatedAt: recentIsoTime,
    title: 'Current Herdr orchestration',
  };
  const selectorCollisions = [
    'functional-qc-custom-g1-fixture',
    'functional-qc-manifestless-g1-fixture',
  ].map((runId, index) => ({
    ...structuredClone(compact),
    spaceName: 'herdr-orchestrator',
    shortName: 'g1-fixture',
    scopeId: 'herdr:wK',
    runId,
    generatedAt: new Date(recentEpochMilliseconds - 4000 - index * 1000).toISOString(),
    title: `Selector collision ${index + 1}`,
    nodes: compact.nodes.map(node => ({...node, status: 'pending'})),
  }));
  const scopeCollisions = ['herdr:wK', 'archive:wK'].map((scopeId, index) => ({
    ...structuredClone(compact),
    spaceName: 'herdr-orchestrator',
    shortName: 'same-run',
    scopeId,
    runId: 'same-run',
    generatedAt: new Date(recentEpochMilliseconds - 6000 - index * 1000).toISOString(),
    title: `Scope collision ${index + 1}`,
    nodes: compact.nodes.map(node => ({...node, status: 'pending'})),
  }));
  const liveDensityNodeIds = Array.from(
    {length: 9},
    (_, index) => `019fd-live-session-${String(index + 1).padStart(2, '0')}-opaque`,
  );
  const liveDensityRoles = [
    'p1_orchestrator',
    'p2_impl',
    'p3_impl',
    'p4_impl',
    'p5_integration',
    'p6_review',
    'p7_qc',
    'p8_design',
    'p9_persona',
  ];
  const liveDensity = {
    ...structuredClone(compact),
    flowId: 'live-session',
    spaceName: 'herdr-orchestrator',
    shortName: 'current',
    scopeId: 'herdr:wK',
    runId: '019fb24f-f36f-7642-8679-5c6405fb3889',
    sequence: 187,
    generatedAt: recentIsoTime,
    title: 'Current Herdr workspace',
    nodes: liveDensityRoles.map((role, index) => ({
      id: liveDensityNodeIds[index],
      role,
      assignee: `${role}_live_agent_generation_two_with_long_dynamic_name`,
      layer: index === 0 ? 0 : 1,
      status: index === 0 || index === 3 ? 'running' : 'pending',
      task: 'Participate in the current observed Herdr session',
      generation: 2,
    })),
    edges: [],
    events: Array.from({length: 12}, (_, index) => ({
      id: `live-density-event-${index + 1}`,
      at: recentIsoTime,
      nodeId: liveDensityNodeIds[index % liveDensityNodeIds.length],
      message: `Observed lifecycle event ${index + 1}`,
    })),
  };
  const eventBackedLiveness = {
    ...structuredClone(compact),
    flowId: 'live-session',
    relationshipMode: 'event-backed',
    spaceName: 'herdr-orchestrator',
    shortName: 'event-backed',
    scopeId: 'herdr:wK',
    runId: 'event-backed-liveness',
    generatedAt: recentIsoTime,
    title: 'Event-backed liveness',
    nodes: [
      {
        id: 'orchestrator',
        role: 'p1_orchestrator',
        assignee: 'p1_orchestrator_wk',
        layer: 0,
        status: 'passed',
        liveness: 'running',
        lastActivityAt: recentIsoTime,
        task: 'Route current work',
        generation: 1,
      },
      {
        id: 'implementation-ui:g1',
        role: 'p2_impl',
        assignee: 'p2_impl_wk',
        layer: 1,
        status: 'passed',
        liveness: 'offline',
        result: 'pass',
        lastActivityAt: recentIsoTime,
        task: 'Implement protocol',
        generation: 1,
      },
      {
        id: 'implementation-visual:g2',
        role: 'p4_impl',
        assignee: 'p4_impl_wk',
        layer: 1,
        status: 'retrying',
        liveness: 'running',
        result: 'rework',
        lastActivityAt: recentIsoTime,
        task: 'Repair visual finding',
        generation: 2,
      },
      {
        id: 'implementation-launcher:g1',
        role: 'p3_impl',
        assignee: 'p3_impl_wk',
        layer: 1,
        status: 'passed',
        liveness: 'offline',
        result: 'pass',
        lastActivityAt: recentIsoTime,
        task: 'Implement launcher',
        generation: 1,
      },
      {
        id: 'integration:g1',
        role: 'p5_integration',
        assignee: 'p5_integration_wk',
        layer: 2,
        status: 'passed',
        liveness: 'offline',
        result: 'pass',
        lastActivityAt: recentIsoTime,
        task: 'Integrate artifacts',
        generation: 1,
      },
      {
        id: 'independent-qc:g1',
        role: 'p6_review',
        assignee: 'p6_review_wk',
        layer: 2,
        status: 'failed',
        liveness: 'offline',
        result: 'fail',
        lastActivityAt: recentIsoTime,
        task: 'Review candidate',
        generation: 1,
      },
    ],
    edges: [
      {
        id: 'control-p1-p4',
        source: 'orchestrator',
        target: 'implementation-visual:g2',
        kind: 'control',
        status: 'active',
        occurrenceCount: 1,
        lastEventAt: new Date(recentEpochMilliseconds - 3000).toISOString(),
        reason: 'Current remediation owner',
      },
      ...[
        ['implementation-ui:g1', 'passed'],
        ['implementation-launcher:g1', 'passed'],
        ['implementation-visual:g2', 'active'],
      ].map(([source, status], index) => ({
        id: `${source}-to-integration`,
        source,
        target: 'integration:g1',
        kind: 'forward',
        status,
        occurrenceCount: index + 1,
        lastEventAt: new Date(
          recentEpochMilliseconds - (2000 - index * 500),
        ).toISOString(),
        reason: 'Artifact handoff',
      })),
      {
        id: 'integration-to-qc',
        source: 'integration:g1',
        target: 'independent-qc:g1',
        kind: 'forward',
        status: 'passed',
        occurrenceCount: 1,
        lastEventAt: new Date(recentEpochMilliseconds - 500).toISOString(),
        reason: 'Candidate handoff',
      },
      {
        id: 'qc-return-to-p4',
        source: 'independent-qc:g1',
        target: 'implementation-visual:g2',
        kind: 'return',
        status: 'active',
        occurrenceCount: 1,
        lastEventAt: recentIsoTime,
        reason: 'Responsive containment finding',
      },
    ],
    events: [
      {
        id: 'dispatch-p4',
        at: new Date(recentEpochMilliseconds - 2000).toISOString(),
        nodeId: 'implementation-visual:g2',
        message: 'Dispatch P4',
      },
      {
        id: 'handoff-p5',
        at: new Date(recentEpochMilliseconds - 1000).toISOString(),
        nodeId: 'integration:g1',
        message: 'P4 handoff P5',
      },
      {
        id: 'finding-p4',
        at: recentIsoTime,
        nodeId: 'implementation-visual:g2',
        message: 'P6 finding P4',
      },
    ],
    telemetry: {
      status: 'degraded',
      lastValidAt: recentIsoTime,
      reason: 'Malformed journal tail',
    },
  };
  const eventBackedEmpty = {
    ...structuredClone(eventBackedLiveness),
    shortName: 'event-empty',
    runId: 'event-backed-empty',
    title: 'Event-backed empty relationships',
    edges: [],
    events: [],
    telemetry: undefined,
  };
  const historyHardening = {
    ...structuredClone(branched),
    spaceName: undefined,
    scopeId: 'herdr:wK',
    runId: 'herdr-graph-viewer-hardening-20260801',
    generatedAt: new Date(recentEpochMilliseconds - 3000).toISOString(),
  };
  historyHardening.nodes = historyHardening.nodes.map(node =>
    node.assignee === 'P1' ? {...node, status: 'passed'} : node,
  );
  const expiringPresence = {
    ...structuredClone(selectorLayout),
    shortName: 'expiring',
    runId: 'dynamic-expiring-presence',
    generatedAt: new Date(recentEpochMilliseconds + 1000).toISOString(),
    title: 'Expiring presence transition',
  };
  const arrivingPresence = {
    ...structuredClone(selectorLayout),
    shortName: 'arrival',
    runId: 'dynamic-arriving-presence',
    generatedAt: new Date(recentEpochMilliseconds + 2000).toISOString(),
    title: 'Arriving presence transition',
  };
  await postSnapshot(baseUrl, compact);
  await postSnapshot(baseUrl, activeHerdr);
  await postSnapshot(baseUrl, customPersona);
  await postSnapshot(baseUrl, persona);
  await postSnapshot(baseUrl, mobileAssigneeFit);
  await postSnapshot(baseUrl, selectorLayout);
  await postSnapshot(baseUrl, historyHardening);
  for (const collision of selectorCollisions) await postSnapshot(baseUrl, collision);
  for (const collision of scopeCollisions) await postSnapshot(baseUrl, collision);
  await postSnapshot(baseUrl, liveDensity);
  await postSnapshot(baseUrl, eventBackedLiveness);
  await postSnapshot(baseUrl, eventBackedEmpty);
  await postSnapshot(baseUrl, expiringPresence);
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
  await postPresence(baseUrl, {
    scopeId: compact.scopeId,
    runId: compact.runId,
    spaceName: 'car-edge',
    shortName: 'current',
  });
  await postPresence(baseUrl, {
    scopeId: activeHerdr.scopeId,
    runId: activeHerdr.runId,
    spaceName: 'herdr-orchestrator',
    shortName: 'current',
  });

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

  await postPresence(baseUrl, {
    scopeId: expiringPresence.scopeId,
    runId: expiringPresence.runId,
    spaceName: expiringPresence.spaceName,
    shortName: expiringPresence.shortName,
  });
  await page.goto(baseUrl);
  await waitForNodeCount(page, expiringPresence.nodes.length);

  const selector = page.locator('[data-testid="graph-selector"]');
  const optionLabels = await selector.locator('option').allTextContents();
  assert.deepEqual(
    await selector
      .locator('optgroup')
      .evaluateAll(groups => groups.map(group => group.label)),
    ['Active', 'History'],
  );
  for (const label of [
    'LIVE · car-edge · current',
    'LIVE · herdr-orchestrator · current',
    'DONE · herdr-orchestrator · space-selector',
    'DONE · herdr-orchestrator · viewer-hardening',
  ]) {
    assert.ok(optionLabels.includes(label), `Missing selector option: ${label}`);
  }
  const activeHerdrValue = new URLSearchParams({
    scopeId: activeHerdr.scopeId,
    runId: activeHerdr.runId,
  }).toString();
  await selector.selectOption(activeHerdrValue);
  await waitForNodeCount(page, activeHerdr.nodes.length);
  const selectedUrl = page.url();

  await postSnapshot(baseUrl, arrivingPresence);
  await postPresence(baseUrl, {
    scopeId: arrivingPresence.scopeId,
    runId: arrivingPresence.runId,
    spaceName: arrivingPresence.spaceName,
    shortName: arrivingPresence.shortName,
  });
  const transitions = await Promise.allSettled([
    page.waitForFunction(
      label =>
        [...document.querySelectorAll('optgroup[label="Active"] option')].some(
          option => option.textContent?.trim() === label,
        ),
      'LIVE · herdr-orchestrator · arrival',
      {timeout: 10_000},
    ),
    page.waitForFunction(
      label =>
        [...document.querySelectorAll('optgroup[label="History"] option')].some(
          option => option.textContent?.trim() === label,
        ),
      'DONE · herdr-orchestrator · expiring',
      {timeout: 10_000},
    ),
  ]);
  assert.deepEqual(
    transitions.map(result => result.status),
    ['fulfilled', 'fulfilled'],
    'An open viewer must refresh arrival and expiry presence transitions',
  );
  assert.equal(await selector.inputValue(), activeHerdrValue);
  assert.equal(page.url(), selectedUrl);
  await selector.selectOption(
    new URLSearchParams({
      scopeId: selectorLayout.scopeId,
      runId: selectorLayout.runId,
    }).toString(),
  );
  await waitForNodeCount(page, selectorLayout.nodes.length);
  const selectorLayoutMetrics = await selectedOptionLayout(page);
  assert.equal(
    selectorLayoutMetrics.selectedLabel,
    'DONE · herdr-orchestrator · space-selector',
  );
  assert.ok(
    selectorLayoutMetrics.textWidth <= selectorLayoutMetrics.contentWidth,
    `Selected label needs ${selectorLayoutMetrics.textWidth.toFixed(2)}px but only ${selectorLayoutMetrics.contentWidth.toFixed(2)}px is available`,
  );
  for (const [name, bounds] of Object.entries({
    header: selectorLayoutMetrics.header,
    controls: selectorLayoutMetrics.controls,
    select: selectorLayoutMetrics.select,
  })) {
    assert.ok(
      bounds.left >= 0 && bounds.right <= selectorLayoutMetrics.viewportWidth,
      `${name} must remain inside the desktop viewport`,
    );
  }
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
  const authoredOpaqueNode = page.locator(`[data-node-id="${opaqueNodeId}"]`);
  assert.equal(
    await authoredOpaqueNode.locator('.role-task').textContent(),
    opaqueNodeTask,
  );
  assert.equal(
    await authoredOpaqueNode.locator('.role-id').textContent(),
    opaqueNodeId,
  );

  await selector.selectOption(
    new URLSearchParams({
      scopeId: persona.scopeId,
      runId: persona.runId,
    }).toString(),
  );
  await waitForNodeCount(page, persona.nodes.length);
  // Observed topology draws no relationships and explains why, while still
  // surfacing timestamped lifecycle events for every current node.
  assert.equal(await page.locator('.forward-edge').count(), 0);
  assert.equal(await page.locator('[data-testid="feedback-edge"]').count(), 0);
  await page.getByTestId('relationship-notice').waitFor();
  assert.match(
    await page.getByTestId('relationship-notice').innerText(),
    /relationships unavailable/i,
  );
  assert.ok(await page.locator('.timeline-item').count() > 0);
  const generatedNode = page.locator(`[data-node-id="${generatedNodeId}"]`);
  const opaqueNode = page.locator(`[data-node-id="${opaqueNodeId}"]`);
  assert.equal(await generatedNode.locator('h3').textContent(), 'Publisher');
  assert.equal(await opaqueNode.locator('h3').textContent(), 'Review');
  assert.equal(await generatedNode.locator('.assignee-chip').textContent(), 'P5');
  assert.equal(await opaqueNode.locator('.assignee-chip').textContent(), 'P5');
  assert.equal(await generatedNode.locator('.role-task').count(), 0);
  assert.equal(await generatedNode.locator('.role-id').count(), 0);
  assert.equal(await opaqueNode.locator('.role-task').count(), 0);
  assert.equal(await opaqueNode.locator('.role-id').count(), 0);
  const generatedNodeText = await generatedNode.innerText();
  assert.ok(!generatedNodeText.includes(generatedNodeId));
  assert.ok(!generatedNodeText.includes('Publisher Projection'));
  const opaqueNodeText = await opaqueNode.innerText();
  assert.ok(!opaqueNodeText.includes(opaqueNodeId));
  assert.ok(!opaqueNodeText.includes(opaqueNodeTask));
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

  for (const viewport of [
    {width: 1440, height: 1000},
    {width: 1024, height: 900},
    {width: 390, height: 844},
  ]) {
    await page.setViewportSize(viewport);
    await page.goto(
      `${baseUrl}/?${new URLSearchParams({
        scopeId: eventBackedLiveness.scopeId,
        runId: eventBackedLiveness.runId,
      }).toString()}`,
    );
    await waitForNodeCount(page, eventBackedLiveness.nodes.length);
    const responsiveMetrics = await responsiveVisualMetrics(page);
    assert.ok(
      responsiveMetrics.documentWidth <= responsiveMetrics.viewportWidth &&
        responsiveMetrics.bodyWidth <= responsiveMetrics.viewportWidth,
      `${viewport.width}x${viewport.height} event-backed graph must not overflow the page`,
    );
    assert.ok(
      responsiveMetrics.graphPanel.left >= 0 &&
        responsiveMetrics.graphPanel.right <= responsiveMetrics.viewportWidth + 1 &&
        responsiveMetrics.canvas.left >= responsiveMetrics.graphPanel.left - 1 &&
        responsiveMetrics.canvas.right <= responsiveMetrics.graphPanel.right + 1,
      `${viewport.width}x${viewport.height} event-backed canvas must stay contained`,
    );

    const expectedNodes = [
      ['orchestrator', 'running', null, 'P1'],
      ['implementation-ui:g1', 'offline', 'pass', 'P2'],
      ['implementation-launcher:g1', 'offline', 'pass', 'P3'],
      ['implementation-visual:g2', 'running', 'rework', 'P4'],
      ['integration:g1', 'offline', 'pass', 'P5'],
      ['independent-qc:g1', 'offline', 'fail', 'P6'],
    ];
    for (const [nodeId, liveness, result, assignee] of expectedNodes) {
      const node = page.locator(`[data-node-id="${nodeId}"]`);
      assert.equal(await node.getAttribute('data-liveness'), liveness);
      assert.equal(await node.getAttribute('data-result'), result);
      assert.equal(await node.locator('.assignee-chip').textContent(), assignee);
      assert.equal(
        await node.locator('.liveness-badge').textContent(),
        liveness.toUpperCase(),
      );
      assert.equal(await node.locator('.result-badge').count(), result ? 1 : 0);
      if (result) {
        assert.equal(
          await node.locator('.result-badge').textContent(),
          result.toUpperCase(),
        );
      }
      const activity = node.locator('.activity-time');
      assert.equal(await activity.textContent(), 'just now');
      assert.equal(await activity.getAttribute('title'), recentIsoTime);
    }

    const p1Text = await page.locator('[data-node-id="orchestrator"]').innerText();
    assert.ok(!p1Text.includes('PASSED'));
    const badgeContainment = await page
      .locator('[data-testid="role-node"]')
      .evaluateAll(nodes =>
        nodes.flatMap(node => {
          const nodeBounds = node.getBoundingClientRect();
          return [...node.querySelectorAll('.liveness-badge, .result-badge')].map(
            badge => {
              const badgeBounds = badge.getBoundingClientRect();
              return {
                nodeId: node.getAttribute('data-node-id'),
                badge: badge.textContent,
                inside:
                badgeBounds.left >= nodeBounds.left &&
                badgeBounds.right <= nodeBounds.right &&
                badgeBounds.top >= nodeBounds.top &&
                  badgeBounds.bottom <= nodeBounds.bottom,
                nodeBounds: nodeBounds.toJSON(),
                badgeBounds: badgeBounds.toJSON(),
              };
            },
          );
        }),
      );
    assert.ok(
      badgeContainment.every(metric => metric.inside),
      `${viewport.width}x${viewport.height} liveness/result badges must remain inside cards: ${JSON.stringify(badgeContainment)}`,
    );

    if (viewport.width === 1440) {
      const positions = Object.fromEntries(
        await Promise.all(
          eventBackedLiveness.nodes.map(async node => [
            node.id,
            await nodeBox(page, node.id),
          ]),
        ),
      );
      assert.ok(
        ['implementation-ui:g1', 'implementation-launcher:g1', 'implementation-visual:g2'].every(
          nodeId => positions.orchestrator.y < positions[nodeId].y,
        ),
        'P1 must remain above all same-rank implementation workers',
      );
      const workerTops = [
        positions['implementation-ui:g1'].y,
        positions['implementation-launcher:g1'].y,
        positions['implementation-visual:g2'].y,
      ];
      assert.ok(workerTops.every(top => Math.abs(top - workerTops[0]) < 1));
      assert.ok(workerTops[0] < positions['integration:g1'].y);
      assert.ok(positions['integration:g1'].y < positions['independent-qc:g1'].y);

      assert.equal(await page.locator('.control-edge.edge-active').count(), 1);
      assert.equal(await page.locator('.control-edge.animated').count(), 1);
      const controlDash = await page
        .locator('.control-edge .react-flow__edge-path')
        .evaluate(path => getComputedStyle(path).strokeDasharray);
      assert.notEqual(controlDash, 'none');
      assert.equal(await page.locator('.forward-edge').count(), 4);
      assert.equal(await page.locator('.forward-edge.edge-passed.animated').count(), 0);
      const artifactPaths = await page
        .locator('.forward-edge .react-flow__edge-path')
        .evaluateAll(paths => paths.map(path => path.getAttribute('d') || ''));
      assert.ok(
        artifactPaths.every(
          path => !/[CQ]/.test(path) && (path.match(/L/g) || []).length === 1,
        ),
      );
      assert.equal(await page.locator('[data-testid="feedback-edge"]').count(), 1);
      const feedbackBox = await page
        .locator('[data-testid="feedback-edge"]')
        .boundingBox();
      assert.ok(feedbackBox);
      const rightmostNode = Math.max(
        ...Object.values(positions).map(box => box.x + box.width),
      );
      assert.ok(feedbackBox.x + feedbackBox.width > rightmostNode);
      assert.equal(await page.locator('.p1-star').count(), 0);

      const timelineMessages = await page
        .locator('.timeline-item p')
        .allTextContents();
      assert.deepEqual(timelineMessages, [
        'Dispatch P4',
        'P4 handoff P5',
        'P6 finding P4',
      ]);
      assert.deepEqual(
        await page.locator('.timeline-item small').allTextContents(),
        eventBackedLiveness.events.map(
          event =>
            `${event.nodeId === 'integration:g1' ? 'P5 Integration' : 'P4 Implementation'} · ${formatSmokeTimestamp(event.at)}`,
        ),
      );
      const degraded = page.getByTestId('telemetry-degraded');
      await degraded.waitFor();
      assert.match(await degraded.innerText(), /TELEMETRY DEGRADED/i);
      assert.match(await degraded.innerText(), new RegExp(recentClockLabel));
      assert.equal(
        await page.locator('[data-testid="role-node"]').count(),
        eventBackedLiveness.nodes.length,
      );
    }
  }

  await page.goto(
    `${baseUrl}/?${new URLSearchParams({
      scopeId: eventBackedEmpty.scopeId,
      runId: eventBackedEmpty.runId,
    }).toString()}`,
  );
  await waitForNodeCount(page, eventBackedEmpty.nodes.length);
  assert.match(
    await page.getByTestId('relationship-notice').innerText(),
    /no relationship events yet/i,
  );

  await page.setViewportSize({width: 390, height: 844});
  await page.goto(
    `${baseUrl}/?${new URLSearchParams({
      scopeId: mobileAssigneeFit.scopeId,
      runId: mobileAssigneeFit.runId,
    }).toString()}`,
  );
  await waitForNodeCount(page, mobileAssigneeFit.nodes.length);
  const mobileAssigneeMetrics = await page
    .locator('[data-testid="role-node"]')
    .evaluateAll(nodes =>
      nodes.map(node => {
        const assignee = node.querySelector('.assignee-chip');
        const title = node.querySelector('h3');
        if (!(assignee instanceof HTMLElement) || !(title instanceof HTMLElement)) {
          throw new Error('Missing mobile assignee or role title');
        }
        const styles = getComputedStyle(assignee);
        const context = document.createElement('canvas').getContext('2d');
        if (!context) throw new Error('Missing mobile text measurement context');
        context.font = styles.font;
        const nodeBounds = node.getBoundingClientRect();
        const assigneeBounds = assignee.getBoundingClientRect();
        const label = assignee.textContent?.trim() ?? '';
        return {
          label,
          className: assignee.className,
          width: styles.width,
          maxWidth: styles.maxWidth,
          scrollWidth: assignee.scrollWidth,
          clientWidth: assignee.clientWidth,
          textWidth: context.measureText(label).width,
          contentWidth:
            assignee.clientWidth -
            Number.parseFloat(styles.paddingLeft) -
            Number.parseFloat(styles.paddingRight),
          insideNode:
            assigneeBounds.left >= nodeBounds.left &&
            assigneeBounds.right <= nodeBounds.right,
          titleContained:
            title.scrollWidth <= title.clientWidth &&
            title.scrollHeight <= title.clientHeight,
        };
      }),
    );
  await mkdir(artifactsDirectory, {recursive: true});
  const mobileAssigneeScreenshotPath = path.join(
    artifactsDirectory,
    'mobile-assignee-fit-390x844.png',
  );
  await page.screenshot({path: mobileAssigneeScreenshotPath, fullPage: true});
  assert.deepEqual(
    mobileAssigneeMetrics.map(metric => metric.label),
    ['codex', 'Unassigned'],
  );
  assert.ok(
    mobileAssigneeMetrics.every(
      metric =>
        metric.className.includes('assignee-chip-non-position') &&
        metric.width === '76px' &&
        metric.maxWidth === '76px',
    ),
    `390x844 non-position assignees must use the bounded chip class: ${JSON.stringify(mobileAssigneeMetrics)}`,
  );
  assert.ok(
    mobileAssigneeMetrics.every(
      metric =>
        metric.scrollWidth <= metric.clientWidth &&
        metric.textWidth <= metric.contentWidth &&
        metric.insideNode &&
        metric.titleContained,
    ),
    `390x844 assignees and role titles must visibly fit: ${JSON.stringify(mobileAssigneeMetrics)}`,
  );
  console.log(
    `390x844 mobile assignee DOM passed: ${JSON.stringify(mobileAssigneeMetrics)}`,
  );

  for (const viewport of [
    {width: 1440, height: 1000},
    {width: 1024, height: 900},
    {width: 390, height: 844},
  ]) {
    await page.setViewportSize(viewport);
    await page.goto(
      `${baseUrl}/?${new URLSearchParams({
        scopeId: liveDensity.scopeId,
        runId: liveDensity.runId,
      }).toString()}`,
    );
    await waitForNodeCount(page, liveDensity.nodes.length);
    await page.evaluate(
      () =>
        new Promise(resolve =>
          requestAnimationFrame(() => requestAnimationFrame(resolve)),
        ),
    );
    await page.waitForFunction(
      minimum => {
        const flowViewport = document.querySelector('.react-flow__viewport');
        return (
          flowViewport instanceof Element &&
          Math.abs(
            new DOMMatrixReadOnly(getComputedStyle(flowViewport).transform).a,
          ) >= minimum - 0.001
        );
      },
      viewport.width <= 620 ? 0.86 : 0.8,
      {timeout: 2_000},
    );

    const metrics = await responsiveVisualMetrics(page);
    const size = `${viewport.width}x${viewport.height}`;
    assert.ok(
      metrics.documentWidth <= metrics.viewportWidth &&
        metrics.bodyWidth <= metrics.viewportWidth,
      `${size} live-density page must not overflow horizontally`,
    );
    assert.ok(
      metrics.roleTitleSizes.every(value => value >= 12) &&
        metrics.assigneeSizes.every(value => value >= 8) &&
        metrics.statusSizes.every(value => value >= 8),
      `${size} live-density role, P, and status labels must remain readable ` +
        `(role ${Math.min(...metrics.roleTitleSizes).toFixed(2)}, ` +
        `P ${Math.min(...metrics.assigneeSizes).toFixed(2)}, ` +
        `status ${Math.min(...metrics.statusSizes).toFixed(2)})`,
    );
    assert.ok(
      metrics.roleTitlesContained && metrics.assigneesContained,
      `${size} live-density role and P labels must not clip`,
    );
    assert.equal(metrics.overlayOverlap, 0, `${size} graph metadata must not overlap the topology notice`);
    assert.ok(
      metrics.timelinePanel.height <= metrics.graphPanel.height + 1,
      `${size} timeline must not grow taller than the fixed graph`,
    );
    assert.ok(metrics.timelineScrolls, `${size} 12-event timeline must scroll independently`);
    assert.equal(await page.locator('.forward-edge').count(), 0);
    assert.equal(await page.locator('[data-testid="feedback-edge"]').count(), 0);
    await page.getByTestId('relationship-notice').waitFor();

    const p1Top = metrics.nodePositions[liveDensityNodeIds[0]].top;
    const p1Bounds = metrics.nodePositions[liveDensityNodeIds[0]];
    assert.ok(
      p1Bounds.left >= metrics.graphPanel.left - 1 &&
        p1Bounds.right <= metrics.graphPanel.right + 1,
      `${size} P1 must be visible in the initial graph hierarchy`,
    );
    const downstreamTops = liveDensityNodeIds
      .slice(1)
      .map(nodeId => metrics.nodePositions[nodeId].top);
    assert.ok(downstreamTops.every(top => p1Top < top), `${size} P1 must stay above downstream roles`);
    assert.ok(
      downstreamTops.every(top => Math.abs(top - downstreamTops[0]) < 1),
      `${size} same-rank P2-P9 roles must align`,
    );
    assert.deepEqual(
      await page.locator('.assignee-chip').allTextContents(),
      ['P1', 'P2', 'P3', 'P4', 'P5', 'P6', 'P7', 'P8', 'P9'],
    );
    const liveDensityText = await page.locator('.viewer-layout').innerText();
    assert.ok(!liveDensityText.includes('with_long_dynamic_name'));
    assert.ok(!liveDensityText.includes(liveDensityNodeIds[0]));

    const densityScreenshotPath = path.join(
      artifactsDirectory,
      `live-density-${size}.png`,
    );
    await page.screenshot({path: densityScreenshotPath, fullPage: true});
    console.log(`${size} live-density DOM passed. Screenshot: ${densityScreenshotPath}`);
  }

  const refreshedOptionLabels = await selector.locator('option').allTextContents();
  assert.equal(new Set(refreshedOptionLabels).size, refreshedOptionLabels.length);
  const collisionLabels = refreshedOptionLabels.filter(label =>
    label.includes('g1-fixture'),
  );
  assert.deepEqual(collisionLabels, [
    'PENDING · herdr-orchestrator · custom-g1-fixture',
    'PENDING · herdr-orchestrator · manifestless-g1-fixture',
  ]);
  assert.deepEqual(
    refreshedOptionLabels.filter(label => label.includes('same-run')),
    [
      'PENDING · herdr-orchestrator · same-run · herdr:wK',
      'PENDING · herdr-orchestrator · same-run · archive:wK',
    ],
  );

  await selector.selectOption(
    new URLSearchParams({
      scopeId: branched.scopeId,
      runId: branched.runId,
    }).toString(),
  );
  await waitForNodeCount(page, branched.nodes.length);
  // Declared custom topology keeps its authored relationships and shows no
  // observed-topology notice.
  assert.equal(
    await page.locator('[data-testid="relationship-notice"]').count(),
    0,
  );
  await page.evaluate(
    () =>
      new Promise(resolve =>
        requestAnimationFrame(() => requestAnimationFrame(resolve)),
      ),
  );

  await mkdir(artifactsDirectory, {recursive: true});
  for (const viewport of [
    {width: 1440, height: 1000},
    {width: 1024, height: 900},
    {width: 390, height: 844},
  ]) {
    await page.setViewportSize(viewport);
    await page.goto(
      `${baseUrl}/?${new URLSearchParams({
        scopeId: branched.scopeId,
        runId: branched.runId,
      }).toString()}`,
    );
    await waitForNodeCount(page, branched.nodes.length);
    await page.evaluate(
      () =>
        new Promise(resolve =>
          requestAnimationFrame(() => requestAnimationFrame(resolve)),
        ),
    );

    const metrics = await responsiveVisualMetrics(page);
    const size = `${viewport.width}x${viewport.height}`;
    assert.ok(
      metrics.documentWidth <= metrics.viewportWidth &&
        metrics.bodyWidth <= metrics.viewportWidth,
      `${size} page width must not overflow (${metrics.documentWidth}/${metrics.bodyWidth} > ${metrics.viewportWidth})`,
    );
    assert.ok(
      metrics.graphPanel.left >= 0 &&
        metrics.graphPanel.right <= metrics.viewportWidth + 1 &&
        metrics.canvas.left >= metrics.graphPanel.left - 1 &&
        metrics.canvas.right <= metrics.graphPanel.right + 1,
      `${size} graph panel and canvas must stay within the viewport`,
    );
    const nodesInsidePanel = metrics.nodeBounds.filter(
      node =>
        node.left >= metrics.graphPanel.left - 1 &&
        node.right <= metrics.graphPanel.right + 1 &&
        node.bottom <= metrics.graphPanel.bottom + 1,
    );
    assert.ok(
      viewport.width === 390
        ? nodesInsidePanel.length > 0
        : nodesInsidePanel.length === metrics.nodeBounds.length,
      `${size} graph must show initial nodes without clipping the page`,
    );
    assert.ok(
      metrics.roleTitleSizes.every(size => size >= 12) &&
        metrics.roleTitlesContained,
      `${size} role labels must remain fully visible at 12px or larger effective size`,
    );
    assert.ok(
      metrics.assigneeSizes.every(size => size >= 8),
      `${size} P labels must remain at least 8px effective size`,
    );
    assert.ok(
      metrics.timelinePanel.left >= 0 &&
        metrics.timelinePanel.right <= metrics.viewportWidth + 1 &&
        metrics.timelineRowsContained,
      `${size} timeline rows and timestamps must stay within the timeline panel`,
    );
    assert.equal(
      await page.locator('.forward-edge').count(),
      branched.edges.filter(edge => edge.kind === 'forward').length,
      `${size} must preserve every authored forward relationship`,
    );
    if (viewport.width === 1024) {
      const implementationTops = [
        metrics.nodePositions['implementation-a'].top,
        metrics.nodePositions['implementation-b'].top,
        metrics.nodePositions['implementation-c'].top,
      ];
      assert.ok(
        implementationTops.every(top => Math.abs(top - implementationTops[0]) < 1),
        `${size} must keep the authored parallel implementation branch on one row`,
      );
    }
    if (viewport.width === 390) {
      const implementationTops = [
        metrics.nodePositions['implementation-a'].top,
        metrics.nodePositions['implementation-b'].top,
        metrics.nodePositions['implementation-c'].top,
      ];
      assert.ok(
        implementationTops.some(
          (top, index) =>
            implementationTops.some(
              (other, otherIndex) =>
                index !== otherIndex && Math.abs(top - other) < 1,
            ),
        ),
        `${size} must retain a visible parallel branch instead of a single chain`,
      );
      const pane = page.locator('.react-flow__pane');
      const paneBox = await pane.boundingBox();
      assert.ok(paneBox);
      const transformBeforePan = await page
        .locator('.react-flow__viewport')
        .getAttribute('style');
      const panStartX = paneBox.x + 8;
      const panStartY = Math.min(
        paneBox.y + paneBox.height - 20,
        viewport.height - 20,
      );
      await page.mouse.move(panStartX, panStartY);
      await page.mouse.down();
      await page.mouse.move(panStartX + 80, panStartY, {steps: 4});
      await page.mouse.up();
      const transformAfterPan = await page
        .locator('.react-flow__viewport')
        .getAttribute('style');
      assert.notEqual(
        transformAfterPan,
        transformBeforePan,
        `${size} aligned offscreen siblings must remain reachable by panning`,
      );
    }
    const responsiveScreenshotPath = path.join(
      artifactsDirectory,
      `live-role-graph-${size}.png`,
    );
    await page.screenshot({path: responsiveScreenshotPath, fullPage: true});
    console.log(
      `${size} DOM passed (${metrics.documentWidth}px document, ${metrics.nodeBounds.length} nodes). Screenshot: ${responsiveScreenshotPath}`,
    );
  }

  await page.setViewportSize({width: 1440, height: 1000});
  await page.goto(
    `${baseUrl}/?${new URLSearchParams({
      scopeId: branched.scopeId,
      runId: branched.runId,
    }).toString()}`,
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
  await expectTimelineText(firstTimelineItem, 'Older at event');
  await expectTimelineText(firstTimelineItem, newAtEventLabel);
  await expectTimelineText(page.locator('.timeline-item').nth(1), 'Newest at event');
  await expectTimelineText(page.locator('.timeline-item').nth(1), newAtEventLabel);
  const timelineMessages = await page
    .locator('.timeline-item p')
    .evaluateAll(items => items.map(item => item.textContent?.trim()));
  assert.deepEqual(timelineMessages.slice(0, 2), [
    'Older at event',
    'Newest at event',
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
  assert.ok(
    (await selector.locator('option').allTextContents()).includes(
      'RUNNING · herdr-orchestrator · quality-loop',
    ),
  );

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
