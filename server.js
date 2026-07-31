import path from 'node:path';
import {fileURLToPath} from 'node:url';

import {createApp} from './server/app.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const PORT = Number(process.env.PORT || 4173);
const HOST = process.env.HOST || '0.0.0.0';
const DATA_FILE =
  process.env.ROLE_GRAPH_DATA_FILE || path.join(__dirname, 'data', 'snapshots.jsonl');

const server = createApp({
  dataFile: DATA_FILE,
  ingestToken: process.env.ROLE_GRAPH_INGEST_TOKEN,
});
server.listen(PORT, HOST, () => {
  console.log(`Role graph viewer listening at http://${HOST}:${PORT}`);
  console.log(`Snapshots: POST /api/snapshots, SSE /api/stream, file ${DATA_FILE}`);
});
