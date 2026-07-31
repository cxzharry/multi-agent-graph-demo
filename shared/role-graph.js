export const SNAPSHOT_SCHEMA_VERSION = 'role-graph/v1';

export const NODE_STATUSES = new Set([
  'pending',
  'running',
  'passed',
  'failed',
  'blocked',
  'retrying',
  'stale',
  'skipped',
]);

export const EDGE_KINDS = new Set(['forward', 'return']);
export const EDGE_STATUSES = new Set([
  'pending',
  'active',
  'inactive',
  'passed',
  'failed',
  'blocked',
  'retrying',
  'stale',
  'skipped',
]);

export class SnapshotValidationError extends Error {
  constructor(message) {
    super(message);
    this.name = 'SnapshotValidationError';
  }
}

function invalid(message) {
  throw new SnapshotValidationError(message);
}

function isObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function requireObject(value, path) {
  if (!isObject(value)) invalid(`${path} must be an object`);
}

function requireArray(value, path) {
  if (!Array.isArray(value)) invalid(`${path} must be an array`);
}

function requireString(value, path) {
  if (typeof value !== 'string' || value.length === 0) {
    invalid(`${path} must be a non-empty string`);
  }
}

function requireInteger(value, path, minimum = 0) {
  if (!Number.isInteger(value) || value < minimum) {
    invalid(`${path} must be an integer greater than or equal to ${minimum}`);
  }
}

function requireTimestamp(value, path) {
  requireString(value, path);
  const isoTimestamp =
    /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;
  if (!isoTimestamp.test(value) || Number.isNaN(Date.parse(value))) {
    invalid(`${path} must be an ISO 8601 timestamp`);
  }
}

function requireKnownNode(id, nodeIds, path) {
  requireString(id, path);
  if (!nodeIds.has(id)) invalid(`${path} refers to an unknown node: ${id}`);
}

function validateNode(node, index) {
  const path = `nodes[${index}]`;
  requireObject(node, path);
  requireString(node.id, `${path}.id`);
  requireString(node.role, `${path}.role`);
  requireString(node.assignee, `${path}.assignee`);
  requireString(node.task, `${path}.task`);
  requireInteger(node.generation, `${path}.generation`);
  if (node.layer !== undefined) requireInteger(node.layer, `${path}.layer`);
  if (!NODE_STATUSES.has(node.status)) {
    invalid(`${path}.status has an invalid node status: ${node.status}`);
  }
}

function validateEdge(edge, index, nodeIds) {
  const path = `edges[${index}]`;
  requireObject(edge, path);
  requireString(edge.id, `${path}.id`);
  requireKnownNode(edge.source, nodeIds, `${path}.source`);
  requireKnownNode(edge.target, nodeIds, `${path}.target`);
  if (!EDGE_KINDS.has(edge.kind)) {
    invalid(`${path}.kind has an invalid edge kind: ${edge.kind}`);
  }
  if (!EDGE_STATUSES.has(edge.status)) {
    invalid(`${path}.status has an invalid edge status: ${edge.status}`);
  }
}

const routeNodeFields = [
  'gateNodeId',
  'returnToNodeId',
  'ownerNodeId',
  'resumeNodeId',
];

function validateRouteFields(route, path, nodeIds) {
  for (const field of routeNodeFields) {
    requireKnownNode(route[field], nodeIds, `${path}.${field}`);
  }

  for (const field of ['rerunNodeIds', 'excludedNodeIds']) {
    requireArray(route[field], `${path}.${field}`);
    route[field].forEach((nodeId, index) => {
      requireKnownNode(nodeId, nodeIds, `${path}.${field}[${index}]`);
    });
  }
}

function validateFailurePolicy(policy, index, nodeIds) {
  const path = `failurePolicies[${index}]`;
  requireObject(policy, path);
  validateRouteFields(policy, path, nodeIds);
}

function validateActiveFailureRoute(route, nodeIds) {
  if (route === null) return;
  requireObject(route, 'activeFailureRoute');
  validateRouteFields(route, 'activeFailureRoute', nodeIds);
  requireString(route.reason, 'activeFailureRoute.reason');
  requireInteger(route.generation, 'activeFailureRoute.generation');
}

function assertUniqueIds(values, collectionName) {
  const ids = new Set();
  values.forEach((value, index) => {
    if (ids.has(value.id)) {
      invalid(`${collectionName} contains duplicate ${collectionName.slice(0, -1)} id: ${value.id}`);
    }
    ids.add(value.id);
  });
  return ids;
}

function deepFreeze(value) {
  if (!value || typeof value !== 'object' || Object.isFrozen(value)) return value;
  Object.freeze(value);
  Object.values(value).forEach(deepFreeze);
  return value;
}

export function validateSnapshot(value) {
  requireObject(value, 'snapshot');
  if (value.schemaVersion !== SNAPSHOT_SCHEMA_VERSION) {
    invalid(`schemaVersion must be ${SNAPSHOT_SCHEMA_VERSION}`);
  }
  requireString(value.scopeId, 'scopeId');
  requireString(value.runId, 'runId');
  requireInteger(value.sequence, 'sequence');
  requireTimestamp(value.generatedAt, 'generatedAt');
  requireString(value.title, 'title');
  requireArray(value.nodes, 'nodes');
  requireArray(value.edges, 'edges');
  requireArray(value.failurePolicies, 'failurePolicies');
  requireArray(value.events, 'events');

  value.nodes.forEach(validateNode);
  const nodeIds = assertUniqueIds(value.nodes, 'nodes');
  value.edges.forEach((edge, index) => validateEdge(edge, index, nodeIds));
  assertUniqueIds(value.edges, 'edges');
  value.failurePolicies.forEach((policy, index) => {
    validateFailurePolicy(policy, index, nodeIds);
  });
  validateActiveFailureRoute(value.activeFailureRoute, nodeIds);
  value.events.forEach((event, index) => requireObject(event, `events[${index}]`));

  return deepFreeze(structuredClone(value));
}

export function graphKey(scopeId, runId) {
  return `${encodeURIComponent(scopeId)}::${encodeURIComponent(runId)}`;
}
