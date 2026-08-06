import {describe, expect, test} from 'vitest';

import {getFeedbackPath, layoutRoleGraph, ROLE_NODE_WIDTH} from './layout';
import {
  graphMatchesSelection,
  graphOptionLabel,
  graphSelectionFromLocation,
  selectedGraphFromList,
  selectionQuery,
} from './useLiveGraph';
import type {GraphSummary, RoleEdge, RoleNode} from './types';

const nodes: RoleNode[] = [
  {
    id: 'coordination-root',
    role: 'Coordination',
    assignee: 'lead-agent',
    layer: 0,
    status: 'running',
    task: 'Route ready work',
    generation: 1,
  },
  {
    id: 'implementation-west',
    role: 'Implementation West',
    assignee: 'worker-a',
    layer: 1,
    status: 'pending',
    task: 'Build one branch',
    generation: 1,
  },
  {
    id: 'implementation-east',
    role: 'Implementation East',
    assignee: 'worker-b',
    layer: 1,
    status: 'pending',
    task: 'Build another branch',
    generation: 1,
  },
  {
    id: 'quality-gate',
    role: 'Quality Gate',
    assignee: 'reviewer',
    layer: 2,
    status: 'failed',
    task: 'Check the integrated result',
    generation: 1,
  },
];

const edges: RoleEdge[] = [
  {
    id: 'root-to-west',
    source: 'coordination-root',
    target: 'implementation-west',
    kind: 'forward',
    status: 'active',
  },
  {
    id: 'root-to-east',
    source: 'coordination-root',
    target: 'implementation-east',
    kind: 'forward',
    status: 'active',
  },
  {
    id: 'west-to-gate',
    source: 'implementation-west',
    target: 'quality-gate',
    kind: 'forward',
    status: 'pending',
  },
  {
    id: 'active-return',
    source: 'quality-gate',
    target: 'implementation-west',
    kind: 'return',
    status: 'active',
  },
];

describe('layoutRoleGraph', () => {
  test('passes only forward edges into the rendered forward graph', () => {
    const result = layoutRoleGraph(nodes, edges);

    expect(result.forwardEdges.map(edge => edge.id)).toEqual([
      'root-to-east',
      'root-to-west',
      'west-to-gate',
    ]);
  });

  test('places lower explicit layers below higher layers', () => {
    const result = layoutRoleGraph(nodes, edges);
    const positions = new Map(
      result.positionedNodes.map(node => [node.id, node.position]),
    );

    expect(positions.get('coordination-root')!.y).toBeLessThan(
      positions.get('implementation-west')!.y,
    );
    expect(positions.get('implementation-west')!.y).toBeLessThan(
      positions.get('quality-gate')!.y,
    );
  });

  test('aligns nodes sharing an explicit layer horizontally', () => {
    const result = layoutRoleGraph(nodes, edges);
    const positions = new Map(
      result.positionedNodes.map(node => [node.id, node.position]),
    );

    expect(positions.get('implementation-west')!.y).toBe(
      positions.get('implementation-east')!.y,
    );
  });

  test('lays out arbitrary node identifiers without aliases', () => {
    const arbitraryNodes = nodes.map((node, index) => ({
      ...node,
      id: `role-${index * 17 + 3}`,
    }));
    const arbitraryEdges: RoleEdge[] = [
      {
        id: 'relation-a',
        source: arbitraryNodes[0].id,
        target: arbitraryNodes[1].id,
        kind: 'forward',
        status: 'active',
      },
      {
        id: 'relation-b',
        source: arbitraryNodes[1].id,
        target: arbitraryNodes[3].id,
        kind: 'forward',
        status: 'pending',
      },
    ];

    const result = layoutRoleGraph(arbitraryNodes, arbitraryEdges);

    expect(result.positionedNodes.map(node => node.id).sort()).toEqual(
      arbitraryNodes.map(node => node.id).sort(),
    );
    expect(
      result.positionedNodes.every(
        node =>
          Number.isFinite(node.position.x) && Number.isFinite(node.position.y),
      ),
    ).toBe(true);
  });

  test('places the feedback gutter beyond every node', () => {
    const result = layoutRoleGraph(nodes, edges);
    const graphRight = Math.max(
      ...result.positionedNodes.map(node => node.position.x + ROLE_NODE_WIDTH),
    );

    expect(result.feedbackGutterX).toBeGreaterThan(graphRight);
  });

  test('lays out observed topology with no edges into aligned layers', () => {
    const observedNodes: RoleNode[] = [
      {
        id: 'orchestrator',
        role: 'Orchestrator',
        assignee: 'P1',
        layer: 0,
        status: 'running',
        task: 'Coordinate current Herdr session',
        generation: 1,
      },
      ...['agent-a', 'agent-b', 'agent-c'].map(id => ({
        id,
        role: id,
        assignee: id,
        layer: 1,
        status: 'pending' as const,
        task: 'Participate in current Herdr session',
        generation: 1,
      })),
    ];

    const result = layoutRoleGraph(observedNodes, []);
    const positions = new Map(
      result.positionedNodes.map(node => [node.id, node.position]),
    );

    expect(result.forwardEdges).toEqual([]);
    for (const id of ['agent-a', 'agent-b', 'agent-c']) {
      expect(positions.get('orchestrator')!.y).toBeLessThan(
        positions.get(id)!.y,
      );
    }
    expect(positions.get('agent-a')!.y).toBe(positions.get('agent-b')!.y);
    expect(positions.get('agent-b')!.y).toBe(positions.get('agent-c')!.y);
  });
});

describe('getFeedbackPath', () => {
  test('starts and ends at the supplied node anchors through the gutter', () => {
    const path = getFeedbackPath({
      sourceX: 640,
      sourceY: 520,
      targetX: 300,
      targetY: 240,
      gutterX: 820,
    });

    expect(path).toBe('M 640 520 L 820 520 L 820 240 L 300 240');
  });
});

describe('live graph selection', () => {
  const summaries: GraphSummary[] = [
    {
      spaceName: 'herdr-orchestrator',
      shortName: 'current',
      isLive: true,
      runStatus: 'RUNNING',
      scopeId: 'scope:new',
      runId: 'run/new',
      sequence: 4,
      generatedAt: '2026-07-31T10:05:00Z',
      title: 'Newest graph',
    },
    {
      scopeId: 'scope:old',
      runId: 'run/old',
      shortName: 'viewer-hardening',
      isLive: false,
      runStatus: 'DONE',
      sequence: 9,
      generatedAt: '2026-07-31T10:00:00Z',
      title: 'Older graph',
    },
  ];

  test('uses the exact scope and run from the current URL', () => {
    const selected = graphSelectionFromLocation(
      '?scopeId=scope%3Aold&runId=run%2Fold',
    );

    expect(selected).toEqual({scopeId: 'scope:old', runId: 'run/old'});
    expect(selectedGraphFromList(summaries, selected)).toEqual(summaries[1]);
  });

  test('falls back to the first active graph when the URL has no complete key', () => {
    expect(selectedGraphFromList([summaries[1], summaries[0]], null)).toEqual(
      summaries[0],
    );
    expect(graphSelectionFromLocation('?scopeId=scope%3Anew')).toBeNull();
  });

  test('labels graph options compactly by status and space with a scope fallback', () => {
    expect(graphOptionLabel(summaries[0])).toBe(
      'LIVE · herdr-orchestrator · current',
    );
    expect(graphOptionLabel(summaries[1])).toBe(
      'DONE · scope:old · viewer-hardening',
    );
  });

  test('disambiguates colliding short names with the shortest unique run suffix', () => {
    const collisions: GraphSummary[] = [
      {
        ...summaries[1],
        spaceName: 'herdr-orchestrator',
        scopeId: 'herdr:wK',
        runId: 'functional-qc-custom-g1-fixture',
        shortName: 'g1-fixture',
        runStatus: 'PENDING',
      },
      {
        ...summaries[1],
        spaceName: 'herdr-orchestrator',
        scopeId: 'herdr:wK',
        runId: 'functional-qc-manifestless-g1-fixture',
        shortName: 'g1-fixture',
        runStatus: 'PENDING',
      },
    ];

    expect(collisions.map(graph => graphOptionLabel(graph, collisions))).toEqual([
      'PENDING · herdr-orchestrator · custom-g1-fixture',
      'PENDING · herdr-orchestrator · manifestless-g1-fixture',
    ]);
  });

  test('does not replace a missing complete URL key with the newest graph', () => {
    const missing = {scopeId: 'scope:missing', runId: 'run/missing'};

    expect(selectedGraphFromList(summaries, missing)).toBeNull();
  });

  test('matches snapshots only when both scope and run are exact', () => {
    const selected = {scopeId: 'scope:new', runId: 'run/new'};

    expect(graphMatchesSelection(summaries[0], selected)).toBe(true);
    expect(
      graphMatchesSelection(
        {...summaries[0], runId: 'run/other'},
        selected,
      ),
    ).toBe(false);
    expect(
      graphMatchesSelection(
        {...summaries[0], scopeId: 'scope:other'},
        selected,
      ),
    ).toBe(false);
  });

  test('encodes both key fields for API and stream requests', () => {
    expect(
      selectionQuery({scopeId: 'scope with spaces', runId: 'run/with/slashes'}),
    ).toBe('scopeId=scope+with+spaces&runId=run%2Fwith%2Fslashes');
  });

  test('ignores graph summary fields when building the exact key query', () => {
    expect(selectionQuery(summaries[0])).toBe(
      'scopeId=scope%3Anew&runId=run%2Fnew',
    );
  });
});
