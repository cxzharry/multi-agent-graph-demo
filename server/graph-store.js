import {appendFile, mkdir, readFile} from 'node:fs/promises';
import path from 'node:path';

import {graphKey, validateSnapshot} from '../shared/role-graph.js';

export class StaleSequenceError extends Error {
  constructor(scopeId, runId, sequence, currentSequence) {
    super(
      `Sequence ${sequence} is not newer than ${currentSequence} for ${scopeId}/${runId}`,
    );
    this.name = 'StaleSequenceError';
  }
}

export class GraphStore {
  constructor(dataFile, {presenceStore} = {}) {
    if (!dataFile) throw new TypeError('GraphStore requires a data file');
    this.dataFile = dataFile;
    this.latest = new Map();
    this.initialization = null;
    this.writeQueue = Promise.resolve();
    this.presenceStore = presenceStore;
  }

  initialize() {
    if (!this.initialization) this.initialization = this.#hydrate();
    return this.initialization;
  }

  async #hydrate() {
    let text;
    try {
      text = await readFile(this.dataFile, 'utf8');
    } catch (error) {
      if (error.code === 'ENOENT') return;
      throw error;
    }

    for (const line of text.split('\n')) {
      if (!line.trim()) continue;
      const snapshot = validateSnapshot(JSON.parse(line));
      const key = graphKey(snapshot.scopeId, snapshot.runId);
      const current = this.latest.get(key);
      if (!current || snapshot.sequence >= current.sequence) {
        this.latest.set(key, snapshot);
      }
    }
  }

  async append(value, {replaceEqual = false} = {}) {
    const snapshot = validateSnapshot(value);
    await this.initialize();

    const operation = this.writeQueue.then(async () => {
      const key = graphKey(snapshot.scopeId, snapshot.runId);
      const current = this.latest.get(key);
      if (
        current &&
        (snapshot.sequence < current.sequence ||
          (snapshot.sequence === current.sequence && !replaceEqual))
      ) {
        throw new StaleSequenceError(
          snapshot.scopeId,
          snapshot.runId,
          snapshot.sequence,
          current.sequence,
        );
      }

      await mkdir(path.dirname(this.dataFile), {recursive: true});
      await appendFile(this.dataFile, `${JSON.stringify(snapshot)}\n`, 'utf8');
      this.latest.set(key, snapshot);
      return snapshot;
    });

    this.writeQueue = operation.catch(() => {});
    return operation;
  }

  getSnapshot(scopeId, runId) {
    return this.latest.get(graphKey(scopeId, runId)) ?? null;
  }

  listGraphs() {
    const presences = this.presenceStore?.list() ?? [];
    const presenceByGraph = new Map(
      presences.map(presence => [
        graphKey(presence.scopeId, presence.runId),
        presence,
      ]),
    );
    const spaceByScope = new Map();
    for (const snapshot of this.latest.values()) {
      if (snapshot.spaceName !== undefined) {
        spaceByScope.set(snapshot.scopeId, snapshot.spaceName);
      }
    }
    for (const presence of presences) {
      if (presence.spaceName !== undefined) {
        spaceByScope.set(presence.scopeId, presence.spaceName);
      }
    }

    return [...this.latest.values()]
      .map(snapshot => {
        const {scopeId, runId, sequence, generatedAt, title} = snapshot;
        const presence = presenceByGraph.get(graphKey(scopeId, runId));
        const spaceName =
          snapshot.spaceName ?? presence?.spaceName ?? spaceByScope.get(scopeId);
        return {
          ...(spaceName === undefined ? {} : {spaceName}),
          scopeId,
          runId,
          shortName:
            snapshot.shortName ?? presence?.shortName ?? compactRunName(runId),
          isLive: Boolean(presence),
          runStatus: runStatus(snapshot),
          sequence,
          generatedAt,
          title,
        };
      })
      .sort((left, right) => {
        if (left.isLive !== right.isLive) return left.isLive ? -1 : 1;
        const newestFirst = Date.parse(right.generatedAt) - Date.parse(left.generatedAt);
        if (newestFirst !== 0) return newestFirst;
        return graphKey(left.scopeId, left.runId).localeCompare(
          graphKey(right.scopeId, right.runId),
        );
      });
  }
}

function compactRunName(runId) {
  const withoutDate = runId.replace(/-(?:\d{8}|\d{4}-\d{2}-\d{2})$/, '');
  return withoutDate.split('-').slice(-2).join('-');
}

function runStatus(snapshot) {
  const p1 =
    snapshot.nodes.find(node => node.assignee === 'P1') ??
    snapshot.nodes.find(node => node.id === 'orchestrator');
  if (p1?.status === 'running' || p1?.status === 'retrying') return 'RUNNING';
  if (p1?.status === 'passed' || p1?.status === 'skipped') return 'DONE';
  if (p1?.status === 'failed' || p1?.status === 'blocked') return 'FAILED';
  return 'PENDING';
}
