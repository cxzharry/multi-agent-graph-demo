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
  constructor(dataFile) {
    if (!dataFile) throw new TypeError('GraphStore requires a data file');
    this.dataFile = dataFile;
    this.latest = new Map();
    this.initialization = null;
    this.writeQueue = Promise.resolve();
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
    return [...this.latest.values()]
      .map(({scopeId, runId, sequence, generatedAt, title}) => ({
        scopeId,
        runId,
        sequence,
        generatedAt,
        title,
      }))
      .sort((left, right) => {
        const newestFirst = Date.parse(right.generatedAt) - Date.parse(left.generatedAt);
        if (newestFirst !== 0) return newestFirst;
        return graphKey(left.scopeId, left.runId).localeCompare(
          graphKey(right.scopeId, right.runId),
        );
      });
  }
}
