import {useEffect, useMemo, useState} from 'react';
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
  graphOptionLabel,
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

type ResponsiveGraphMode = 'desktop' | 'tablet' | 'mobile';

function useResponsiveGraphMode(): ResponsiveGraphMode {
  const tabletQuery = '(max-width: 1100px)';
  const mobileQuery = '(max-width: 620px)';
  const currentMode = (): ResponsiveGraphMode =>
    window.matchMedia(mobileQuery).matches
      ? 'mobile'
      : window.matchMedia(tabletQuery).matches
        ? 'tablet'
        : 'desktop';
  const [mode, setMode] = useState(currentMode);

  useEffect(() => {
    const tablet = window.matchMedia(tabletQuery);
    const mobile = window.matchMedia(mobileQuery);
    const update = () => setMode(currentMode());
    tablet.addEventListener('change', update);
    mobile.addEventListener('change', update);
    return () => {
      tablet.removeEventListener('change', update);
      mobile.removeEventListener('change', update);
    };
  }, []);

  return mode;
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
  const responsiveGraphMode = useResponsiveGraphMode();
  const positionedNodes = useMemo(() => {
    if (responsiveGraphMode === 'desktop') return layout.positionedNodes;

    const groups = new Map<number, typeof layout.positionedNodes>();
    for (const node of layout.positionedNodes) {
      const group = groups.get(node.position.y) ?? [];
      group.push(node);
      groups.set(node.position.y, group);
    }
    const rows = [...groups.entries()].sort(([left], [right]) => left - right);
    if (responsiveGraphMode === 'tablet') {
      const rowWidth = 944;
      return rows.flatMap(([y, group]) => {
        const sorted = [...group].sort(
          (left, right) =>
            left.position.x - right.position.x ||
            left.id.localeCompare(right.id),
        );
        const groupWidth = sorted.length * 280 + (sorted.length - 1) * 52;
        const left = (rowWidth - groupWidth) / 2;
        return sorted.map((node, index) => ({
          ...node,
          position: {x: left + index * 332, y},
        }));
      });
    }

    let stageY = 0;
    return rows.flatMap(([, group]) => {
      const sorted = [...group].sort(
        (left, right) =>
          left.position.x - right.position.x || left.id.localeCompare(right.id),
      );
      const stage = sorted.map((node, index) => {
        const row = Math.floor(index / 2);
        const itemsInRow = Math.min(2, sorted.length - row * 2);
        const rowWidth = itemsInRow * 140 + (itemsInRow - 1) * 20;
        const left = (300 - rowWidth) / 2;
        return {
          ...node,
          position: {x: left + (index % 2) * 160, y: stageY + row * 256},
        };
      });
      stageY += Math.ceil(sorted.length / 2) * 256;
      return stage;
    });
  }, [layout.positionedNodes, responsiveGraphMode]);

  const nodes = useMemo<RoleFlowNode[]>(
    () =>
      positionedNodes.map(node => ({
        id: node.id,
        type: 'role',
        position: node.position,
        data: {
          ...node,
          synthetic: snapshot?.flowId === 'auto-operational',
        },
        draggable: false,
        selectable: false,
      })),
    [positionedNodes, snapshot?.flowId],
  );
  const initialFitView = useMemo<FitViewOptions<RoleFlowNode>>(() => {
    const rows = [...new Set(nodes.map(node => node.position.y))].sort(
      (left, right) => left - right,
    );
    if (rows.length <= 4) return {padding: 0.24, maxZoom: 1.05};

    return {
      padding: 0.06,
      minZoom: 0.85,
      maxZoom: 1.05,
    };
  }, [nodes]);
  const graphPanelHeight = useMemo(() => {
    const rows = new Set(nodes.map(node => node.position.y));
    if (rows.size <= 4) return 720;
    const nodeHeight = responsiveGraphMode === 'mobile' ? 188 : 148;
    const graphBottom = Math.max(
      ...nodes.map(node => node.position.y + nodeHeight),
    );
    return Math.max(720, graphBottom + 120);
  }, [nodes, responsiveGraphMode]);
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
        feedbackGutterX:
          responsiveGraphMode === 'mobile'
            ? 316
            : responsiveGraphMode === 'tablet'
              ? 960
              : layout.feedbackGutterX,
        reason: route.reason,
      },
    };
    return [...forwardEdges, feedbackEdge];
  }, [
    layout.feedbackGutterX,
    layout.forwardEdges,
    responsiveGraphMode,
    snapshot,
  ]);

  const selectedValue = selection ? selectionQuery(selection) : '';
  const observedTopology =
    snapshot?.flowId === 'auto-operational' ||
    snapshot?.flowId === 'live-session';
  const missingSelection = Boolean(
    selection &&
      !graphs.some(graph => graphMatchesSelection(graph, selection)),
  );
  const timeline = snapshot ? [...snapshot.events].slice(-12).reverse() : [];
  const activeGraphs = graphs.filter(graph => graph.isLive);
  const historicalGraphs = graphs.filter(graph => !graph.isLive);

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
              {activeGraphs.length > 0 && (
                <optgroup label="Active">
                  {activeGraphs.map(graph => (
                    <option
                      key={selectionQuery(graph)}
                      value={selectionQuery(graph)}
                    >
                      {graphOptionLabel(graph)}
                    </option>
                  ))}
                </optgroup>
              )}
              {historicalGraphs.length > 0 && (
                <optgroup label="History">
                  {historicalGraphs.map(graph => (
                    <option
                      key={selectionQuery(graph)}
                      value={selectionQuery(graph)}
                    >
                      {graphOptionLabel(graph)}
                    </option>
                  ))}
                </optgroup>
              )}
            </select>
          </label>
        </div>
      </header>

      {error && <div className="error-banner">{error}</div>}

      <section className="viewer-layout">
        <div
          className="graph-panel"
          aria-label="Live role graph canvas"
          style={{height: graphPanelHeight}}
        >
          {snapshot ? (
            <>
              <div className="graph-meta">
                <span>
                  {snapshot.scopeId} / {snapshot.runId}
                </span>
                <span>Sequence {snapshot.sequence}</span>
              </div>
              {observedTopology && (
                <div
                  className="relationship-notice"
                  data-testid="relationship-notice"
                  role="note"
                >
                  <strong>Observed topology — relationships unavailable</strong>
                  <span>
                    Live agents and statuses are observed directly. An exact
                    custom topology is required to draw workflow relationships.
                  </span>
                </div>
              )}
              <ReactFlow
                key={`${snapshot.scopeId}\u001f${snapshot.runId}\u001f${responsiveGraphMode}`}
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

function formatTimestamp(value: string | number) {
  const text = String(value).trim();
  const numeric = Number(text);
  const timestamp =
    text && Number.isFinite(numeric)
      ? Math.abs(numeric) < 1_000_000_000_000
        ? numeric * 1000
        : numeric
      : Date.parse(text);
  return Number.isNaN(timestamp)
    ? text
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
