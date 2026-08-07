"""Deterministically project validated workflow events into graph facts."""

from __future__ import annotations

import copy


TIMELINE_LIMIT = 50
RESULT_STATUS = {
    "PASS": "pass",
    "FAIL": "fail",
    "BLOCKED": "blocked",
    "SKIPPED": "skipped",
    "REWORK": "rework",
}


def project_flow(*, events, live_agents, p1_session_id, prior_nodes=None):
    """Return nodes, edges, activeFailureRoute, timeline, and telemetry."""
    nodes = _prior_nodes(prior_nodes)
    nodes.setdefault(
        "orchestrator",
        {
            "id": "orchestrator",
            "role": "Orchestrator",
            "assignee": "P1",
            "status": "pending",
            "task": "Route ready work",
            "generation": 1,
            "layer": 0,
            "liveness": "offline",
        },
    )
    sessions = {"orchestrator": p1_session_id}
    relationships = {
        "control": {},
        "forward": {},
        "return": {},
    }
    active_control = None
    active_rework = None
    timeline = []
    seen_event_ids = set()

    for index, original in enumerate(events):
        event = copy.deepcopy(original)
        event_id = event.get("eventId")
        if event_id in seen_event_ids:
            continue
        seen_event_ids.add(event_id)
        generation = event["generation"]
        kind = event["kind"]
        descriptors = _event_descriptors(event)
        for descriptor_name, descriptor in descriptors:
            _merge_assignment(
                nodes,
                sessions,
                descriptor,
                generation if descriptor.get("id") != "orchestrator" else None,
                event["at"],
            )

        if kind == "CONTROLLER_RECOVERED":
            _merge_assignment(
                nodes,
                sessions,
                event["assignment"],
                generation,
                event["at"],
            )
        elif kind == "ASSIGNMENT_RESULT":
            node = nodes[event["assignment"]["id"]]
            if generation >= node["generation"]:
                node["result"] = RESULT_STATUS[event["result"]]
                node["generation"] = generation
        elif kind in {"CONTROL_DISPATCH", "ARTIFACT_HANDOFF", "REWORK_ROUTE"}:
            edge_kind = {
                "CONTROL_DISPATCH": "control",
                "ARTIFACT_HANDOFF": "forward",
                "REWORK_ROUTE": "return",
            }[kind]
            key = (event["source"]["id"], event["target"]["id"])
            relationship = relationships[edge_kind].setdefault(
                key,
                {
                    "id": _edge_id(edge_kind, *key),
                    "source": key[0],
                    "target": key[1],
                    "kind": edge_kind,
                    "status": "complete",
                    "occurrenceCount": 0,
                    "lastEventAt": event["at"],
                    "generation": generation,
                },
            )
            relationship["occurrenceCount"] += 1
            if generation >= relationship["generation"]:
                relationship["lastEventAt"] = event["at"]
                relationship["generation"] = generation
                if kind == "REWORK_ROUTE":
                    relationship["reason"] = event["reason"]
            marker = (generation, index, key)
            if kind == "CONTROL_DISPATCH" and (
                active_control is None or marker[:2] > active_control[:2]
            ):
                active_control = marker
            if kind == "REWORK_ROUTE" and (
                active_rework is None or marker[:2] > active_rework[:2]
            ):
                active_rework = marker

        timeline.append(_timeline_event(event, descriptors))

    live_by_session = {
        identity[1]: agent
        for agent in live_agents
        if (identity := _agent_identity(agent)) is not None
    }
    observed_p1 = live_by_session.get(p1_session_id)
    if observed_p1 is not None and "lastActivityAt" not in nodes["orchestrator"]:
        nodes["orchestrator"]["assignee"] = (
            observed_p1.get("name") or observed_p1.get("agent") or "P1"
        )
    assigned_sessions = set(sessions.values())
    for session_id, agent in sorted(live_by_session.items()):
        if session_id in assigned_sessions:
            continue
        identity = _agent_identity(agent)
        node_id = _observed_node_id(identity[0], session_id)
        name = agent.get("name") or agent.get("agent") or "Herdr agent"
        nodes[node_id] = {
            "id": node_id,
            "role": name,
            "assignee": name,
            "status": "pending",
            "task": "Participate in current Herdr session",
            "generation": 1,
            "layer": 1,
            "liveness": "offline",
        }
        sessions[node_id] = session_id

    _apply_liveness(nodes, sessions, live_by_session, p1_session_id)
    _apply_layers(nodes, relationships["forward"])

    if active_control is not None:
        relationships["control"][active_control[2]]["status"] = "active"
    edges = [
        edge
        for edge_kind in ("forward", "control", "return")
        for edge in relationships[edge_kind].values()
    ]
    failure_route = None
    if active_rework is not None:
        edge = relationships["return"][active_rework[2]]
        failure_route = {
            "sourceNodeId": edge["source"],
            "targetNodeId": edge["target"],
            "reason": edge["reason"],
            "generation": edge["generation"],
        }
    timeline = timeline[-TIMELINE_LIMIT:]
    telemetry = {"status": "ok"}
    if timeline:
        telemetry["lastValidAt"] = timeline[-1]["at"]
    return {
        "nodes": sorted(
            nodes.values(), key=lambda node: (node.get("layer", 1), node["id"])
        ),
        "edges": edges,
        "activeFailureRoute": failure_route,
        "timeline": timeline,
        "telemetry": telemetry,
    }


def _prior_nodes(prior_nodes):
    nodes = {}
    for original in prior_nodes or []:
        if not isinstance(original, dict) or not isinstance(original.get("id"), str):
            continue
        node = copy.deepcopy(original)
        node["liveness"] = "offline"
        nodes[node["id"]] = node
    return nodes


def _event_descriptors(event):
    kind = event["kind"]
    if kind in {"CONTROL_DISPATCH", "ARTIFACT_HANDOFF", "REWORK_ROUTE"}:
        return (("source", event["source"]), ("target", event["target"]))
    if kind in {"ASSIGNMENT_RESULT", "CONTROLLER_RECOVERED"}:
        return (("assignment", event["assignment"]),)
    return ()


def _merge_assignment(nodes, sessions, descriptor, generation, activity_at):
    node_id = descriptor["id"]
    node = nodes.setdefault(
        node_id,
        {
            "id": node_id,
            "role": descriptor["role"],
            "assignee": descriptor["slot"],
            "status": "pending",
            "task": descriptor["task"],
            "generation": 1,
            "layer": 1,
            "liveness": "offline",
        },
    )
    next_generation = node["generation"] if generation is None else generation
    if next_generation >= node["generation"]:
        node.update(
            {
                "role": descriptor["role"],
                "assignee": descriptor["slot"],
                "task": descriptor["task"],
                "generation": next_generation,
                "lastActivityAt": activity_at,
            }
        )
        session_id = descriptor.get("agentSessionId")
        if session_id is not None:
            sessions[node_id] = session_id


def _apply_liveness(nodes, sessions, live_by_session, p1_session_id):
    for node_id, node in nodes.items():
        session_id = sessions.get(node_id)
        agent = live_by_session.get(session_id)
        if node_id == "orchestrator" and session_id == p1_session_id and agent:
            liveness = "running"
        elif agent is None:
            liveness = "offline"
        else:
            status = str(agent.get("agent_status", "")).lower()
            liveness = {
                "working": "running",
                "done": "idle",
                "idle": "idle",
                "blocked": "idle",
            }.get(status, "stale")
        node["liveness"] = liveness
        result = node.get("result")
        node["status"] = {
            "pass": "passed",
            "fail": "failed",
            "blocked": "blocked",
            "skipped": "skipped",
            "rework": "retrying",
        }.get(result, "running" if liveness == "running" else "pending")


def _apply_layers(nodes, forward_edges):
    for node_id, node in nodes.items():
        node["layer"] = 0 if node_id == "orchestrator" else 1
    for _ in range(len(nodes)):
        changed = False
        for source, target in forward_edges:
            source_layer = nodes[source]["layer"]
            target_layer = max(nodes[target]["layer"], source_layer + 1)
            if target_layer != nodes[target]["layer"]:
                nodes[target]["layer"] = target_layer
                changed = True
        if not changed:
            break


def _timeline_event(event, descriptors):
    value = {
        "id": event["eventId"],
        "at": event["at"],
        "kind": event["kind"],
        "message": event["kind"].replace("_", " ").title(),
        "generation": event["generation"],
    }
    if descriptors:
        value["nodeId"] = descriptors[-1][1]["id"]
    if "reason" in event:
        value["reason"] = event["reason"]
    return value


def _agent_identity(agent):
    if not isinstance(agent, dict):
        return None
    pane_id = agent.get("pane_id")
    session_id = agent.get("agent_session", {}).get("value")
    if not isinstance(pane_id, str) or not pane_id:
        return None
    if not isinstance(session_id, str) or not session_id:
        return None
    return pane_id, session_id


def _observed_node_id(pane_id, session_id):
    identity = session_id + "\0" + pane_id
    return f"agent-{identity.encode('utf-8').hex()}"


def _edge_id(kind, source, target):
    identity = f"{kind}\0{source}\0{target}"
    return f"event-{identity.encode('utf-8').hex()}"
