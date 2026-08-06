#!/usr/bin/env python3
"""Start or reuse the local viewer for one explicit Herdr workspace run."""

from __future__ import annotations

import argparse
import hashlib
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
from dataclasses import dataclass
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


class P1Identity(NamedTuple):
    pane_id: str
    session_id: str


class ManifestSelection(NamedTuple):
    mode: str
    path: Path | None


@dataclass(frozen=True)
class ProcessMatch:
    pane_id: str | None
    status: str

    def __bool__(self) -> bool:
        return self.status == "reusable"


def _content_fingerprint(repo: Path, relative_paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for relative in sorted(relative_paths, key=lambda value: value.as_posix()):
        path = repo / relative
        if not path.is_file():
            raise LauncherError("missing_viewer", f"Missing runtime file: {path}")
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def publisher_runtime_fingerprint(repo: Path) -> str:
    adapter_root = repo / "adapters/herdr"
    paths = [
        path.relative_to(repo)
        for path in adapter_root.glob("*.py")
        if path.is_file() and not path.name.startswith("test_")
    ]
    if not paths:
        raise LauncherError(
            "missing_viewer", f"Missing publisher runtime: {adapter_root}"
        )
    return _content_fingerprint(repo, paths)


def viewer_runtime_fingerprint(repo: Path) -> str:
    required = {
        Path("server.js"),
        Path("index.html"),
        Path("package.json"),
        Path("package-lock.json"),
    }
    patterns = (
        "server/**/*.js",
        "shared/**/*.js",
        "src/**/*",
        "vite.config.*",
        "tsconfig*.json",
    )
    discovered = {
        path.relative_to(repo)
        for pattern in patterns
        for path in repo.glob(pattern)
        if path.is_file()
    }
    return _content_fingerprint(repo, list(required | discovered))


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


def _p1_session(state: dict[str, Any]) -> str | None:
    controller = state.get("controller", {})
    if isinstance(controller.get("session_id"), str):
        return controller["session_id"]
    p1 = state.get("slots", {}).get("P1", {})
    return p1.get("session_id") if isinstance(p1.get("session_id"), str) else None


def select_state(
    runs_root: Path,
    workspace_id: str,
    current_p1_pane_id: str,
    current_p1_session_id: str = "",
    *,
    explicit: Path | None = None,
) -> SelectedState | None:
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

    matches = [
        item
        for item in candidates
        if _p1_pane(item.value) == current_p1_pane_id
        and _p1_session(item.value) == current_p1_session_id
    ]
    return matches[0] if len(matches) == 1 else None


def probe_viewer(port: int, expected_runtime_fingerprint: str | None = None) -> str:
    url = f"http://127.0.0.1:{port}/api/health"
    try:
        with urllib.request.urlopen(url, timeout=0.5) as response:
            data = json.load(response)
        if not isinstance(data, dict):
            return "occupied"
        capabilities = data.get("capabilities")
        if (
            data.get("service") == "herdr-role-graph-viewer"
            and data.get("schemaVersion") == "role-graph/v1"
            and isinstance(capabilities, list)
            and "space-name-summary" in capabilities
            and "session-presence" in capabilities
        ):
            if expected_runtime_fingerprint is None:
                return "viewer"
            if data.get("runtimeFingerprint") == expected_runtime_fingerprint:
                return "viewer-current"
            return "viewer-stale"
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


def _publisher_state_matches(
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


def _publisher_common_matches(
    argv: list[str],
    state_path: str,
    workspace_id: str,
    space_name: str,
    endpoint: str,
    watch: bool,
) -> bool:
    return _publisher_state_matches(
        argv, state_path, workspace_id, endpoint, watch
    ) and _argv_value(argv, "--space-name") == space_name


def publisher_matches(
    process_info: dict[str, Any],
    state_path: str,
    selection: ManifestSelection,
    workspace_id: str,
    space_name: str,
    endpoint: str,
    watch: bool,
    expected_runtime_fingerprint: str | None = None,
) -> ProcessMatch:
    status = "missing"
    for argv in _publisher_argvs(process_info):
        if not _publisher_common_matches(
            argv, state_path, workspace_id, space_name, endpoint, watch
        ):
            continue
        manifest_path = _argv_value(argv, "--manifest")
        synthetic = "--synthesize" in argv
        if selection.mode == "synthetic" and synthetic and manifest_path is None:
            status = (
                "reusable"
                if expected_runtime_fingerprint is None
                or _argv_value(argv, "--runtime-fingerprint")
                == expected_runtime_fingerprint
                else "stale"
            )
        if (
            selection.mode == "custom"
            and selection.path is not None
            and not synthetic
            and manifest_path == str(selection.path)
        ):
            status = (
                "reusable"
                if expected_runtime_fingerprint is None
                or _argv_value(argv, "--runtime-fingerprint")
                == expected_runtime_fingerprint
                else "stale"
            )
        if status == "reusable":
            break
    return ProcessMatch(None, status)


def session_publisher_matches(
    process_info: dict[str, Any],
    workspace_id: str,
    space_name: str,
    p1_session_id: str,
    p1_pane_id: str,
    endpoint: str,
    watch: bool,
    expected_runtime_fingerprint: str | None = None,
) -> ProcessMatch:
    status = "missing"
    for argv in _publisher_argvs(process_info):
        if (
            any(item.endswith("adapters/herdr/session_publisher.py") for item in argv)
            and _argv_value(argv, "--workspace-id") == workspace_id
            and _argv_value(argv, "--space-name") == space_name
            and _argv_value(argv, "--p1-session-id") == p1_session_id
            and _argv_value(argv, "--p1-pane-id") == p1_pane_id
            and _argv_value(argv, "--endpoint") == endpoint
            and ("--watch" in argv) is watch
        ):
            status = (
                "reusable"
                if expected_runtime_fingerprint is None
                or _argv_value(argv, "--runtime-fingerprint")
                == expected_runtime_fingerprint
                else "stale"
            )
            if status == "reusable":
                break
    return ProcessMatch(None, status)


def _publisher_matches_state(
    process_info: dict[str, Any],
    state_path: str,
    workspace_id: str,
    endpoint: str,
    watch: bool,
) -> bool:
    for argv in _publisher_argvs(process_info):
        if not _publisher_state_matches(
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
    if not result.stdout.strip():
        if args[:2] in {("pane", "run"), ("pane", "send-keys")}:
            return {}
        raise LauncherError(
            "herdr_error", "Invalid Herdr response: empty stdout", invalid_response=True
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise LauncherError(
            "herdr_error",
            f"Invalid Herdr response: {result.stdout}",
            invalid_response=True,
        ) from error


def _result_value(response: dict[str, Any], key: str) -> Any:
    return response.get("result", {}).get(key)


def _bound_controller_p1_identities(
    runs_root: Path, workspace_id: str
) -> set[P1Identity]:
    matches: set[P1Identity] = set()
    workspace_root = runs_root.expanduser() / workspace_id
    for path in sorted(workspace_root.rglob("workspace-state.json")):
        try:
            state = _load_state(path, workspace_id).value
        except LauncherError:
            continue
        controller = state.get("controller")
        if (
            not isinstance(controller, dict)
            or controller.get("workspace_id") != workspace_id
            or controller.get("role_name") != "p1_orchestrator"
            or not isinstance(controller.get("agent_name"), str)
            or not controller["agent_name"]
        ):
            continue
        pane_id = controller.get("pane_id")
        session_id = controller.get("session_id")
        if (
            isinstance(pane_id, str)
            and pane_id
            and isinstance(session_id, str)
            and session_id
        ):
            matches.add(P1Identity(pane_id, session_id))
    return matches


def _resolve_p1_identity(
    workspace_id: str, *, runs_root: Path | None = None
) -> P1Identity:
    agents = _result_value(_herdr("agent", "list"), "agents")
    matches: list[P1Identity] = []
    unnamed: list[P1Identity] = []
    if isinstance(agents, list):
        for agent in agents:
            if (
                not isinstance(agent, dict)
                or agent.get("workspace_id") != workspace_id
            ):
                continue
            pane_id = agent.get("pane_id")
            session = agent.get("agent_session")
            session_id = session.get("value") if isinstance(session, dict) else None
            if (
                isinstance(pane_id, str)
                and pane_id
                and isinstance(session_id, str)
                and session_id
            ):
                identity = P1Identity(pane_id, session_id)
                if agent.get("name") == "p1_orchestrator":
                    matches.append(identity)
                elif agent.get("name") is None:
                    unnamed.append(identity)
    if unnamed and runs_root is not None:
        bound = _bound_controller_p1_identities(runs_root, workspace_id)
        matches.extend(identity for identity in unnamed if identity in bound)
    if len(matches) != 1:
        raise LauncherError(
            "p1_identity_error",
            f"Cannot resolve one active P1 identity for workspace {workspace_id}",
        )
    return matches[0]


def _resolve_space_name(workspace_id: str) -> str:
    workspaces = _result_value(_herdr("workspace", "list"), "workspaces")
    if isinstance(workspaces, list):
        for workspace in workspaces:
            if (
                not isinstance(workspace, dict)
                or workspace.get("workspace_id") != workspace_id
            ):
                continue
            label = workspace.get("label")
            if isinstance(label, str) and label.strip():
                return label
            break
    raise LauncherError(
        "workspace_selection_error",
        f"Herdr workspace {workspace_id!r} has no non-empty label",
    )


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


def _wait_for_viewer(
    port: int, expected_runtime_fingerprint: str, timeout: float = 60.0
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if probe_viewer(port, expected_runtime_fingerprint) == "viewer-current":
            return
        time.sleep(0.25)
    raise LauncherError("viewer_start_failed", f"Viewer did not start on port {port}")


def _wait_for_shell(pane_id: str, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = _herdr("pane", "process-info", "--pane", pane_id)
        info = _result_value(response, "process_info") or {}
        if isinstance(info, dict) and _shell_ready(info):
            return
        time.sleep(0.1)
    raise LauncherError(
        "process_stop_failed", f"Pane {pane_id} did not return to its shell"
    )


def _shell_ready(info: dict[str, Any]) -> bool:
    processes = info.get("foreground_processes")
    if processes == []:
        return True
    shell_pid = info.get("shell_pid")
    if (
        not isinstance(processes, list)
        or len(processes) != 1
        or isinstance(shell_pid, bool)
        or not isinstance(shell_pid, int)
        or shell_pid <= 0
        or info.get("foreground_process_group_id") != shell_pid
    ):
        return False
    process = processes[0]
    if not isinstance(process, dict) or process.get("pid") != shell_pid:
        return False
    command = process.get("cmdline")
    if not isinstance(command, str):
        return False
    try:
        argv = shlex.split(command)
    except ValueError:
        return False
    return bool(argv) and Path(argv[0]).name.removeprefix("-") == "zsh"


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
    expected_sequence: int | None,
    expected_space_name: str,
    expected_publisher_fingerprint: str | None = None,
    minimum_sequence_exclusive: int | None = None,
    timeout: float = 20.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = _snapshot(port, scope_id, run_id)
        if (
            value
            and value.get("scopeId") == scope_id
            and value.get("runId") == run_id
            and (
                expected_sequence is None
                or value.get("sequence") == expected_sequence
            )
            and value.get("spaceName") == expected_space_name
            and (
                expected_publisher_fingerprint is None
                or value.get("publisherFingerprint")
                == expected_publisher_fingerprint
            )
            and (
                minimum_sequence_exclusive is None
                or (
                    isinstance(value.get("sequence"), int)
                    and value["sequence"] > minimum_sequence_exclusive
                )
            )
        ):
            return value
        time.sleep(0.25)
    raise LauncherError(
        "publisher_start_failed",
        f"No matching snapshot published for {scope_id}/{run_id} "
        f"with spaceName {expected_space_name!r}",
    )


def _workspace_panes(workspace_id: str) -> list[dict[str, Any]]:
    response = _herdr("pane", "list", "--workspace", workspace_id)
    panes = _result_value(response, "panes")
    return panes if isinstance(panes, list) else []


def _legacy_server_pane(
    workspace_id: str,
    repo: Path,
    panes: list[dict[str, Any]],
    process_info: Callable[[str], dict[str, Any]],
) -> str | None:
    candidates: list[str] = []
    for pane in panes:
        pane_id = pane.get("pane_id")
        if (
            not isinstance(pane_id, str)
            or isinstance(pane.get("agent"), str)
            or pane.get("label") != "graph-viewer-server"
        ):
            continue
        info = process_info(pane_id)
        foreground = info.get("foreground_processes")
        if not isinstance(foreground, list):
            continue
        if any(
            _legacy_server_process_matches(process, repo, info.get("cwd"))
            for process in foreground
        ):
            candidates.append(pane_id)
    if len(candidates) > 1:
        raise LauncherError(
            "ambiguous_stale_server",
            f"Multiple legacy graph-viewer-server panes in workspace {workspace_id}",
        )
    return candidates[0] if candidates else None


def _legacy_server_process_matches(
    process: Any, repo: Path, fallback_cwd: Any
) -> bool:
    argv = _server_process_argv(process, repo, fallback_cwd)
    return argv is not None and len(argv) == 2


def _server_process_argv(
    process: Any, repo: Path, fallback_cwd: Any = None
) -> list[str] | None:
    if not isinstance(process, dict):
        return None
    command = process.get("cmdline")
    cwd = process.get("cwd", fallback_cwd)
    if not isinstance(command, str) or not isinstance(cwd, str):
        return None
    try:
        argv = shlex.split(command)
    except ValueError:
        return None
    if len(argv) < 2 or Path(argv[0]).name != "node":
        return None
    process_cwd = Path(cwd).resolve()
    if process_cwd != repo.resolve():
        return None
    script = Path(argv[1])
    resolved_script = (
        script.resolve() if script.is_absolute() else (process_cwd / script).resolve()
    )
    if resolved_script != (repo / "server.js").resolve():
        return None
    return argv


def _pane_process_info(pane_id: str) -> dict[str, Any]:
    response = _herdr("pane", "process-info", "--pane", pane_id)
    info = _result_value(response, "process_info") or {}
    return info if isinstance(info, dict) else {}


def _stale_server_pane(
    workspace_id: str, repo: Path, port: int, panes: list[dict[str, Any]]
) -> str | None:
    process_infos: dict[str, dict[str, Any]] = {}
    managed: list[str] = []
    for pane in panes:
        pane_id = pane.get("pane_id")
        if (
            not isinstance(pane_id, str)
            or isinstance(pane.get("agent"), str)
            or pane.get("label") != "graph-viewer-server"
        ):
            continue
        info = _pane_process_info(pane_id)
        process_infos[pane_id] = info
        foreground = info.get("foreground_processes")
        if not isinstance(foreground, list):
            continue
        for process in foreground:
            argv = _server_process_argv(process, repo, info.get("cwd"))
            if argv is not None and _argv_value(argv, "--port") == str(port):
                managed.append(pane_id)
                break
    if len(managed) > 1:
        raise LauncherError(
            "ambiguous_stale_server",
            f"Multiple graph-viewer-server panes in workspace {workspace_id} for port {port}",
        )
    legacy = _legacy_server_pane(
        workspace_id,
        repo,
        panes,
        lambda pane_id: process_infos.get(pane_id, {}),
    )
    candidates = set(managed)
    if legacy is not None:
        candidates.add(legacy)
    if len(candidates) > 1:
        raise LauncherError(
            "ambiguous_stale_server",
            f"Multiple graph-viewer-server panes in workspace {workspace_id} for port {port}",
        )
    return next(iter(candidates)) if candidates else None


def _select_server(
    workspace_id: str,
    repo: Path,
    expected_runtime_fingerprint: str,
    port_start: int,
    port_end: int,
) -> tuple[int, ProcessMatch]:
    first_free: int | None = None
    stale_ports: list[int] = []
    for port in range(port_start, port_end + 1):
        status = probe_viewer(port, expected_runtime_fingerprint)
        if status == "viewer-current":
            return port, ProcessMatch(None, "reusable")
        if status == "viewer-stale":
            stale_ports.append(port)
        elif status == "free" and first_free is None:
            first_free = port
    if stale_ports:
        panes = _workspace_panes(workspace_id)
        for port in stale_ports:
            pane_id = _stale_server_pane(workspace_id, repo, port, panes)
            if pane_id is not None:
                return port, ProcessMatch(pane_id, "stale")
    if first_free is not None:
        return first_free, ProcessMatch(None, "missing")
    raise LauncherError(
        "no_port",
        f"No current viewer, recoverable stale viewer, or free localhost port in "
        f"{port_start}-{port_end}",
    )


def _find_publisher(
    workspace_id: str,
    space_name: str,
    state_path: Path,
    selection: ManifestSelection,
    endpoint: str,
    expected_runtime_fingerprint: str,
) -> ProcessMatch:
    for _ in range(2):
        stale_seen = False
        matches: dict[str, str] = {}
        for pane in _workspace_panes(workspace_id):
            pane_id = pane.get("pane_id")
            if not isinstance(pane_id, str) or isinstance(pane.get("agent"), str):
                continue
            try:
                response = _herdr("pane", "process-info", "--pane", pane_id)
            except LauncherError as error:
                if error.details.get("invalid_response"):
                    raise
                if error.code in {"herdr_error", "herdr_timeout"}:
                    stale_seen = True
                    continue
                raise
            info = _result_value(response, "process_info") or {}
            if not isinstance(info, dict):
                continue
            match = publisher_matches(
                info,
                str(state_path),
                selection,
                workspace_id,
                space_name,
                endpoint,
                True,
                expected_runtime_fingerprint,
            )
            if match.status == "reusable":
                matches[pane_id] = "reusable"
            elif match.status == "stale":
                matches[pane_id] = "stale"
        found = _unique_publisher_match(workspace_id, matches)
        if found.status != "missing":
            return found
        if not stale_seen:
            break
    return ProcessMatch(None, "missing")


def _find_publisher_for_state(
    workspace_id: str, state_path: Path, endpoint: str
) -> ProcessMatch:
    matches: dict[str, str] = {}
    for pane in _workspace_panes(workspace_id):
        pane_id = pane.get("pane_id")
        if not isinstance(pane_id, str) or isinstance(pane.get("agent"), str):
            continue
        try:
            response = _herdr("pane", "process-info", "--pane", pane_id)
        except LauncherError as error:
            if error.details.get("invalid_response"):
                raise
            if error.code in {"herdr_error", "herdr_timeout"}:
                continue
            raise
        info = _result_value(response, "process_info") or {}
        if isinstance(info, dict) and _publisher_matches_state(
            info, str(state_path), workspace_id, endpoint, True
        ):
            matches[pane_id] = "stale"
    return _unique_publisher_match(workspace_id, matches)


def _find_session_publisher(
    workspace_id: str,
    space_name: str,
    p1_session_id: str,
    p1_pane_id: str,
    endpoint: str,
    expected_runtime_fingerprint: str,
) -> ProcessMatch:
    matches: dict[str, str] = {}
    for pane in _workspace_panes(workspace_id):
        pane_id = pane.get("pane_id")
        if not isinstance(pane_id, str) or isinstance(pane.get("agent"), str):
            continue
        try:
            response = _herdr("pane", "process-info", "--pane", pane_id)
        except LauncherError as error:
            if error.details.get("invalid_response"):
                raise
            if error.code in {"herdr_error", "herdr_timeout"}:
                continue
            raise
        info = _result_value(response, "process_info") or {}
        if isinstance(info, dict):
            match = session_publisher_matches(
                info,
                workspace_id,
                space_name,
                p1_session_id,
                p1_pane_id,
                endpoint,
                True,
                expected_runtime_fingerprint,
            )
            if match.status == "reusable":
                matches[pane_id] = "reusable"
            elif match.status == "stale":
                matches[pane_id] = "stale"
    return _unique_publisher_match(workspace_id, matches)


def _unique_publisher_match(
    workspace_id: str, matches: dict[str, str]
) -> ProcessMatch:
    if len(matches) > 1:
        raise LauncherError(
            "ambiguous_publisher",
            f"Multiple exact publisher panes in workspace {workspace_id}",
        )
    if not matches:
        return ProcessMatch(None, "missing")
    pane_id, status = next(iter(matches.items()))
    return ProcessMatch(pane_id, status)


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
        _manifest_string(node.get("task"), f"{node_path}.task")
        if "layer" in node:
            layer = node["layer"]
            if isinstance(layer, bool) or not isinstance(layer, int) or layer < 0:
                raise LauncherError(
                    "invalid_manifest",
                    f"{node_path}.layer must be a non-negative integer",
                )
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
    if not (repo / "server.js").is_file():
        raise LauncherError("missing_viewer", f"Viewer repo is incomplete: {repo}")

    with _workspace_launch_lock(args.runs_root, workspace_id):
        publisher_fingerprint = publisher_runtime_fingerprint(repo)
        viewer_fingerprint = viewer_runtime_fingerprint(repo)
        current_p1: P1Identity | None = None
        if args.state is not None:
            selected = select_state(
                args.runs_root,
                workspace_id,
                current_pane,
                "",
                explicit=args.state,
            )
        else:
            current_p1 = _resolve_p1_identity(
                workspace_id, runs_root=args.runs_root
            )
            selected = select_state(
                args.runs_root,
                workspace_id,
                current_p1.pane_id,
                current_p1.session_id,
            )

        session_mode = selected is None
        if session_mode:
            if current_p1 is None:
                raise LauncherError(
                    "p1_identity_error",
                    f"Cannot resolve current P1 identity for workspace {workspace_id}",
                )
            p1_pane = current_p1.pane_id
            p1_session_id = current_p1.session_id
            run_id = p1_session_id
            selection: ManifestSelection | None = None
            revision: int | None = None
            publisher_script = repo / "adapters/herdr/session_publisher.py"
        else:
            p1_pane = _p1_pane(selected.value)
            if not p1_pane:
                raise LauncherError(
                    "invalid_state",
                    f"State has no usable P1 pane binding: {selected.path}",
                )
            p1_session_id = ""
            run_id = selected.run_id
            selection = _resolve_manifest(selected, args.manifest)
            revision = selected.value.get("revision")
            if not isinstance(revision, int):
                raise LauncherError(
                    "invalid_state",
                    f"State has no integer revision: {selected.path}",
                )
            publisher_script = repo / "adapters/herdr/publisher.py"
        if not publisher_script.is_file():
            raise LauncherError(
                "missing_viewer", f"Viewer repo is incomplete: {repo}"
            )
        space_name = _resolve_space_name(workspace_id)
        scope_id = f"herdr:{workspace_id}"
        port, server_match = _select_server(
            workspace_id,
            repo,
            viewer_fingerprint,
            args.port_start,
            args.port_end,
        )
        server_reused = server_match.status == "reusable"
        server_replaced = server_match.status == "stale"
        server_pane = server_match.pane_id
        endpoint = f"http://127.0.0.1:{port}/api/snapshots"
        if session_mode:
            publisher_match = _find_session_publisher(
                workspace_id,
                space_name,
                p1_session_id,
                p1_pane,
                endpoint,
                publisher_fingerprint,
            )
        else:
            publisher_match = _find_publisher(
                workspace_id,
                space_name,
                selected.path,
                selection,
                endpoint,
                publisher_fingerprint,
            )
            if publisher_match.status == "missing":
                publisher_match = _find_publisher_for_state(
                    workspace_id, selected.path, endpoint
                )
        publisher_reused = publisher_match.status == "reusable"
        publisher_replaced = publisher_match.status == "stale"
        publisher_pane = publisher_match.pane_id

        prior_snapshot = _snapshot(port, scope_id, run_id)
        prior_sequence = None
        if (
            prior_snapshot
            and prior_snapshot.get("scopeId") == scope_id
            and prior_snapshot.get("runId") == run_id
            and isinstance(prior_snapshot.get("sequence"), int)
        ):
            prior_sequence = prior_snapshot["sequence"]
        replace_equal_sequence = (
            publisher_replaced
            or not server_reused
            or (revision is not None and prior_sequence == revision)
        )

        if publisher_replaced:
            assert publisher_pane is not None
            _herdr("pane", "send-keys", publisher_pane, "ctrl+c")
            _wait_for_shell(publisher_pane)
        if server_replaced:
            assert server_pane is not None
            _herdr("pane", "send-keys", server_pane, "ctrl+c")
            _wait_for_shell(server_pane)

        if not server_reused:
            if server_pane is None:
                server_pane = _split_pane(
                    p1_pane,
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
                        f"ROLE_GRAPH_DATA_FILE={shlex.quote(str(data_file))} "
                        f"npm run server -- --port {port} "
                        f"--runtime-fingerprint {viewer_fingerprint}"
                    ),
                ]
            )
            _run_in_pane(server_pane, server_command)
            _wait_for_viewer(port, viewer_fingerprint)

        if not publisher_reused:
            if publisher_pane is None:
                anchor_pane = server_pane or p1_pane
                publisher_pane = _split_pane(
                    anchor_pane,
                    repo,
                    "graph-viewer-publisher",
                    direction="down" if server_pane is not None else "right",
                    ratio="0.5" if server_pane is not None else "0.32",
                )
            if session_mode:
                command_values = [
                    "python3",
                    "-B",
                    str(publisher_script),
                    "--workspace-id",
                    workspace_id,
                    "--space-name",
                    space_name,
                    "--p1-session-id",
                    p1_session_id,
                    "--p1-pane-id",
                    p1_pane,
                    "--endpoint",
                    endpoint,
                    "--runtime-fingerprint",
                    publisher_fingerprint,
                    "--sequence-floor",
                    str((prior_sequence or 0) + 1),
                    "--watch",
                    "--interval",
                    "2",
                ]
            else:
                topology_args = (
                    ["--synthesize"]
                    if selection.mode == "synthetic"
                    else ["--manifest", str(selection.path)]
                )
                command_values = [
                    "python3",
                    "-B",
                    str(publisher_script),
                    "--state",
                    str(selected.path),
                    *topology_args,
                    *(["--replace-current"] if replace_equal_sequence else []),
                    "--workspace-id",
                    workspace_id,
                    "--space-name",
                    space_name,
                    "--endpoint",
                    endpoint,
                    "--runtime-fingerprint",
                    publisher_fingerprint,
                    "--watch",
                    "--interval",
                    "2",
                ]
            command = " ".join(
                shlex.quote(value)
                for value in command_values
            )
            _run_in_pane(publisher_pane, command)

        snapshot = _wait_for_snapshot(
            port,
            scope_id,
            run_id,
            revision,
            space_name,
            expected_publisher_fingerprint=publisher_fingerprint,
            minimum_sequence_exclusive=(
                prior_sequence
                if session_mode and not publisher_reused and prior_sequence is not None
                else None
            ),
        )
    return {
        "status": "ready",
        "workspace_id": workspace_id,
        "space_name": space_name,
        "run_id": run_id,
        "state": str(selected.path) if selected is not None else None,
        "mode": "session" if session_mode else selection.mode,
        "manifest": (
            str(selection.path)
            if selection is not None and selection.path is not None
            else None
        ),
        "url": viewer_url(port, scope_id, run_id),
        "sequence": snapshot.get("sequence"),
        "viewerFingerprint": viewer_fingerprint,
        "publisherFingerprint": publisher_fingerprint,
        "server": {
            "port": port,
            "pane_id": server_pane,
            "reused": server_reused,
            "replaced": server_replaced,
        },
        "publisher": {
            "pane_id": publisher_pane,
            "reused": publisher_reused,
            "replaced": publisher_replaced,
        },
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
