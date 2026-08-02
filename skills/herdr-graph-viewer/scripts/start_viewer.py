#!/usr/bin/env python3
"""Start or reuse the local viewer for one explicit Herdr workspace run."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import fcntl
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, NamedTuple


DEFAULT_REPO = Path("/Users/haido/multi-agent-graph-demo")
DEFAULT_RUNS_ROOT = Path.home() / ".codex" / "herdr-runs"
HERDR_TIMEOUT_SECONDS = 5
MANIFEST_SCHEMA_VERSION = "herdr-role-graph-manifest/v1"
MANIFEST_EDGE_KINDS = {"forward", "return"}
MANIFEST_EDGE_STATUSES = {
    "pending",
    "active",
    "inactive",
    "passed",
    "failed",
    "blocked",
    "retrying",
    "stale",
    "skipped",
}


class LauncherError(RuntimeError):
    def __init__(self, code: str, message: str, **details: Any):
        super().__init__(message)
        self.code = code
        self.details = details


class SelectedState(NamedTuple):
    path: Path
    value: dict[str, Any]
    run_id: str


class ManifestSelection(NamedTuple):
    mode: str
    path: Path | None


def _load_state(path: Path, workspace_id: str) -> SelectedState:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LauncherError("invalid_state", f"Cannot read {path}: {error}") from error
    observed = value.get("workspace_id")
    if observed != workspace_id:
        raise LauncherError(
            "workspace_mismatch",
            f"State belongs to {observed!r}, not {workspace_id!r}",
            state=str(path.resolve()),
            expected_workspace=workspace_id,
            observed_workspace=observed,
        )
    run_id = value.get("run", {}).get("contract_id")
    if not isinstance(run_id, str) or not run_id:
        raise LauncherError("invalid_state", f"State has no run.contract_id: {path}")
    return SelectedState(path.resolve(), value, run_id)


def _p1_pane(state: dict[str, Any]) -> str | None:
    controller = state.get("controller", {})
    if isinstance(controller.get("pane_id"), str):
        return controller["pane_id"]
    p1 = state.get("slots", {}).get("P1", {})
    return p1.get("pane_id") if isinstance(p1.get("pane_id"), str) else None


def select_state(
    runs_root: Path,
    workspace_id: str,
    current_pane_id: str,
    *,
    explicit: Path | None = None,
) -> SelectedState:
    if explicit is not None:
        return _load_state(explicit.expanduser().resolve(), workspace_id)

    workspace_root = runs_root.expanduser() / workspace_id
    candidates: list[SelectedState] = []
    for path in sorted(workspace_root.rglob("workspace-state.json")):
        try:
            candidates.append(_load_state(path, workspace_id))
        except LauncherError as error:
            if error.code != "workspace_mismatch":
                continue

    if not candidates:
        raise LauncherError(
            "no_active_run",
            f"No workspace-state.json found for {workspace_id}",
            search_root=str(workspace_root),
        )

    pane_matches = [item for item in candidates if _p1_pane(item.value) == current_pane_id]
    if len(pane_matches) == 1:
        return pane_matches[0]
    if len(candidates) == 1:
        return candidates[0]

    ambiguous = pane_matches or candidates
    raise LauncherError(
        "ambiguous_run",
        f"Multiple Herdr runs match workspace {workspace_id}; pass --state",
        candidates=[str(item.path) for item in ambiguous],
    )


def probe_viewer(port: int) -> str:
    url = f"http://127.0.0.1:{port}/api/health"
    try:
        with urllib.request.urlopen(url, timeout=0.5) as response:
            data = json.load(response)
        if not isinstance(data, dict):
            return "occupied"
        if (
            data.get("service") == "herdr-role-graph-viewer"
            and data.get("schemaVersion") == "role-graph/v1"
        ):
            return "viewer"
        return "occupied"
    except urllib.error.URLError as error:
        reason = error.reason
        if isinstance(reason, ConnectionRefusedError):
            return "free"
        return "occupied"
    except (TimeoutError, json.JSONDecodeError, ValueError):
        return "occupied"


def select_port(
    probe: Callable[[int], str], port_start: int, port_end: int
) -> tuple[int, bool]:
    first_free: int | None = None
    for port in range(port_start, port_end + 1):
        status = probe(port)
        if status == "viewer":
            return port, True
        if status == "free" and first_free is None:
            first_free = port
    if first_free is not None:
        return first_free, False
    raise LauncherError(
        "no_port",
        f"No viewer or free localhost port in {port_start}-{port_end}",
    )


def viewer_url(port: int, scope_id: str, run_id: str) -> str:
    query = urllib.parse.urlencode({"scopeId": scope_id, "runId": run_id})
    return f"http://127.0.0.1:{port}/?{query}"


def _argv_value(argv: list[str], flag: str) -> str | None:
    try:
        index = argv.index(flag)
    except ValueError:
        return None
    next_index = index + 1
    if next_index >= len(argv):
        return None
    return argv[next_index]


def _publisher_argvs(process_info: dict[str, Any]) -> Iterator[list[str]]:
    for process in process_info.get("foreground_processes", []):
        command = process.get("cmdline", "")
        if not isinstance(command, str):
            continue
        try:
            yield shlex.split(command)
        except ValueError:
            continue


def _publisher_common_matches(
    argv: list[str],
    state_path: str,
    workspace_id: str,
    endpoint: str,
    watch: bool,
) -> bool:
    return (
        any(item.endswith("adapters/herdr/publisher.py") for item in argv)
        and _argv_value(argv, "--state") == state_path
        and _argv_value(argv, "--workspace-id") == workspace_id
        and _argv_value(argv, "--endpoint") == endpoint
        and ("--watch" in argv) is watch
    )


def publisher_matches(
    process_info: dict[str, Any],
    state_path: str,
    selection: ManifestSelection,
    workspace_id: str,
    endpoint: str,
    watch: bool,
) -> bool:
    for argv in _publisher_argvs(process_info):
        if not _publisher_common_matches(
            argv, state_path, workspace_id, endpoint, watch
        ):
            continue
        manifest_path = _argv_value(argv, "--manifest")
        synthetic = "--synthesize" in argv
        if selection.mode == "synthetic" and synthetic and manifest_path is None:
            return True
        if (
            selection.mode == "custom"
            and selection.path is not None
            and not synthetic
            and manifest_path == str(selection.path)
        ):
            return True
    return False


def _publisher_matches_state(
    process_info: dict[str, Any],
    state_path: str,
    workspace_id: str,
    endpoint: str,
    watch: bool,
) -> bool:
    for argv in _publisher_argvs(process_info):
        if not _publisher_common_matches(
            argv, state_path, workspace_id, endpoint, watch
        ):
            continue
        mode_count = int("--synthesize" in argv) + int(
            _argv_value(argv, "--manifest") is not None
        )
        if mode_count == 1:
            return True
    return False


def _herdr(*args: str) -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["herdr", *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=HERDR_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        raise LauncherError(
            "herdr_timeout", f"herdr {' '.join(args)} timed out"
        ) from error
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise LauncherError("herdr_error", message or f"herdr {' '.join(args)} failed")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise LauncherError("herdr_error", f"Invalid Herdr response: {result.stdout}") from error


def _result_value(response: dict[str, Any], key: str) -> Any:
    return response.get("result", {}).get(key)


def _split_pane(
    anchor_pane: str,
    cwd: Path,
    label: str,
    *,
    direction: str,
    ratio: str,
) -> str:
    response = _herdr(
        "pane",
        "split",
        "--pane",
        anchor_pane,
        "--direction",
        direction,
        "--ratio",
        ratio,
        "--cwd",
        str(cwd),
        "--no-focus",
    )
    pane = _result_value(response, "pane") or {}
    pane_id = pane.get("pane_id")
    if not isinstance(pane_id, str):
        raise LauncherError("herdr_error", "pane split returned no pane_id")
    _herdr("pane", "rename", pane_id, label)
    return pane_id


def _run_in_pane(pane_id: str, command: str) -> None:
    _herdr("pane", "run", pane_id, command)


def _wait_for_viewer(port: int, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if probe_viewer(port) == "viewer":
            return
        time.sleep(0.25)
    raise LauncherError("viewer_start_failed", f"Viewer did not start on port {port}")


def _snapshot(port: int, scope_id: str, run_id: str) -> dict[str, Any] | None:
    query = urllib.parse.urlencode({"scopeId": scope_id, "runId": run_id})
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/snapshot?{query}", timeout=0.75
        ) as response:
            value = json.load(response)
        return value if isinstance(value, dict) else None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return None


def _wait_for_snapshot(
    port: int,
    scope_id: str,
    run_id: str,
    expected_sequence: int,
    timeout: float = 20.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = _snapshot(port, scope_id, run_id)
        if (
            value
            and value.get("scopeId") == scope_id
            and value.get("runId") == run_id
            and value.get("sequence") == expected_sequence
        ):
            return value
        time.sleep(0.25)
    raise LauncherError(
        "publisher_start_failed",
        f"No snapshot published for {scope_id}/{run_id} at sequence {expected_sequence}",
    )


def _workspace_panes(workspace_id: str) -> list[dict[str, Any]]:
    response = _herdr("pane", "list", "--workspace", workspace_id)
    panes = _result_value(response, "panes")
    return panes if isinstance(panes, list) else []


def _find_publisher(
    workspace_id: str,
    state_path: Path,
    selection: ManifestSelection,
    endpoint: str,
) -> str | None:
    for _ in range(2):
        stale_seen = False
        for pane in _workspace_panes(workspace_id):
            pane_id = pane.get("pane_id")
            if not isinstance(pane_id, str):
                continue
            try:
                response = _herdr("pane", "process-info", "--pane", pane_id)
            except LauncherError as error:
                if error.code in {"herdr_error", "herdr_timeout"}:
                    stale_seen = True
                    continue
                raise
            info = _result_value(response, "process_info") or {}
            if not isinstance(info, dict):
                continue
            if publisher_matches(
                info,
                str(state_path),
                selection,
                workspace_id,
                endpoint,
                True,
            ):
                return pane_id
        if not stale_seen:
            break
    return None


def _find_publisher_for_state(
    workspace_id: str, state_path: Path, endpoint: str
) -> str | None:
    for pane in _workspace_panes(workspace_id):
        pane_id = pane.get("pane_id")
        if not isinstance(pane_id, str) or isinstance(pane.get("agent"), str):
            continue
        try:
            response = _herdr("pane", "process-info", "--pane", pane_id)
        except LauncherError as error:
            if error.code in {"herdr_error", "herdr_timeout"}:
                continue
            raise
        info = _result_value(response, "process_info") or {}
        if isinstance(info, dict) and _publisher_matches_state(
            info, str(state_path), workspace_id, endpoint, True
        ):
            return pane_id
    return None


def _manifest_object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LauncherError("invalid_manifest", f"{path} must be a JSON object")
    return value


def _manifest_array(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise LauncherError("invalid_manifest", f"{path} must be an array")
    return value


def _manifest_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise LauncherError(
            "invalid_manifest", f"{path} must be a non-empty string"
        )
    return value


def _known_manifest_node(value: Any, node_ids: set[str], path: str) -> None:
    node_id = _manifest_string(value, path)
    if node_id not in node_ids:
        raise LauncherError(
            "invalid_manifest", f"{path} refers to an unknown node: {node_id}"
        )


def _validate_custom_manifest(path: Path) -> None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise LauncherError(
            "invalid_manifest", f"Cannot read manifest {path}: {error}"
        ) from error
    except json.JSONDecodeError as error:
        raise LauncherError(
            "invalid_manifest", f"Cannot parse manifest {path}: {error}"
        ) from error

    manifest = _manifest_object(value, "manifest")
    if manifest.get("schemaVersion") != MANIFEST_SCHEMA_VERSION:
        raise LauncherError(
            "invalid_manifest",
            f"manifest.schemaVersion must be {MANIFEST_SCHEMA_VERSION}",
        )

    nodes = _manifest_array(manifest.get("nodes"), "manifest.nodes")
    edges = _manifest_array(manifest.get("edges"), "manifest.edges")
    policies = _manifest_array(
        manifest.get("failurePolicies"), "manifest.failurePolicies"
    )

    node_ids: set[str] = set()
    for index, raw_node in enumerate(nodes):
        node_path = f"nodes[{index}]"
        node = _manifest_object(raw_node, node_path)
        node_id = _manifest_string(node.get("id"), f"{node_path}.id")
        if node_id in node_ids:
            raise LauncherError(
                "invalid_manifest", f"nodes contains duplicate node id: {node_id}"
            )
        node_ids.add(node_id)
        _manifest_string(node.get("role"), f"{node_path}.role")
        _manifest_string(node.get("assignee"), f"{node_path}.assignee")
        source = _manifest_object(node.get("source"), f"{node_path}.source")
        source_type = _manifest_string(
            source.get("type"), f"{node_path}.source.type"
        )
        if source_type not in {"lane", "slot"}:
            raise LauncherError(
                "invalid_manifest",
                f"{node_path}.source.type must be lane or slot",
            )
        _manifest_string(source.get("id"), f"{node_path}.source.id")

    edge_ids: set[str] = set()
    for index, raw_edge in enumerate(edges):
        edge_path = f"edges[{index}]"
        edge = _manifest_object(raw_edge, edge_path)
        edge_id = _manifest_string(edge.get("id"), f"{edge_path}.id")
        if edge_id in edge_ids:
            raise LauncherError(
                "invalid_manifest", f"edges contains duplicate edge id: {edge_id}"
            )
        edge_ids.add(edge_id)
        _known_manifest_node(edge.get("source"), node_ids, f"{edge_path}.source")
        _known_manifest_node(edge.get("target"), node_ids, f"{edge_path}.target")
        kind = _manifest_string(edge.get("kind"), f"{edge_path}.kind")
        if kind not in MANIFEST_EDGE_KINDS:
            raise LauncherError(
                "invalid_manifest", f"{edge_path}.kind has an invalid edge kind: {kind}"
            )
        status = _manifest_string(edge.get("status"), f"{edge_path}.status")
        if status not in MANIFEST_EDGE_STATUSES:
            raise LauncherError(
                "invalid_manifest",
                f"{edge_path}.status has an invalid edge status: {status}",
            )

    route_fields = ("gateNodeId", "returnToNodeId", "ownerNodeId", "resumeNodeId")
    for index, raw_policy in enumerate(policies):
        policy_path = f"failurePolicies[{index}]"
        policy = _manifest_object(raw_policy, policy_path)
        for field in route_fields:
            _known_manifest_node(
                policy.get(field), node_ids, f"{policy_path}.{field}"
            )
        for field in ("rerunNodeIds", "excludedNodeIds"):
            values = _manifest_array(policy.get(field), f"{policy_path}.{field}")
            for value_index, node_id in enumerate(values):
                _known_manifest_node(
                    node_id,
                    node_ids,
                    f"{policy_path}.{field}[{value_index}]",
                )


def _resolve_manifest(
    selected: SelectedState, explicit: Path | None
) -> ManifestSelection:
    if explicit is not None:
        manifest = explicit.expanduser().resolve()
    else:
        configured = selected.value.get("run", {}).get("role_graph_manifest")
        if isinstance(configured, str) and configured:
            candidate = Path(configured).expanduser()
            manifest = (
                candidate.resolve()
                if candidate.is_absolute()
                else (selected.path.parent / candidate).resolve()
            )
        else:
            run_manifest = selected.path.parent / "role-graph-manifest.json"
            if run_manifest.exists():
                manifest = run_manifest.resolve()
            else:
                return ManifestSelection("synthetic", None)
    if not manifest.is_file():
        raise LauncherError("missing_manifest", f"Manifest not found: {manifest}")
    _validate_custom_manifest(manifest)
    return ManifestSelection("custom", manifest)


@contextmanager
def _workspace_launch_lock(runs_root: Path, workspace_id: str) -> Iterator[None]:
    lock_dir = runs_root.expanduser() / workspace_id / "viewer"
    lock_dir.mkdir(parents=True, exist_ok=True)
    with (lock_dir / "launcher.lock").open("w", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def launch(args: argparse.Namespace) -> dict[str, Any]:
    if os.environ.get("HERDR_ENV") != "1":
        raise LauncherError("not_in_herdr", "HERDR_ENV=1 is required")
    workspace_id = os.environ.get("HERDR_WORKSPACE_ID", "")
    current_pane = os.environ.get("HERDR_PANE_ID", "")
    if not workspace_id or not current_pane:
        raise LauncherError("not_in_herdr", "Herdr workspace and pane IDs are required")

    repo = args.repo.expanduser().resolve()
    if not (repo / "server.js").is_file() or not (
        repo / "adapters/herdr/publisher.py"
    ).is_file():
        raise LauncherError("missing_viewer", f"Viewer repo is incomplete: {repo}")

    with _workspace_launch_lock(args.runs_root, workspace_id):
        selected = select_state(
            args.runs_root,
            workspace_id,
            current_pane,
            explicit=args.state,
        )
        selection = _resolve_manifest(selected, args.manifest)
        revision = selected.value.get("revision")
        if not isinstance(revision, int):
            raise LauncherError(
                "invalid_state", f"State has no integer revision: {selected.path}"
            )
        scope_id = f"herdr:{workspace_id}"
        port, server_reused = select_port(probe_viewer, args.port_start, args.port_end)
        server_pane: str | None = None

        if not server_reused:
            server_pane = _split_pane(
                current_pane,
                repo,
                "graph-viewer-server",
                direction="right",
                ratio="0.32",
            )
            data_file = (
                args.runs_root.expanduser() / workspace_id / "viewer" / "snapshots.jsonl"
            )
            quoted_repo = shlex.quote(str(repo))
            server_command = " && ".join(
                [
                    f"mkdir -p {shlex.quote(str(data_file.parent))}",
                    f"cd {quoted_repo}",
                    "npm ci",
                    "npm run build",
                    (
                        f"HOST=127.0.0.1 PORT={port} "
                        f"ROLE_GRAPH_DATA_FILE={shlex.quote(str(data_file))} npm run server"
                    ),
                ]
            )
            _run_in_pane(server_pane, server_command)
            _wait_for_viewer(port)

        endpoint = f"http://127.0.0.1:{port}/api/snapshots"
        publisher_pane = _find_publisher(workspace_id, selected.path, selection, endpoint)
        publisher_reused = publisher_pane is not None
        if publisher_pane is None:
            publisher_pane = _find_publisher_for_state(
                workspace_id, selected.path, endpoint
            )
            if publisher_pane is not None:
                _herdr("pane", "send-keys", publisher_pane, "ctrl+c")
            else:
                anchor_pane = server_pane or current_pane
                publisher_pane = _split_pane(
                    anchor_pane,
                    repo,
                    "graph-viewer-publisher",
                    direction="down" if server_pane is not None else "right",
                    ratio="0.5" if server_pane is not None else "0.32",
                )
            topology_args = (
                ["--synthesize"]
                if selection.mode == "synthetic"
                else ["--manifest", str(selection.path)]
            )
            command = " ".join(
                shlex.quote(value)
                for value in [
                    "python3",
                    "-B",
                    str(repo / "adapters/herdr/publisher.py"),
                    "--state",
                    str(selected.path),
                    *topology_args,
                    "--workspace-id",
                    workspace_id,
                    "--endpoint",
                    endpoint,
                    "--watch",
                    "--interval",
                    "2",
                ]
            )
            _run_in_pane(publisher_pane, command)

        snapshot = _wait_for_snapshot(port, scope_id, selected.run_id, revision)
    return {
        "status": "ready",
        "workspace_id": workspace_id,
        "run_id": selected.run_id,
        "state": str(selected.path),
        "mode": selection.mode,
        "manifest": str(selection.path) if selection.path is not None else None,
        "url": viewer_url(port, scope_id, selected.run_id),
        "sequence": snapshot.get("sequence"),
        "server": {"port": port, "pane_id": server_pane, "reused": server_reused},
        "publisher": {"pane_id": publisher_pane, "reused": publisher_reused},
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    parser.add_argument("--runs-root", type=Path, default=DEFAULT_RUNS_ROOT)
    parser.add_argument("--port-start", type=int, default=4173)
    parser.add_argument("--port-end", type=int, default=4183)
    return parser.parse_args()


def main() -> int:
    try:
        result = launch(parse_args())
    except LauncherError as error:
        print(
            json.dumps(
                {
                    "status": "error",
                    "code": error.code,
                    "message": str(error),
                    **error.details,
                },
                indent=2,
            )
        )
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
