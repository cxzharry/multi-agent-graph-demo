import {describe, expect, test} from 'vitest';

import {getFeedbackPath, layoutRoleGraph, ROLE_NODE_WIDTH} from './layout';
import {
  graphMatchesSelection,
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
      scopeId: 'scope:new',
      runId: 'run/new',
      sequence: 4,
      generatedAt: '2026-07-31T10:05:00Z',
      title: 'Newest graph',
    },
    {
      scopeId: 'scope:old',
      runId: 'run/old',
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

  test('falls back to the newest listed graph when the URL has no complete key', () => {
    expect(selectedGraphFromList(summaries, null)).toEqual(summaries[0]);
    expect(graphSelectionFromLocation('?scopeId=scope%3Anew')).toBeNull();
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
