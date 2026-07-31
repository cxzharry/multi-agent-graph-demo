import ast
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from adapters.herdr.publisher import (
    PublisherError,
    build_snapshot,
    publish_if_changed,
    publish_snapshot,
)


def fixture_state():
    return {
        "schema_version": "herdr-workspace-state/v1",
        "workspace_id": "wK",
        "revision": 42,
        "slots": {
            "P1": {"status": "BUSY", "task_summary": "Route ready work"},
        },
        "run": {
            "contract_id": "role-graph-live-viewer-20260731",
            "started_at": "2026-07-31T10:15:00Z",
        },
        "lanes": {
            "implementation_a": {
                "state": "ACTIVE",
                "generation": 1,
                "task_summary": "Build the adapter",
            },
            "integration": {
                "state": "ACCEPTED",
                "generation": 1,
                "task_summary": "Integrate lane commits",
            },
            "correction_owner": {
                "state": "READY",
                "generation": 1,
            },
            "functional_qc": {
                "state": "FINDING",
                "generation": 2,
                "finding_reason": "Live update did not arrive",
            },
        },
        "watcher": {},
        "events": [
            {
                "cursor": cursor,
                "event_id": f"event-{cursor}",
                "kind": "LANE_PROGRESS",
                "lane_id": "implementation_a",
                "generation": 1,
            }
            for cursor in range(1, 61)
        ],
    }


def fixture_manifest():
    return {
        "schemaVersion": "herdr-role-graph-manifest/v1",
        "flowId": "test-flow",
        "title": "Test delivery",
        "nodes": [
            {
                "id": "orchestrator",
                "role": "Orchestrator",
                "assignee": "P1",
                "layer": 0,
                "task": "Route ready work",
                "source": {"type": "slot", "id": "P1"},
            },
            {
                "id": "implementation-a",
                "role": "Implementation A",
                "assignee": "P2",
                "layer": 1,
                "task": "Implement",
                "source": {"type": "lane", "id": "implementation_a"},
            },
            {
                "id": "integration",
                "role": "Integration",
                "assignee": "P5",
                "layer": 3,
                "task": "Integrate",
                "source": {"type": "lane", "id": "integration"},
            },
            {
                "id": "correction-owner",
                "role": "Correction Owner",
                "assignee": "P5",
                "layer": 2,
                "task": "Correct findings",
                "source": {"type": "lane", "id": "correction_owner"},
            },
            {
                "id": "functional-qc",
                "role": "Functional QC",
                "assignee": "P7",
                "layer": 4,
                "task": "Verify behavior",
                "source": {"type": "lane", "id": "functional_qc"},
            },
        ],
        "edges": [
            {
                "id": "orchestrator-to-implementation-a",
                "source": "orchestrator",
                "target": "implementation-a",
                "kind": "forward",
                "status": "active",
            },
            {
                "id": "implementation-a-to-integration",
                "source": "implementation-a",
                "target": "integration",
                "kind": "forward",
                "status": "active",
            },
            {
                "id": "integration-to-functional-qc",
                "source": "integration",
                "target": "functional-qc",
                "kind": "forward",
                "status": "active",
            },
        ],
        "failurePolicies": [
            {
                "gateNodeId": "functional-qc",
                "returnToNodeId": "correction-owner",
                "ownerNodeId": "correction-owner",
                "resumeNodeId": "integration",
                "rerunNodeIds": ["integration", "functional-qc"],
                "excludedNodeIds": ["implementation-a"],
            }
        ],
    }


class BuildSnapshotTests(unittest.TestCase):
    def test_maps_exact_workspace_to_generic_snapshot_identity(self):
        snapshot = build_snapshot(fixture_state(), fixture_manifest(), "wK")

        self.assertEqual("role-graph/v1", snapshot["schemaVersion"])
        self.assertEqual("herdr:wK", snapshot["scopeId"])
        self.assertEqual(
            "role-graph-live-viewer-20260731",
            snapshot["runId"],
        )
        self.assertEqual(42, snapshot["sequence"])
        self.assertEqual("2026-07-31T10:15:00Z", snapshot["generatedAt"])

    def test_rejects_workspace_mismatch(self):
        with self.assertRaisesRegex(PublisherError, "workspace_id"):
            build_snapshot(fixture_state(), fixture_manifest(), "another")

    def test_maps_slot_and_lane_sources_to_role_statuses(self):
        snapshot = build_snapshot(fixture_state(), fixture_manifest(), "wK")
        nodes = {node["id"]: node for node in snapshot["nodes"]}

        self.assertEqual("running", nodes["orchestrator"]["status"])
        self.assertEqual("running", nodes["implementation-a"]["status"])
        self.assertEqual("passed", nodes["integration"]["status"])
        self.assertEqual("failed", nodes["functional-qc"]["status"])
        self.assertEqual(2, nodes["functional-qc"]["generation"])

    def test_preserves_same_assignee_across_multiple_logical_roles(self):
        snapshot = build_snapshot(fixture_state(), fixture_manifest(), "wK")
        nodes = {node["id"]: node for node in snapshot["nodes"]}

        self.assertEqual("P5", nodes["integration"]["assignee"])
        self.assertEqual("P5", nodes["correction-owner"]["assignee"])

    def test_finding_selects_complete_matching_failure_policy(self):
        snapshot = build_snapshot(fixture_state(), fixture_manifest(), "wK")

        self.assertEqual(
            {
                **fixture_manifest()["failurePolicies"][0],
                "reason": "Live update did not arrive",
                "generation": 2,
            },
            snapshot["activeFailureRoute"],
        )

    def test_unknown_lane_remains_pending_without_borrowing_other_work(self):
        manifest = fixture_manifest()
        missing = manifest["nodes"][1]
        missing["source"]["id"] = "missing_lane"
        state = fixture_state()

        snapshot = build_snapshot(state, manifest, "wK")
        node = next(
            item for item in snapshot["nodes"] if item["id"] == "implementation-a"
        )

        self.assertEqual("pending", node["status"])
        self.assertEqual("Implement", node["task"])
        self.assertEqual(1, node["generation"])

    def test_omits_layer_when_manifest_does_not_define_one(self):
        manifest = fixture_manifest()
        del manifest["nodes"][1]["layer"]

        snapshot = build_snapshot(fixture_state(), manifest, "wK")
        node = next(
            item for item in snapshot["nodes"] if item["id"] == "implementation-a"
        )

        self.assertNotIn("layer", node)

    def test_events_are_bounded_and_keep_ledger_order(self):
        snapshot = build_snapshot(fixture_state(), fixture_manifest(), "wK")

        self.assertEqual(50, len(snapshot["events"]))
        self.assertEqual(
            [f"event-{cursor}" for cursor in range(11, 61)],
            [event["id"] for event in snapshot["events"]],
        )

    def test_input_values_are_not_mutated(self):
        state = fixture_state()
        manifest = fixture_manifest()
        original_state = copy.deepcopy(state)
        original_manifest = copy.deepcopy(manifest)

        build_snapshot(state, manifest, "wK")

        self.assertEqual(original_state, state)
        self.assertEqual(original_manifest, manifest)


class PublishingTests(unittest.TestCase):
    def test_workspace_mismatch_fails_before_network_access(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "state.json"
            manifest_path = root / "manifest.json"
            state_path.write_text(json.dumps(fixture_state()), encoding="utf-8")
            manifest_path.write_text(
                json.dumps(fixture_manifest()),
                encoding="utf-8",
            )

            with mock.patch(
                "adapters.herdr.publisher.publish_snapshot"
            ) as publish:
                with self.assertRaisesRegex(PublisherError, "workspace_id"):
                    publish_if_changed(
                        state_path,
                        manifest_path,
                        "another",
                        "http://127.0.0.1:4173/api/snapshots",
                        None,
                        None,
                    )

            publish.assert_not_called()

    def test_unchanged_revision_is_not_republished(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "state.json"
            manifest_path = root / "manifest.json"
            state_path.write_text(json.dumps(fixture_state()), encoding="utf-8")
            manifest_path.write_text(
                json.dumps(fixture_manifest()),
                encoding="utf-8",
            )

            with mock.patch(
                "adapters.herdr.publisher.publish_snapshot"
            ) as publish:
                revision = publish_if_changed(
                    state_path,
                    manifest_path,
                    "wK",
                    "http://127.0.0.1:4173/api/snapshots",
                    None,
                    None,
                )
                unchanged = publish_if_changed(
                    state_path,
                    manifest_path,
                    "wK",
                    "http://127.0.0.1:4173/api/snapshots",
                    None,
                    revision,
                )

            self.assertEqual(42, revision)
            self.assertEqual(42, unchanged)
            publish.assert_called_once()

    def test_missing_revision_is_rejected_before_network_access(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = fixture_state()
            del state["revision"]
            state_path = root / "state.json"
            manifest_path = root / "manifest.json"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            manifest_path.write_text(
                json.dumps(fixture_manifest()),
                encoding="utf-8",
            )

            with mock.patch(
                "adapters.herdr.publisher.publish_snapshot"
            ) as publish:
                with self.assertRaisesRegex(PublisherError, "revision"):
                    publish_if_changed(
                        state_path,
                        manifest_path,
                        "wK",
                        "http://127.0.0.1:4173/api/snapshots",
                        None,
                        None,
                    )

            publish.assert_not_called()

    def test_posts_json_with_optional_bearer_token(self):
        response = mock.MagicMock()
        response.__enter__.return_value.status = 202

        with mock.patch(
            "adapters.herdr.publisher.urllib.request.urlopen",
            return_value=response,
        ) as urlopen:
            publish_snapshot(
                {"schemaVersion": "role-graph/v1"},
                "http://127.0.0.1:4173/api/snapshots",
                "secret",
            )

        request = urlopen.call_args.args[0]
        self.assertEqual("POST", request.method)
        self.assertEqual("Bearer secret", request.get_header("Authorization"))
        self.assertEqual(
            {"schemaVersion": "role-graph/v1"},
            json.loads(request.data),
        )


class ReadOnlyContractTests(unittest.TestCase):
    def test_source_has_no_process_pane_state_mutation_or_receipt_calls(self):
        import adapters.herdr.publisher as publisher

        source = Path(publisher.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported_modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.add(node.module)
        called_names = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        called_attributes = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }

        self.assertNotIn("subprocess", imported_modules)
        self.assertFalse(
            imported_modules
            & {
                "manage_worker_pool",
                "run_watcher",
                "workspace_state",
                "write_lane_receipt",
            }
        )
        self.assertFalse(
            (called_names | called_attributes)
            & {
                "mutate_state",
                "append_observation",
                "start_agent",
                "signal_agent",
                "write_receipt",
                "Popen",
                "system",
            }
        )


if __name__ == "__main__":
    unittest.main()
