import {useCallback, useEffect, useState} from 'react';

import type {
  GraphSelection,
  GraphSummary,
  RoleGraphSnapshot,
} from './types';

export function graphSelectionFromLocation(
  search: string,
): GraphSelection | null {
  const params = new URLSearchParams(search);
  const scopeId = params.get('scopeId');
  const runId = params.get('runId');
  return scopeId && runId ? {scopeId, runId} : null;
}

export function selectedGraphFromList(
  graphs: GraphSummary[],
  requested: GraphSelection | null,
): GraphSummary | null {
  if (requested) {
    return graphs.find(graph => graphMatchesSelection(graph, requested)) ?? null;
  }
  return graphs.find(graph => graph.isLive) ?? graphs[0] ?? null;
}

export function graphMatchesSelection(
  graph: GraphSelection,
  selection: GraphSelection,
): boolean {
  return (
    graph.scopeId === selection.scopeId && graph.runId === selection.runId
  );
}

export function selectionQuery(selection: GraphSelection): string {
  return new URLSearchParams({
    scopeId: selection.scopeId,
    runId: selection.runId,
  }).toString();
}

export function graphOptionLabel(
  graph: GraphSummary,
  graphs: GraphSummary[] = [graph],
): string {
  const prefix = `${graph.isLive ? 'LIVE' : graph.runStatus} · ${graph.spaceName ?? graph.scopeId}`;
  const collisions = graphs.filter(
    candidate =>
      `${candidate.isLive ? 'LIVE' : candidate.runStatus} · ${candidate.spaceName ?? candidate.scopeId}` ===
        prefix && candidate.shortName === graph.shortName,
  );
  if (collisions.length <= 1) return `${prefix} · ${graph.shortName}`;

  const runParts = graph.runId.split('-').filter(Boolean);
  const initialParts = Math.max(1, graph.shortName.split('-').length);
  for (let count = initialParts; count <= runParts.length; count += 1) {
    const suffix = runParts.slice(-count).join('-');
    if (
      collisions.every(
        candidate =>
          candidate === graph ||
          candidate.runId.split('-').filter(Boolean).slice(-count).join('-') !==
            suffix,
      )
    ) {
      return `${prefix} · ${suffix}`;
    }
  }

  return `${prefix} · ${graph.shortName} · ${graph.scopeId}`;
}

export type ConnectionState =
  | 'idle'
  | 'connecting'
  | 'connected'
  | 'reconnecting'
  | 'error';

export function useLiveGraph() {
  const [graphs, setGraphs] = useState<GraphSummary[]>([]);
  const [selection, setSelection] = useState<GraphSelection | null>(null);
  const [snapshot, setSnapshot] = useState<RoleGraphSnapshot | null>(null);
  const [connection, setConnection] = useState<ConnectionState>('idle');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    let refreshing = false;

    async function loadGraphs() {
      if (refreshing) return;
      refreshing = true;
      try {
        const response = await fetch('/api/graphs');
        if (!response.ok) throw new Error(`Graph list returned ${response.status}`);
        const nextGraphs = (await response.json()) as GraphSummary[];
        if (!active) return;
        const requested = graphSelectionFromLocation(window.location.search);
        const nextGraph = selectedGraphFromList(nextGraphs, requested);
        const fallbackSelection = nextGraph
          ? {scopeId: nextGraph.scopeId, runId: nextGraph.runId}
          : null;
        setGraphs(nextGraphs);
        setSelection(current => current ?? requested ?? fallbackSelection);
        setError(null);
      } catch (loadError) {
        if (active) {
          setError(messageFromError(loadError));
          setConnection('error');
        }
      } finally {
        refreshing = false;
        if (active) setLoading(false);
      }
    }

    void loadGraphs();
    const refreshTimer = window.setInterval(() => void loadGraphs(), 2_000);
    return () => {
      active = false;
      window.clearInterval(refreshTimer);
    };
  }, []);

  useEffect(() => {
    if (!selection) {
      setSnapshot(null);
      setConnection('idle');
      return;
    }

    let active = true;
    const activeSelection = selection;
    const query = selectionQuery(activeSelection);

    async function hydrate() {
      try {
        const response = await fetch(`/api/snapshot?${query}`);
        if (response.status === 404) {
          if (active) setSnapshot(null);
          return;
        }
        if (!response.ok) throw new Error(`Snapshot returned ${response.status}`);
        const nextSnapshot = (await response.json()) as RoleGraphSnapshot;
        if (active && graphMatchesSelection(nextSnapshot, activeSelection)) {
          setSnapshot(current =>
            !current ||
            !graphMatchesSelection(current, activeSelection) ||
            nextSnapshot.sequence >= current.sequence
              ? nextSnapshot
              : current,
          );
          setError(null);
        }
      } catch (hydrateError) {
        if (active) setError(messageFromError(hydrateError));
      }
    }

    setSnapshot(null);
    setConnection('connecting');
    void hydrate();

    const stream = new EventSource(`/api/stream?${query}`);
    stream.onopen = () => {
      if (!active) return;
      setConnection('connected');
      void hydrate();
    };
    stream.onerror = () => {
      if (!active) return;
      setConnection(
        stream.readyState === EventSource.CLOSED ? 'error' : 'reconnecting',
      );
    };
    stream.addEventListener('snapshot', event => {
      if (!active) return;
      try {
        const nextSnapshot = JSON.parse(
          (event as MessageEvent<string>).data,
        ) as RoleGraphSnapshot;
        if (!graphMatchesSelection(nextSnapshot, activeSelection)) return;

        setSnapshot(current =>
          !current || nextSnapshot.sequence > current.sequence
            ? nextSnapshot
            : current,
        );
        setGraphs(current =>
          current.map(graph =>
            graphMatchesSelection(graph, activeSelection)
              ? {
                  ...graph,
                  spaceName: nextSnapshot.spaceName ?? graph.spaceName,
                  shortName: nextSnapshot.shortName ?? graph.shortName,
                  scopeId: nextSnapshot.scopeId,
                  runId: nextSnapshot.runId,
                  sequence: nextSnapshot.sequence,
                  generatedAt: nextSnapshot.generatedAt,
                  title: nextSnapshot.title,
                }
              : graph,
          ),
        );
        setError(null);
      } catch {
        setError('The live stream sent an unreadable snapshot.');
      }
    });

    return () => {
      active = false;
      stream.close();
    };
  }, [selection]);

  const selectGraph = useCallback((nextSelection: GraphSelection) => {
    const params = new URLSearchParams(window.location.search);
    params.set('scopeId', nextSelection.scopeId);
    params.set('runId', nextSelection.runId);
    window.history.replaceState(null, '', `${window.location.pathname}?${params}`);
    setSelection(nextSelection);
  }, []);

  return {
    graphs,
    selection,
    snapshot,
    connection,
    loading,
    error,
    selectGraph,
  };
}

function messageFromError(error: unknown) {
  return error instanceof Error ? error.message : 'Unable to load the live graph.';
}
