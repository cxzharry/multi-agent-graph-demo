import http from 'node:http';
import {createReadStream} from 'node:fs';
import {stat} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

import {SnapshotValidationError, graphKey} from '../shared/role-graph.js';
import {GraphStore, StaleSequenceError} from './graph-store.js';

const moduleDirectory = path.dirname(fileURLToPath(import.meta.url));
const repositoryRoot = path.dirname(moduleDirectory);

const mimeTypes = {
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.ico': 'image/x-icon',
  '.jpeg': 'image/jpeg',
  '.jpg': 'image/jpeg',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.webp': 'image/webp',
};

function sendJson(response, statusCode, data) {
  const body = JSON.stringify(data);
  response.writeHead(statusCode, {
    'access-control-allow-origin': '*',
    'content-length': Buffer.byteLength(body),
    'content-type': 'application/json; charset=utf-8',
  });
  response.end(body);
}

function readBody(request) {
  return new Promise((resolve, reject) => {
    let body = '';
    request.setEncoding('utf8');
    request.on('data', chunk => {
      body += chunk;
      if (body.length > 1024 * 1024) {
        reject(Object.assign(new Error('Request body too large'), {statusCode: 413}));
        request.destroy();
      }
    });
    request.on('end', () => resolve(body));
    request.on('error', reject);
  });
}

function requireGraphSelection(url) {
  const scopeId = url.searchParams.get('scopeId');
  const runId = url.searchParams.get('runId');
  if (!scopeId || !runId) {
    throw Object.assign(new Error('scopeId and runId are required'), {statusCode: 400});
  }
  return {scopeId, runId};
}

function addStreamClient(request, response, clients, key) {
  response.writeHead(200, {
    'access-control-allow-origin': '*',
    'cache-control': 'no-cache, no-transform',
    connection: 'keep-alive',
    'content-type': 'text/event-stream; charset=utf-8',
  });
  response.write(': connected\n\n');

  let subscribers = clients.get(key);
  if (!subscribers) {
    subscribers = new Set();
    clients.set(key, subscribers);
  }
  subscribers.add(response);

  const keepAlive = setInterval(() => response.write(': ping\n\n'), 25000);
  request.on('close', () => {
    clearInterval(keepAlive);
    subscribers.delete(response);
    if (subscribers.size === 0) clients.delete(key);
  });
}

function broadcast(clients, snapshot) {
  const key = graphKey(snapshot.scopeId, snapshot.runId);
  const message = `event: snapshot\ndata: ${JSON.stringify(snapshot)}\n\n`;
  for (const response of clients.get(key) ?? []) response.write(message);
}

async function serveStatic(request, response, distDirectory) {
  const url = new URL(request.url, `http://${request.headers.host || 'localhost'}`);
  const requestedPath = decodeURIComponent(url.pathname);
  const relativePath = requestedPath === '/' ? 'index.html' : requestedPath.slice(1);
  const filePath = path.resolve(distDirectory, relativePath);
  const allowedPrefix = `${path.resolve(distDirectory)}${path.sep}`;

  if (!filePath.startsWith(allowedPrefix)) {
    sendJson(response, 403, {error: 'Forbidden'});
    return;
  }

  let finalPath = filePath;
  try {
    const info = await stat(finalPath);
    if (info.isDirectory()) finalPath = path.join(finalPath, 'index.html');
    await stat(finalPath);
  } catch {
    finalPath = path.join(distDirectory, 'index.html');
    try {
      await stat(finalPath);
    } catch {
      sendJson(response, 404, {error: 'Not found. Run npm run build to create dist/.'});
      return;
    }
  }

  response.writeHead(200, {
    'content-type': mimeTypes[path.extname(finalPath)] || 'application/octet-stream',
  });
  if (request.method === 'HEAD') {
    response.end();
    return;
  }
  createReadStream(finalPath).pipe(response);
}

export function createApp({
  dataFile = path.join(repositoryRoot, 'data', 'snapshots.jsonl'),
  distDirectory = path.join(repositoryRoot, 'dist'),
  ingestToken,
} = {}) {
  const store = new GraphStore(dataFile);
  const ready = store.initialize();
  const clients = new Map();

  return http.createServer(async (request, response) => {
    try {
      const url = new URL(request.url, `http://${request.headers.host || 'localhost'}`);

      if (request.method === 'OPTIONS') {
        response.writeHead(204, {
          'access-control-allow-headers': 'authorization,content-type',
          'access-control-allow-methods': 'GET,POST,OPTIONS',
          'access-control-allow-origin': '*',
        });
        response.end();
        return;
      }

      if (request.method === 'GET' && url.pathname === '/api/health') {
        sendJson(response, 200, {
          service: 'herdr-role-graph-viewer',
          schemaVersion: 'role-graph/v1',
        });
        return;
      }

      if (request.method === 'POST' && url.pathname === '/api/snapshots') {
        if (
          ingestToken &&
          request.headers.authorization !== `Bearer ${ingestToken}`
        ) {
          sendJson(response, 401, {error: 'Unauthorized'});
          return;
        }

        const body = await readBody(request);
        const snapshot = await store.append(JSON.parse(body || '{}'));
        broadcast(clients, snapshot);
        sendJson(response, 202, snapshot);
        return;
      }

      if (request.method === 'GET' && url.pathname === '/api/graphs') {
        await ready;
        sendJson(response, 200, store.listGraphs());
        return;
      }

      if (request.method === 'GET' && url.pathname === '/api/snapshot') {
        const {scopeId, runId} = requireGraphSelection(url);
        await ready;
        const snapshot = store.getSnapshot(scopeId, runId);
        if (!snapshot) {
          sendJson(response, 404, {error: 'Snapshot not found'});
          return;
        }
        sendJson(response, 200, snapshot);
        return;
      }

      if (request.method === 'GET' && url.pathname === '/api/stream') {
        const {scopeId, runId} = requireGraphSelection(url);
        await ready;
        addStreamClient(request, response, clients, graphKey(scopeId, runId));
        return;
      }

      if (url.pathname.startsWith('/api/')) {
        sendJson(response, 404, {error: 'Not found'});
        return;
      }

      if (request.method === 'GET' || request.method === 'HEAD') {
        await serveStatic(request, response, distDirectory);
        return;
      }

      sendJson(response, 405, {error: 'Method not allowed'});
    } catch (error) {
      const statusCode =
        error.statusCode ||
        (error instanceof SnapshotValidationError || error instanceof SyntaxError
          ? 400
          : error instanceof StaleSequenceError
            ? 409
            : 500);
      sendJson(response, statusCode, {error: error.message || 'Internal server error'});
    }
  });
}
