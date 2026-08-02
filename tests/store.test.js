import {mkdtemp, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';

import {afterEach, beforeEach, describe, expect, test} from 'vitest';

import {GraphStore, StaleSequenceError} from '../server/graph-store.js';

function snapshot(scopeId, runId, sequence, generatedAt) {
  return {
    schemaVersion: 'role-graph/v1',
    scopeId,
    runId,
    sequence,
    generatedAt,
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

describe('GraphStore', () => {
  let directory;
  let dataFile;

  beforeEach(async () => {
    directory = await mkdtemp(path.join(tmpdir(), 'role-graph-store-'));
    dataFile = path.join(directory, 'snapshots.jsonl');
  });

  afterEach(async () => {
    await rm(directory, {recursive: true, force: true});
  });

  test('hydrates appended snapshots after restart', async () => {
    const firstStore = new GraphStore(dataFile);
    await firstStore.initialize();
    const input = snapshot('scope-a', 'run-1', 1, '2026-07-31T10:00:00Z');
    await firstStore.append(input);

    const restartedStore = new GraphStore(dataFile);
    await restartedStore.initialize();

    expect(restartedStore.getSnapshot('scope-a', 'run-1')).toEqual(input);
  });

  test('keeps the latest snapshot for each scope and run pair', async () => {
    const store = new GraphStore(dataFile);
    await store.initialize();
    await store.append(snapshot('scope-a', 'run-1', 1, '2026-07-31T10:00:00Z'));
    await store.append(snapshot('scope-a', 'run-1', 2, '2026-07-31T10:01:00Z'));

    expect(store.getSnapshot('scope-a', 'run-1').sequence).toBe(2);
  });

  test('rejects sequences that do not increase', async () => {
    const store = new GraphStore(dataFile);
    await store.initialize();
    await store.append(snapshot('scope-a', 'run-1', 2, '2026-07-31T10:00:00Z'));

    await expect(
      store.append(snapshot('scope-a', 'run-1', 2, '2026-07-31T10:01:00Z')),
    ).rejects.toBeInstanceOf(StaleSequenceError);
    await expect(
      store.append(snapshot('scope-a', 'run-1', 1, '2026-07-31T10:02:00Z')),
    ).rejects.toBeInstanceOf(StaleSequenceError);
    await expect(
      store.append(
        snapshot('scope-a', 'run-1', 1, '2026-07-31T10:03:00Z'),
        {replaceEqual: true},
      ),
    ).rejects.toBeInstanceOf(StaleSequenceError);
  });

  test('explicitly replaces only the exact current sequence', async () => {
    const store = new GraphStore(dataFile);
    await store.initialize();
    await store.append(snapshot('scope-a', 'run-1', 2, '2026-07-31T10:00:00Z'));
    const replacement = snapshot(
      'scope-a',
      'run-1',
      2,
      '2026-07-31T10:01:00Z',
    );
    replacement.title = 'Explicit replacement';

    await store.append(replacement, {replaceEqual: true});

    expect(store.getSnapshot('scope-a', 'run-1')).toEqual(replacement);
    const restartedStore = new GraphStore(dataFile);
    await restartedStore.initialize();
    expect(restartedStore.getSnapshot('scope-a', 'run-1')).toEqual(replacement);
  });

  test('does not mix scopes that share a run ID', async () => {
    const store = new GraphStore(dataFile);
    await store.initialize();
    await store.append(snapshot('scope-a', 'shared-run', 1, '2026-07-31T10:00:00Z'));
    await store.append(snapshot('scope-b', 'shared-run', 7, '2026-07-31T10:01:00Z'));

    expect(store.getSnapshot('scope-a', 'shared-run').sequence).toBe(1);
    expect(store.getSnapshot('scope-b', 'shared-run').sequence).toBe(7);
  });

  test('lists graph summaries newest first', async () => {
    const store = new GraphStore(dataFile);
    await store.initialize();
    await store.append(snapshot('older', 'run-1', 1, '2026-07-31T09:00:00Z'));
    await store.append(snapshot('newer', 'run-2', 3, '2026-07-31T11:00:00Z'));

    expect(store.listGraphs()).toEqual([
      {
        scopeId: 'newer',
        runId: 'run-2',
        sequence: 3,
        generatedAt: '2026-07-31T11:00:00Z',
        title: 'newer run-2',
      },
      {
        scopeId: 'older',
        runId: 'run-1',
        sequence: 1,
        generatedAt: '2026-07-31T09:00:00Z',
        title: 'older run-1',
      },
    ]);
  });
});
