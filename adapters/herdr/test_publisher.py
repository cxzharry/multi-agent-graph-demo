import ast
import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from adapters.herdr.publisher import (
    PublisherError,
    _parser,
    build_snapshot,
    main,
    publish_if_changed,
    publish_snapshot,
    synthesize_manifest,
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


def assert_protocol_valid(test_case, snapshot):
    validator = """
import {validateSnapshot} from './shared/role-graph.js';
const chunks = [];
for await (const chunk of process.stdin) chunks.push(chunk);
validateSnapshot(JSON.parse(chunks.join('')));
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", validator],
        cwd=Path(__file__).parents[2],
        input=json.dumps(snapshot),
        text=True,
        capture_output=True,
        check=False,
    )
    test_case.assertEqual(0, result.returncode, result.stderr)


class SyntheticManifestTests(unittest.TestCase):
    def test_synthetic_manifest_is_deterministic_and_only_claims_control_edges(self):
        state = fixture_state()
        state["lanes"]["implementation_a"].update(
            {
                "lane_id": "implementation_a",
                "role": "Implementation",
                "slot": "P2",
            }
        )

        first = synthesize_manifest(state)
        second = synthesize_manifest(copy.deepcopy(state))

        self.assertEqual(first, second)
        self.assertEqual([], first["failurePolicies"])
        self.assertTrue(first["title"].startswith("Auto operational view"))
        self.assertEqual(
            {("orchestrator", node["id"]) for node in first["nodes"][1:]},
            {(edge["source"], edge["target"]) for edge in first["edges"]},
        )

    def test_synthetic_snapshot_contains_lane_added_at_current_revision(self):
        state = fixture_state()
        state["revision"] = 43
        state["lanes"]["late_task"] = {
            "lane_id": "late_task",
            "role": "Follow-up",
            "slot": "P3",
            "state": "ACTIVE",
            "generation": 1,
            "task_summary": "Handle late task",
        }

        snapshot = build_snapshot(state, synthesize_manifest(state), "wK")

        self.assertEqual(43, snapshot["sequence"])
        self.assertIn(
            "Handle late task",
            {node["task"] for node in snapshot["nodes"]},
        )

    def test_sparse_canonical_lanes_produce_a_protocol_valid_snapshot(self):
        state = fixture_state()

        snapshot = build_snapshot(state, synthesize_manifest(state), "wK")
        correction = next(
            node for node in snapshot["nodes"] if node["role"] == "Correction Owner"
        )

        self.assertEqual("Unassigned", correction["assignee"])
        self.assertEqual("Correction Owner", correction["task"])
        assert_protocol_valid(self, snapshot)

    def test_synthetic_lane_ids_do_not_collide_after_encoding(self):
        state = fixture_state()
        state["lanes"] = {
            "lane_a": {
                "role": "Underscore Lane",
                "slot": "P2",
                "task_summary": "Handle underscore lane",
            },
            "lane-a": {
                "role": "Hyphen Lane",
                "slot": "P3",
                "task_summary": "Handle hyphen lane",
            },
        }

        snapshot = build_snapshot(state, synthesize_manifest(state), "wK")
        lane_ids = [node["id"] for node in snapshot["nodes"][1:]]

        self.assertEqual(2, len(set(lane_ids)))
        assert_protocol_valid(self, snapshot)


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

    def test_custom_node_tracks_reassignment_tip_and_chain_events(self):
        state = fixture_state()
        state["lanes"]["implementation_a"]["state"] = "SUPERSEDED"
        state["lanes"]["implementation_a_reassigned_g2"] = {
            "lane_id": "implementation_a_reassigned_g2",
            "supersedes": "implementation_a",
            "state": "ACTIVE",
            "generation": 2,
            "slot": "P3",
            "task_summary": "Build adapter",
        }
        state["events"].append(
            {
                "cursor": 61,
                "event_id": "event-g2",
                "kind": "LANE_PROGRESS",
                "lane_id": "implementation_a_reassigned_g2",
                "generation": 2,
            }
        )

        snapshot = build_snapshot(state, fixture_manifest(), "wK")
        node = next(
            item for item in snapshot["nodes"] if item["id"] == "implementation-a"
        )

        self.assertEqual("running", node["status"])
        self.assertEqual(2, node["generation"])
        self.assertEqual("P3", node["assignee"])
        self.assertEqual("implementation-a", snapshot["events"][-2]["nodeId"])
        self.assertEqual("implementation-a", snapshot["events"][-1]["nodeId"])

    def test_custom_manifest_appends_only_unmapped_logical_lane(self):
        state = fixture_state()
        state["lanes"]["late_task"] = {
            "lane_id": "late_task",
            "role": "Follow-up",
            "slot": "P4",
            "state": "ACTIVE",
            "generation": 1,
        }

        snapshot = build_snapshot(state, fixture_manifest(), "wK")
        additions = [
            node for node in snapshot["nodes"] if node["id"].startswith("live-")
        ]

        self.assertEqual(["P4"], [node["assignee"] for node in additions])
        self.assertEqual(
            1,
            sum(
                edge["target"] == additions[0]["id"]
                for edge in snapshot["edges"]
            ),
        )

    def test_live_addition_has_no_control_edge_when_p1_source_is_ambiguous(self):
        state = fixture_state()
        state["lanes"]["late_task"] = {
            "state": "ACTIVE",
            "generation": 1,
        }
        manifest = fixture_manifest()
        manifest["nodes"].append(
            {
                "id": "orchestrator-shadow",
                "role": "Orchestrator Shadow",
                "assignee": "P1",
                "source": {"type": "slot", "id": "P1"},
            }
        )

        snapshot = build_snapshot(state, manifest, "wK")
        addition = next(
            node for node in snapshot["nodes"] if node["id"].startswith("live-")
        )

        self.assertFalse(
            any(edge["target"] == addition["id"] for edge in snapshot["edges"])
        )

    def test_custom_live_addition_ids_do_not_collide_after_encoding(self):
        state = fixture_state()
        state["lanes"]["lane_a"] = {
            "role": "Underscore Lane",
            "slot": "P2",
            "task_summary": "Handle underscore lane",
        }
        state["lanes"]["lane-a"] = {
            "role": "Hyphen Lane",
            "slot": "P3",
            "task_summary": "Handle hyphen lane",
        }

        snapshot = build_snapshot(state, fixture_manifest(), "wK")
        additions = [
            node for node in snapshot["nodes"] if node["id"].startswith("live-")
        ]

        self.assertEqual(2, len(additions))
        self.assertEqual(2, len({node["id"] for node in additions}))
        assert_protocol_valid(self, snapshot)

    def test_live_addition_allocates_around_an_authored_node_id(self):
        state = fixture_state()
        state["lanes"]["late_task"] = {
            "role": "Follow-up",
            "slot": "P4",
            "task_summary": "Handle late task",
        }
        manifest = fixture_manifest()
        would_be_generated = "live-6c6174655f7461736b"
        manifest["nodes"].append(
            {
                "id": would_be_generated,
                "role": "Authored Observer",
                "assignee": "P9",
                "task": "Observe authored work",
                "source": {"type": "slot", "id": "P9"},
            }
        )

        first = build_snapshot(state, manifest, "wK")
        second = build_snapshot(copy.deepcopy(state), manifest, "wK")
        node_ids = [node["id"] for node in first["nodes"]]
        addition = next(
            node for node in first["nodes"] if node["role"] == "Follow-up"
        )

        self.assertEqual(first, second)
        self.assertIn(would_be_generated, node_ids)
        self.assertNotEqual(would_be_generated, addition["id"])
        self.assertEqual(len(node_ids), len(set(node_ids)))
        assert_protocol_valid(self, first)

    def test_live_control_edge_allocates_around_an_authored_edge_id(self):
        state = fixture_state()
        state["lanes"]["late_task"] = {
            "role": "Follow-up",
            "slot": "P4",
            "task_summary": "Handle late task",
        }
        manifest = fixture_manifest()
        would_be_generated = "control-orchestrator-live-6c6174655f7461736b"
        authored_edge = {
            "id": would_be_generated,
            "source": "orchestrator",
            "target": "implementation-a",
            "kind": "forward",
            "status": "active",
        }
        manifest["edges"].append(authored_edge)

        first = build_snapshot(state, manifest, "wK")
        second = build_snapshot(copy.deepcopy(state), manifest, "wK")
        addition = next(
            node for node in first["nodes"] if node["role"] == "Follow-up"
        )
        generated_edge = next(
            edge for edge in first["edges"] if edge["target"] == addition["id"]
        )
        edge_ids = [edge["id"] for edge in first["edges"]]

        self.assertEqual(first, second)
        self.assertIn(authored_edge, first["edges"])
        self.assertNotEqual(would_be_generated, generated_edge["id"])
        self.assertEqual(len(edge_ids), len(set(edge_ids)))
        assert_protocol_valid(self, first)


class PublishingTests(unittest.TestCase):
    def test_posts_explicit_replacement_header_when_requested(self):
        response = mock.MagicMock()
        response.__enter__.return_value.status = 202

        with mock.patch(
            "adapters.herdr.publisher.urllib.request.urlopen",
            return_value=response,
        ) as urlopen:
            publish_snapshot(
                {"schemaVersion": "role-graph/v1"},
                "http://127.0.0.1:4173/api/snapshots",
                None,
                replace_current=True,
            )

        request = urlopen.call_args.args[0]
        headers = {key.lower(): value for key, value in request.header_items()}
        self.assertEqual("true", headers["x-role-graph-replace-current"])

    def test_cli_replace_current_marks_only_first_watch_post(self):
        argv = [
            "publisher.py",
            "--state",
            "state.json",
            "--synthesize",
            "--workspace-id",
            "wK",
            "--endpoint",
            "http://127.0.0.1:4173/api/snapshots",
            "--watch",
            "--replace-current",
        ]
        with mock.patch("sys.argv", argv), mock.patch(
            "adapters.herdr.publisher.publish_if_changed",
            side_effect=[42, 43],
        ) as publish, mock.patch(
            "adapters.herdr.publisher.time.sleep",
            side_effect=[None, KeyboardInterrupt],
        ):
            with self.assertRaises(KeyboardInterrupt):
                main()

        self.assertEqual(
            [True, False],
            [call.kwargs["replace_current"] for call in publish.call_args_list],
        )

    def test_synthetic_mode_publishes_without_manifest_file(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            state_path.write_text(json.dumps(fixture_state()), encoding="utf-8")

            with mock.patch(
                "adapters.herdr.publisher.publish_snapshot"
            ) as publish:
                revision = publish_if_changed(
                    state_path,
                    None,
                    "wK",
                    "http://127.0.0.1:4173/api/snapshots",
                    None,
                    None,
                    synthesize=True,
                )

        self.assertEqual(42, revision)
        snapshot = publish.call_args.args[0]
        self.assertTrue(snapshot["title"].startswith("Auto operational view"))

    def test_rejects_missing_or_conflicting_publisher_modes_before_network(self):
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
                for selected_manifest, synthesize in (
                    (None, False),
                    (manifest_path, True),
                ):
                    with self.subTest(
                        manifest=selected_manifest,
                        synthesize=synthesize,
                    ):
                        with self.assertRaisesRegex(
                            PublisherError,
                            "select exactly one",
                        ):
                            publish_if_changed(
                                state_path,
                                selected_manifest,
                                "wK",
                                "http://127.0.0.1:4173/api/snapshots",
                                None,
                                None,
                                synthesize=synthesize,
                            )

            publish.assert_not_called()

    def test_supersession_branch_fails_before_network_access(self):
        state = fixture_state()
        state["lanes"]["implementation_a_reassigned_g2"] = {
            "supersedes": "implementation_a",
        }
        state["lanes"]["implementation_a_hotfix_g2"] = {
            "supersedes": "implementation_a",
        }

        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            with mock.patch(
                "adapters.herdr.publisher.publish_snapshot"
            ) as publish:
                with self.assertRaisesRegex(
                    PublisherError,
                    "implementation_a.*implementation_a_hotfix_g2.*"
                    "implementation_a_reassigned_g2",
                ):
                    publish_if_changed(
                        state_path,
                        None,
                        "wK",
                        "http://127.0.0.1:4173/api/snapshots",
                        None,
                        None,
                        synthesize=True,
                    )

        publish.assert_not_called()

    def test_supersession_cycle_fails_before_network_access(self):
        state = fixture_state()
        state["lanes"]["implementation_a"]["supersedes"] = "integration"
        state["lanes"]["integration"]["supersedes"] = "implementation_a"

        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            with mock.patch(
                "adapters.herdr.publisher.publish_snapshot"
            ) as publish:
                with self.assertRaisesRegex(
                    PublisherError,
                    "implementation_a.*integration|integration.*implementation_a",
                ):
                    publish_if_changed(
                        state_path,
                        None,
                        "wK",
                        "http://127.0.0.1:4173/api/snapshots",
                        None,
                        None,
                        synthesize=True,
                    )

        publish.assert_not_called()

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


class ParserTests(unittest.TestCase):
    def test_accepts_synthetic_mode_without_manifest(self):
        args = _parser().parse_args(
            [
                "--state",
                "state.json",
                "--synthesize",
                "--workspace-id",
                "wK",
                "--endpoint",
                "http://127.0.0.1:4173/api/snapshots",
            ]
        )

        self.assertTrue(args.synthesize)
        self.assertIsNone(args.manifest)


if __name__ == "__main__":
    unittest.main()
