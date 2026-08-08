#!/usr/bin/env python3
"""Publish one supplied Herdr workspace state as an immutable role graph."""

from __future__ import annotations

import argparse
import copy
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from adapters.herdr.observed_events import ObservationLedger
from adapters.herdr.flow_journal import FlowJournalReader, JournalError
from adapters.herdr.flow_projection import project_flow


EVENT_LIMIT = 50
LANE_STATUSES = {
    "READY": "pending",
    "ACTIVE": "running",
    "ACCEPTED": "passed",
    "PASS": "passed",
    "FINDING": "failed",
    "BLOCKED": "blocked",
    "RETRYING": "retrying",
    "LOST": "stale",
    "SUPERSEDED": "skipped",
}
SLOT_STATUSES = {
    "ACTIVE": "running",
    "COLD": "pending",
    "IDLE": "pending",
    "STARTING": "running",
    "WARMING": "running",
    "BUSY": "running",
    "RUNNING": "running",
    "DONE": "passed",
    "START_FAILED": "failed",
    "BLOCKED": "blocked",
    "RETRYING": "retrying",
    "LOST": "stale",
    "STALE": "stale",
    "SKIPPED": "skipped",
}


class PublisherError(ValueError):
    """Raised when supplied state cannot produce a role-graph snapshot."""


class FlowRuntime:
    """Retain validated journal facts and fail open with explicit telemetry."""

    def __init__(self, path: Path, *, workspace_id: str, run_id: str):
        self.reader = FlowJournalReader(
            path, workspace_id=workspace_id, run_id=run_id
        )
        self.events: list[dict] = []
        self.telemetry = {"status": "ok"}

    def poll(self) -> bool:
        previous_telemetry = copy.deepcopy(self.telemetry)
        try:
            new_events = self.reader.read_new()
        except (JournalError, OSError) as error:
            recovered_events = getattr(error, "recovered_events", [])
            self.events.extend(recovered_events)
            self.telemetry = {
                "status": "degraded",
                **(
                    {"lastValidAt": self.events[-1]["at"]}
                    if self.events
                    else {}
                ),
                "reason": str(error),
            }
            return bool(recovered_events) or self.telemetry != previous_telemetry

        self.events.extend(new_events)
        self.telemetry = {
            "status": "ok",
            **(
                {"lastValidAt": self.events[-1]["at"]}
                if self.events
                else {}
            ),
        }
        return bool(new_events) or self.telemetry != previous_telemetry


def _lane_chains(
    state: dict,
) -> tuple[list[str], dict[str, str], dict[str, list[str]]]:
    lanes = state.get("lanes", {})
    successors: dict[str, list[str]] = {}
    non_roots: set[str] = set()
    for lane_id, lane in lanes.items():
        predecessor = lane.get("supersedes")
        if predecessor is None:
            continue
        if predecessor not in lanes:
            raise PublisherError(
                f"lane {lane_id} supersedes unknown lane {predecessor}"
            )
        successors.setdefault(predecessor, []).append(lane_id)
        non_roots.add(lane_id)

    roots = sorted(set(lanes) - non_roots)
    member_to_tip: dict[str, str] = {}
    root_to_members: dict[str, list[str]] = {}
    visited_all: set[str] = set()
    for root in roots:
        current = root
        members = [root]
        seen = {root}
        while current in successors:
            choices = sorted(successors[current])
            if len(choices) != 1:
                raise PublisherError(
                    f"lane {current} has multiple supersession successors: "
                    f"{', '.join(choices)}"
                )
            current = choices[0]
            if current in seen:
                raise PublisherError(f"supersession cycle includes lane {current}")
            seen.add(current)
            members.append(current)
        for member in members:
            member_to_tip[member] = current
        root_to_members[root] = members
        visited_all.update(members)
    if visited_all != set(lanes):
        unresolved = ", ".join(sorted(set(lanes) - visited_all))
        raise PublisherError(f"supersession cycle includes lanes: {unresolved}")
    return roots, member_to_tip, root_to_members


def _lane_definition(
    state: dict,
    root: str,
    tip: str,
    lane: dict,
    layer: int,
    prefix: str,
) -> dict:
    label = root.replace("_", " ").replace("-", " ").title()
    return {
        "id": _lane_node_id(prefix, root),
        "role": lane.get("role") or label,
        "assignee": _live_lane_assignee(state, tip, lane, "Unassigned"),
        "layer": layer,
        "task": lane.get("task_summary") or label,
        "source": {"type": "lane", "id": tip},
    }


def _lane_assignee(lane: dict, fallback: str) -> str:
    return lane.get("slot") or lane.get("assignee") or fallback


def _live_lane_assignee(
    state: dict,
    lane_id: str,
    lane: dict,
    fallback: str,
) -> str:
    for slot_id, slot in sorted(state.get("slots", {}).items()):
        if slot.get("lane_id") == lane_id:
            return slot_id
    return _lane_assignee(lane, fallback)


def _lane_node_id(prefix: str, lane_id: str) -> str:
    return f"{prefix}-{lane_id.encode('utf-8').hex()}"


def _allocate_id(preferred: str, used_ids: set[str]) -> str:
    candidate = preferred
    suffix = 2
    while candidate in used_ids:
        candidate = f"{preferred}-{suffix}"
        suffix += 1
    used_ids.add(candidate)
    return candidate


def _allocate_live_node_id(lane_id: str, used_ids: set[str]) -> str:
    return _allocate_id(_lane_node_id("live", lane_id), used_ids)


def synthesize_manifest(state: dict) -> dict:
    """Derive a deterministic operational manifest without writing it."""
    run_id = state.get("run", {}).get("contract_id")
    if not isinstance(run_id, str) or not run_id:
        raise PublisherError("run.contract_id is required")
    roots, member_to_tip, _ = _lane_chains(state)
    lanes = state.get("lanes", {})
    nodes = [
        {
            "id": "orchestrator",
            "role": "Orchestrator",
            "assignee": "P1",
            "layer": 0,
            "task": state.get("slots", {})
            .get("P1", {})
            .get("task_summary", "Route ready work"),
            "source": {"type": "slot", "id": "P1"},
        }
    ]
    for root in roots:
        tip = member_to_tip[root]
        nodes.append(_lane_definition(state, root, tip, lanes[tip], 1, "auto"))
    return {
        "schemaVersion": "herdr-role-graph-manifest/v1",
        "flowId": "auto-operational",
        "title": f"Auto operational view - {run_id}",
        "nodes": nodes,
        # Synthetic mode observes nodes and statuses but has no trusted
        # workflow-edge source, so it fabricates no relationships. P1 stays in
        # layer 0 and lanes in layer 1 for a readable disconnected layout.
        "edges": [],
        "failurePolicies": [],
    }


def _materialize_manifest(state: dict, manifest: dict) -> tuple[dict, dict[str, str]]:
    materialized = copy.deepcopy(manifest)
    roots, member_to_tip, root_to_members = _lane_chains(state)
    lanes = state.get("lanes", {})
    member_to_root = {
        member: root
        for root, members in root_to_members.items()
        for member in members
    }
    lane_nodes: dict[str, str] = {}
    mapped_roots: set[str] = set()
    authored_nodes = materialized.get("nodes", [])
    p1_nodes = [
        node
        for node in authored_nodes
        if node.get("source", {}).get("type") == "slot"
        and node.get("source", {}).get("id") == "P1"
    ]
    used_node_ids = {node["id"] for node in authored_nodes}

    for node in authored_nodes:
        source = node.get("source", {})
        if source.get("type") != "lane":
            continue
        source_id = source.get("id")
        if source_id not in member_to_tip:
            continue
        root = member_to_root[source_id]
        tip = member_to_tip[source_id]
        source["id"] = tip
        node["assignee"] = _live_lane_assignee(
            state, tip, lanes[tip], node["assignee"]
        )
        mapped_roots.add(root)
        for member in root_to_members[root]:
            lane_nodes.setdefault(member, node["id"])

    additions = []
    for root in roots:
        if root in mapped_roots:
            continue
        tip = member_to_tip[root]
        addition = _lane_definition(state, root, tip, lanes[tip], 1, "live")
        addition["id"] = _allocate_live_node_id(root, used_node_ids)
        additions.append(addition)
        for member in root_to_members[root]:
            lane_nodes[member] = addition["id"]
    authored_nodes.extend(additions)

    if len(p1_nodes) == 1:
        source_id = p1_nodes[0]["id"]
        edges = materialized.setdefault("edges", [])
        used_edge_ids = {edge["id"] for edge in edges}
        for addition in additions:
            preferred = f"control-{source_id}-{addition['id']}"
            edges.append(
                {
                    "id": _allocate_id(preferred, used_edge_ids),
                    "source": source_id,
                    "target": addition["id"],
                    "kind": "forward",
                    "status": "active",
                }
            )
    return materialized, lane_nodes


def build_snapshot(
    state: dict,
    manifest: dict,
    workspace_id: str,
    space_name: str,
    *,
    publisher_fingerprint: str = "unmanaged",
    flow_events: list[dict] | None = None,
    flow_telemetry: dict | None = None,
    synthetic: bool | None = None,
) -> dict:
    """Return one role-graph/v1 snapshot without I/O."""
    if state.get("workspace_id") != workspace_id:
        raise PublisherError(
            "workspace_id does not match the supplied workspace state"
        )
    space_name = _space_name(space_name)
    if manifest.get("schemaVersion") != "herdr-role-graph-manifest/v1":
        raise PublisherError("unsupported manifest schemaVersion")

    revision = _revision(state)
    run_id = state.get("run", {}).get("contract_id")
    if not isinstance(run_id, str) or not run_id:
        raise PublisherError("run.contract_id is required")

    materialized, lane_nodes = _materialize_manifest(state, manifest)
    resolved = {}
    nodes = []
    for definition in materialized.get("nodes", []):
        record, source_type = _resolve_source(state, definition)
        resolved[definition["id"]] = (record, source_type)
        node = {
            "id": definition["id"],
            "role": definition["role"],
            "assignee": definition["assignee"],
            "status": _status(record, source_type),
            "task": record.get("task_summary") or definition.get("task", ""),
            "generation": _generation(record),
        }
        if "layer" in definition:
            node["layer"] = definition["layer"]
        nodes.append(node)

    policies = copy.deepcopy(materialized.get("failurePolicies", []))
    active_route = _active_failure_route(policies, resolved, materialized)
    generated_at = _generated_at(state)

    snapshot = {
        "schemaVersion": "role-graph/v1",
        "scopeId": f"herdr:{workspace_id}",
        "runId": run_id,
        "flowId": materialized["flowId"],
        "spaceName": space_name,
        "publisherFingerprint": publisher_fingerprint,
        "sequence": revision,
        "generatedAt": generated_at,
        "title": materialized.get(
            "title", materialized.get("flowId", run_id)
        ),
        "nodes": nodes,
        "edges": copy.deepcopy(materialized.get("edges", [])),
        "failurePolicies": policies,
        "activeFailureRoute": active_route,
        "events": _events(state, lane_nodes, generated_at),
    }
    if synthetic is None:
        synthetic = materialized.get("flowId") == "auto-operational"
    snapshot["relationshipMode"] = "unavailable" if synthetic else "declared"
    if flow_events is not None:
        projection = project_flow(
            events=flow_events,
            live_agents=_control_live_agents(state),
            p1_session_id=_control_p1_session_id(state),
            prior_nodes=None,
        )
        telemetry = copy.deepcopy(flow_telemetry or projection["telemetry"])
        if synthetic:
            _apply_synthetic_flow(snapshot, projection)
            snapshot["relationshipMode"] = "event-backed"
        else:
            _apply_declared_flow(snapshot, projection)
        snapshot["events"] = projection["timeline"]
        snapshot["telemetry"] = telemetry
        latest = _timestamp(telemetry.get("lastValidAt"))
        current = _timestamp(snapshot["generatedAt"])
        if latest is not None and (current is None or latest > current):
            snapshot["generatedAt"] = _format_timestamp(latest)
    return snapshot


def _control_p1_session_id(state: dict) -> str:
    candidates = (
        state.get("controller", {}).get("session_id"),
        state.get("slots", {}).get("P1", {}).get("session_id"),
    )
    return next(
        (value for value in candidates if isinstance(value, str) and value),
        "unavailable-p1-session",
    )


def _control_live_agents(state: dict) -> list[dict]:
    agents = []
    for slot_id, slot in sorted(state.get("slots", {}).items()):
        session_id = slot.get("session_id")
        pane_id = slot.get("pane_id")
        if not isinstance(session_id, str) or not session_id:
            continue
        if not isinstance(pane_id, str) or not pane_id:
            continue
        status = str(slot.get("status", "")).upper()
        agent_status = (
            "working"
            if status in {"ACTIVE", "STARTING", "WARMING", "BUSY", "RUNNING"}
            else "done"
            if status == "DONE"
            else "idle"
            if status in {"COLD", "IDLE"}
            else "blocked"
            if status == "BLOCKED"
            else "unknown"
        )
        agents.append(
            {
                "workspace_id": state.get("workspace_id"),
                "pane_id": pane_id,
                "name": slot.get("role_name") or slot_id,
                "agent_status": agent_status,
                "agent_session": {"value": session_id},
            }
        )
    controller = state.get("controller", {})
    controller_session = controller.get("session_id")
    controller_pane = controller.get("pane_id")
    represented_sessions = {
        agent["agent_session"]["value"] for agent in agents
    }
    if (
        isinstance(controller_session, str)
        and controller_session
        and isinstance(controller_pane, str)
        and controller_pane
        and controller_session not in represented_sessions
    ):
        agents.append(
            {
                "workspace_id": state.get("workspace_id"),
                "pane_id": controller_pane,
                "name": controller.get("name") or "P1",
                "agent_status": "working",
                "agent_session": {"value": controller_session},
            }
        )
    return agents


def _apply_synthetic_flow(snapshot: dict, projection: dict) -> None:
    authored_by_assignee = {
        node["assignee"]: node for node in snapshot["nodes"]
    }
    projected_assignees = set()
    projected_ids = set()
    nodes = []
    for original in projection["nodes"]:
        node = copy.deepcopy(original)
        projected_assignees.add(node["assignee"])
        projected_ids.add(node["id"])
        authored = authored_by_assignee.get(node["assignee"])
        if authored is not None:
            if "result" not in node:
                result = _result_from_status(authored["status"])
                if result is not None:
                    node["result"] = result
            if not node.get("task"):
                node["task"] = authored["task"]
        nodes.append(node)
    nodes.extend(
        copy.deepcopy(node)
        for node in snapshot["nodes"]
        if node["assignee"] not in projected_assignees
        and node["id"] not in projected_ids
    )
    snapshot["nodes"] = nodes
    snapshot["edges"] = copy.deepcopy(projection["edges"])
    snapshot["failurePolicies"] = []
    snapshot["activeFailureRoute"] = copy.deepcopy(
        projection["activeFailureRoute"]
    )


def _apply_declared_flow(snapshot: dict, projection: dict) -> None:
    projected_by_assignee = {
        node["assignee"]: node for node in projection["nodes"]
    }
    for node in snapshot["nodes"]:
        projected = projected_by_assignee.get(node["assignee"])
        if projected is None:
            continue
        node["liveness"] = projected["liveness"]
        result = projected.get("result") or _result_from_status(node["status"])
        if result is not None:
            node["result"] = result
        if "lastActivityAt" in projected:
            node["lastActivityAt"] = projected["lastActivityAt"]


def _result_from_status(status: str) -> str | None:
    return {
        "passed": "pass",
        "failed": "fail",
        "blocked": "blocked",
        "skipped": "skipped",
        "retrying": "rework",
    }.get(status)


def publish_snapshot(
    snapshot: dict,
    endpoint: str,
    token: str | None,
    *,
    replace_current: bool = False,
) -> None:
    """POST one immutable snapshot."""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if replace_current:
        headers["X-Role-Graph-Replace-Current"] = "true"
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(snapshot, separators=(",", ":")).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        if not 200 <= response.status < 300:
            raise PublisherError(
                f"viewer rejected snapshot with HTTP {response.status}"
            )


def load_current_snapshot(
    endpoint: str,
    token: str | None,
    scope_id: str,
    run_id: str,
) -> dict | None:
    """Load the current exact-scope snapshot, or return None when unavailable."""
    query = urllib.parse.urlencode({"scopeId": scope_id, "runId": run_id})
    snapshot_url = (
        endpoint.removesuffix("/api/snapshots") + "/api/snapshot?" + query
    )
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(snapshot_url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            snapshot = json.loads(response.read())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(snapshot, dict):
        return None
    if snapshot.get("scopeId") != scope_id or snapshot.get("runId") != run_id:
        return None
    return snapshot


def heartbeat_presence(
    endpoint: str,
    token: str | None,
    snapshot: dict,
) -> None:
    """POST one compact in-memory presence heartbeat."""
    suffix = "/api/snapshots"
    if not endpoint.endswith(suffix):
        raise PublisherError("snapshot endpoint must end with /api/snapshots")
    payload = {
        key: snapshot[key]
        for key in ("scopeId", "runId", "spaceName", "shortName")
        if key in snapshot
    }
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"{endpoint[:-len(suffix)]}/api/presence",
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        if not 200 <= response.status < 300:
            raise PublisherError(
                f"viewer rejected presence with HTTP {response.status}"
            )


def heartbeat_control_run(
    state_path: Path,
    workspace_id: str,
    space_name: str,
    endpoint: str,
    token: str | None,
) -> bool:
    """Heartbeat one active control run and ignore terminal runs."""
    state = _read_json(state_path)
    if state.get("workspace_id") != workspace_id:
        raise PublisherError(
            "workspace_id does not match the supplied workspace state"
        )
    run = state.get("run", {})
    if str(run.get("status", "")).upper() != "ACTIVE":
        return False
    run_id = run.get("contract_id")
    if not isinstance(run_id, str) or not run_id:
        raise PublisherError("run.contract_id is required")
    heartbeat_presence(
        endpoint,
        token,
        {
            "scopeId": f"herdr:{workspace_id}",
            "runId": run_id,
            "spaceName": _space_name(space_name),
        },
    )
    return True


def publish_if_changed(
    state_path: Path,
    manifest_path: Path | None,
    workspace_id: str,
    endpoint: str,
    token: str | None,
    last_revision: int | None,
    *,
    space_name: str,
    synthesize: bool = False,
    replace_current: bool = False,
    ledger: ObservationLedger | None = None,
    observed_at: str | None = None,
    publisher_fingerprint: str = "unmanaged",
    flow_events: list[dict] | None = None,
    flow_telemetry: dict | None = None,
    flow_changed: bool = False,
) -> int:
    """Publish the supplied state only when its revision changes."""
    if synthesize == (manifest_path is not None):
        raise PublisherError("select exactly one of manifest_path or synthesize")
    space_name = _space_name(space_name)
    state = _read_json(state_path)
    if state.get("workspace_id") != workspace_id:
        raise PublisherError(
            "workspace_id does not match the supplied workspace state"
        )
    revision = _revision(state)
    if revision == last_revision and not flow_changed:
        return revision

    manifest = synthesize_manifest(state) if synthesize else _read_json(manifest_path)
    snapshot = build_snapshot(
        state,
        manifest,
        workspace_id,
        space_name=space_name,
        publisher_fingerprint=publisher_fingerprint,
        flow_events=flow_events,
        flow_telemetry=flow_telemetry,
        synthetic=synthesize,
    )
    if flow_events is None:
        _merge_observed_events(snapshot, ledger, observed_at)
    publish_snapshot(snapshot, endpoint, token, replace_current=replace_current)
    return snapshot["sequence"]


def _merge_observed_events(
    snapshot: dict,
    ledger: ObservationLedger | None,
    observed_at: str | None,
) -> None:
    """Append bounded observer events to authored events in place.

    Authored ``workspace-state`` events keep their order and IDs; observer
    events occupy a separate ``observed-`` ID namespace. The combined list is
    capped and ``generatedAt`` advances to the newest valid event time so watch
    mode alone supplies wall-clock observation timestamps.
    """
    if ledger is None:
        return
    ledger.observe(snapshot["nodes"], observed_at=observed_at)
    combined = list(snapshot["events"]) + ledger.events
    snapshot["events"] = combined[-EVENT_LIMIT:]
    times = [
        parsed
        for event in snapshot["events"]
        if (parsed := _timestamp(event.get("at"))) is not None
    ]
    if times:
        snapshot["generatedAt"] = _format_timestamp(max(times))


def _read_json(path: Path) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PublisherError(f"expected a JSON object: {path}")
    return value


def _revision(state: dict) -> int:
    revision = state.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise PublisherError("workspace revision must be a non-negative integer")
    return revision


def _resolve_source(state: dict, definition: dict) -> tuple[dict, str]:
    source = definition.get("source", {})
    source_type = source.get("type")
    source_id = source.get("id")
    if source_type == "lane":
        return state.get("lanes", {}).get(source_id, {}), "lane"
    if source_type == "slot":
        slot = state.get("slots", {}).get(source_id, {})
        lane_id = slot.get("lane_id")
        lane = state.get("lanes", {}).get(lane_id)
        if lane is not None:
            return lane, "lane"
        return slot, "slot"
    raise PublisherError(
        f"node {definition.get('id', '<unknown>')} has an invalid source"
    )


def _status(record: dict, source_type: str) -> str:
    if not record:
        return "pending"
    if source_type == "lane":
        return LANE_STATUSES.get(str(record.get("state", "")).upper(), "pending")
    return SLOT_STATUSES.get(str(record.get("status", "")).upper(), "pending")


def _generation(record: dict) -> int:
    value = record.get("generation", 1)
    return value if isinstance(value, int) and not isinstance(value, bool) else 1


def _active_failure_route(
    policies: list[dict],
    resolved: dict[str, tuple[dict, str]],
    manifest: dict,
) -> dict | None:
    roles = {
        node["id"]: node.get("role", node["id"])
        for node in manifest.get("nodes", [])
    }
    for policy in policies:
        gate_id = policy.get("gateNodeId")
        record, source_type = resolved.get(gate_id, ({}, "lane"))
        if source_type != "lane" or record.get("state") != "FINDING":
            continue
        return {
            **copy.deepcopy(policy),
            "reason": _failure_reason(record, roles.get(gate_id, gate_id)),
            "generation": _generation(record),
        }
    return None


def _failure_reason(record: dict, role: str) -> str:
    direct = record.get("finding_reason") or record.get("message")
    if isinstance(direct, str) and direct:
        return direct
    finding = record.get("finding_or_blocker")
    if isinstance(finding, str) and finding:
        return finding
    if isinstance(finding, dict):
        for key in ("summary", "actual", "expected"):
            value = finding.get(key)
            if isinstance(value, str) and value:
                return value
    return f"{role} reported a finding"


def _timestamp(value: object) -> datetime | None:
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            seconds = value / 1000 if abs(value) >= 100_000_000_000 else value
            return datetime.fromtimestamp(seconds, timezone.utc)
        if isinstance(value, str) and value:
            normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
    except (OSError, OverflowError, ValueError):
        pass
    return None


def _format_timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _generated_at(state: dict) -> str:
    event_times = [
        parsed
        for event in state.get("events", [])
        if isinstance(event, dict)
        if (parsed := _timestamp(event.get("at"))) is not None
    ]
    if event_times:
        return _format_timestamp(max(event_times))

    candidates = (
        state.get("updated_at"),
        state.get("watcher", {}).get("heartbeat_at"),
        state.get("run", {}).get("updated_at"),
        state.get("run", {}).get("started_at"),
    )
    for value in candidates:
        parsed = _timestamp(value)
        if parsed is not None:
            return _format_timestamp(parsed)
    return "1970-01-01T00:00:00Z"


def _events(
    state: dict,
    lane_nodes: dict[str, str],
    generated_at: str,
) -> list[dict]:
    result = []
    events = state.get("events", [])
    for index, event in enumerate(events[-EVENT_LIMIT:]):
        cursor = event.get("cursor", index)
        kind = str(event.get("kind", "HERDR_EVENT"))
        value = {
            "id": str(event.get("event_id") or f"herdr-event-{cursor}"),
            "at": event.get("at") or event.get("observed_at") or generated_at,
            "kind": kind,
            "message": event.get("message")
            or kind.replace("_", " ").strip().title(),
        }
        node_id = lane_nodes.get(event.get("lane_id"))
        if node_id:
            value["nodeId"] = node_id
        generation = event.get("generation")
        if isinstance(generation, int) and not isinstance(generation, bool):
            value["generation"] = generation
        result.append(value)
    return result


def _positive_interval(value: str) -> float:
    interval = float(value)
    if interval <= 0:
        raise argparse.ArgumentTypeError("interval must be greater than zero")
    return interval


def _space_name(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PublisherError("space name must be non-empty")
    return value


def _space_name_argument(value: str) -> str:
    try:
        return _space_name(value)
    except PublisherError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--manifest", type=Path)
    mode.add_argument("--synthesize", action="store_true")
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--space-name", required=True, type=_space_name_argument)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--token")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--replace-current", action="store_true")
    parser.add_argument("--runtime-fingerprint", default="unmanaged")
    parser.add_argument("--flow-journal", type=Path)
    parser.add_argument("--interval", type=_positive_interval, default=2.0)
    return parser


def main() -> int:
    args = _parser().parse_args()
    last_revision = None
    replace_current = args.replace_current
    ledger = ObservationLedger()
    flow_runtime = None
    if args.flow_journal is not None:
        state = _read_json(args.state)
        run_id = state.get("run", {}).get("contract_id")
        if not isinstance(run_id, str) or not run_id:
            raise PublisherError("run.contract_id is required")
        flow_runtime = FlowRuntime(
            args.flow_journal,
            workspace_id=args.workspace_id,
            run_id=run_id,
        )
    while True:
        try:
            flow_changed = flow_runtime.poll() if flow_runtime else False
            revision = publish_if_changed(
                args.state,
                args.manifest,
                args.workspace_id,
                args.endpoint,
                args.token,
                last_revision,
                space_name=args.space_name,
                synthesize=args.synthesize,
                replace_current=replace_current,
                ledger=ledger,
                publisher_fingerprint=args.runtime_fingerprint,
                flow_events=flow_runtime.events if flow_runtime else None,
                flow_telemetry=flow_runtime.telemetry if flow_runtime else None,
                flow_changed=flow_changed,
            )
            replace_current = False
            if revision != last_revision:
                print(json.dumps({"status": "published", "revision": revision}))
            last_revision = revision
            heartbeat_control_run(
                args.state,
                args.workspace_id,
                args.space_name,
                args.endpoint,
                args.token,
            )
        except (OSError, PublisherError, json.JSONDecodeError) as error:
            print(
                json.dumps({"status": "error", "error": str(error)}),
                file=sys.stderr,
            )
            if not args.watch:
                return 1
        if not args.watch:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
