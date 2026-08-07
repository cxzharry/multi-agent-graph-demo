import copy
import unittest

from adapters.herdr.flow_journal import EVENT_SCHEMA_VERSION
from adapters.herdr.flow_projection import project_flow


def assignment(identifier, role, slot, session_id=None, task=None):
    value = {
        "id": identifier,
        "role": role,
        "slot": slot,
        "task": task or role,
    }
    if session_id is not None:
        value["agentSessionId"] = session_id
    return value


def event(kind, event_id, generation, at, **fields):
    return {
        "schemaVersion": EVENT_SCHEMA_VERSION,
        "eventId": event_id,
        "workspaceId": "wK",
        "runId": "run-1",
        "at": at,
        "kind": kind,
        "generation": generation,
        **fields,
    }


def agent(session_id, status="working", name="agent"):
    return {
        "workspace_id": "wK",
        "pane_id": f"wK:{session_id}",
        "name": name,
        "agent_status": status,
        "agent_session": {"value": session_id},
    }


P1 = assignment(
    "orchestrator", "Orchestrator", "P1", "session-p1", "Route ready work"
)
P2 = assignment("implementation-api:g1", "Implementation", "P2", "session-p2")
P3 = assignment("implementation-cli:g1", "Implementation", "P3", "session-p3")
P4_G1 = assignment("implementation-ui:g1", "Implementation", "P4", "session-p4-g1")
P4_G2 = assignment("implementation-ui:g2", "Implementation", "P4", "session-p4-g2")
P5 = assignment("integration:g1", "Integration", "P5", "session-p5")
P6 = assignment("independent-qc:g1", "Independent QC", "P6", "session-p6")


def option_a_events():
    values = []
    cursor = 0

    def add(kind, generation=1, **fields):
        nonlocal cursor
        cursor += 1
        values.append(
            event(
                kind,
                f"evt-{cursor:02d}",
                generation,
                f"2026-08-07T01:00:{cursor:02d}Z",
                **fields,
            )
        )

    for target in (P2, P3, P4_G1):
        add("CONTROL_DISPATCH", source=P1, target=target)
    for source in (P2, P3, P4_G1):
        add(
            "ARTIFACT_HANDOFF",
            source=source,
            target=P5,
            artifact={"commit": source["id"]},
        )
        add("ASSIGNMENT_RESULT", assignment=source, result="PASS")
    add("ARTIFACT_HANDOFF", source=P5, target=P6, artifact={"tree": "candidate"})
    add("ASSIGNMENT_RESULT", assignment=P5, result="PASS")
    add("ASSIGNMENT_RESULT", assignment=P6, result="FAIL")
    add(
        "REWORK_ROUTE",
        generation=2,
        source=P6,
        target=P4_G2,
        reason="Browser assertion failed",
    )
    add("CONTROL_DISPATCH", generation=2, source=P1, target=P4_G2)
    add(
        "ARTIFACT_HANDOFF",
        generation=2,
        source=P4_G2,
        target=P5,
        artifact={"commit": "fixed"},
    )
    return values


class OptionAProjectionTests(unittest.TestCase):
    def test_relationships_match_consumer_status_and_active_route_contract(self):
        projected = project_flow(
            events=option_a_events(),
            live_agents=[
                agent("session-p1", name="p1_orchestrator"),
                agent("session-p4-g2", name="p4_impl"),
            ],
            p1_session_id="session-p1",
        )
        edges_by_kind = {
            kind: [edge for edge in projected["edges"] if edge["kind"] == kind]
            for kind in ("forward", "control", "return")
        }

        self.assertEqual(
            {"passed"}, {edge["status"] for edge in edges_by_kind["forward"]}
        )
        self.assertEqual(
            1,
            sum(edge["status"] == "active" for edge in edges_by_kind["control"]),
        )
        self.assertEqual(
            {"active", "inactive"},
            {edge["status"] for edge in edges_by_kind["control"]},
        )
        self.assertEqual(
            ["active"], [edge["status"] for edge in edges_by_kind["return"]]
        )
        self.assertEqual(
            {
                "gateNodeId": P6["id"],
                "returnToNodeId": P4_G2["id"],
                "ownerNodeId": P4_G2["id"],
                "resumeNodeId": P6["id"],
                "rerunNodeIds": [P6["id"]],
                "excludedNodeIds": [],
                "reason": "Browser assertion failed",
                "generation": 2,
            },
            projected["activeFailureRoute"],
        )

    def test_seeds_observed_agents_without_inventing_relationships(self):
        projected = project_flow(
            events=[],
            live_agents=[
                agent("session-p1", name="p1_orchestrator"),
                agent("session-observer", name="unassigned_observer"),
            ],
            p1_session_id="session-p1",
        )

        self.assertEqual(
            {"p1_orchestrator", "unassigned_observer"},
            {node["assignee"] for node in projected["nodes"]},
        )
        self.assertEqual([], projected["edges"])

    def test_projects_truthful_option_a_nodes_edges_and_active_routes(self):
        projected = project_flow(
            events=option_a_events(),
            live_agents=[
                agent("session-p1", status="done", name="p1_orchestrator"),
                agent("session-p4-g2", status="working", name="p4_impl"),
            ],
            p1_session_id="session-p1",
        )
        nodes = {node["id"]: node for node in projected["nodes"]}

        self.assertEqual("running", nodes["orchestrator"]["liveness"])
        self.assertNotIn("result", nodes["orchestrator"])
        self.assertEqual("offline", nodes[P2["id"]]["liveness"])
        self.assertEqual("pass", nodes[P2["id"]]["result"])
        self.assertEqual("running", nodes[P4_G2["id"]]["liveness"])

        forward_pairs = {
            (edge["source"], edge["target"])
            for edge in projected["edges"]
            if edge["kind"] == "forward"
        }
        self.assertEqual(
            {
                (P2["id"], P5["id"]),
                (P3["id"], P5["id"]),
                (P4_G1["id"], P5["id"]),
                (P4_G2["id"], P5["id"]),
                (P5["id"], P6["id"]),
            },
            forward_pairs,
        )
        active_control_pairs = [
            (edge["source"], edge["target"])
            for edge in projected["edges"]
            if edge["kind"] == "control" and edge["status"] == "active"
        ]
        self.assertEqual([("orchestrator", "implementation-ui:g2")], active_control_pairs)
        return_pairs = [
            (edge["source"], edge["target"])
            for edge in projected["edges"]
            if edge["kind"] == "return"
        ]
        self.assertEqual([("independent-qc:g1", "implementation-ui:g2")], return_pairs)
        self.assertEqual(
            "Browser assertion failed", projected["activeFailureRoute"]["reason"]
        )
        self.assertEqual(
            [value["eventId"] for value in option_a_events()],
            [value["id"] for value in projected["timeline"]],
        )
        self.assertEqual("ok", projected["telemetry"]["status"])

    def test_layers_come_only_from_artifact_flow(self):
        projected = project_flow(
            events=option_a_events(),
            live_agents=[agent("session-p1")],
            p1_session_id="session-p1",
        )
        layers = {node["id"]: node["layer"] for node in projected["nodes"]}

        self.assertEqual(0, layers["orchestrator"])
        self.assertEqual(1, layers[P2["id"]])
        self.assertEqual(1, layers[P4_G2["id"]])
        self.assertEqual(2, layers[P5["id"]])
        self.assertEqual(3, layers[P6["id"]])


class RetentionAndRecoveryTests(unittest.TestCase):
    def test_timeline_retains_only_the_newest_fifty_events_in_append_order(self):
        values = [
            event(
                "RUN_TERMINAL",
                f"evt-{index:03d}",
                1,
                f"2026-08-07T01:{index // 60:02d}:{index % 60:02d}Z",
                result="PASS",
            )
            for index in range(55)
        ]

        projected = project_flow(
            events=values,
            live_agents=[agent("session-p1")],
            p1_session_id="session-p1",
        )

        self.assertEqual(50, len(projected["timeline"]))
        self.assertEqual("evt-005", projected["timeline"][0]["id"])
        self.assertEqual("evt-054", projected["timeline"][-1]["id"])

    def test_missing_live_assignments_are_retained_offline(self):
        first = project_flow(
            events=option_a_events(),
            live_agents=[agent("session-p1"), agent("session-p2")],
            p1_session_id="session-p1",
        )
        retained = project_flow(
            events=[],
            live_agents=[agent("session-p1")],
            p1_session_id="session-p1",
            prior_nodes=first["nodes"],
        )
        nodes = {node["id"]: node for node in retained["nodes"]}

        self.assertEqual("offline", nodes[P2["id"]]["liveness"])
        self.assertEqual("pass", nodes[P2["id"]]["result"])

    def test_repeated_handoffs_aggregate_in_ledger_order(self):
        handoff = event(
            "ARTIFACT_HANDOFF",
            "evt-handoff-1",
            1,
            "2026-08-07T01:00:01Z",
            source=P2,
            target=P5,
            artifact={"commit": "one"},
        )
        repeated = copy.deepcopy(handoff)
        repeated.update(
            {
                "eventId": "evt-handoff-2",
                "at": "2026-08-07T01:00:02Z",
                "artifact": {"commit": "two"},
            }
        )

        projected = project_flow(
            events=[handoff, repeated],
            live_agents=[agent("session-p1")],
            p1_session_id="session-p1",
        )
        edge = next(edge for edge in projected["edges"] if edge["kind"] == "forward")

        self.assertEqual(2, edge["occurrenceCount"])
        self.assertEqual("2026-08-07T01:00:02Z", edge["lastEventAt"])

    def test_stale_generation_cannot_replace_newest_active_control(self):
        newest = event(
            "CONTROL_DISPATCH",
            "evt-new",
            2,
            "2026-08-07T01:00:01Z",
            source=P1,
            target=P4_G2,
        )
        stale = event(
            "CONTROL_DISPATCH",
            "evt-stale",
            1,
            "2026-08-07T01:00:02Z",
            source=P1,
            target=P4_G1,
        )

        projected = project_flow(
            events=[newest, stale],
            live_agents=[agent("session-p1")],
            p1_session_id="session-p1",
        )
        active = [
            edge
            for edge in projected["edges"]
            if edge["kind"] == "control" and edge["status"] == "active"
        ]

        self.assertEqual([P4_G2["id"]], [edge["target"] for edge in active])

    def test_controller_recovery_keeps_orchestrator_identity_and_generation(self):
        recovered = assignment(
            "orchestrator",
            "Orchestrator",
            "P1",
            "session-p1-recovered",
            "Route ready work",
        )
        projected = project_flow(
            events=[
                event(
                    "CONTROLLER_RECOVERED",
                    "evt-recovered",
                    2,
                    "2026-08-07T01:00:01Z",
                    assignment=recovered,
                )
            ],
            live_agents=[agent("session-p1-recovered")],
            p1_session_id="session-p1-recovered",
        )
        orchestrators = [
            node for node in projected["nodes"] if node["id"] == "orchestrator"
        ]

        self.assertEqual(1, len(orchestrators))
        self.assertEqual(2, orchestrators[0]["generation"])
        self.assertEqual("running", orchestrators[0]["liveness"])

    def test_stale_controller_recovery_cannot_replace_newer_session_binding(self):
        recovered = assignment(
            "orchestrator",
            "Orchestrator",
            "P1",
            "session-p1-recovered",
            "Route ready work",
        )
        stale = assignment(
            "orchestrator",
            "Orchestrator",
            "P1",
            "session-p1-stale",
            "Route ready work",
        )
        projected = project_flow(
            events=[
                event(
                    "CONTROLLER_RECOVERED",
                    "evt-recovered-g2",
                    2,
                    "2026-08-07T01:00:02Z",
                    assignment=recovered,
                ),
                event(
                    "CONTROLLER_RECOVERED",
                    "evt-stale-g1",
                    1,
                    "2026-08-07T01:00:03Z",
                    assignment=stale,
                ),
            ],
            live_agents=[agent("session-p1-recovered")],
            p1_session_id="session-p1-recovered",
        )
        orchestrator = next(
            node for node in projected["nodes"] if node["id"] == "orchestrator"
        )

        self.assertEqual(2, orchestrator["generation"])
        self.assertEqual("2026-08-07T01:00:02Z", orchestrator["lastActivityAt"])
        self.assertEqual("running", orchestrator["liveness"])


if __name__ == "__main__":
    unittest.main()
