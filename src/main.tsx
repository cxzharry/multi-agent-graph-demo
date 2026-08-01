import {useEffect, useMemo} from 'react';
import {createRoot} from 'react-dom/client';
import {
  Background,
  Controls,
  MarkerType,
  ReactFlow,
  type Edge,
  type FitViewOptions,
  useUpdateNodeInternals,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import {
  FeedbackEdge,
  type FeedbackFlowEdge,
} from './graph/FeedbackEdge';
import {layoutRoleGraph} from './graph/layout';
import {RoleNode, type RoleFlowNode} from './graph/RoleNode';
import type {GraphEvent, GraphSummary} from './graph/types';
import {
  graphMatchesSelection,
  selectionQuery,
  useLiveGraph,
} from './graph/useLiveGraph';
import './style.css';

const nodeTypes = {role: RoleNode};
const edgeTypes = {feedback: FeedbackEdge};

function SyncNodeInternals({nodes}: {nodes: RoleFlowNode[]}) {
  const updateNodeInternals = useUpdateNodeInternals();

  useEffect(
    () => updateNodeInternals(nodes.map(node => node.id)),
    [nodes, updateNodeInternals],
  );
  return null;
}

function App() {
  const {
    graphs,
    selection,
    snapshot,
    connection,
    loading,
    error,
    selectGraph,
  } = useLiveGraph();
  const layout = useMemo(
    () => layoutRoleGraph(snapshot?.nodes ?? [], snapshot?.edges ?? []),
    [snapshot],
  );

  const nodes = useMemo<RoleFlowNode[]>(
    () =>
      layout.positionedNodes.map(node => ({
        id: node.id,
        type: 'role',
        position: node.position,
        data: {...node},
        draggable: false,
        selectable: false,
      })),
    [layout.positionedNodes],
  );
  const initialFitView = useMemo<FitViewOptions<RoleFlowNode>>(() => {
    const rows = [...new Set(nodes.map(node => node.position.y))].sort(
      (left, right) => left - right,
    );
    if (rows.length <= 4) return {padding: 0.24, maxZoom: 1.05};

    const topRows = new Set(rows.slice(0, 2));
    return {
      nodes: nodes
        .filter(node => topRows.has(node.position.y))
        .map(node => ({id: node.id})),
      padding: 0.08,
      minZoom: 0.9,
      maxZoom: 1.05,
    };
  }, [nodes]);
  const edges = useMemo<Edge[]>(() => {
    const forwardEdges: Edge[] = layout.forwardEdges.map(edge => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      type: 'straight',
      animated: edge.status === 'active' || edge.status === 'retrying',
      className: `forward-edge edge-${edge.status}`,
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: '#748298',
      },
    }));
    const route = snapshot?.activeFailureRoute;
    if (!route) return forwardEdges;

    const feedbackEdge: FeedbackFlowEdge = {
      id: `active-failure-${route.gateNodeId}-${route.generation}`,
      source: route.gateNodeId,
      target: route.returnToNodeId,
      type: 'feedback',
      animated: true,
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: '#ef6a4c',
      },
      data: {
        feedbackGutterX: layout.feedbackGutterX,
        reason: route.reason,
      },
    };
    return [...forwardEdges, feedbackEdge];
  }, [layout.feedbackGutterX, layout.forwardEdges, snapshot]);

  const selectedValue = selection ? selectionQuery(selection) : '';
  const missingSelection = Boolean(
    selection &&
      !graphs.some(graph => graphMatchesSelection(graph, selection)),
  );
  const timeline = snapshot ? [...snapshot.events].slice(-12).reverse() : [];

  function handleGraphSelection(value: string) {
    const graph = graphs.find(item => selectionQuery(item) === value);
    if (graph) selectGraph({scopeId: graph.scopeId, runId: graph.runId});
  }

  return (
    <main className="viewer-shell">
      <header className="viewer-header">
        <div className="viewer-title">
          <p className="eyebrow">Live role graph</p>
          <h1>{snapshot?.title ?? 'Role graph viewer'}</h1>
          <p className="subtitle">
            Read-only orchestration state, hydrated from immutable snapshots.
          </p>
        </div>

        <div className="viewer-controls">
          <div className={`connection-state state-${connection}`}>
            <span className="connection-dot" aria-hidden="true" />
            <span>{connectionLabel(connection)}</span>
          </div>
          <label className="graph-selector">
            <span>Scope and run</span>
            <select
              data-testid="graph-selector"
              value={selectedValue}
              disabled={graphs.length === 0}
              onChange={event => handleGraphSelection(event.target.value)}
            >
              {graphs.length === 0 && <option value="">No saved graphs</option>}
              {missingSelection && selection && (
                <option value={selectedValue}>
                  Missing · {selection.scopeId} / {selection.runId}
                </option>
              )}
              {graphs.map(graph => (
                <option key={selectionQuery(graph)} value={selectionQuery(graph)}>
                  {graph.title} · {graph.scopeId} / {graph.runId}
                </option>
              ))}
            </select>
          </label>
        </div>
      </header>

      {error && <div className="error-banner">{error}</div>}

      <section className="viewer-layout">
        <div className="graph-panel" aria-label="Live role graph canvas">
          {snapshot ? (
            <>
              <div className="graph-meta">
                <span>
                  {snapshot.scopeId} / {snapshot.runId}
                </span>
                <span>Sequence {snapshot.sequence}</span>
              </div>
              <ReactFlow
                key={`${snapshot.scopeId}\u001f${snapshot.runId}`}
                nodes={nodes}
                edges={edges}
                nodeTypes={nodeTypes}
                edgeTypes={edgeTypes}
                fitView
                fitViewOptions={initialFitView}
                minZoom={0.2}
                maxZoom={1.5}
                nodesDraggable={false}
                nodesConnectable={false}
                elementsSelectable={false}
                proOptions={{hideAttribution: true}}
              >
                <SyncNodeInternals nodes={nodes} />
                <Background color="#27303c" gap={28} size={1} />
                <Controls showInteractive={false} />
              </ReactFlow>
            </>
          ) : (
            <div className="empty-state" data-testid="empty-state">
              <span className="empty-mark" aria-hidden="true">
                ◌
              </span>
              <h2>
                {loading
                  ? 'Loading saved graphs'
                  : missingSelection
                    ? 'Graph not found'
                    : 'No graph selected'}
              </h2>
              <p>
                {loading
                  ? 'Checking the local snapshot store.'
                  : missingSelection && selection
                    ? `No snapshot exists for ${selection.scopeId} / ${selection.runId}.`
                  : 'Publish an immutable snapshot to POST /api/snapshots to begin.'}
              </p>
            </div>
          )}
        </div>

        <aside className="timeline-panel">
          <div className="timeline-heading">
            <div>
              <p className="eyebrow">Recent state</p>
              <h2>Event timeline</h2>
            </div>
            {snapshot && (
              <span className="event-count">{snapshot.events.length}</span>
            )}
          </div>

          {snapshot?.activeFailureRoute && (
            <div className="failure-summary">
              <span>Active return</span>
              <strong>{snapshot.activeFailureRoute.reason}</strong>
              <small>
                {snapshot.activeFailureRoute.gateNodeId} →{' '}
                {snapshot.activeFailureRoute.returnToNodeId}
              </small>
            </div>
          )}

          <div className="timeline-list">
            {timeline.length === 0 ? (
              <p className="timeline-empty">No recent events in this snapshot.</p>
            ) : (
              timeline.map((event, index) => (
                <TimelineItem
                  key={`${eventValue(event, 'id') || 'event'}-${index}`}
                  event={event}
                />
              ))
            )}
          </div>

          {snapshot && (
            <footer className="snapshot-time">
              Snapshot generated {formatTimestamp(snapshot.generatedAt)}
            </footer>
          )}
        </aside>
      </section>
    </main>
  );
}

function TimelineItem({event}: {event: GraphEvent}) {
  const label =
    eventValue(event, 'message') ||
    eventValue(event, 'label') ||
    eventValue(event, 'type') ||
    'Graph event';
  const node = eventValue(event, 'nodeId') || eventValue(event, 'node');
  const at = eventValue(event, 'at');

  return (
    <article className="timeline-item">
      <div className="timeline-rail" aria-hidden="true">
        <span />
      </div>
      <div>
        <p>{label}</p>
        <small>
          {[node, at && formatTimestamp(at)]
            .filter(Boolean)
            .join(' · ')}
        </small>
      </div>
    </article>
  );
}

function eventValue(event: GraphEvent, key: string) {
  const value = event[key];
  return typeof value === 'string' || typeof value === 'number'
    ? String(value)
    : '';
}

function formatTimestamp(value: string) {
  const timestamp = Date.parse(value);
  return Number.isNaN(timestamp)
    ? value
    : new Intl.DateTimeFormat(undefined, {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      }).format(timestamp);
}

function connectionLabel(connection: ReturnType<typeof useLiveGraph>['connection']) {
  return {
    idle: 'No graph',
    connecting: 'Connecting',
    connected: 'Live',
    reconnecting: 'Reconnecting',
    error: 'Connection error',
  }[connection];
}

createRoot(document.getElementById('root')!).render(<App />);
