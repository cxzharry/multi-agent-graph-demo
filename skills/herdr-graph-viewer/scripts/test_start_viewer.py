from __future__ import annotations

import importlib.util
import json
import os
import threading
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).with_name("start_viewer.py")


def load_launcher():
    if not SCRIPT.exists():
        return None
    spec = importlib.util.spec_from_file_location("start_viewer", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class StartViewerTest(unittest.TestCase):
    def setUp(self):
        self.launcher = load_launcher()

    def require_launcher(self):
        self.assertIsNotNone(self.launcher, "start_viewer.py is missing")
        return self.launcher

    def workspace_list(
        self, workspace: str = "w1", label: str = "herdr-orchestrator"
    ):
        return {
            "result": {
                "type": "workspace_list",
                "workspaces": [{"workspace_id": workspace, "label": label}],
            }
        }

    def write_state(
        self,
        root: Path,
        name: str,
        *,
        workspace: str,
        pane: str,
        run_id: str,
        session_id: str = "p1-session",
        revision: int = 3,
        role_graph_manifest: str | None = None,
    ) -> Path:
        run = {"contract_id": run_id}
        if role_graph_manifest is not None:
            run["role_graph_manifest"] = role_graph_manifest
        path = root / workspace / name / "workspace-state.json"
        path.parent.mkdir(parents=True)
        path.write_text(
            json.dumps(
                {
                    "schema_version": "herdr-workspace-state/v1",
                    "workspace_id": workspace,
                    "revision": revision,
                    "run": run,
                    "controller": {
                        "pane_id": pane,
                        "session_id": session_id,
                        "workspace_id": workspace,
                    },
                    "slots": {
                        "P1": {
                            "pane_id": pane,
                            "session_id": session_id,
                            "workspace_id": workspace,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        return path

    def write_manifest(self, path: Path) -> Path:
        path.write_text(
            json.dumps(
                {
                    "schemaVersion": "herdr-role-graph-manifest/v1",
                    "nodes": [],
                    "edges": [],
                    "failurePolicies": [],
                }
            ),
            encoding="utf-8",
        )
        return path

    def manifest_with_node(self, **overrides) -> str:
        node = {
            "id": "orchestrator",
            "role": "Orchestrator",
            "assignee": "P1",
            "task": "Route ready work",
            "source": {"type": "slot", "id": "P1"},
        }
        node.update(overrides)
        return json.dumps(
            {
                "schemaVersion": "herdr-role-graph-manifest/v1",
                "nodes": [node],
                "edges": [],
                "failurePolicies": [],
            }
        )

    def assert_custom_manifest_preflight_error(
        self, manifest_contents: str, expected_message: str
    ) -> None:
        launcher = self.require_launcher()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            (repo / "adapters/herdr").mkdir(parents=True)
            (repo / "server.js").write_text("", encoding="utf-8")
            (repo / "adapters/herdr/publisher.py").write_text("", encoding="utf-8")
            manifest = root / "custom-manifest.json"
            manifest.write_text(manifest_contents, encoding="utf-8")
            state = self.write_state(
                root,
                "current",
                workspace="w1",
                pane="w1:p1",
                run_id="current-run",
                role_graph_manifest=str(manifest),
            )
            args = Namespace(
                state=state,
                manifest=None,
                repo=repo,
                runs_root=root,
                port_start=4173,
                port_end=4173,
            )

            with mock.patch.dict(
                os.environ,
                {
                    "HERDR_ENV": "1",
                    "HERDR_WORKSPACE_ID": "w1",
                    "HERDR_PANE_ID": "w1:p1",
                },
                clear=True,
            ), mock.patch.object(launcher, "_herdr") as herdr, mock.patch.object(
                launcher, "probe_viewer"
            ) as probe:
                with self.assertRaises(launcher.LauncherError) as raised:
                    launcher.launch(args)

            self.assertEqual(raised.exception.code, "invalid_manifest")
            self.assertIn(expected_message, str(raised.exception))
            herdr.assert_not_called()
            probe.assert_not_called()

    def assert_query_output_fails_before_mutation(
        self,
        query: str,
        query_output: str = "",
        *,
        cold_server: bool = False,
    ) -> None:
        launcher = self.require_launcher()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            (repo / "adapters/herdr").mkdir(parents=True)
            (repo / "server.js").write_text("", encoding="utf-8")
            (repo / "adapters/herdr/publisher.py").write_text("", encoding="utf-8")
            state = self.write_state(
                root,
                "current",
                workspace="w1",
                pane="w1:p1",
                run_id="current-run",
                revision=8,
            )
            commands: list[tuple[str, ...]] = []

            def fake_run(command, **_kwargs):
                args = tuple(command[1:])
                commands.append(args)
                if args[:2] == ("workspace", "list"):
                    stdout = json.dumps(self.workspace_list())
                elif args[:2] == ("pane", "list"):
                    stdout = (
                        query_output
                        if query == "pane-list"
                        else json.dumps(
                            {"result": {"panes": [{"pane_id": "publisher"}]}}
                        )
                    )
                elif args[:2] == ("pane", "process-info"):
                    stdout = query_output
                elif args[:2] == ("pane", "split"):
                    stdout = json.dumps(
                        {"result": {"pane": {"pane_id": "new-publisher"}}}
                    )
                elif args[:2] == ("pane", "rename"):
                    stdout = json.dumps({"result": {}})
                elif args[:2] in {("pane", "run"), ("pane", "send-keys")}:
                    stdout = ""
                else:
                    raise AssertionError(args)
                return mock.Mock(returncode=0, stdout=stdout, stderr="")

            args = Namespace(
                state=state,
                manifest=None,
                repo=repo,
                runs_root=root,
                port_start=4173,
                port_end=4173,
            )
            probe_results = iter(("free", "viewer") if cold_server else ("viewer",))

            with mock.patch.dict(
                os.environ,
                {
                    "HERDR_ENV": "1",
                    "HERDR_WORKSPACE_ID": "w1",
                    "HERDR_PANE_ID": "w1:p1",
                },
                clear=True,
            ), mock.patch.object(
                launcher.subprocess, "run", side_effect=fake_run
            ), mock.patch.object(
                launcher, "probe_viewer", side_effect=lambda _port: next(probe_results)
            ), mock.patch.object(
                launcher,
                "_snapshot",
                return_value={
                    "spaceName": "herdr-orchestrator",
                    "scopeId": "herdr:w1",
                    "runId": "current-run",
                    "sequence": 8,
                },
            ):
                with self.assertRaises(launcher.LauncherError) as raised:
                    launcher.launch(args)

            self.assertEqual(raised.exception.code, "herdr_error")
            expected = [
                ("workspace", "list"),
                ("pane", "list", "--workspace", "w1"),
            ]
            if query == "process-info":
                expected.append(("pane", "process-info", "--pane", "publisher"))
            self.assertEqual(commands, expected)

    def test_selects_state_bound_to_current_p1_pane_and_session(self):
        launcher = self.require_launcher()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current = self.write_state(
                root,
                "current",
                workspace="w1",
                pane="w1:p1",
                session_id="current-session",
                run_id="current-run",
            )
            self.write_state(
                root,
                "stale",
                workspace="w1",
                pane="w1:p1",
                session_id="stale-session",
                run_id="stale-run",
            )
            self.write_state(
                root, "foreign", workspace="w2", pane="w2:p1", run_id="foreign-run"
            )

            try:
                selected = launcher.select_state(
                    root,
                    "w1",
                    "w1:p1",
                    "current-session",
                )
            except (TypeError, launcher.LauncherError) as error:
                self.fail(f"pane-and-session selection is unavailable: {error}")

            self.assertEqual(selected.path, current.resolve())
            self.assertEqual(selected.run_id, "current-run")

    def test_resolves_exact_workspace_label(self):
        launcher = self.require_launcher()
        response = {
            "result": {
                "type": "workspace_list",
                "workspaces": [
                    {"workspace_id": "w2", "label": "car-edge"},
                    {"workspace_id": "w1", "label": "herdr-orchestrator"},
                ],
            }
        }

        with mock.patch.object(launcher, "_herdr", return_value=response) as herdr:
            space_name = launcher._resolve_space_name("w1")

        self.assertEqual(space_name, "herdr-orchestrator")
        herdr.assert_called_once_with("workspace", "list")

    def test_rejects_missing_or_blank_workspace_label(self):
        launcher = self.require_launcher()
        responses = [
            {"result": {"type": "workspace_list", "workspaces": []}},
            self.workspace_list(label="  "),
        ]

        for response in responses:
            with self.subTest(response=response), mock.patch.object(
                launcher, "_herdr", return_value=response
            ):
                with self.assertRaises(launcher.LauncherError) as raised:
                    launcher._resolve_space_name("w1")

                self.assertEqual(raised.exception.code, "workspace_selection_error")

    def test_stale_states_do_not_fall_back_by_pane_or_candidate_count(self):
        launcher = self.require_launcher()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_state(
                root,
                "stale",
                workspace="w1",
                pane="w1:p1",
                session_id="stale-session",
                run_id="stale-run",
            )

            try:
                selected = launcher.select_state(
                    root,
                    "w1",
                    "w1:p1",
                    "current-session",
                )
            except (TypeError, launcher.LauncherError) as error:
                self.fail(f"stale-state rejection is unavailable: {error}")

            self.assertIsNone(selected)

    def test_explicit_state_remains_exact_despite_current_p1_identity(self):
        launcher = self.require_launcher()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            explicit = self.write_state(
                root,
                "explicit",
                workspace="w1",
                pane="w1:p9",
                session_id="historical-session",
                run_id="explicit-run",
            )

            try:
                selected = launcher.select_state(
                    root,
                    "w1",
                    "w1:p1",
                    "current-session",
                    explicit=explicit,
                )
            except TypeError as error:
                self.fail(f"exact explicit selection is unavailable: {error}")

            self.assertEqual(selected.path, explicit.resolve())
            self.assertEqual(selected.run_id, "explicit-run")

    def test_rejects_explicit_state_from_another_workspace(self):
        launcher = self.require_launcher()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            foreign = self.write_state(
                root, "foreign", workspace="w2", pane="w2:p1", run_id="foreign-run"
            )

            with self.assertRaises(launcher.LauncherError) as raised:
                launcher.select_state(root, "w1", "w1:p1", explicit=foreign)

            self.assertEqual(raised.exception.code, "workspace_mismatch")

    def test_launch_rejects_selected_state_without_p1_pane_binding(self):
        launcher = self.require_launcher()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            (repo / "adapters/herdr").mkdir(parents=True)
            (repo / "server.js").write_text("", encoding="utf-8")
            (repo / "adapters/herdr/publisher.py").write_text("", encoding="utf-8")
            state = self.write_state(
                root, "current", workspace="w1", pane="w1:p1", run_id="current-run"
            )
            value = json.loads(state.read_text(encoding="utf-8"))
            value["controller"]["pane_id"] = None
            value["slots"]["P1"]["pane_id"] = None
            state.write_text(json.dumps(value), encoding="utf-8")
            args = Namespace(
                state=state,
                manifest=None,
                repo=repo,
                runs_root=root,
                port_start=4173,
                port_end=4173,
            )

            with mock.patch.dict(
                os.environ,
                {
                    "HERDR_ENV": "1",
                    "HERDR_WORKSPACE_ID": "w1",
                    "HERDR_PANE_ID": "w1:p6",
                },
                clear=True,
            ), mock.patch.object(launcher, "_herdr") as herdr, mock.patch.object(
                launcher, "probe_viewer", return_value="free"
            ):
                with self.assertRaises(launcher.LauncherError) as raised:
                    launcher.launch(args)

            self.assertEqual(raised.exception.code, "invalid_state")
            self.assertIn("no usable P1 pane binding", str(raised.exception))
            herdr.assert_not_called()

    def test_blank_workspace_label_fails_before_pane_mutation(self):
        launcher = self.require_launcher()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            (repo / "adapters/herdr").mkdir(parents=True)
            (repo / "server.js").write_text("", encoding="utf-8")
            (repo / "adapters/herdr/publisher.py").write_text("", encoding="utf-8")
            state = self.write_state(
                root, "current", workspace="w1", pane="w1:p1", run_id="current-run"
            )
            mutations: list[tuple[str, ...]] = []

            def fake_herdr(*args):
                if args[:2] == ("workspace", "list"):
                    return self.workspace_list(label=" ")
                if args[:2] == ("pane", "list"):
                    return {"result": {"panes": []}}
                if args[:2] in {
                    ("pane", "split"),
                    ("pane", "rename"),
                    ("pane", "run"),
                    ("pane", "send-keys"),
                }:
                    mutations.append(args)
                    return {"result": {"pane": {"pane_id": "publisher"}}}
                raise AssertionError(args)

            args = Namespace(
                state=state,
                manifest=None,
                repo=repo,
                runs_root=root,
                port_start=4173,
                port_end=4173,
            )

            with mock.patch.dict(
                os.environ,
                {
                    "HERDR_ENV": "1",
                    "HERDR_WORKSPACE_ID": "w1",
                    "HERDR_PANE_ID": "w1:p1",
                },
                clear=True,
            ), mock.patch.object(
                launcher, "_herdr", side_effect=fake_herdr
            ), mock.patch.object(
                launcher, "probe_viewer", return_value="viewer"
            ), mock.patch.object(
                launcher,
                "_snapshot",
                return_value={
                    "spaceName": "herdr-orchestrator",
                    "scopeId": "herdr:w1",
                    "runId": "current-run",
                    "sequence": 3,
                },
            ):
                with self.assertRaises(launcher.LauncherError) as raised:
                    launcher.launch(args)

            self.assertEqual(raised.exception.code, "workspace_selection_error")
            self.assertEqual(mutations, [])

    def test_port_selection_reuses_viewer_and_skips_unrelated_service(self):
        launcher = self.require_launcher()
        probes = {4173: "occupied", 4174: "viewer", 4175: "free"}

        selected = launcher.select_port(lambda port: probes[port], 4173, 4175)

        self.assertEqual(selected, (4174, True))

    def test_port_selection_uses_first_free_port(self):
        launcher = self.require_launcher()
        probes = {4173: "occupied", 4174: "free"}

        selected = launcher.select_port(lambda port: probes[port], 4173, 4174)

        self.assertEqual(selected, (4174, False))

    def test_publisher_match_requires_exact_state_and_endpoint(self):
        launcher = self.require_launcher()
        target = "/tmp/current/workspace-state.json"
        manifest = "/tmp/current/role-graph-manifest.json"
        endpoint = "http://127.0.0.1:4173/api/snapshots"
        process = {
            "foreground_processes": [
                {
                    "cmdline": (
                        "python3 -B adapters/herdr/publisher.py "
                        f"--state {target} --manifest {manifest} "
                        "--workspace-id w1 --space-name herdr-orchestrator "
                        f"--endpoint {endpoint} --watch"
                    )
                }
            ]
        }

        self.assertTrue(
            launcher.publisher_matches(
                process,
                target,
                launcher.ManifestSelection("custom", Path(manifest)),
                "w1",
                "herdr-orchestrator",
                endpoint,
                True,
            )
        )
        self.assertFalse(
            launcher.publisher_matches(
                process,
                "/tmp/other/workspace-state.json",
                launcher.ManifestSelection("custom", Path(manifest)),
                "w1",
                "herdr-orchestrator",
                endpoint,
                True,
            )
        )

    def test_selects_synthetic_only_when_no_custom_source_exists(self):
        launcher = self.require_launcher()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = self.write_state(
                root, "current", workspace="w1", pane="w1:p1", run_id="current-run"
            )
            selected = launcher._load_state(state, "w1")

            self.assertEqual(
                launcher.ManifestSelection("synthetic", None),
                launcher._resolve_manifest(selected, None),
            )

    def test_configured_missing_manifest_fails_instead_of_synthesizing(self):
        launcher = self.require_launcher()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = self.write_state(
                root,
                "current",
                workspace="w1",
                pane="w1:p1",
                run_id="current-run",
                role_graph_manifest=str(root / "missing.json"),
            )

            with self.assertRaises(launcher.LauncherError) as raised:
                launcher._resolve_manifest(launcher._load_state(state, "w1"), None)
            self.assertEqual(raised.exception.code, "missing_manifest")

    def test_malformed_custom_manifest_fails_before_process_discovery(self):
        self.assert_custom_manifest_preflight_error("{", "Cannot parse manifest")

    def test_non_object_custom_manifest_fails_before_process_discovery(self):
        self.assert_custom_manifest_preflight_error("[]", "must be a JSON object")

    def test_wrong_schema_custom_manifest_fails_before_process_discovery(self):
        self.assert_custom_manifest_preflight_error(
            json.dumps(
                {
                    "schemaVersion": "role-graph/v1",
                    "nodes": [],
                    "edges": [],
                    "failurePolicies": [],
                }
            ),
            "schemaVersion must be herdr-role-graph-manifest/v1",
        )

    def test_invalid_custom_graph_fails_before_process_discovery(self):
        self.assert_custom_manifest_preflight_error(
            json.dumps(
                {
                    "schemaVersion": "herdr-role-graph-manifest/v1",
                    "nodes": [
                        {
                            "id": "orchestrator",
                            "role": "Orchestrator",
                            "assignee": "P1",
                            "task": "Route ready work",
                            "source": {"type": "slot", "id": "P1"},
                        }
                    ],
                    "edges": [
                        {
                            "id": "missing-target",
                            "source": "orchestrator",
                            "target": "missing",
                            "kind": "forward",
                            "status": "active",
                        }
                    ],
                    "failurePolicies": [],
                }
            ),
            "edges[0].target refers to an unknown node: missing",
        )

    def test_empty_node_task_fails_before_process_discovery(self):
        self.assert_custom_manifest_preflight_error(
            self.manifest_with_node(task=""),
            "nodes[0].task must be a non-empty string",
        )

    def test_wrong_type_node_layer_fails_before_process_discovery(self):
        self.assert_custom_manifest_preflight_error(
            self.manifest_with_node(layer="1"),
            "nodes[0].layer must be a non-negative integer",
        )

    def test_negative_node_layer_fails_before_process_discovery(self):
        self.assert_custom_manifest_preflight_error(
            self.manifest_with_node(layer=-1),
            "nodes[0].layer must be a non-negative integer",
        )

    def test_resolves_custom_manifest_by_exact_precedence(self):
        launcher = self.require_launcher()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            explicit_manifest = root / "explicit.json"
            self.write_manifest(explicit_manifest)
            state_manifest = root / "manifest.json"
            self.write_manifest(state_manifest)
            state = self.write_state(
                root,
                "current",
                workspace="w1",
                pane="w1:p1",
                run_id="current-run",
                role_graph_manifest=str(state_manifest),
            )
            selected = launcher._load_state(state, "w1")

            self.assertEqual(
                launcher.ManifestSelection("custom", explicit_manifest.resolve()),
                launcher._resolve_manifest(selected, explicit_manifest),
            )
            self.assertEqual(
                launcher.ManifestSelection("custom", state_manifest.resolve()),
                launcher._resolve_manifest(selected, None),
            )

            no_manifest_state = self.write_state(
                root, "local", workspace="w1", pane="w1:p1", run_id="local-run"
            )
            run_local = no_manifest_state.parent / "role-graph-manifest.json"
            self.write_manifest(run_local)
            selected = launcher._load_state(no_manifest_state, "w1")

            self.assertEqual(
                launcher.ManifestSelection("custom", run_local.resolve()),
                launcher._resolve_manifest(selected, None),
            )

    def test_resolves_relative_configured_manifest_from_run_directory(self):
        launcher = self.require_launcher()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = self.write_state(
                root,
                "current",
                workspace="w1",
                pane="w1:p1",
                run_id="current-run",
                role_graph_manifest="graphs/custom.json",
            )
            manifest = state.parent / "graphs/custom.json"
            manifest.parent.mkdir()
            self.write_manifest(manifest)

            self.assertEqual(
                launcher.ManifestSelection("custom", manifest.resolve()),
                launcher._resolve_manifest(launcher._load_state(state, "w1"), None),
            )

    def test_publisher_match_requires_exact_argv_values(self):
        launcher = self.require_launcher()
        target = "/tmp/current/workspace-state.json"
        manifest = "/tmp/current/role-graph-manifest.json"
        workspace = "w1"
        endpoint = "http://127.0.0.1:4173/api/snapshots"
        exact = (
            "python3 -B adapters/herdr/publisher.py "
            f"--state {target} --manifest {manifest} --workspace-id {workspace} "
            "--space-name herdr-orchestrator "
            f"--endpoint {endpoint} --watch --interval 2"
        )
        process = {"foreground_processes": [{"cmdline": exact}]}

        self.assertTrue(
            launcher.publisher_matches(
                process,
                target,
                launcher.ManifestSelection("custom", Path(manifest)),
                workspace,
                "herdr-orchestrator",
                endpoint,
                True,
            )
        )
        self.assertFalse(
            launcher.publisher_matches(
                process,
                "/tmp/current/workspace-state.json.bak",
                launcher.ManifestSelection("custom", Path(manifest)),
                workspace,
                "herdr-orchestrator",
                endpoint,
                True,
            )
        )
        self.assertFalse(
            launcher.publisher_matches(
                process,
                target,
                launcher.ManifestSelection("custom", Path(manifest)),
                "w10",
                "herdr-orchestrator",
                endpoint,
                True,
            )
        )
        self.assertFalse(
            launcher.publisher_matches(
                process,
                target,
                launcher.ManifestSelection("custom", Path(manifest)),
                workspace,
                "herdr-orchestrator",
                endpoint + "/other",
                True,
            )
        )
        self.assertFalse(
            launcher.publisher_matches(
                process,
                target,
                launcher.ManifestSelection("custom", Path(manifest)),
                workspace,
                "car-edge",
                endpoint,
                True,
            )
        )

    def test_publisher_match_requires_exact_topology_mode(self):
        launcher = self.require_launcher()
        target = "/tmp/current/workspace-state.json"
        endpoint = "http://127.0.0.1:4173/api/snapshots"
        process = {
            "foreground_processes": [
                {
                    "cmdline": (
                        "python3 -B adapters/herdr/publisher.py "
                        f"--state {target} --synthesize --workspace-id w1 "
                        "--space-name herdr-orchestrator "
                        f"--endpoint {endpoint} --watch"
                    )
                }
            ]
        }

        self.assertTrue(
            launcher.publisher_matches(
                process,
                target,
                launcher.ManifestSelection("synthetic", None),
                "w1",
                "herdr-orchestrator",
                endpoint,
                True,
            )
        )
        self.assertFalse(
            launcher.publisher_matches(
                process,
                target,
                launcher.ManifestSelection("custom", Path("/tmp/manifest.json")),
                "w1",
                "herdr-orchestrator",
                endpoint,
                True,
            )
        )

    def test_wait_for_snapshot_requires_exact_revision_and_space_name(self):
        launcher = self.require_launcher()
        snapshots = iter(
            [
                {
                    "spaceName": "herdr-orchestrator",
                    "scopeId": "herdr:w1",
                    "runId": "run-1",
                    "sequence": 2,
                },
                {"scopeId": "herdr:w1", "runId": "run-1", "sequence": 3},
                {
                    "spaceName": "car-edge",
                    "scopeId": "herdr:w1",
                    "runId": "run-1",
                    "sequence": 3,
                },
                {
                    "spaceName": "herdr-orchestrator",
                    "scopeId": "herdr:w1",
                    "runId": "run-1",
                    "sequence": 3,
                },
            ]
        )
        with mock.patch.object(launcher, "_snapshot", side_effect=lambda *_: next(snapshots)):
            found = launcher._wait_for_snapshot(
                4173,
                "herdr:w1",
                "run-1",
                3,
                "herdr-orchestrator",
                timeout=1,
            )

        self.assertEqual(found["sequence"], 3)
        self.assertEqual(found["spaceName"], "herdr-orchestrator")

    def test_viewer_probe_requires_space_name_summary_and_session_presence(self):
        launcher = self.require_launcher()

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

        def response_for(value):
            response = Response()
            response.read = lambda: json.dumps(value).encode("utf-8")
            return response

        with mock.patch.object(
            launcher.urllib.request,
            "urlopen",
            return_value=response_for(
                {
                    "service": "herdr-role-graph-viewer",
                    "schemaVersion": "role-graph/v1",
                }
            ),
        ) as opened:
            self.assertEqual(launcher.probe_viewer(4173), "occupied")
            self.assertIn("/api/health", opened.call_args.args[0])

        with mock.patch.object(
            launcher.urllib.request,
            "urlopen",
            return_value=response_for(
                {
                    "service": "herdr-role-graph-viewer",
                    "schemaVersion": "role-graph/v1",
                    "capabilities": ["space-name-summary"],
                }
            ),
        ):
            self.assertEqual(launcher.probe_viewer(4173), "occupied")

        with mock.patch.object(
            launcher.urllib.request,
            "urlopen",
            return_value=response_for(
                {
                    "service": "herdr-role-graph-viewer",
                    "schemaVersion": "role-graph/v1",
                    "capabilities": [
                        "space-name-summary",
                        "session-presence",
                    ],
                }
            ),
        ):
            self.assertEqual(launcher.probe_viewer(4173), "viewer")

        with mock.patch.object(
            launcher.urllib.request,
            "urlopen",
            return_value=response_for([{"id": "graph"}]),
        ):
            self.assertEqual(launcher.probe_viewer(4173), "occupied")

    def test_session_publisher_match_requires_exact_local_identity(self):
        launcher = self.require_launcher()
        matcher = getattr(launcher, "session_publisher_matches", None)
        self.assertIsNotNone(matcher, "session publisher matching is missing")
        if matcher is None:
            return
        process_info = {
            "foreground_processes": [
                {
                    "cmdline": (
                        "python3 -B adapters/herdr/session_publisher.py "
                        "--workspace-id w1 --space-name herdr-orchestrator "
                        "--p1-session-id current-session --p1-pane-id w1:p1 "
                        "--endpoint http://127.0.0.1:4173/api/snapshots "
                        "--watch --interval 2"
                    )
                }
            ]
        }

        self.assertTrue(
            matcher(
                process_info,
                "w1",
                "herdr-orchestrator",
                "current-session",
                "w1:p1",
                "http://127.0.0.1:4173/api/snapshots",
                True,
            )
        )
        self.assertFalse(
            matcher(
                process_info,
                "w1",
                "herdr-orchestrator",
                "stale-session",
                "w1:p1",
                "http://127.0.0.1:4173/api/snapshots",
                True,
            )
        )

    def test_legacy_viewer_is_skipped_for_next_free_port(self):
        launcher = self.require_launcher()

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

        response = Response()
        response.read = lambda: json.dumps(
            {
                "service": "herdr-role-graph-viewer",
                "schemaVersion": "role-graph/v1",
            }
        ).encode("utf-8")

        def probe(port):
            if port == 4174:
                return "free"
            return launcher.probe_viewer(port)

        with mock.patch.object(
            launcher.urllib.request, "urlopen", return_value=response
        ):
            selected = launcher.select_port(probe, 4173, 4174)

        self.assertEqual(selected, (4174, False))

    def test_find_publisher_retries_stale_pane_and_skips_missing_process_info(self):
        launcher = self.require_launcher()
        calls: list[tuple[str, ...]] = []
        target = "/tmp/current/workspace-state.json"
        manifest = "/tmp/current/role-graph-manifest.json"
        endpoint = "http://127.0.0.1:4173/api/snapshots"

        def fake_herdr(*args):
            calls.append(args)
            if args[:2] == ("pane", "list"):
                return {
                    "result": {
                        "panes": [
                            {"pane_id": "stale"},
                            {"pane_id": "missing-info"},
                            {"pane_id": "publisher"},
                        ]
                    }
                }
            if args[:2] == ("pane", "process-info") and args[-1] == "stale":
                raise launcher.LauncherError("herdr_error", "pane not found")
            if args[:2] == ("pane", "process-info") and args[-1] == "missing-info":
                return {"result": {}}
            if args[:2] == ("pane", "process-info") and args[-1] == "publisher":
                return {
                    "result": {
                        "process_info": {
                            "foreground_processes": [
                                {
                                    "cmdline": (
                                        "python3 -B adapters/herdr/publisher.py "
                                        f"--state {target} --manifest {manifest} "
                                        "--workspace-id w1 "
                                        "--space-name herdr-orchestrator "
                                        f"--endpoint {endpoint} --watch --interval 2"
                                    )
                                }
                            ]
                        }
                    }
                }
            raise AssertionError(args)

        with mock.patch.object(launcher, "_herdr", side_effect=fake_herdr):
            self.assertEqual(
                launcher._find_publisher(
                    "w1",
                    "herdr-orchestrator",
                    Path(target),
                    launcher.ManifestSelection("custom", Path(manifest)),
                    endpoint,
                ),
                "publisher",
            )

        self.assertIn(("pane", "process-info", "--pane", "stale"), calls)

    def test_space_name_mismatch_replaces_publisher_in_same_ordinary_pane(self):
        launcher = self.require_launcher()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            (repo / "adapters/herdr").mkdir(parents=True)
            (repo / "server.js").write_text("", encoding="utf-8")
            (repo / "adapters/herdr/publisher.py").write_text("", encoding="utf-8")
            manifest = root / "role-graph-manifest.json"
            self.write_manifest(manifest)
            state = self.write_state(
                root,
                "current",
                workspace="w1",
                pane="w1:p1",
                run_id="current-run",
                revision=8,
                role_graph_manifest=str(manifest),
            )
            endpoint = "http://127.0.0.1:4173/api/snapshots"
            old_command = (
                "python3 -B adapters/herdr/publisher.py "
                f"--state {state.resolve()} --manifest {manifest.resolve()} "
                "--workspace-id w1 --space-name old-space "
                f"--endpoint {endpoint} --watch --interval 2"
            )
            calls: list[tuple[str, ...]] = []

            def fake_herdr(*args):
                calls.append(args)
                if args[:2] == ("workspace", "list"):
                    return self.workspace_list()
                if args[:2] == ("pane", "list"):
                    return {
                        "result": {
                            "panes": [
                                {"pane_id": "publisher", "agent_status": "unknown"}
                            ]
                        }
                    }
                if args[:2] == ("pane", "process-info"):
                    return {
                        "result": {
                            "process_info": {
                                "foreground_processes": [{"cmdline": old_command}]
                            }
                        }
                    }
                if args[:2] in {("pane", "send-keys"), ("pane", "run")}:
                    return {"result": {}}
                raise AssertionError(args)

            args = Namespace(
                state=state,
                manifest=None,
                repo=repo,
                runs_root=root,
                port_start=4173,
                port_end=4173,
            )

            with mock.patch.dict(
                os.environ,
                {
                    "HERDR_ENV": "1",
                    "HERDR_WORKSPACE_ID": "w1",
                    "HERDR_PANE_ID": "w1:p1",
                },
                clear=True,
            ), mock.patch.object(launcher, "_herdr", side_effect=fake_herdr), mock.patch.object(
                launcher, "probe_viewer", return_value="viewer"
            ), mock.patch.object(
                launcher,
                "_snapshot",
                return_value={
                    "spaceName": "herdr-orchestrator",
                    "scopeId": "herdr:w1",
                    "runId": "current-run",
                    "sequence": 8,
                },
            ):
                result = launcher.launch(args)

            self.assertIn(("pane", "send-keys", "publisher", "ctrl+c"), calls)
            replacement = [call for call in calls if call[:2] == ("pane", "run")]
            self.assertEqual(len(replacement), 1)
            self.assertEqual(replacement[0][2], "publisher")
            self.assertIn("--manifest " + str(manifest.resolve()), replacement[0][3])
            self.assertIn("--space-name herdr-orchestrator", replacement[0][3])
            self.assertIn("--replace-current", replacement[0][3].split())
            self.assertFalse(any(call[:2] == ("pane", "split") for call in calls))
            self.assertFalse(result["publisher"]["reused"])

    def test_mode_replacement_ignores_agent_panes(self):
        launcher = self.require_launcher()
        target = Path("/tmp/current/workspace-state.json")
        endpoint = "http://127.0.0.1:4173/api/snapshots"
        command = (
            "python3 -B adapters/herdr/publisher.py "
            f"--state {target} --synthesize --workspace-id w1 "
            "--space-name herdr-orchestrator "
            f"--endpoint {endpoint} --watch"
        )
        calls: list[tuple[str, ...]] = []

        def fake_herdr(*args):
            calls.append(args)
            if args[:2] == ("pane", "list"):
                return {
                    "result": {
                        "panes": [
                            {"pane_id": "agent-pane", "agent": "codex"},
                            {"pane_id": "publisher-pane", "agent_status": "unknown"},
                        ]
                    }
                }
            if args[:2] == ("pane", "process-info"):
                return {
                    "result": {
                        "process_info": {
                            "foreground_processes": [{"cmdline": command}]
                        }
                    }
                }
            raise AssertionError(args)

        with mock.patch.object(launcher, "_herdr", side_effect=fake_herdr):
            found = launcher._find_publisher_for_state("w1", target, endpoint)

        self.assertEqual(found, "publisher-pane")
        self.assertNotIn(
            ("pane", "process-info", "--pane", "agent-pane"), calls
        )

    def test_herdr_uses_bounded_timeout(self):
        launcher = self.require_launcher()

        with mock.patch.object(
            launcher.subprocess,
            "run",
            return_value=mock.Mock(returncode=0, stdout='{"result": {}}', stderr=""),
        ) as run:
            launcher._herdr("pane", "list", "--workspace", "w1")

        self.assertEqual(run.call_args.kwargs["timeout"], launcher.HERDR_TIMEOUT_SECONDS)

    def test_cold_pane_run_accepts_empty_stdout_success(self):
        launcher = self.require_launcher()

        with mock.patch.object(
            launcher.subprocess,
            "run",
            return_value=mock.Mock(returncode=0, stdout="", stderr=""),
        ):
            response = launcher._herdr("pane", "run", "publisher", "command")

        self.assertEqual(response, {})

    def test_mode_switch_send_keys_accepts_empty_stdout_success(self):
        launcher = self.require_launcher()

        with mock.patch.object(
            launcher.subprocess,
            "run",
            return_value=mock.Mock(returncode=0, stdout="", stderr=""),
        ):
            response = launcher._herdr(
                "pane", "send-keys", "publisher", "ctrl+c"
            )

        self.assertEqual(response, {})

    def test_herdr_still_parses_json_query_response(self):
        launcher = self.require_launcher()
        expected = {"result": {"panes": [{"pane_id": "w1:p1"}]}}

        with mock.patch.object(
            launcher.subprocess,
            "run",
            return_value=mock.Mock(
                returncode=0, stdout=json.dumps(expected), stderr=""
            ),
        ):
            response = launcher._herdr("pane", "list", "--workspace", "w1")

        self.assertEqual(response, expected)

    def test_empty_pane_list_fails_before_pane_mutation(self):
        self.assert_query_output_fails_before_mutation("pane-list")

    def test_empty_process_info_fails_before_pane_mutation(self):
        self.assert_query_output_fails_before_mutation("process-info")

    def test_cold_server_empty_pane_list_fails_before_pane_mutation(self):
        self.assert_query_output_fails_before_mutation(
            "pane-list", cold_server=True
        )

    def test_cold_server_malformed_pane_list_fails_before_pane_mutation(self):
        self.assert_query_output_fails_before_mutation(
            "pane-list", "not-json", cold_server=True
        )

    def test_cold_server_empty_process_info_fails_before_pane_mutation(self):
        self.assert_query_output_fails_before_mutation(
            "process-info", cold_server=True
        )

    def test_cold_server_malformed_process_info_fails_before_pane_mutation(self):
        self.assert_query_output_fails_before_mutation(
            "process-info", "not-json", cold_server=True
        )

    def test_split_pane_still_requires_pane_result(self):
        launcher = self.require_launcher()

        with mock.patch.object(launcher, "_herdr", return_value={}):
            with self.assertRaises(launcher.LauncherError) as raised:
                launcher._split_pane(
                    "w1:p1",
                    Path("/tmp/repo"),
                    "graph-viewer",
                    direction="right",
                    ratio="0.32",
                )

        self.assertEqual(raised.exception.code, "herdr_error")
        self.assertEqual(str(raised.exception), "pane split returned no pane_id")

    def test_no_matching_control_state_launches_current_session_publisher(self):
        launcher = self.require_launcher()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            (repo / "adapters/herdr").mkdir(parents=True)
            (repo / "server.js").write_text("", encoding="utf-8")
            (repo / "adapters/herdr/publisher.py").write_text("", encoding="utf-8")
            (repo / "adapters/herdr/session_publisher.py").write_text(
                "", encoding="utf-8"
            )
            calls: list[tuple[str, ...]] = []
            commands: dict[str, str] = {}

            def fake_herdr(*args):
                calls.append(args)
                if args[:2] == ("agent", "list"):
                    return {
                        "result": {
                            "agents": [
                                {
                                    "workspace_id": "w2",
                                    "pane_id": "w2:p1",
                                    "name": "p1_orchestrator",
                                    "agent_session": {
                                        "kind": "id",
                                        "value": "foreign-session",
                                    },
                                },
                                {
                                    "workspace_id": "w1",
                                    "pane_id": "w1:p1",
                                    "name": "p1_orchestrator",
                                    "agent_session": {
                                        "kind": "id",
                                        "value": "019fb24f-f36f-7642-8679-5c6405fb3889",
                                    },
                                },
                            ]
                        }
                    }
                if args[:2] == ("workspace", "list"):
                    return self.workspace_list()
                if args[:2] == ("pane", "list"):
                    return {"result": {"panes": []}}
                if args[:2] == ("pane", "split"):
                    return {"result": {"pane": {"pane_id": "publisher"}}}
                if args[:2] == ("pane", "rename"):
                    return {"result": {}}
                if args[:2] == ("pane", "run"):
                    commands[args[2]] = args[3]
                    return {"result": {}}
                raise AssertionError(args)

            args = Namespace(
                state=None,
                manifest=None,
                repo=repo,
                runs_root=root,
                port_start=4173,
                port_end=4173,
            )

            with mock.patch.dict(
                os.environ,
                {
                    "HERDR_ENV": "1",
                    "HERDR_WORKSPACE_ID": "w1",
                    "HERDR_PANE_ID": "w1:p6",
                },
                clear=True,
            ), mock.patch.object(
                launcher, "_herdr", side_effect=fake_herdr
            ), mock.patch.object(
                launcher, "probe_viewer", return_value="viewer"
            ), mock.patch.object(
                launcher,
                "_snapshot",
                return_value={
                    "spaceName": "herdr-orchestrator",
                    "scopeId": "herdr:w1",
                    "runId": "019fb24f-f36f-7642-8679-5c6405fb3889",
                    "sequence": 1,
                },
            ):
                try:
                    result = launcher.launch(args)
                except launcher.LauncherError as error:
                    self.fail(f"session mode is unavailable: {error}")

            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["mode"], "session")
            self.assertEqual(
                result["run_id"], "019fb24f-f36f-7642-8679-5c6405fb3889"
            )
            self.assertIsNone(result["state"])
            command = commands["publisher"]
            self.assertIn(
                (
                    "session_publisher.py --workspace-id w1 "
                    "--space-name herdr-orchestrator "
                    "--p1-session-id 019fb24f-f36f-7642-8679-5c6405fb3889 "
                    "--p1-pane-id w1:p1"
                ),
                command,
            )
            self.assertIn(
                (
                    "pane",
                    "split",
                    "--pane",
                    "w1:p1",
                    "--direction",
                    "right",
                    "--ratio",
                    "0.32",
                    "--cwd",
                    str(repo.resolve()),
                    "--no-focus",
                ),
                calls,
            )
            self.assertFalse(
                any(call[:2] in {("pane", "send-keys"), ("pane", "close")} for call in calls)
            )

    def test_cold_start_from_non_p1_pane_anchors_selected_controller_p1(self):
        launcher = self.require_launcher()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            (repo / "adapters/herdr").mkdir(parents=True)
            (repo / "server.js").write_text("", encoding="utf-8")
            (repo / "adapters/herdr/publisher.py").write_text("", encoding="utf-8")
            manifest = root / "role-graph-manifest.json"
            self.write_manifest(manifest)
            state = self.write_state(
                root,
                "current",
                workspace="w1",
                pane="w1:p1",
                run_id="current-run",
                revision=8,
                role_graph_manifest=str(manifest),
            )
            data_file = root / "w1" / "viewer" / "snapshots.jsonl"
            data_file.parent.mkdir(parents=True)
            data_file.write_text(
                json.dumps(
                    {
                        "scopeId": "herdr:w1",
                        "runId": "current-run",
                        "sequence": 8,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            commands: dict[str, str] = {}
            splits: list[tuple[str, ...]] = []
            calls: list[tuple[str, ...]] = []

            def fake_herdr(*args):
                calls.append(args)
                if args[:2] == ("workspace", "list"):
                    return self.workspace_list()
                if args[:2] == ("pane", "list"):
                    return {"result": {"panes": []}}
                if args[:2] == ("pane", "split"):
                    pane_id = f"pane-{len(splits) + 1}"
                    splits.append(args)
                    return {"result": {"pane": {"pane_id": pane_id}}}
                if args[:2] == ("pane", "rename"):
                    return {"result": {}}
                if args[:2] == ("pane", "run"):
                    commands[args[2]] = args[3]
                    return {"result": {}}
                raise AssertionError(args)

            args = Namespace(
                state=state,
                manifest=None,
                repo=repo,
                runs_root=root,
                port_start=4173,
                port_end=4173,
            )

            with mock.patch.dict(
                os.environ,
                {
                    "HERDR_ENV": "1",
                    "HERDR_WORKSPACE_ID": "w1",
                    "HERDR_PANE_ID": "w1:p6",
                },
                clear=True,
            ), mock.patch.object(launcher, "_herdr", side_effect=fake_herdr), mock.patch.object(
                launcher, "probe_viewer", side_effect=["free", "viewer"]
            ), mock.patch.object(
                launcher,
                "_snapshot",
                return_value={
                    "spaceName": "herdr-orchestrator",
                    "scopeId": "herdr:w1",
                    "runId": "current-run",
                    "sequence": 8,
                },
            ):
                result = launcher.launch(args)

            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["space_name"], "herdr-orchestrator")
            self.assertEqual(result.get("mode"), "custom")
            self.assertEqual(result["sequence"], 8)
            self.assertEqual(
                splits,
                [
                    (
                        "pane",
                        "split",
                        "--pane",
                        "w1:p1",
                        "--direction",
                        "right",
                        "--ratio",
                        "0.32",
                        "--cwd",
                        str(repo.resolve()),
                        "--no-focus",
                    ),
                    (
                        "pane",
                        "split",
                        "--pane",
                        "pane-1",
                        "--direction",
                        "down",
                        "--ratio",
                        "0.5",
                        "--cwd",
                        str(repo.resolve()),
                        "--no-focus",
                    ),
                ],
            )
            server_command = commands["pane-1"]
            self.assertIn("npm ci", server_command)
            self.assertIn("npm run build", server_command)
            self.assertNotIn("test -d node_modules ||", server_command)
            self.assertNotIn("test -f dist/index.html ||", server_command)
            self.assertIn(str(data_file), server_command)
            publisher_command = commands["pane-2"]
            self.assertIn("--manifest " + str(manifest.resolve()), publisher_command)
            self.assertIn("--workspace-id w1", publisher_command)
            self.assertIn("--space-name herdr-orchestrator", publisher_command)
            self.assertIn("--replace-current", publisher_command.split())
            self.assertFalse(
                any(call[:2] == ("pane", "send-keys") for call in calls)
            )

    def test_manifestless_launch_emits_synthetic_mode_and_null_manifest(self):
        launcher = self.require_launcher()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            (repo / "adapters/herdr").mkdir(parents=True)
            (repo / "server.js").write_text("", encoding="utf-8")
            (repo / "adapters/herdr/publisher.py").write_text("", encoding="utf-8")
            state = self.write_state(
                root,
                "current",
                workspace="w1",
                pane="w1:p1",
                run_id="current-run",
                revision=8,
            )
            commands: list[str] = []

            def fake_herdr(*args):
                if args[:2] == ("workspace", "list"):
                    return self.workspace_list()
                if args[:2] == ("pane", "list"):
                    return {"result": {"panes": []}}
                if args[:2] == ("pane", "split"):
                    return {"result": {"pane": {"pane_id": "publisher"}}}
                if args[:2] == ("pane", "rename"):
                    return {"result": {}}
                if args[:2] == ("pane", "run"):
                    commands.append(args[3])
                    return {"result": {}}
                raise AssertionError(args)

            args = Namespace(
                state=state,
                manifest=None,
                repo=repo,
                runs_root=root,
                port_start=4173,
                port_end=4173,
            )

            with mock.patch.dict(
                os.environ,
                {
                    "HERDR_ENV": "1",
                    "HERDR_WORKSPACE_ID": "w1",
                    "HERDR_PANE_ID": "w1:p1",
                },
                clear=True,
            ), mock.patch.object(launcher, "_herdr", side_effect=fake_herdr), mock.patch.object(
                launcher, "probe_viewer", return_value="viewer"
            ), mock.patch.object(
                launcher,
                "_snapshot",
                return_value={
                    "spaceName": "herdr-orchestrator",
                    "scopeId": "herdr:w1",
                    "runId": "current-run",
                    "sequence": 8,
                },
            ):
                result = launcher.launch(args)

            self.assertEqual(result.get("mode"), "synthetic")
            self.assertIsNone(result["manifest"])
            self.assertEqual(len(commands), 1)
            self.assertIn("--synthesize", commands[0])
            self.assertNotIn("--manifest", commands[0])
            self.assertNotIn("--replace-current", commands[0].split())

    def test_reused_server_from_non_p1_pane_anchors_unique_controller_p1(self):
        launcher = self.require_launcher()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            (repo / "adapters/herdr").mkdir(parents=True)
            (repo / "server.js").write_text("", encoding="utf-8")
            (repo / "adapters/herdr/publisher.py").write_text("", encoding="utf-8")
            manifest = root / "role-graph-manifest.json"
            self.write_manifest(manifest)
            state = self.write_state(
                root,
                "current",
                workspace="w1",
                pane="w1:p1",
                run_id="current-run",
                revision=8,
                role_graph_manifest=str(manifest),
            )
            splits: list[tuple[str, ...]] = []

            def fake_herdr(*args):
                if args[:2] == ("agent", "list"):
                    return {
                        "result": {
                            "agents": [
                                {
                                    "workspace_id": "w1",
                                    "pane_id": "w1:p1",
                                    "name": "p1_orchestrator",
                                    "agent_session": {
                                        "kind": "id",
                                        "value": "p1-session",
                                    },
                                }
                            ]
                        }
                    }
                if args[:2] == ("workspace", "list"):
                    return self.workspace_list()
                if args[:2] == ("pane", "list"):
                    return {"result": {"panes": []}}
                if args[:2] == ("pane", "split"):
                    splits.append(args)
                    return {"result": {"pane": {"pane_id": "publisher"}}}
                if args[:2] in {("pane", "rename"), ("pane", "run")}:
                    return {"result": {}}
                raise AssertionError(args)

            args = Namespace(
                state=None,
                manifest=None,
                repo=repo,
                runs_root=root,
                port_start=4173,
                port_end=4173,
            )

            with mock.patch.dict(
                os.environ,
                {
                    "HERDR_ENV": "1",
                    "HERDR_WORKSPACE_ID": "w1",
                    "HERDR_PANE_ID": "w1:p6",
                },
                clear=True,
            ), mock.patch.object(launcher, "_herdr", side_effect=fake_herdr), mock.patch.object(
                launcher, "probe_viewer", return_value="viewer"
            ), mock.patch.object(
                launcher,
                "_snapshot",
                return_value={
                    "spaceName": "herdr-orchestrator",
                    "scopeId": "herdr:w1",
                    "runId": "current-run",
                    "sequence": 8,
                },
            ):
                launcher.launch(args)

            self.assertEqual(
                splits,
                [
                    (
                        "pane",
                        "split",
                        "--pane",
                        "w1:p1",
                        "--direction",
                        "right",
                        "--ratio",
                        "0.32",
                        "--cwd",
                        str(repo.resolve()),
                        "--no-focus",
                    )
                ],
            )

    def test_concurrent_launches_do_not_duplicate_processes(self):
        launcher = self.require_launcher()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            (repo / "adapters/herdr").mkdir(parents=True)
            (repo / "server.js").write_text("", encoding="utf-8")
            (repo / "adapters/herdr/publisher.py").write_text("", encoding="utf-8")
            manifest = root / "role-graph-manifest.json"
            self.write_manifest(manifest)
            state = self.write_state(
                root,
                "current",
                workspace="w1",
                pane="w1:p1",
                run_id="current-run",
                revision=8,
                role_graph_manifest=str(manifest),
            )
            commands: dict[str, str] = {}
            splits: list[str] = []
            lock = threading.Lock()

            def fake_herdr(*args):
                with lock:
                    if args[:2] == ("workspace", "list"):
                        return self.workspace_list()
                    if args[:2] == ("pane", "list"):
                        panes = [{"pane_id": pane_id} for pane_id in commands]
                        return {"result": {"panes": panes}}
                    if args[:2] == ("pane", "process-info"):
                        command = commands.get(args[-1])
                        if command is None:
                            return {"result": {}}
                        return {
                            "result": {
                                "process_info": {
                                    "foreground_processes": [{"cmdline": command}]
                                }
                            }
                        }
                    if args[:2] == ("pane", "split"):
                        pane_id = f"pane-{len(splits) + 1}"
                        splits.append(pane_id)
                        return {"result": {"pane": {"pane_id": pane_id}}}
                    if args[:2] == ("pane", "rename"):
                        return {"result": {}}
                    if args[:2] == ("pane", "run"):
                        commands[args[2]] = args[3]
                        return {"result": {}}
                raise AssertionError(args)

            def fake_probe(_port):
                with lock:
                    if any("npm run server" in command for command in commands.values()):
                        return "viewer"
                return "free"

            args = Namespace(
                state=state,
                manifest=None,
                repo=repo,
                runs_root=root,
                port_start=4173,
                port_end=4173,
            )

            errors: list[BaseException] = []

            def run_launch():
                try:
                    launcher.launch(args)
                except BaseException as error:
                    errors.append(error)

            with mock.patch.dict(
                os.environ,
                {
                    "HERDR_ENV": "1",
                    "HERDR_WORKSPACE_ID": "w1",
                    "HERDR_PANE_ID": "w1:p1",
                },
                clear=True,
            ), mock.patch.object(launcher, "_herdr", side_effect=fake_herdr), mock.patch.object(
                launcher, "probe_viewer", side_effect=fake_probe
            ), mock.patch.object(
                launcher,
                "_snapshot",
                return_value={
                    "spaceName": "herdr-orchestrator",
                    "scopeId": "herdr:w1",
                    "runId": "current-run",
                    "sequence": 8,
                },
            ):
                threads = [threading.Thread(target=run_launch) for _ in range(2)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join()

            publisher_commands = [
                command for command in commands.values() if "publisher.py" in command
            ]
            server_commands = [
                command for command in commands.values() if "npm run server" in command
            ]
            self.assertEqual(errors, [])
            self.assertEqual(len(server_commands), 1)
            self.assertEqual(len(publisher_commands), 1)
            self.assertEqual(len(splits), 2)

    def test_viewer_url_encodes_scope_and_run(self):
        launcher = self.require_launcher()

        url = launcher.viewer_url(4173, "herdr:w 1", "run/with space")

        self.assertEqual(
            url,
            "http://127.0.0.1:4173/?scopeId=herdr%3Aw+1&runId=run%2Fwith+space",
        )


if __name__ == "__main__":
    unittest.main()
