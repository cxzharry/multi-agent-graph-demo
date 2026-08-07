"""Exact workspace/run-scoped append-only workflow event journal."""

from __future__ import annotations

import copy
import fcntl
import json
import os
from datetime import datetime
from pathlib import Path


EVENT_SCHEMA_VERSION = "role-graph-event/v1"
EVENT_KINDS = {
    "CONTROL_DISPATCH",
    "ARTIFACT_HANDOFF",
    "ASSIGNMENT_RESULT",
    "REWORK_ROUTE",
    "CONTROLLER_RECOVERED",
    "RUN_TERMINAL",
}
RESULTS = {"PASS", "FAIL", "BLOCKED", "SKIPPED", "REWORK"}


class JournalError(ValueError):
    """Raised when journal data violates the event contract."""

    def __init__(self, message: str, *, recovered_events=None):
        super().__init__(message)
        self.recovered_events = list(recovered_events or [])


class FlowJournal:
    """Append validated events without scanning existing journal history."""

    def __init__(self, path: Path, *, workspace_id: str, run_id: str):
        self.path = Path(path)
        self.workspace_id = workspace_id
        self.run_id = run_id
        self.lock_path = self.path.with_name(f"{self.path.name}.lock")

    def append(self, value: object) -> None:
        event = validate_event(
            value, workspace_id=self.workspace_id, run_id=self.run_id
        )
        try:
            line = json.dumps(
                event, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8") + b"\n"
        except (TypeError, ValueError) as error:
            raise JournalError(f"event is not JSON serializable: {error}") from error
        with self.lock_path.open("a+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                with self.path.open("ab") as journal:
                    journal.write(line)
                    journal.flush()
                    os.fsync(journal.fileno())
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


class FlowJournalReader:
    """Incrementally read validated events, deduplicated in ledger order."""

    def __init__(self, path: Path, *, workspace_id: str, run_id: str):
        self.path = Path(path)
        self.workspace_id = workspace_id
        self.run_id = run_id
        self.lock_path = self.path.with_name(f"{self.path.name}.lock")
        self._offset = 0
        self._seen_event_ids: set[str] = set()

    def read_new(self) -> list[dict]:
        with self.lock_path.open("a+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                if not self.path.exists():
                    return []
                size = self.path.stat().st_size
                if size < self._offset:
                    raise JournalError("journal was truncated")
                with self.path.open("rb") as journal:
                    journal.seek(self._offset)
                    suffix = journal.read()
                    next_offset = journal.tell()
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

        if not suffix:
            return []
        seen = set(self._seen_event_ids)
        events = []
        recovered_bytes = 0
        for line_number, raw_line in enumerate(
            suffix.splitlines(keepends=True), start=1
        ):
            if not raw_line.endswith(b"\n"):
                self._offset += recovered_bytes
                self._seen_event_ids = seen
                raise JournalError(
                    "journal has a malformed tail", recovered_events=events
                )
            try:
                value = json.loads(raw_line)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                self._offset += recovered_bytes
                self._seen_event_ids = seen
                raise JournalError(
                    f"journal has malformed JSON at appended line {line_number}",
                    recovered_events=events,
                ) from error
            try:
                event = validate_event(
                    value, workspace_id=self.workspace_id, run_id=self.run_id
                )
            except JournalError as error:
                self._offset += recovered_bytes
                self._seen_event_ids = seen
                raise JournalError(
                    str(error), recovered_events=events
                ) from error
            if event["eventId"] in seen:
                recovered_bytes += len(raw_line)
                continue
            seen.add(event["eventId"])
            events.append(event)
            recovered_bytes += len(raw_line)

        self._offset = next_offset
        self._seen_event_ids = seen
        return events


def validate_event(value: object, *, workspace_id: str, run_id: str) -> dict:
    """Return a defensive event copy after strict scope and shape validation."""
    if not isinstance(value, dict):
        raise JournalError("event must be a JSON object")
    event = copy.deepcopy(value)
    for field in ("eventId", "workspaceId", "runId", "at", "kind"):
        _required_string(event, field)
    if event.get("schemaVersion") != EVENT_SCHEMA_VERSION:
        raise JournalError("schemaVersion is missing or unsupported")
    if event["workspaceId"] != workspace_id:
        raise JournalError("workspaceId does not match journal identity")
    if event["runId"] != run_id:
        raise JournalError("runId does not match journal identity")
    if event["kind"] not in EVENT_KINDS:
        raise JournalError("kind is unknown")
    generation = event.get("generation")
    if (
        isinstance(generation, bool)
        or not isinstance(generation, int)
        or generation <= 0
    ):
        raise JournalError("generation must be a positive integer")
    _validate_timestamp(event["at"])

    kind = event["kind"]
    if kind in {"CONTROL_DISPATCH", "ARTIFACT_HANDOFF", "REWORK_ROUTE"}:
        _validate_assignment(event.get("source"), "source")
        _validate_assignment(event.get("target"), "target")
    if kind == "ARTIFACT_HANDOFF" and not isinstance(event.get("artifact"), dict):
        raise JournalError("artifact must be a JSON object")
    if kind == "ASSIGNMENT_RESULT":
        _validate_assignment(event.get("assignment"), "assignment")
        _validate_result(event.get("result"))
    if kind == "REWORK_ROUTE":
        _required_string(event, "reason")
    if kind == "CONTROLLER_RECOVERED":
        _validate_assignment(event.get("assignment"), "assignment")
    if kind == "RUN_TERMINAL":
        _validate_result(event.get("result"))
    return event


def _required_string(value: dict, field: str) -> str:
    item = value.get(field)
    if not isinstance(item, str) or not item:
        raise JournalError(f"{field} must be a non-empty string")
    return item


def _validate_timestamp(value: str) -> None:
    try:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError
    except (TypeError, ValueError):
        raise JournalError("at must be an ISO-8601 timestamp with timezone") from None


def _validate_assignment(value: object, field: str) -> None:
    if not isinstance(value, dict):
        raise JournalError(f"{field} must be an assignment descriptor")
    for descriptor_field in ("id", "role", "slot", "task"):
        item = value.get(descriptor_field)
        if not isinstance(item, str) or not item:
            raise JournalError(
                f"{field}.{descriptor_field} must be a non-empty string"
            )
    if "agentSessionId" in value:
        session_id = value["agentSessionId"]
        if not isinstance(session_id, str) or not session_id:
            raise JournalError(
                f"{field}.agentSessionId must be a non-empty string"
            )


def _validate_result(value: object) -> None:
    if not isinstance(value, str) or value not in RESULTS:
        raise JournalError("result is unknown")
