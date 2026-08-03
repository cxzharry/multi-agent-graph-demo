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
    const newer = snapshot('newer', 'run-2', 3, '2026-07-31T11:00:00Z');
    newer.spaceName = 'herdr-orchestrator';
    await store.append(newer);

    expect(store.listGraphs()).toEqual([
      {
        spaceName: 'herdr-orchestrator',
        scopeId: 'newer',
        runId: 'run-2',
        shortName: 'run-2',
        isLive: false,
        runStatus: 'RUNNING',
        sequence: 3,
        generatedAt: '2026-07-31T11:00:00Z',
        title: 'newer run-2',
      },
      {
        scopeId: 'older',
        runId: 'run-1',
        shortName: 'run-1',
        isLive: false,
        runStatus: 'RUNNING',
        sequence: 1,
        generatedAt: '2026-07-31T09:00:00Z',
        title: 'older run-1',
      },
    ]);
  });

  test('merges exact presence and lists active summaries before history', async () => {
    const presenceStore = {
      list: () => [
        {scopeId: 'herdr:wP', runId: 'current', spaceName: 'car-edge', shortName: 'current'},
        {scopeId: 'herdr:wK', runId: 'current', spaceName: 'herdr-orchestrator', shortName: 'current'},
      ],
    };
    const store = new GraphStore(dataFile, {presenceStore});
    await store.initialize();
    const car = snapshot('herdr:wP', 'current', 1, '2026-08-03T10:04:00Z');
    car.spaceName = 'car-edge';
    car.shortName = 'current';
    const current = snapshot('herdr:wK', 'current', 1, '2026-08-03T10:03:00Z');
    const selector = snapshot('herdr:wK', 'herdr-graph-viewer-space-selector-20260802', 1, '2026-08-03T10:02:00Z');
    selector.nodes[0].status = 'passed';
    const hardening = snapshot('herdr:wK', 'herdr-graph-viewer-hardening-20260801', 1, '2026-08-03T10:01:00Z');
    hardening.nodes[0].status = 'passed';
    for (const value of [hardening, current, selector, car]) await store.append(value);

    expect(store.listGraphs().map(({scopeId, runId, spaceName, shortName, isLive, runStatus}) => ({scopeId, runId, spaceName, shortName, isLive, runStatus}))).toEqual([
      {scopeId: 'herdr:wP', runId: 'current', spaceName: 'car-edge', shortName: 'current', isLive: true, runStatus: 'RUNNING'},
      {scopeId: 'herdr:wK', runId: 'current', spaceName: 'herdr-orchestrator', shortName: 'current', isLive: true, runStatus: 'RUNNING'},
      {scopeId: 'herdr:wK', runId: 'herdr-graph-viewer-space-selector-20260802', spaceName: 'herdr-orchestrator', shortName: 'space-selector', isLive: false, runStatus: 'DONE'},
      {scopeId: 'herdr:wK', runId: 'herdr-graph-viewer-hardening-20260801', spaceName: 'herdr-orchestrator', shortName: 'viewer-hardening', isLive: false, runStatus: 'DONE'},
    ]);
  });
});
