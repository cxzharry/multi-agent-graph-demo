#!/usr/bin/env node

const endpoint = process.env.EVENT_ENDPOINT || process.env.HERMES_EVENT_ENDPOINT || 'http://127.0.0.1:4173/events';

function parseArgs(argv) {
  const event = {payload: {}};
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--json') {
      return JSON.parse(argv[++i]);
    }
    if (!arg.startsWith('--')) continue;
    const key = arg.slice(2);
    const value = argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[++i] : true;
    if (key.startsWith('payload.')) event.payload[key.slice('payload.'.length)] = value;
    else event[key] = value;
  }
  return event;
}

const event = parseArgs(process.argv.slice(2));
event.timestamp ||= new Date().toISOString();

const response = await fetch(endpoint, {
  method: 'POST',
  headers: {'content-type': 'application/json'},
  body: JSON.stringify(event),
});

const text = await response.text();
if (!response.ok) {
  console.error(`Failed to emit event: ${response.status} ${response.statusText}`);
  console.error(text);
  process.exit(1);
}

console.log(text);
