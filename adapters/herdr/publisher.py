#!/usr/bin/env python3
"""Publish one supplied Herdr workspace state as an immutable role graph."""

from __future__ import annotations

import argparse
import copy
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


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
        "title": f"Auto operational view — {run_id}",
        "nodes": nodes,
        "edges": [
            {
                "id": f"control-{node['id']}",
                "source": "orchestrator",
                "target": node["id"],
                "kind": "forward",
                "status": "active",
            }
            for node in nodes[1:]
        ],
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

    return {
        "schemaVersion": "role-graph/v1",
        "scopeId": f"herdr:{workspace_id}",
        "runId": run_id,
        "flowId": materialized["flowId"],
        "spaceName": space_name,
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
    if revision == last_revision:
        return revision

    manifest = synthesize_manifest(state) if synthesize else _read_json(manifest_path)
    snapshot = build_snapshot(
        state,
        manifest,
        workspace_id,
        space_name=space_name,
    )
    publish_snapshot(snapshot, endpoint, token, replace_current=replace_current)
    return snapshot["sequence"]


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
    parser.add_argument("--interval", type=_positive_interval, default=1.0)
    return parser


def main() -> int:
    args = _parser().parse_args()
    last_revision = None
    replace_current = args.replace_current
    while True:
        try:
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
            )
            replace_current = False
            if revision != last_revision:
                print(json.dumps({"status": "published", "revision": revision}))
            last_revision = revision
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
