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

    def write_state(
        self,
        root: Path,
        name: str,
        *,
        workspace: str,
        pane: str,
        run_id: str,
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
                    "controller": {"pane_id": pane, "workspace_id": workspace},
                    "slots": {"P1": {"pane_id": pane, "workspace_id": workspace}},
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_selects_state_bound_to_current_p1_pane(self):
        launcher = self.require_launcher()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current = self.write_state(
                root, "current", workspace="w1", pane="w1:p1", run_id="current-run"
            )
            self.write_state(
                root, "older", workspace="w1", pane="w1:p9", run_id="older-run"
            )
            self.write_state(
                root, "foreign", workspace="w2", pane="w2:p1", run_id="foreign-run"
            )

            selected = launcher.select_state(root, "w1", "w1:p1")

            self.assertEqual(selected.path, current.resolve())
            self.assertEqual(selected.run_id, "current-run")

    def test_refuses_to_guess_between_multiple_runs(self):
        launcher = self.require_launcher()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = self.write_state(
                root, "first", workspace="w1", pane="w1:p2", run_id="first-run"
            )
            second = self.write_state(
                root, "second", workspace="w1", pane="w1:p3", run_id="second-run"
            )

            with self.assertRaises(launcher.LauncherError) as raised:
                launcher.select_state(root, "w1", "w1:p1")

            self.assertEqual(raised.exception.code, "ambiguous_run")
            self.assertEqual(
                set(raised.exception.details["candidates"]),
                {str(first.resolve()), str(second.resolve())},
            )

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
                        f"--workspace-id w1 --endpoint {endpoint} --watch"
                    )
                }
            ]
        }

        self.assertTrue(
            launcher.publisher_matches(process, target, manifest, "w1", endpoint, True)
        )
        self.assertFalse(
            launcher.publisher_matches(
                process, "/tmp/other/workspace-state.json", manifest, "w1", endpoint, True
            )
        )

    def test_refuses_manifest_fallback_when_run_does_not_select_one(self):
        launcher = self.require_launcher()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            (repo / "adapters/herdr/manifests").mkdir(parents=True)
            (repo / "adapters/herdr/manifests/standard.json").write_text("{}", encoding="utf-8")
            state = self.write_state(
                root, "current", workspace="w1", pane="w1:p1", run_id="current-run"
            )
            selected = launcher._load_state(state, "w1")

            with self.assertRaises(launcher.LauncherError) as raised:
                launcher._resolve_manifest(selected, repo, None)

            self.assertEqual(raised.exception.code, "missing_manifest")
            self.assertIn("explicit --manifest", str(raised.exception))

    def test_resolves_manifest_from_state_or_run_local_file_only(self):
        launcher = self.require_launcher()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_manifest = root / "manifest.json"
            state_manifest.write_text("{}", encoding="utf-8")
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
                launcher._resolve_manifest(selected, root / "repo", None),
                state_manifest.resolve(),
            )

            no_manifest_state = self.write_state(
                root, "local", workspace="w1", pane="w1:p1", run_id="local-run"
            )
            run_local = no_manifest_state.parent / "role-graph-manifest.json"
            run_local.write_text("{}", encoding="utf-8")
            selected = launcher._load_state(no_manifest_state, "w1")

            self.assertEqual(
                launcher._resolve_manifest(selected, root / "repo", None),
                run_local.resolve(),
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
            f"--endpoint {endpoint} --watch --interval 2"
        )
        process = {"foreground_processes": [{"cmdline": exact}]}

        self.assertTrue(
            launcher.publisher_matches(process, target, manifest, workspace, endpoint, True)
        )
        self.assertFalse(
            launcher.publisher_matches(
                process,
                "/tmp/current/workspace-state.json.bak",
                manifest,
                workspace,
                endpoint,
                True,
            )
        )
        self.assertFalse(
            launcher.publisher_matches(
                process,
                target,
                manifest,
                "w10",
                endpoint,
                True,
            )
        )
        self.assertFalse(
            launcher.publisher_matches(
                process,
                target,
                manifest,
                workspace,
                endpoint + "/other",
                True,
            )
        )

    def test_wait_for_snapshot_requires_exact_revision_sequence(self):
        launcher = self.require_launcher()
        snapshots = iter(
            [
                {"scopeId": "herdr:w1", "runId": "run-1", "sequence": 2},
                {"scopeId": "herdr:w1", "runId": "run-1", "sequence": 3},
            ]
        )
        with mock.patch.object(launcher, "_snapshot", side_effect=lambda *_: next(snapshots)):
            found = launcher._wait_for_snapshot(4173, "herdr:w1", "run-1", 3, timeout=1)

        self.assertEqual(found["sequence"], 3)

    def test_viewer_probe_requires_health_fingerprint(self):
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
            self.assertEqual(launcher.probe_viewer(4173), "viewer")
            self.assertIn("/api/health", opened.call_args.args[0])

        with mock.patch.object(
            launcher.urllib.request,
            "urlopen",
            return_value=response_for([{"id": "graph"}]),
        ):
            self.assertEqual(launcher.probe_viewer(4173), "occupied")

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
                launcher._find_publisher("w1", Path(target), Path(manifest), endpoint),
                "publisher",
            )

        self.assertIn(("pane", "process-info", "--pane", "stale"), calls)

    def test_herdr_uses_bounded_timeout(self):
        launcher = self.require_launcher()

        with mock.patch.object(
            launcher.subprocess,
            "run",
            return_value=mock.Mock(returncode=0, stdout='{"result": {}}', stderr=""),
        ) as run:
            launcher._herdr("pane", "list", "--workspace", "w1")

        self.assertEqual(run.call_args.kwargs["timeout"], launcher.HERDR_TIMEOUT_SECONDS)

    def test_cold_start_launch_uses_lock_deterministic_build_and_exact_readiness(self):
        launcher = self.require_launcher()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            (repo / "adapters/herdr").mkdir(parents=True)
            (repo / "server.js").write_text("", encoding="utf-8")
            (repo / "adapters/herdr/publisher.py").write_text("", encoding="utf-8")
            manifest = root / "role-graph-manifest.json"
            manifest.write_text("{}", encoding="utf-8")
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

            def fake_herdr(*args):
                if args[:2] == ("pane", "list"):
                    return {"result": {"panes": []}}
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
                launcher, "probe_viewer", side_effect=["free", "viewer"]
            ), mock.patch.object(
                launcher,
                "_snapshot",
                return_value={"scopeId": "herdr:w1", "runId": "current-run", "sequence": 8},
            ):
                result = launcher.launch(args)

            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["sequence"], 8)
            self.assertEqual(len(splits), 2)
            server_command = commands["pane-1"]
            self.assertIn("npm ci", server_command)
            self.assertIn("npm run build", server_command)
            self.assertNotIn("test -d node_modules ||", server_command)
            self.assertNotIn("test -f dist/index.html ||", server_command)
            publisher_command = commands["pane-2"]
            self.assertIn("--manifest " + str(manifest.resolve()), publisher_command)
            self.assertIn("--workspace-id w1", publisher_command)

    def test_concurrent_launches_do_not_duplicate_processes(self):
        launcher = self.require_launcher()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            (repo / "adapters/herdr").mkdir(parents=True)
            (repo / "server.js").write_text("", encoding="utf-8")
            (repo / "adapters/herdr/publisher.py").write_text("", encoding="utf-8")
            manifest = root / "role-graph-manifest.json"
            manifest.write_text("{}", encoding="utf-8")
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
