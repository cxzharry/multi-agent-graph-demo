import {Graph, layout} from '@dagrejs/dagre';

import type {RelationshipMode, RoleEdge, RoleNode} from './types';

export const ROLE_NODE_WIDTH = 280;
export const ROLE_NODE_HEIGHT = 148;
const NODE_SEPARATION = 52;
const LAYER_SEPARATION = 88;
const FEEDBACK_GUTTER_MARGIN = 96;
const MAX_EVENT_BACKED_ROW_SIZE = 3;

export type PositionedRoleNode = RoleNode & {
  position: {x: number; y: number};
};

export type RoleGraphLayout = {
  positionedNodes: PositionedRoleNode[];
  forwardEdges: RoleEdge[];
  feedbackGutterX: number;
};

export function layoutRoleGraph(
  nodes: RoleNode[],
  edges: RoleEdge[],
  relationshipMode?: RelationshipMode,
): RoleGraphLayout {
  const sortedNodes = [...nodes].sort((left, right) =>
    left.id.localeCompare(right.id),
  );
  const forwardEdges = edges
    .filter(edge => edge.kind === 'forward')
    .sort((left, right) => left.id.localeCompare(right.id));

  if (sortedNodes.length === 0) {
    return {positionedNodes: [], forwardEdges, feedbackGutterX: 0};
  }

  const graph = new Graph()
    .setGraph({
      rankdir: 'TB',
      nodesep: NODE_SEPARATION,
      ranksep: LAYER_SEPARATION,
      marginx: 0,
      marginy: 0,
    })
    .setDefaultEdgeLabel(() => ({}));

  for (const node of sortedNodes) {
    graph.setNode(node.id, {
      width: ROLE_NODE_WIDTH,
      height: ROLE_NODE_HEIGHT,
    });
  }
  for (const edge of forwardEdges) {
    graph.setEdge(edge.source, edge.target, {weight: 2});
  }
  layout(graph);

  const derivedLayers = deriveLayers(sortedNodes, forwardEdges);
  const p1Ids = new Set(
    sortedNodes.filter(isP1Node).map(node => node.id),
  );
  const p1ParticipatesInArtifactFlow = forwardEdges.some(
    edge => p1Ids.has(edge.source) || p1Ids.has(edge.target),
  );
  const reserveP1Rank =
    relationshipMode === 'event-backed' &&
    p1Ids.size > 0 &&
    !p1ParticipatesInArtifactFlow;
  const nodesByLayer = new Map<number, RoleNode[]>();
  for (const node of sortedNodes) {
    const artifactLayer = derivedLayers.get(node.id) ?? 0;
    const layer =
      relationshipMode === 'event-backed'
        ? p1Ids.has(node.id)
          ? 0
          : artifactLayer + (reserveP1Rank ? 1 : 0)
        : (node.layer ?? artifactLayer);
    const group = nodesByLayer.get(layer) ?? [];
    group.push(node);
    nodesByLayer.set(layer, group);
  }

  const layerValues = [...nodesByLayer.keys()].sort((left, right) => left - right);
  const widestLayer = Math.max(
    ...layerValues.map(layerValue => {
      const group = nodesByLayer.get(layerValue)!;
      const nodeCount =
        relationshipMode === 'event-backed'
          ? Math.min(group.length, MAX_EVENT_BACKED_ROW_SIZE)
          : group.length;
      return (
        nodeCount * ROLE_NODE_WIDTH +
        (nodeCount - 1) * NODE_SEPARATION
      );
    }),
  );
  const positionedNodes: PositionedRoleNode[] = [];
  let rowIndex = 0;
  for (const layerValue of layerValues) {
    const group = nodesByLayer.get(layerValue)!;
    group.sort((left, right) => {
      const leftX = graph.node(left.id).x ?? 0;
      const rightX = graph.node(right.id).x ?? 0;
      return leftX - rightX || left.id.localeCompare(right.id);
    });

    const rows =
      relationshipMode === 'event-backed'
        ? eventBackedRows(group)
        : [group];
    for (const row of rows) {
      const candidateCenters = row.map(node => graph.node(node.id).x ?? 0);
      const averageCenter =
        candidateCenters.reduce((sum, x) => sum + x, 0) /
        candidateCenters.length;
      const rowWidth =
        row.length * ROLE_NODE_WIDTH + (row.length - 1) * NODE_SEPARATION;
      const rowLeft =
        relationshipMode === 'event-backed'
          ? (widestLayer - rowWidth) / 2
          : averageCenter - rowWidth / 2;

      row.forEach((node, groupIndex) => {
        positionedNodes.push({
          ...node,
          position: {
            x: rowLeft + groupIndex * (ROLE_NODE_WIDTH + NODE_SEPARATION),
            y: rowIndex * (ROLE_NODE_HEIGHT + LAYER_SEPARATION),
          },
        });
      });
      rowIndex += 1;
    }
  }

  const leftmost = Math.min(...positionedNodes.map(node => node.position.x));
  const normalizedNodes = positionedNodes
    .map(node => ({
      ...node,
      position: {
        x: node.position.x - leftmost,
        y: node.position.y,
      },
    }))
    .sort((left, right) => left.id.localeCompare(right.id));
  const graphRight = Math.max(
    ...normalizedNodes.map(node => node.position.x + ROLE_NODE_WIDTH),
  );

  return {
    positionedNodes: normalizedNodes,
    forwardEdges,
    feedbackGutterX: graphRight + FEEDBACK_GUTTER_MARGIN,
  };
}

function isP1Node(node: RoleNode): boolean {
  return /^P1$/i.test(node.assignee) || /^p1(?:[_-]|$)/i.test(node.role);
}

function eventBackedRows(group: RoleNode[]): RoleNode[][] {
  const currentByPosition = new Map<number, RoleNode>();
  for (const node of group) {
    const match = /^P(\d+)$/i.exec(node.assignee);
    if (!match) continue;
    const position = Number(match[1]);
    const current = currentByPosition.get(position);
    if (
      !current ||
      node.generation > current.generation ||
      (node.generation === current.generation && node.id > current.id)
    ) {
      currentByPosition.set(position, node);
    }
  }
  const current = [...currentByPosition.entries()]
    .sort(([left], [right]) => left - right)
    .map(([, node]) => node);
  const currentIds = new Set(current.map(node => node.id));
  const ordered = [
    ...current,
    ...group.filter(node => !currentIds.has(node.id)),
  ];
  const rows: RoleNode[][] = [];
  for (
    let index = 0;
    index < ordered.length;
    index += MAX_EVENT_BACKED_ROW_SIZE
  ) {
    rows.push(ordered.slice(index, index + MAX_EVENT_BACKED_ROW_SIZE));
  }
  return rows;
}

function deriveLayers(nodes: RoleNode[], edges: RoleEdge[]) {
  const predecessors = new Map<string, string[]>();
  for (const edge of edges) {
    const sources = predecessors.get(edge.target) ?? [];
    sources.push(edge.source);
    predecessors.set(edge.target, sources);
  }

  const nodeIds = new Set(nodes.map(node => node.id));
  const resolved = new Map<string, number>();
  const visiting = new Set<string>();

  function resolve(nodeId: string): number {
    const known = resolved.get(nodeId);
    if (known !== undefined) return known;
    if (visiting.has(nodeId)) return 0;

    visiting.add(nodeId);
    const depth = Math.max(
      0,
      ...(predecessors.get(nodeId) ?? [])
        .filter(sourceId => nodeIds.has(sourceId))
        .map(sourceId => resolve(sourceId) + 1),
    );
    visiting.delete(nodeId);
    resolved.set(nodeId, depth);
    return depth;
  }

  nodes.forEach(node => resolve(node.id));
  return resolved;
}

export function getFeedbackPath(input: {
  sourceX: number;
  sourceY: number;
  targetX: number;
  targetY: number;
  gutterX: number;
}): string {
  const {sourceX, sourceY, targetX, targetY, gutterX} = input;
  return `M ${sourceX} ${sourceY} L ${gutterX} ${sourceY} L ${gutterX} ${targetY} L ${targetX} ${targetY}`;
}
