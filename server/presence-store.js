import {graphKey} from '../shared/role-graph.js';

export class PresenceValidationError extends Error {
  constructor(message) {
    super(message);
    this.name = 'PresenceValidationError';
  }
}

function requireString(value, name) {
  if (typeof value !== 'string' || value.length === 0) {
    throw new PresenceValidationError(`${name} must be a non-empty string`);
  }
}

export class PresenceStore {
  constructor({ttlMs = 6_000, now = Date.now} = {}) {
    this.ttlMs = ttlMs;
    this.now = now;
    this.entries = new Map();
  }

  heartbeat(value) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      throw new PresenceValidationError('presence must be an object');
    }
    requireString(value.scopeId, 'scopeId');
    requireString(value.runId, 'runId');
    if (value.spaceName !== undefined) requireString(value.spaceName, 'spaceName');
    if (value.shortName !== undefined) requireString(value.shortName, 'shortName');
    const presence = {
      scopeId: value.scopeId,
      runId: value.runId,
      ...(value.spaceName === undefined ? {} : {spaceName: value.spaceName}),
      ...(value.shortName === undefined ? {} : {shortName: value.shortName}),
    };
    this.entries.set(graphKey(value.scopeId, value.runId), {
      presence,
      expiresAt: this.now() + this.ttlMs,
    });
    return presence;
  }

  list() {
    const now = this.now();
    const active = [];
    for (const [key, entry] of this.entries) {
      if (entry.expiresAt <= now) {
        this.entries.delete(key);
      } else {
        active.push(entry.presence);
      }
    }
    return active;
  }
}
