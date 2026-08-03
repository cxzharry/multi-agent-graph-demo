import copy
import json
import subprocess
import unittest
from unittest import mock

from adapters.herdr.session_publisher import (
    _parser,
    build_session_snapshot,
    heartbeat_presence,
    list_agents,
    publish_if_changed,
    select_workspace_agents,
)


P1_SESSION = "019fb24f-f36f-7642-8679-5c6405fb3889"


def agent(
    workspace_id,
    pane_id,
    session_id,
    name,
    status="working",
    revision=1,
):
    return {
        "workspace_id": workspace_id,
        "pane_id": pane_id,
        "name": name,
        "agent": "codex",
        "agent_status": status,
        "revision": revision,
        "agent_session": {"value": session_id},
    }


class WorkspaceSelectionTests(unittest.TestCase):
    def test_filters_exact_workspace_and_deduplicates_agent_identity(self):
        p1 = agent("wK", "wK:p1", P1_SESSION, "p1_orchestrator")
        old_p2 = agent("wK", "wK:p2", "session-p2", "p2_old", revision=1)
        new_p2 = agent(
            "wK", "wK:p2", "session-p2", "p2_impl", revision=2
        )
        foreign = agent("wK2", "wK2:p1", "foreign", "foreign_p1")

        selected = select_workspace_agents(
            [foreign, old_p2, p1, new_p2], workspace_id="wK"
        )

        self.assertEqual(["wK:p1", "wK:p2"], [item["pane_id"] for item in selected])
        self.assertEqual("p2_impl", selected[1]["name"])

    def test_agent_discovery_uses_only_read_only_list_command(self):
        completed = subprocess.CompletedProcess(
            ["herdr", "agent", "list"],
            0,
            stdout=json.dumps({"result": {"agents": []}}),
            stderr="",
        )
        with mock.patch(
            "adapters.herdr.session_publisher.subprocess.run",
            return_value=completed,
        ) as run:
            self.assertEqual([], list_agents())

        self.assertEqual(("herdr", "agent", "list"), run.call_args.args[0])


class SessionSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.agents = [
            agent("wK", "wK:p1", P1_SESSION, "p1_orchestrator"),
            agent("wK", "wK:p2", "session-p2", "p2_impl", "working"),
            agent("wK", "wK:p3", "session-p3", "p3_impl", "done"),
        ]

    def test_builds_p1_rooted_agent_only_snapshot_with_full_session_identity(self):
        snapshot = build_session_snapshot(
            agents=self.agents,
            workspace_id="wK",
            space_name="herdr-orchestrator",
            p1_session_id=P1_SESSION,
            p1_pane_id="wK:p1",
            sequence=1,
        )

        self.assertEqual("herdr:wK", snapshot["scopeId"])
        self.assertEqual(P1_SESSION, snapshot["runId"])
        self.assertEqual("current", snapshot["shortName"])
        self.assertEqual("herdr-orchestrator", snapshot["spaceName"])
        self.assertEqual("orchestrator", snapshot["nodes"][0]["id"])
        self.assertEqual("running", snapshot["nodes"][0]["status"])
        self.assertEqual("passed", snapshot["nodes"][2]["status"])
        self.assertEqual(
            {("orchestrator", node["id"]) for node in snapshot["nodes"][1:]},
            {(edge["source"], edge["target"]) for edge in snapshot["edges"]},
        )

    def test_publishes_only_when_projected_agent_status_changes(self):
        with mock.patch(
            "adapters.herdr.session_publisher.publish_snapshot"
        ) as publish:
            first = publish_if_changed(
                self.agents,
                "wK",
                "herdr-orchestrator",
                P1_SESSION,
                "wK:p1",
                "http://127.0.0.1:4173/api/snapshots",
                None,
                None,
            )
            reordered = copy.deepcopy(list(reversed(self.agents)))
            reordered[0]["focused"] = True
            unchanged = publish_if_changed(
                reordered,
                "wK",
                "herdr-orchestrator",
                P1_SESSION,
                "wK:p1",
                "http://127.0.0.1:4173/api/snapshots",
                None,
                first,
            )
            changed_agents = copy.deepcopy(self.agents)
            changed_agents[1]["agent_status"] = "done"
            changed = publish_if_changed(
                changed_agents,
                "wK",
                "herdr-orchestrator",
                P1_SESSION,
                "wK:p1",
                "http://127.0.0.1:4173/api/snapshots",
                None,
                unchanged,
            )

        self.assertEqual(2, publish.call_count)
        self.assertIs(first, unchanged)
        self.assertEqual(1, first["sequence"])
        self.assertEqual(2, changed["sequence"])

    def test_heartbeat_posts_compact_identity_to_presence_endpoint(self):
        response = mock.MagicMock()
        response.__enter__.return_value.status = 202
        snapshot = build_session_snapshot(
            self.agents,
            "wK",
            "herdr-orchestrator",
            P1_SESSION,
            "wK:p1",
            1,
        )
        with mock.patch(
            "adapters.herdr.publisher.urllib.request.urlopen",
            return_value=response,
        ) as urlopen:
            heartbeat_presence(
                "http://127.0.0.1:4173/api/snapshots", "secret", snapshot
            )

        request = urlopen.call_args.args[0]
        self.assertEqual("http://127.0.0.1:4173/api/presence", request.full_url)
        self.assertEqual("Bearer secret", request.get_header("Authorization"))
        self.assertEqual(
            {
                "scopeId": "herdr:wK",
                "runId": P1_SESSION,
                "spaceName": "herdr-orchestrator",
                "shortName": "current",
            },
            json.loads(request.data),
        )

    def test_cli_heartbeat_interval_defaults_to_two_seconds(self):
        args = _parser().parse_args(
            [
                "--workspace-id",
                "wK",
                "--space-name",
                "herdr-orchestrator",
                "--p1-session-id",
                P1_SESSION,
                "--p1-pane-id",
                "wK:p1",
                "--endpoint",
                "http://127.0.0.1:4173/api/snapshots",
            ]
        )
        self.assertEqual(2.0, args.interval)


if __name__ == "__main__":
    unittest.main()
