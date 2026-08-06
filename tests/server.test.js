import {spawn, spawnSync} from 'node:child_process';
import {once} from 'node:events';
import {mkdtemp, readFile, rm} from 'node:fs/promises';
import {createServer} from 'node:net';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

import {afterEach, beforeEach, describe, expect, test} from 'vitest';

import {createApp} from '../server/app.js';

const serverEntryPoint = fileURLToPath(new URL('../server.js', import.meta.url));

function snapshot(scopeId = 'scope-a', runId = 'run-1', sequence = 1) {
  return {
    schemaVersion: 'role-graph/v1',
    scopeId,
    runId,
    sequence,
    generatedAt: `2026-07-31T10:00:${String(sequence).padStart(2, '0')}Z`,
    title: `${scopeId} ${runId}`,
    nodes: [
      {
        id: 'orchestrator',
        role: 'Orchestrator',
        assignee: 'P1',
        status: 'running',
        task: 'Route work',
        generation: 1,
      },
    ],
    edges: [],
    failurePolicies: [],
    activeFailureRoute: null,
    events: [],
  };
}

async function listen(server) {
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  const {port} = server.address();
  return `http://127.0.0.1:${port}`;
}

async function close(server) {
  if (!server?.listening) return;
  await new Promise(resolve => server.close(resolve));
}

async function availablePort() {
  const probe = createServer();
  const baseUrl = await listen(probe);
  await close(probe);
  return Number(new URL(baseUrl).port);
}

async function waitForHealth(child, baseUrl) {
  let stderr = '';
  child.stderr.on('data', chunk => {
    stderr += chunk;
  });

  for (let attempt = 0; attempt < 50; attempt += 1) {
    if (child.exitCode !== null) {
      throw new Error(`Server exited before health was ready: ${stderr}`);
    }
    try {
      const response = await fetch(`${baseUrl}/api/health`);
      if (response.ok) return response;
    } catch {
      // Wait for the child process to bind its port.
    }
    await new Promise(resolve => setTimeout(resolve, 20));
  }
  throw new Error(`Server health did not become ready: ${stderr}`);
}

function waitForExit(child, timeout = 1_000) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(
      () => reject(new Error('Server did not reject invalid CLI options')),
      timeout,
    );
    child.once('exit', (code, signal) => {
      clearTimeout(timer);
      resolve({code, signal});
    });
  });
}

async function post(baseUrl, body, headers = {}) {
  return fetch(`${baseUrl}/api/snapshots`, {
    method: 'POST',
    headers: {'content-type': 'application/json', ...headers},
    body: JSON.stringify(body),
  });
}

async function postPresence(baseUrl, body, headers = {}) {
  return fetch(`${baseUrl}/api/presence`, {
    method: 'POST',
    headers: {'content-type': 'application/json', ...headers},
    body: JSON.stringify(body),
  });
}

async function openSnapshotStream(url) {
  const controller = new AbortController();
  const response = await fetch(url, {signal: controller.signal});
  expect(response.status).toBe(200);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffered = '';

  async function nextSnapshot() {
    while (true) {
      const {done, value} = await reader.read();
      if (done) throw new Error('SSE stream ended before a snapshot arrived');
      buffered += decoder.decode(value, {stream: true});
      const boundary = buffered.indexOf('\n\n');
      if (boundary === -1) continue;
      const message = buffered.slice(0, boundary);
      buffered = buffered.slice(boundary + 2);
      const data = message
        .split('\n')
        .find(line => line.startsWith('data: '));
      if (data) return JSON.parse(data.slice(6));
    }
  }

  return {
    nextSnapshot,
    close() {
      controller.abort();
    },
  };
}

describe('role graph server', () => {
  let directory;
  let dataFile;
  let server;
  let baseUrl;
  let cliServer;

  beforeEach(async () => {
    directory = await mkdtemp(path.join(tmpdir(), 'role-graph-server-'));
    dataFile = path.join(directory, 'snapshots.jsonl');
    server = createApp({dataFile});
    baseUrl = await listen(server);
  });

  afterEach(async () => {
    if (cliServer?.exitCode === null && cliServer.signalCode === null) {
      const exited = once(cliServer, 'exit');
      cliServer.kill('SIGTERM');
      await exited;
    }
    await close(server);
    await rm(directory, {recursive: true, force: true});
  });

  test('accepts and persists a snapshot without a publisher fingerprint', async () => {
    const response = await post(baseUrl, snapshot());

    expect(response.status).toBe(202);
    expect(await response.json()).toEqual(snapshot());
  });

  test('accepts and persists a non-empty publisher fingerprint', async () => {
    const input = snapshot();
    input.publisherFingerprint = 'publisher-sha';

    const response = await post(baseUrl, input);
    const persisted = await fetch(
      `${baseUrl}/api/snapshot?scopeId=scope-a&runId=run-1`,
    );

    expect(response.status).toBe(202);
    expect(await response.json()).toEqual(input);
    expect(await persisted.json()).toEqual(input);
  });

  test('rejects an empty publisher fingerprint', async () => {
    const input = snapshot();
    input.publisherFingerprint = '';

    const response = await post(baseUrl, input);

    expect(response.status).toBe(400);
    expect((await response.json()).error).toMatch(
      /publisherFingerprint must be a non-empty string/,
    );
  });

  test('rejects a non-string publisher fingerprint', async () => {
    const input = snapshot();
    input.publisherFingerprint = 42;

    const response = await post(baseUrl, input);

    expect(response.status).toBe(400);
    expect((await response.json()).error).toMatch(
      /publisherFingerprint must be a non-empty string/,
    );
  });

  test('returns a stable viewer health identity', async () => {
    const response = await fetch(`${baseUrl}/api/health`);

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({
      service: 'herdr-role-graph-viewer',
      schemaVersion: 'role-graph/v1',
      capabilities: ['space-name-summary', 'session-presence'],
      runtimeFingerprint: 'unmanaged',
    });
  });

  test('returns the configured viewer runtime fingerprint', async () => {
    await close(server);
    server = createApp({dataFile, runtimeFingerprint: 'viewer-sha'});
    baseUrl = await listen(server);

    const response = await fetch(`${baseUrl}/api/health`);

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({
      service: 'herdr-role-graph-viewer',
      schemaVersion: 'role-graph/v1',
      capabilities: ['space-name-summary', 'session-presence'],
      runtimeFingerprint: 'viewer-sha',
    });
  });

  test('forwards explicit port and runtime fingerprint CLI options', async () => {
    const port = await availablePort();
    cliServer = spawn(
      process.execPath,
      [serverEntryPoint, '--port', String(port), '--runtime-fingerprint', 'viewer-sha'],
      {
        env: {...process.env, PORT: '0', ROLE_GRAPH_DATA_FILE: dataFile},
        stdio: ['ignore', 'pipe', 'pipe'],
      },
    );

    const response = await waitForHealth(cliServer, `http://127.0.0.1:${port}`);

    expect(await response.json()).toMatchObject({runtimeFingerprint: 'viewer-sha'});
  });

  test('rejects an invalid explicit port', () => {
    const result = spawnSync(
      process.execPath,
      [serverEntryPoint, '--port', 'not-a-port'],
      {encoding: 'utf8', timeout: 1_000},
    );

    expect(result.status).not.toBe(0);
    expect(result.stderr).toMatch(/--port/);
  });

  test('rejects an empty explicit runtime fingerprint', async () => {
    const port = await availablePort();
    let stderr = '';
    cliServer = spawn(
      process.execPath,
      [serverEntryPoint, '--port', String(port), '--runtime-fingerprint', ''],
      {stdio: ['ignore', 'pipe', 'pipe']},
    );
    cliServer.stderr.on('data', chunk => {
      stderr += chunk;
    });

    const {code} = await waitForExit(cliServer);

    expect(code).not.toBe(0);
    expect(stderr).toMatch(/--runtime-fingerprint requires a value/);
  });

  test('authenticates in-memory presence, expires it, and does not churn JSONL', async () => {
    await close(server);
    let now = 1_000;
    server = createApp({dataFile, ingestToken: 'secret', now: () => now});
    baseUrl = await listen(server);
    expect((await post(baseUrl, snapshot(), {authorization: 'Bearer secret'})).status).toBe(202);
    const before = await readFile(dataFile, 'utf8');

    expect((await postPresence(baseUrl, {scopeId: 'scope-a', runId: 'run-1'})).status).toBe(401);
    expect((await postPresence(baseUrl, {scopeId: 'scope-a', runId: 'run-1', shortName: ''}, {authorization: 'Bearer secret'})).status).toBe(400);
    expect((await postPresence(baseUrl, {scopeId: 'scope-a', runId: 'run-1', spaceName: 'herdr-orchestrator', shortName: 'current'}, {authorization: 'Bearer secret'})).status).toBe(202);
    expect((await (await fetch(`${baseUrl}/api/graphs`)).json())[0]).toMatchObject({isLive: true, shortName: 'current'});
    expect(await readFile(dataFile, 'utf8')).toBe(before);

    now += 6_001;
    expect((await (await fetch(`${baseUrl}/api/graphs`)).json())[0].isLive).toBe(false);
    expect(await readFile(dataFile, 'utf8')).toBe(before);
  });

  test('returns 400 for an invalid snapshot', async () => {
    const input = snapshot();
    input.nodes[0].status = 'working';
    const response = await post(baseUrl, input);
    const body = await response.json();

    expect(response.status).toBe(400);
    expect(body.error).toMatch(/node status/i);
  });

  test('returns 409 for a stale sequence', async () => {
    expect((await post(baseUrl, snapshot())).status).toBe(202);

    const equal = await post(baseUrl, snapshot());
    const lower = await post(baseUrl, snapshot('scope-a', 'run-1', 0));

    expect(equal.status).toBe(409);
    expect(lower.status).toBe(409);
  });

  test('accepts explicit replacement only at the exact current sequence', async () => {
    expect((await post(baseUrl, snapshot())).status).toBe(202);
    const replacement = snapshot();
    replacement.title = 'Explicit replacement';

    const equal = await post(baseUrl, replacement, {
      'x-role-graph-replace-current': 'true',
    });
    const lower = await post(baseUrl, snapshot('scope-a', 'run-1', 0), {
      'x-role-graph-replace-current': 'true',
    });

    expect(equal.status).toBe(202);
    expect(await equal.json()).toEqual(replacement);
    expect(lower.status).toBe(409);
  });

  test('lists graphs and returns only the requested snapshot key', async () => {
    const spaceSnapshot = snapshot('scope-a', 'shared-run', 1);
    spaceSnapshot.spaceName = 'herdr-orchestrator';
    await post(baseUrl, spaceSnapshot);
    await post(baseUrl, snapshot('scope-b', 'shared-run', 2));

    const graphsResponse = await fetch(`${baseUrl}/api/graphs`);
    const snapshotResponse = await fetch(
      `${baseUrl}/api/snapshot?scopeId=scope-a&runId=shared-run`,
    );

    const graphs = await graphsResponse.json();
    expect(graphs).toHaveLength(2);
    expect(
      graphs.find(graph => graph.scopeId === 'scope-a'),
    ).toMatchObject({
      spaceName: 'herdr-orchestrator',
      scopeId: 'scope-a',
      runId: 'shared-run',
    });
    expect(await snapshotResponse.json()).toMatchObject({
      scopeId: 'scope-a',
      runId: 'shared-run',
      sequence: 1,
    });
  });

  test('filters snapshot events by exact scope and run', async () => {
    const streamA = await openSnapshotStream(
      `${baseUrl}/api/stream?scopeId=scope-a&runId=shared-run`,
    );
    const streamB = await openSnapshotStream(
      `${baseUrl}/api/stream?scopeId=scope-b&runId=shared-run`,
    );

    try {
      const nextA = streamA.nextSnapshot();
      const nextB = streamB.nextSnapshot();
      await post(baseUrl, snapshot('scope-a', 'shared-run', 1));
      await post(baseUrl, snapshot('scope-b', 'shared-run', 1));

      await expect(nextA).resolves.toMatchObject({scopeId: 'scope-a'});
      await expect(nextB).resolves.toMatchObject({scopeId: 'scope-b'});
    } finally {
      streamA.close();
      streamB.close();
    }
  });

  test('enforces bearer auth only when an ingest token is configured', async () => {
    const openResponse = await post(baseUrl, snapshot());
    expect(openResponse.status).toBe(202);

    await close(server);
    server = createApp({dataFile: path.join(directory, 'protected.jsonl'), ingestToken: 'secret'});
    baseUrl = await listen(server);

    expect((await post(baseUrl, snapshot())).status).toBe(401);
    expect(
      (await post(baseUrl, snapshot(), {authorization: 'Bearer wrong'})).status,
    ).toBe(401);
    expect(
      (await post(baseUrl, snapshot(), {authorization: 'Bearer secret'})).status,
    ).toBe(202);
    expect((await fetch(`${baseUrl}/api/graphs`)).status).toBe(200);
  });
});
