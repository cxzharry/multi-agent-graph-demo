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


def build_snapshot(state: dict, manifest: dict, workspace_id: str) -> dict:
    """Return one role-graph/v1 snapshot without I/O."""
    if state.get("workspace_id") != workspace_id:
        raise PublisherError(
            "workspace_id does not match the supplied workspace state"
        )
    if manifest.get("schemaVersion") != "herdr-role-graph-manifest/v1":
        raise PublisherError("unsupported manifest schemaVersion")

    revision = _revision(state)
    run_id = state.get("run", {}).get("contract_id")
    if not isinstance(run_id, str) or not run_id:
        raise PublisherError("run.contract_id is required")

    resolved = {}
    nodes = []
    for definition in manifest.get("nodes", []):
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

    policies = copy.deepcopy(manifest.get("failurePolicies", []))
    active_route = _active_failure_route(policies, resolved, manifest)
    generated_at = _generated_at(state)

    return {
        "schemaVersion": "role-graph/v1",
        "scopeId": f"herdr:{workspace_id}",
        "runId": run_id,
        "sequence": revision,
        "generatedAt": generated_at,
        "title": manifest.get("title", manifest.get("flowId", run_id)),
        "nodes": nodes,
        "edges": copy.deepcopy(manifest.get("edges", [])),
        "failurePolicies": policies,
        "activeFailureRoute": active_route,
        "events": _events(state, manifest, generated_at),
    }


def publish_snapshot(snapshot: dict, endpoint: str, token: str | None) -> None:
    """POST one immutable snapshot."""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
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
    manifest_path: Path,
    workspace_id: str,
    endpoint: str,
    token: str | None,
    last_revision: int | None,
) -> int:
    """Publish the supplied state only when its revision changes."""
    state = _read_json(state_path)
    if state.get("workspace_id") != workspace_id:
        raise PublisherError(
            "workspace_id does not match the supplied workspace state"
        )
    revision = _revision(state)
    if revision == last_revision:
        return revision

    manifest = _read_json(manifest_path)
    snapshot = build_snapshot(state, manifest, workspace_id)
    publish_snapshot(snapshot, endpoint, token)
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


def _generated_at(state: dict) -> str:
    candidates = (
        state.get("updated_at"),
        state.get("watcher", {}).get("heartbeat_at"),
        state.get("run", {}).get("updated_at"),
        state.get("run", {}).get("started_at"),
    )
    for value in candidates:
        if isinstance(value, str) and value:
            return value
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return (
                datetime.fromtimestamp(value, timezone.utc)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
            )
    return "1970-01-01T00:00:00Z"


def _events(state: dict, manifest: dict, generated_at: str) -> list[dict]:
    lane_nodes = {}
    for node in manifest.get("nodes", []):
        source = node.get("source", {})
        if source.get("type") == "lane":
            lane_nodes.setdefault(source.get("id"), node["id"])

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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--token")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=_positive_interval, default=1.0)
    return parser


def main() -> int:
    args = _parser().parse_args()
    last_revision = None
    while True:
        try:
            revision = publish_if_changed(
                args.state,
                args.manifest,
                args.workspace_id,
                args.endpoint,
                args.token,
                last_revision,
            )
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
