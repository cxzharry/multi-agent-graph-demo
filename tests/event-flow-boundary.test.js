import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';

import {describe, expect, test} from 'vitest';

import {validateSnapshot} from '../shared/role-graph.js';

const repositoryRoot = fileURLToPath(new URL('..', import.meta.url));

function projectFlow(caseName) {
  const script = String.raw`
import json
import sys

from adapters.herdr.flow_projection import project_flow


def assignment(identifier, role, slot):
    return {"id": identifier, "role": role, "slot": slot, "task": role}


source, target = {
    "artifact": (
        assignment("implementation:g1", "Implementation", "P2"),
        assignment("integration:g1", "Integration", "P5"),
    ),
    "rework": (
        assignment("independent-qc:g1", "Independent QC", "P6"),
        assignment("implementation:g2", "Implementation", "P4"),
    ),
}[sys.argv[1]]
kind = "ARTIFACT_HANDOFF" if sys.argv[1] == "artifact" else "REWORK_ROUTE"
event = {
    "schemaVersion": "role-graph-event/v1",
    "eventId": f"evt-{sys.argv[1]}",
    "workspaceId": "wK",
    "runId": "run-1",
    "at": "2026-08-07T03:30:00Z",
    "kind": kind,
    "generation": 2,
    "source": source,
    "target": target,
}
if kind == "ARTIFACT_HANDOFF":
    event["artifact"] = {"commit": "candidate"}
else:
    event["reason"] = "Browser assertion failed"

print(json.dumps(project_flow(
    events=[event],
    live_agents=[],
    p1_session_id="session-p1",
)))
`;
  return JSON.parse(
    execFileSync('python3', ['-B', '-c', script, caseName], {
      cwd: repositoryRoot,
      encoding: 'utf8',
    }),
  );
}

function snapshot(projection) {
  return {
    schemaVersion: 'role-graph/v1',
    scopeId: 'herdr:wK',
    runId: 'run-1',
    sequence: 1,
    generatedAt: '2026-08-07T03:30:00Z',
    title: 'Event flow boundary',
    nodes: projection.nodes,
    edges: projection.edges,
    failurePolicies: [],
    activeFailureRoute: projection.activeFailureRoute,
    events: projection.timeline,
    relationshipMode: 'event-backed',
  };
}

describe('Python event flow to JavaScript snapshot boundary', () => {
  test('validates an artifact handoff projection', () => {
    const projection = projectFlow('artifact');

    expect(projection.edges).toContainEqual(
      expect.objectContaining({kind: 'forward', status: 'passed'}),
    );
    expect(() => validateSnapshot(snapshot(projection))).not.toThrow();
  });

  test('validates a rework projection and active route', () => {
    const projection = projectFlow('rework');

    expect(projection.edges).toContainEqual(
      expect.objectContaining({kind: 'return', status: 'active'}),
    );
    expect(projection.activeFailureRoute).toEqual(
      expect.objectContaining({
        gateNodeId: 'independent-qc:g1',
        returnToNodeId: 'implementation:g2',
      }),
    );
    expect(() => validateSnapshot(snapshot(projection))).not.toThrow();
  });
});
