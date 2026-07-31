import http from 'node:http';
import {createReadStream} from 'node:fs';
import {mkdir, readFile, stat, appendFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const PORT = Number(process.env.PORT || 4173);
const HOST = process.env.HOST || '0.0.0.0';
const DATA_DIR = path.join(__dirname, 'data');
const EVENTS_FILE = path.join(DATA_DIR, 'events.jsonl');
const DIST_DIR = path.join(__dirname, 'dist');

const clients = new Set();
const schemaFields = ['graphId', 'nodeId', 'type', 'status', 'activity', 'sessionId', 'agent', 'label', 'timestamp', 'payload'];

function sendJson(res, statusCode, data) {
  const body = JSON.stringify(data);
  res.writeHead(statusCode, {
    'content-type': 'application/json; charset=utf-8',
    'content-length': Buffer.byteLength(body),
    'access-control-allow-origin': '*',
  });
  res.end(body);
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let body = '';
    req.setEncoding('utf8');
    req.on('data', chunk => {
      body += chunk;
      if (body.length > 1024 * 1024) {
        reject(Object.assign(new Error('Request body too large'), {statusCode: 413}));
        req.destroy();
      }
    });
    req.on('end', () => resolve(body));
    req.on('error', reject);
  });
}

function normalizeEvent(input = {}) {
  const now = new Date().toISOString();
  const event = {};
  for (const field of schemaFields) event[field] = input[field] ?? null;
  event.graphId = event.graphId || 'default';
  event.type = event.type || 'event';
  event.status = event.status || 'running';
  event.timestamp = event.timestamp || now;
  event.payload = event.payload && typeof event.payload === 'object' ? event.payload : {};
  return event;
}

async function appendEvent(event) {
  await mkdir(DATA_DIR, {recursive: true});
  await appendFile(EVENTS_FILE, `${JSON.stringify(event)}\n`, 'utf8');
}

async function readEvents() {
  try {
    const text = await readFile(EVENTS_FILE, 'utf8');
    return text.split('\n').filter(Boolean).map(line => JSON.parse(line));
  } catch (error) {
    if (error.code === 'ENOENT') return [];
    throw error;
  }
}

function broadcast(event) {
  const message = `event: event\ndata: ${JSON.stringify(event)}\n\n`;
  for (const res of clients) res.write(message);
}

function handleStream(req, res) {
  res.writeHead(200, {
    'content-type': 'text/event-stream; charset=utf-8',
    'cache-control': 'no-cache, no-transform',
    connection: 'keep-alive',
    'access-control-allow-origin': '*',
  });
  res.write(': connected\n\n');
  clients.add(res);
  const keepAlive = setInterval(() => res.write(': ping\n\n'), 25000);
  req.on('close', () => {
    clearInterval(keepAlive);
    clients.delete(res);
  });
}

const mimeTypes = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.ico': 'image/x-icon',
};

async function serveStatic(req, res) {
  const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  const pathname = decodeURIComponent(url.pathname);
  const requestedPath = pathname === '/' ? '/index.html' : pathname;
  const filePath = path.normalize(path.join(DIST_DIR, requestedPath));

  if (!filePath.startsWith(DIST_DIR)) {
    sendJson(res, 403, {error: 'Forbidden'});
    return;
  }

  try {
    const info = await stat(filePath);
    const finalPath = info.isDirectory() ? path.join(filePath, 'index.html') : filePath;
    const type = mimeTypes[path.extname(finalPath)] || 'application/octet-stream';
    res.writeHead(200, {'content-type': type});
    createReadStream(finalPath).pipe(res);
  } catch (error) {
    const fallback = path.join(DIST_DIR, 'index.html');
    try {
      await stat(fallback);
      res.writeHead(200, {'content-type': mimeTypes['.html']});
      createReadStream(fallback).pipe(res);
    } catch {
      sendJson(res, 404, {error: 'Not found. Run npm run build to create dist/.'});
    }
  }
}

const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);

    if (req.method === 'OPTIONS') {
      res.writeHead(204, {
        'access-control-allow-origin': '*',
        'access-control-allow-methods': 'GET,POST,OPTIONS',
        'access-control-allow-headers': 'content-type',
      });
      res.end();
      return;
    }

    if (req.method === 'POST' && url.pathname === '/events') {
      const body = await readBody(req);
      const parsed = body ? JSON.parse(body) : {};
      const event = normalizeEvent(parsed);
      await appendEvent(event);
      broadcast(event);
      sendJson(res, 201, event);
      return;
    }

    if (req.method === 'GET' && url.pathname === '/events') {
      const events = await readEvents();
      sendJson(res, 200, events);
      return;
    }

    if (req.method === 'GET' && url.pathname === '/stream') {
      handleStream(req, res);
      return;
    }

    if (req.method === 'GET' || req.method === 'HEAD') {
      await serveStatic(req, res);
      return;
    }

    sendJson(res, 405, {error: 'Method not allowed'});
  } catch (error) {
    const statusCode = error.statusCode || (error instanceof SyntaxError ? 400 : 500);
    sendJson(res, statusCode, {error: error.message || 'Internal server error'});
  }
});

server.listen(PORT, HOST, () => {
  console.log(`Multi-agent graph demo server listening at http://${HOST}:${PORT}`);
  console.log(`Events: POST /events, GET /events, SSE /stream, file ${EVENTS_FILE}`);
});
