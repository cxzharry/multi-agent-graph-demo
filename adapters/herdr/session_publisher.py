#!/usr/bin/env python3
"""Publish the current workspace's live Herdr agent session graph."""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from adapters.herdr.observed_events import ObservationError, ObservationLedger
from adapters.herdr.flow_projection import project_flow
from adapters.herdr.publisher import (
    FlowRuntime,
    PublisherError,
    _positive_interval,
    _space_name_argument,
    heartbeat_presence,
    load_current_snapshot,
    publish_snapshot,
)


AGENT_STATUSES = {
    "working": "running",
    "done": "passed",
    "blocked": "blocked",
    "idle": "pending",
}


def list_agents() -> list[dict]:
    """Return agents from the sole allowed read-only Herdr command."""
    completed = subprocess.run(
        ("herdr", "agent", "list"),
        capture_output=True,
        text=True,
        check=True,
    )
    value = json.loads(completed.stdout)
    agents = value.get("result", {}).get("agents")
    if not isinstance(agents, list):
        raise PublisherError("herdr agent list returned no agent list")
    return agents


def _agent_identity(agent: dict) -> tuple[str, str] | None:
    pane_id = agent.get("pane_id")
    session_id = agent.get("agent_session", {}).get("value")
    if not isinstance(pane_id, str) or not pane_id:
        return None
    if not isinstance(session_id, str) or not session_id:
        return None
    return pane_id, session_id


def select_workspace_agents(
    raw_agents: list[dict],
    workspace_id: str,
) -> list[dict]:
    """Filter exact workspace agents and retain the newest duplicate record."""
    selected: dict[tuple[str, str], dict] = {}
    for agent in raw_agents:
        if not isinstance(agent, dict) or agent.get("workspace_id") != workspace_id:
            continue
        identity = _agent_identity(agent)
        if identity is None:
            continue
        previous = selected.get(identity)
        revision = agent.get("revision", 0)
        previous_revision = previous.get("revision", 0) if previous else -1
        if previous is None or revision >= previous_revision:
            selected[identity] = agent
    return [selected[key] for key in sorted(selected)]


def _node_id(agent: dict) -> str:
    pane_id, session_id = _agent_identity(agent) or ("", "")
    identity = session_id + "\0" + pane_id
    return f"agent-{identity.encode('utf-8').hex()}"


def _node_status(agent: dict) -> str:
    return AGENT_STATUSES.get(str(agent.get("agent_status", "")).lower(), "stale")


def build_session_snapshot(
    agents: list[dict],
    workspace_id: str,
    space_name: str,
    p1_session_id: str,
    p1_pane_id: str,
    sequence: int,
    *,
    ledger: ObservationLedger | None = None,
    observed_at: str | None = None,
    publisher_fingerprint: str = "unmanaged",
    flow_events: list[dict] | None = None,
    prior_nodes: list[dict] | None = None,
    flow_telemetry: dict | None = None,
) -> dict:
    """Build one P1-rooted observed graph from exact workspace-local agents.

    Session mode has nodes and statuses but no trusted workflow-edge source, so
    it never fabricates relationships: ``edges``, ``failurePolicies`` and
    ``activeFailureRoute`` are empty. When a ledger is supplied it turns the
    already-built nodes into bounded, timestamped lifecycle events.
    """
    local_agents = select_workspace_agents(agents, workspace_id)
    p1 = next(
        (
            agent
            for agent in local_agents
            if _agent_identity(agent) == (p1_pane_id, p1_session_id)
        ),
        None,
    )
    if p1 is None:
        raise PublisherError("current P1 pane and session were not found")
    ordered = [p1] + [agent for agent in local_agents if agent is not p1]
    nodes = []
    for index, agent in enumerate(ordered):
        name = agent.get("name") or agent.get("agent") or "Herdr agent"
        nodes.append(
            {
                "id": "orchestrator" if index == 0 else _node_id(agent),
                "role": "Orchestrator" if index == 0 else name,
                "assignee": name,
                "status": _node_status(agent),
                "task": (
                    "Coordinate current Herdr session"
                    if index == 0
                    else "Participate in current Herdr session"
                ),
                "generation": 1,
                "layer": 0 if index == 0 else 1,
            }
        )
    snapshot = {
        "schemaVersion": "role-graph/v1",
        "scopeId": f"herdr:{workspace_id}",
        "runId": p1_session_id,
        "flowId": "live-session",
        "spaceName": _space_name_argument(space_name),
        "shortName": "current",
        "publisherFingerprint": publisher_fingerprint,
        "sequence": sequence,
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "title": f"Current Herdr session — {space_name}",
        "nodes": nodes,
        "edges": [],
        "failurePolicies": [],
        "activeFailureRoute": None,
        "events": _observed_events(ledger, nodes, observed_at),
        "relationshipMode": "unavailable",
    }
    if flow_events is not None:
        projection = project_flow(
            events=flow_events,
            live_agents=local_agents,
            p1_session_id=p1_session_id,
            prior_nodes=prior_nodes,
        )
        snapshot.update(
            {
                "nodes": projection["nodes"],
                "edges": projection["edges"],
                "failurePolicies": [],
                "activeFailureRoute": projection["activeFailureRoute"],
                "events": projection["timeline"],
                "relationshipMode": "event-backed",
                "telemetry": copy.deepcopy(
                    flow_telemetry or projection["telemetry"]
                ),
            }
        )
    return snapshot


def _observed_events(
    ledger: ObservationLedger | None,
    nodes: list[dict],
    observed_at: str | None,
) -> list[dict]:
    """Return the ledger's bounded lifecycle history for the current nodes."""
    if ledger is None:
        return []
    ledger.observe(nodes, observed_at=observed_at)
    return ledger.events


def _projection(snapshot: dict) -> dict:
    value = copy.deepcopy(snapshot)
    value.pop("sequence", None)
    value.pop("generatedAt", None)
    return value


def publish_if_changed(
    agents: list[dict],
    workspace_id: str,
    space_name: str,
    p1_session_id: str,
    p1_pane_id: str,
    endpoint: str,
    token: str | None,
    last_snapshot: dict | None,
    *,
    ledger: ObservationLedger | None = None,
    observed_at: str | None = None,
    publisher_fingerprint: str = "unmanaged",
    sequence_floor: int = 1,
    flow_events: list[dict] | None = None,
    flow_telemetry: dict | None = None,
) -> dict:
    """Publish only projected topology, status, or lifecycle-event changes."""
    next_sequence = 1 if last_snapshot is None else last_snapshot["sequence"] + 1
    sequence = max(sequence_floor, next_sequence)
    snapshot = build_session_snapshot(
        agents,
        workspace_id,
        space_name,
        p1_session_id,
        p1_pane_id,
        sequence,
        ledger=ledger,
        observed_at=observed_at,
        publisher_fingerprint=publisher_fingerprint,
        flow_events=flow_events,
        prior_nodes=last_snapshot.get("nodes") if last_snapshot else None,
        flow_telemetry=flow_telemetry,
    )
    if last_snapshot is not None and _projection(snapshot) == _projection(
        last_snapshot
    ):
        return last_snapshot
    publish_snapshot(snapshot, endpoint, token)
    return snapshot


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--space-name", required=True, type=_space_name_argument)
    parser.add_argument("--p1-session-id", required=True)
    parser.add_argument("--p1-pane-id", required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--token")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--runtime-fingerprint", default="unmanaged")
    parser.add_argument("--flow-journal", type=Path)
    parser.add_argument("--sequence-floor", type=_positive_sequence, default=1)
    parser.add_argument("--interval", type=_positive_interval, default=2.0)
    return parser


def _positive_sequence(value: str) -> int:
    sequence = int(value)
    if sequence <= 0:
        raise argparse.ArgumentTypeError("sequence floor must be greater than zero")
    return sequence


def main() -> int:
    args = _parser().parse_args()
    scope_id = f"herdr:{args.workspace_id}"
    seed = load_current_snapshot(
        args.endpoint,
        args.token,
        scope_id,
        args.p1_session_id,
    )
    sequence_floor = args.sequence_floor
    ledger = ObservationLedger()
    flow_runtime = (
        FlowRuntime(
            args.flow_journal,
            workspace_id=args.workspace_id,
            run_id=args.p1_session_id,
        )
        if args.flow_journal is not None
        else None
    )
    if seed is not None:
        seed_sequence = seed.get("sequence")
        if (
            isinstance(seed_sequence, int)
            and not isinstance(seed_sequence, bool)
            and seed_sequence >= 0
        ):
            sequence_floor = max(sequence_floor, seed_sequence + 1)
        nodes = seed.get("nodes")
        events = seed.get("events")
        if flow_runtime is None and isinstance(nodes, list) and isinstance(events, list):
            try:
                ledger = ObservationLedger.restore(nodes, events)
            except ObservationError:
                ledger = ObservationLedger()
    last_snapshot = None
    while True:
        try:
            if flow_runtime is not None:
                flow_runtime.poll()
            agents = select_workspace_agents(list_agents(), args.workspace_id)
            last_snapshot = publish_if_changed(
                agents,
                args.workspace_id,
                args.space_name,
                args.p1_session_id,
                args.p1_pane_id,
                args.endpoint,
                args.token,
                last_snapshot,
                ledger=ledger,
                publisher_fingerprint=args.runtime_fingerprint,
                sequence_floor=sequence_floor,
                flow_events=flow_runtime.events if flow_runtime else None,
                flow_telemetry=flow_runtime.telemetry if flow_runtime else None,
            )
            heartbeat_presence(args.endpoint, args.token, last_snapshot)
        except (
            OSError,
            PublisherError,
            json.JSONDecodeError,
            subprocess.SubprocessError,
        ) as error:
            print(json.dumps({"status": "error", "error": str(error)}), file=sys.stderr)
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
