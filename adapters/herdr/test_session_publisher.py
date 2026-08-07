import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import adapters.herdr.publisher as publisher_module
from adapters.herdr.flow_journal import EVENT_SCHEMA_VERSION, FlowJournal
from adapters.herdr.observed_events import ObservationLedger
from adapters.herdr.session_publisher import (
    _parser,
    build_session_snapshot,
    heartbeat_presence,
    list_agents,
    publish_if_changed,
    select_workspace_agents,
)


P1_SESSION = "019fb24f-f36f-7642-8679-5c6405fb3889"
SCRIPT_PATH = Path(__file__).with_name("session_publisher.py").resolve()
REPOSITORY_ROOT = Path(__file__).parents[2]


def flow_assignment(identifier, role, slot, session_id):
    return {
        "id": identifier,
        "role": role,
        "slot": slot,
        "agentSessionId": session_id,
        "task": role,
    }


def flow_event(kind, event_id, **fields):
    return {
        "schemaVersion": EVENT_SCHEMA_VERSION,
        "eventId": event_id,
        "workspaceId": "wK",
        "runId": P1_SESSION,
        "at": "2026-08-07T01:02:03Z",
        "kind": kind,
        "generation": 1,
        **fields,
    }


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


class LauncherContractTests(unittest.TestCase):
    def test_absolute_path_help_imports_without_repository_pythonpath(self):
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, "-B", str(SCRIPT_PATH), "--help"],
                cwd=directory,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("usage:", result.stdout)

    def test_absolute_path_parser_accepts_launcher_watch_flag(self):
        env = {**os.environ, "PYTHONPATH": str(REPOSITORY_ROOT)}
        probe = (
            "import runpy; "
            f"values = runpy.run_path({str(SCRIPT_PATH)!r}); "
            "args = values['_parser']().parse_args(["
            "'--workspace-id', 'wK', "
            "'--space-name', 'herdr-orchestrator', "
            f"'--p1-session-id', {P1_SESSION!r}, "
            "'--p1-pane-id', 'wK:p1', "
            "'--endpoint', 'http://127.0.0.1:4173/api/snapshots', "
            "'--watch']); "
            "print(args.watch)"
        )
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, "-B", "-c", probe],
                cwd=directory,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("True", result.stdout.strip())


class SessionSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.agents = [
            agent("wK", "wK:p1", P1_SESSION, "p1_orchestrator"),
            agent("wK", "wK:p2", "session-p2", "p2_impl", "working"),
            agent("wK", "wK:p3", "session-p3", "p3_impl", "done"),
        ]

    def test_builds_p1_rooted_agent_only_snapshot_with_full_session_identity(self):
        ledger = ObservationLedger()
        snapshot = build_session_snapshot(
            agents=self.agents,
            workspace_id="wK",
            space_name="herdr-orchestrator",
            p1_session_id=P1_SESSION,
            p1_pane_id="wK:p1",
            sequence=1,
            ledger=ledger,
            observed_at="2026-08-05T10:00:00Z",
        )

        self.assertEqual("herdr:wK", snapshot["scopeId"])
        self.assertEqual(P1_SESSION, snapshot["runId"])
        self.assertEqual("live-session", snapshot["flowId"])
        self.assertEqual("current", snapshot["shortName"])
        self.assertEqual("herdr-orchestrator", snapshot["spaceName"])
        self.assertEqual("orchestrator", snapshot["nodes"][0]["id"])
        self.assertEqual(0, snapshot["nodes"][0]["layer"])
        self.assertEqual("running", snapshot["nodes"][0]["status"])
        self.assertEqual("passed", snapshot["nodes"][2]["status"])
        self.assertTrue(all(node["layer"] == 1 for node in snapshot["nodes"][1:]))

        # Observed topology proves no fabricated relationships.
        self.assertEqual([], snapshot["edges"])
        self.assertEqual([], snapshot["failurePolicies"])
        self.assertIsNone(snapshot["activeFailureRoute"])

        # Every current node yields one immediate timestamped lifecycle event.
        self.assertEqual(len(snapshot["nodes"]), len(snapshot["events"]))
        self.assertTrue(
            all(event["at"].endswith("Z") for event in snapshot["events"])
        )
        self.assertEqual(
            {"NODE_OBSERVED"}, {event["kind"] for event in snapshot["events"]}
        )
        self.assertEqual(
            {node["id"] for node in snapshot["nodes"]},
            {event["nodeId"] for event in snapshot["events"]},
        )

    def test_snapshot_defaults_to_unmanaged_publisher_fingerprint(self):
        snapshot = build_session_snapshot(
            self.agents,
            "wK",
            "herdr-orchestrator",
            P1_SESSION,
            "wK:p1",
            1,
        )

        self.assertEqual("unmanaged", snapshot["publisherFingerprint"])

    def test_snapshot_includes_supplied_publisher_fingerprint(self):
        snapshot = build_session_snapshot(
            self.agents,
            "wK",
            "herdr-orchestrator",
            P1_SESSION,
            "wK:p1",
            1,
            publisher_fingerprint="publisher-sha",
        )

        self.assertEqual("publisher-sha", snapshot["publisherFingerprint"])

    def test_snapshot_without_ledger_is_deterministic_and_eventless(self):
        snapshot = build_session_snapshot(
            agents=self.agents,
            workspace_id="wK",
            space_name="herdr-orchestrator",
            p1_session_id=P1_SESSION,
            p1_pane_id="wK:p1",
            sequence=1,
        )

        self.assertEqual([], snapshot["edges"])
        self.assertEqual([], snapshot["events"])

    def test_publishes_only_when_projected_agent_status_changes(self):
        ledger = ObservationLedger()
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
                ledger=ledger,
                observed_at="2026-08-05T10:00:00Z",
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
                ledger=ledger,
                observed_at="2026-08-05T10:00:02Z",
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
                ledger=ledger,
                observed_at="2026-08-05T10:00:04Z",
            )

        self.assertEqual(2, publish.call_count)
        self.assertIs(first, unchanged)
        self.assertEqual(1, first["sequence"])
        self.assertEqual(2, changed["sequence"])
        # The initial publish records one lifecycle event per current node; the
        # status change appends exactly one more without duplicating the rest.
        self.assertEqual(len(self.agents), len(first["events"]))
        self.assertEqual(len(self.agents) + 1, len(changed["events"]))
        self.assertEqual("NODE_STATUS_CHANGED", changed["events"][-1]["kind"])

    def test_sequence_floor_controls_the_first_snapshot(self):
        ledger = ObservationLedger()
        with mock.patch(
            "adapters.herdr.session_publisher.publish_snapshot"
        ) as publish:
            snapshot = publish_if_changed(
                self.agents,
                "wK",
                "herdr-orchestrator",
                P1_SESSION,
                "wK:p1",
                "http://127.0.0.1:4173/api/snapshots",
                None,
                None,
                ledger=ledger,
                observed_at="2026-08-07T01:00:00Z",
                publisher_fingerprint="publisher-sha",
                sequence_floor=112,
            )

        self.assertEqual(112, snapshot["sequence"])
        self.assertEqual("publisher-sha", snapshot["publisherFingerprint"])
        self.assertEqual([], snapshot["edges"])
        self.assertGreater(len(snapshot["events"]), 0)
        publish.assert_called_once()

    def test_restored_history_appends_only_a_real_later_transition(self):
        prior_ledger = ObservationLedger()
        prior = build_session_snapshot(
            self.agents,
            "wK",
            "herdr-orchestrator",
            P1_SESSION,
            "wK:p1",
            111,
            ledger=prior_ledger,
            observed_at="2026-08-07T00:00:00Z",
            publisher_fingerprint="old-sha",
        )
        restored = ObservationLedger.restore(prior["nodes"], prior["events"])
        changed_agents = copy.deepcopy(self.agents)
        changed_agents[1]["agent_status"] = "done"

        with mock.patch("adapters.herdr.session_publisher.publish_snapshot"):
            restarted = publish_if_changed(
                self.agents,
                "wK",
                "herdr-orchestrator",
                P1_SESSION,
                "wK:p1",
                "http://127.0.0.1:4173/api/snapshots",
                None,
                None,
                ledger=restored,
                observed_at="2026-08-07T01:00:00Z",
                publisher_fingerprint="publisher-sha",
                sequence_floor=112,
            )
            changed = publish_if_changed(
                changed_agents,
                "wK",
                "herdr-orchestrator",
                P1_SESSION,
                "wK:p1",
                "http://127.0.0.1:4173/api/snapshots",
                None,
                restarted,
                ledger=restored,
                observed_at="2026-08-07T01:00:02Z",
                publisher_fingerprint="publisher-sha",
                sequence_floor=112,
            )

        self.assertEqual(prior["events"], restarted["events"])
        self.assertEqual(len(prior["events"]) + 1, len(changed["events"]))
        self.assertEqual("observed-000004", changed["events"][-1]["id"])
        self.assertEqual("NODE_STATUS_CHANGED", changed["events"][-1]["kind"])

    def test_main_fails_closed_for_malformed_legacy_history(self):
        legacy = build_session_snapshot(
            self.agents,
            "wK",
            "herdr-orchestrator",
            P1_SESSION,
            "wK:p1",
            111,
        )
        legacy["edges"] = [
            {
                "id": f"invented-{index}",
                "source": "orchestrator",
                "target": legacy["nodes"][1]["id"],
                "kind": "forward",
                "status": "active",
            }
            for index in range(8)
        ]
        legacy["events"] = [{"id": "observed-000001"}]
        argv = [
            "session_publisher.py",
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
            "--runtime-fingerprint",
            "publisher-sha",
            "--sequence-floor",
            "112",
        ]

        with mock.patch("sys.argv", argv), mock.patch(
            "adapters.herdr.session_publisher.load_current_snapshot",
            return_value=legacy,
        ) as load, mock.patch(
            "adapters.herdr.session_publisher.list_agents",
            return_value=self.agents,
        ), mock.patch(
            "adapters.herdr.session_publisher.publish_snapshot"
        ) as publish, mock.patch(
            "adapters.herdr.session_publisher.heartbeat_presence"
        ), mock.patch(
            "adapters.herdr.session_publisher.time.sleep",
            side_effect=KeyboardInterrupt,
        ):
            with self.assertRaises(KeyboardInterrupt):
                from adapters.herdr.session_publisher import main

                main()

        load.assert_called_once_with(
            "http://127.0.0.1:4173/api/snapshots",
            None,
            "herdr:wK",
            P1_SESSION,
        )
        snapshot = publish.call_args.args[0]
        self.assertEqual(112, snapshot["sequence"])
        self.assertEqual("publisher-sha", snapshot["publisherFingerprint"])
        self.assertEqual([], snapshot["edges"])
        self.assertEqual(len(self.agents), len(snapshot["events"]))
        self.assertTrue(
            all(event.get("kind") == "NODE_OBSERVED" for event in snapshot["events"])
        )

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
        self.assertEqual("unmanaged", args.runtime_fingerprint)
        self.assertEqual(1, args.sequence_floor)

    def test_cli_accepts_runtime_fingerprint_and_sequence_floor(self):
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
                "--runtime-fingerprint",
                "publisher-sha",
                "--sequence-floor",
                "112",
            ]
        )

        self.assertEqual("publisher-sha", args.runtime_fingerprint)
        self.assertEqual(112, args.sequence_floor)


class EventBackedSessionTests(unittest.TestCase):
    def setUp(self):
        self.p1 = flow_assignment(
            "orchestrator", "Orchestrator", "P1", P1_SESSION
        )
        self.worker = flow_assignment(
            "implementation-api:g1", "Implementation", "P2", "session-p2"
        )
        self.events = [
            flow_event(
                "CONTROL_DISPATCH",
                "evt-dispatch",
                source=self.p1,
                target=self.worker,
            ),
            flow_event(
                "ASSIGNMENT_RESULT",
                "evt-result",
                assignment=self.worker,
                result="PASS",
            ),
        ]
        self.agents = [
            agent("wK", "wK:p1", P1_SESSION, "p1_orchestrator", "done"),
            agent("wK", "wK:p2", "session-p2", "p2_impl", "done"),
        ]

    def test_without_flow_events_preserves_legacy_nodes_as_unavailable(self):
        snapshot = build_session_snapshot(
            self.agents,
            "wK",
            "herdr-orchestrator",
            P1_SESSION,
            "wK:p1",
            1,
        )

        self.assertEqual("unavailable", snapshot["relationshipMode"])
        self.assertEqual("orchestrator", snapshot["nodes"][0]["id"])
        self.assertEqual([], snapshot["edges"])

    def test_events_separate_liveness_result_and_keep_p1_running(self):
        snapshot = build_session_snapshot(
            self.agents,
            "wK",
            "herdr-orchestrator",
            P1_SESSION,
            "wK:p1",
            1,
            flow_events=self.events,
        )
        nodes = {node["id"]: node for node in snapshot["nodes"]}

        self.assertEqual("event-backed", snapshot["relationshipMode"])
        self.assertEqual("running", nodes["orchestrator"]["liveness"])
        self.assertNotIn("result", nodes["orchestrator"])
        self.assertEqual("idle", nodes[self.worker["id"]]["liveness"])
        self.assertEqual("pass", nodes[self.worker["id"]]["result"])
        self.assertEqual(
            [("orchestrator", self.worker["id"], "control")],
            [
                (edge["source"], edge["target"], edge["kind"])
                for edge in snapshot["edges"]
            ],
        )

    def test_removed_completed_worker_remains_offline_with_result(self):
        first = build_session_snapshot(
            self.agents,
            "wK",
            "herdr-orchestrator",
            P1_SESSION,
            "wK:p1",
            1,
            flow_events=self.events,
        )
        removed = build_session_snapshot(
            self.agents[:1],
            "wK",
            "herdr-orchestrator",
            P1_SESSION,
            "wK:p1",
            2,
            flow_events=self.events,
            prior_nodes=first["nodes"],
        )
        node = next(
            node for node in removed["nodes"] if node["id"] == self.worker["id"]
        )

        self.assertEqual("offline", node["liveness"])
        self.assertEqual("pass", node["result"])

    def test_unchanged_event_projection_is_not_republished(self):
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
                flow_events=self.events,
            )
            unchanged = publish_if_changed(
                self.agents,
                "wK",
                "herdr-orchestrator",
                P1_SESSION,
                "wK:p1",
                "http://127.0.0.1:4173/api/snapshots",
                None,
                first,
                flow_events=self.events,
            )

        self.assertIs(first, unchanged)
        publish.assert_called_once()

    def test_flow_runtime_retains_valid_events_and_reports_malformed_tail(self):
        with tempfile.TemporaryDirectory() as directory:
            journal_path = Path(directory) / "flow-events.jsonl"
            journal = FlowJournal(
                journal_path, workspace_id="wK", run_id=P1_SESSION
            )
            journal.append(self.events[0])
            runtime = publisher_module.FlowRuntime(
                journal_path, workspace_id="wK", run_id=P1_SESSION
            )

            self.assertTrue(runtime.poll())
            valid_events = copy.deepcopy(runtime.events)
            with journal_path.open("ab") as handle:
                handle.write(b'{"malformed"')
            before = journal_path.read_bytes()

            self.assertTrue(runtime.poll())

            self.assertEqual(valid_events, runtime.events)
            self.assertEqual("degraded", runtime.telemetry["status"])
            self.assertEqual(self.events[0]["at"], runtime.telemetry["lastValidAt"])
            self.assertIn("malformed", runtime.telemetry["reason"])
            self.assertEqual(before, journal_path.read_bytes())

    def test_cli_accepts_exact_flow_journal_path(self):
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
                "--flow-journal",
                "/tmp/exact-flow.jsonl",
            ]
        )

        self.assertEqual(Path("/tmp/exact-flow.jsonl"), args.flow_journal)


if __name__ == "__main__":
    unittest.main()
