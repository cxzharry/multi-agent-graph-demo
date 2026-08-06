import path from 'node:path';
import {fileURLToPath} from 'node:url';

import {createApp} from './server/app.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

function option(name, fallback) {
  const index = process.argv.indexOf(name);
  if (index === -1) return fallback;
  const value = process.argv[index + 1];
  if (!value || value.startsWith('--')) {
    throw new Error(`${name} requires a value`);
  }
  return value;
}

const PORT = Number(option('--port', process.env.PORT || 4173));
if (!Number.isInteger(PORT) || PORT < 0 || PORT > 65535) {
  throw new Error('--port must be an integer between 0 and 65535');
}
const RUNTIME_FINGERPRINT = option('--runtime-fingerprint', 'unmanaged');
const HOST = process.env.HOST || '0.0.0.0';
const DATA_FILE =
  process.env.ROLE_GRAPH_DATA_FILE || path.join(__dirname, 'data', 'snapshots.jsonl');

const server = createApp({
  dataFile: DATA_FILE,
  ingestToken: process.env.ROLE_GRAPH_INGEST_TOKEN,
  runtimeFingerprint: RUNTIME_FINGERPRINT,
});
server.listen(PORT, HOST, () => {
  console.log(`Role graph viewer listening at http://${HOST}:${PORT}`);
  console.log(`Snapshots: POST /api/snapshots, SSE /api/stream, file ${DATA_FILE}`);
});
