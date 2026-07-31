#!/usr/bin/env node

const endpoint = process.env.EVENT_ENDPOINT || process.env.HERMES_EVENT_ENDPOINT || 'http://127.0.0.1:4173/events';
const graphId = process.env.GRAPH_ID || `demo-${Date.now()}`;
const delayMs = Number(process.env.SIM_DELAY_MS || 700);

const sequence = [
  {nodeId: 'bibi', type: 'orchestration', status: 'running', activity: 'Receiving user task and drafting execution graph', sessionId: 'tg:1786660169', agent: 'Bibi', label: 'Bibi starts orchestration'},
  {nodeId: 'codex', type: 'handoff', status: 'running', activity: 'Implementing backend event ingestion', sessionId: 'codex:pane-01', agent: 'Codex', label: 'Bibi → Codex'},
  {nodeId: 'codex', type: 'completion', status: 'done', activity: 'Server and hook scripts implemented', sessionId: 'codex:pane-01', agent: 'Codex', label: 'Codex completes implementation'},
  {nodeId: 'claude', type: 'handoff', status: 'running', activity: 'Running QC and verification checks', sessionId: 'claude:pane-01', agent: 'Claude', label: 'Codex → Claude'},
  {nodeId: 'claude', type: 'completion', status: 'done', activity: 'Build and ingestion checks passed', sessionId: 'claude:pane-01', agent: 'Claude', label: 'Claude completes QC'},
  {nodeId: 'final', type: 'delivery', status: 'done', activity: 'Final event stream ready for UI consumption', sessionId: 'artifact:demo', agent: 'Final', label: 'Claude → Final'},
];

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

async function emit(event, index) {
  const body = {
    graphId,
    timestamp: new Date().toISOString(),
    payload: {step: index + 1, total: sequence.length},
    ...event,
  };
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {'content-type': 'application/json'},
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`POST ${endpoint} failed: ${response.status} ${await response.text()}`);
  console.log(`${body.label} (${body.status})`);
}

for (let i = 0; i < sequence.length; i += 1) {
  await emit(sequence[i], i);
  if (i < sequence.length - 1) await sleep(delayMs);
}

console.log(`Simulated graph run ${graphId}`);
