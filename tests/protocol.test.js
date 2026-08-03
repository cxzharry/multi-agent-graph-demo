import {describe, expect, test} from 'vitest';

import {
  SNAPSHOT_SCHEMA_VERSION,
  SnapshotValidationError,
  graphKey,
  validateSnapshot,
} from '../shared/role-graph.js';

function snapshot(overrides = {}) {
  return {
    schemaVersion: SNAPSHOT_SCHEMA_VERSION,
    scopeId: 'scope:a',
    runId: 'run/1',
    sequence: 1,
    generatedAt: '2026-07-31T10:15:00Z',
    title: 'Compact graph',
    nodes: [
      {
        id: 'orchestrator',
        role: 'Orchestrator',
        assignee: 'P1',
        layer: 0,
        status: 'running',
        task: 'Route ready work',
        generation: 1,
      },
      {
        id: 'implementation',
        role: 'Implementation',
        assignee: 'P2',
        layer: 1,
        status: 'pending',
        task: 'Implement',
        generation: 1,
      },
    ],
    edges: [
      {
        id: 'orchestrator-to-implementation',
        source: 'orchestrator',
        target: 'implementation',
        kind: 'forward',
        status: 'active',
      },
    ],
    failurePolicies: [],
    activeFailureRoute: null,
    events: [],
    ...overrides,
  };
}

describe('validateSnapshot', () => {
  test('accepts a valid compact snapshot without retaining caller mutations', () => {
    const input = snapshot();
    const result = validateSnapshot(input);

    expect(result).toEqual(input);
    expect(result).not.toBe(input);
    input.nodes[0].status = 'failed';
    expect(result.nodes[0].status).toBe('running');
  });

  test('accepts and retains an optional non-empty space name', () => {
    const result = validateSnapshot(
      snapshot({spaceName: 'herdr-orchestrator'}),
    );

    expect(result.spaceName).toBe('herdr-orchestrator');
  });

  test.each(['', 42, null])('rejects malformed space name %j', spaceName => {
    expect(() => validateSnapshot(snapshot({spaceName}))).toThrow(/spaceName/i);
  });

  test('accepts and validates an optional non-empty short name', () => {
    expect(validateSnapshot(snapshot({shortName: 'current'})).shortName).toBe(
      'current',
    );
    expect(() => validateSnapshot(snapshot({shortName: ''}))).toThrow(
      /shortName/i,
    );
  });

  test('rejects duplicate node IDs', () => {
    const input = snapshot();
    input.nodes.push({...input.nodes[0]});

    expect(() => validateSnapshot(input)).toThrow(/duplicate node id/i);
  });

  test('rejects an edge whose endpoint is unknown', () => {
    const input = snapshot();
    input.edges[0].target = 'missing';

    expect(() => validateSnapshot(input)).toThrow(/unknown node/i);
  });

  test('rejects an invalid node status', () => {
    const input = snapshot();
    input.nodes[0].status = 'working';

    expect(() => validateSnapshot(input)).toThrow(/node status/i);
  });

  test('rejects an invalid edge kind', () => {
    const input = snapshot();
    input.edges[0].kind = 'feedback';

    expect(() => validateSnapshot(input)).toThrow(/edge kind/i);
  });

  test('rejects an active failure route that refers to an unknown node', () => {
    const input = snapshot({
      activeFailureRoute: {
        gateNodeId: 'missing-gate',
        returnToNodeId: 'implementation',
        ownerNodeId: 'implementation',
        resumeNodeId: 'implementation',
        rerunNodeIds: ['implementation'],
        excludedNodeIds: [],
        reason: 'Functional check failed',
        generation: 2,
      },
    });

    expect(() => validateSnapshot(input)).toThrow(/unknown node/i);
  });

  test('rejects a malformed generatedAt timestamp', () => {
    expect(() => validateSnapshot(snapshot({generatedAt: 'yesterday'}))).toThrow(
      /generatedAt/i,
    );
  });

  test.each([-1, 1.5])('rejects invalid sequence %s', sequence => {
    expect(() => validateSnapshot(snapshot({sequence}))).toThrow(/sequence/i);
  });

  test('throws a dedicated validation error', () => {
    expect(() => validateSnapshot(null)).toThrow(SnapshotValidationError);
  });
});

test('graphKey preserves exact scope and run boundaries', () => {
  expect(graphKey('scope:a', 'run/1')).toBe('scope%3Aa::run%2F1');
});
