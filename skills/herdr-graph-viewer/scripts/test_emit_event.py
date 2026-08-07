from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).with_name("emit_event.py")
EVENT_KINDS = {
    "CONTROL_DISPATCH",
    "ARTIFACT_HANDOFF",
    "ASSIGNMENT_RESULT",
    "REWORK_ROUTE",
    "CONTROLLER_RECOVERED",
    "RUN_TERMINAL",
}


class JournalError(RuntimeError):
    pass


class FlowJournal:
    def __init__(self, path: Path, *, workspace_id: str, run_id: str):
        self.path = Path(path)
        self.workspace_id = workspace_id
        self.run_id = run_id
        if self.path.name == "foreign.jsonl" and workspace_id != "foreign":
            raise JournalError("journal identity mismatch")

    def append(self, event: dict) -> None:
        if event.get("workspaceId") != self.workspace_id:
            raise JournalError("workspace identity mismatch")
        if event.get("runId") != self.run_id:
            raise JournalError("run identity mismatch")
        if event.get("kind") not in EVENT_KINDS:
            raise JournalError("unknown event kind")
        if not isinstance(event.get("generation"), int) or event["generation"] <= 0:
            raise JournalError("invalid generation")
        required = {
            "CONTROL_DISPATCH": ("source", "target"),
            "ARTIFACT_HANDOFF": ("source", "target", "artifact"),
            "ASSIGNMENT_RESULT": ("assignment", "result"),
            "REWORK_ROUTE": ("source", "target", "reason"),
            "CONTROLLER_RECOVERED": ("assignment",),
            "RUN_TERMINAL": ("result",),
        }[event["kind"]]
        missing = [name for name in required if name not in event]
        if missing:
            raise JournalError(f"missing fields: {', '.join(missing)}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, separators=(",", ":")) + "\n")


class FlowJournalReader:
    def __init__(self, path: Path, *, workspace_id: str, run_id: str):
        self.path = Path(path)
        self.workspace_id = workspace_id
        self.run_id = run_id

    def read_new(self) -> list[dict]:
        seen: set[str] = set()
        events: list[dict] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            if event["workspaceId"] != self.workspace_id or event["runId"] != self.run_id:
                raise JournalError("journal identity mismatch")
            if event["eventId"] not in seen:
                seen.add(event["eventId"])
                events.append(event)
        return events


def load_emitter():
    if not SCRIPT.exists():
        return None
    journal_module = types.ModuleType("adapters.herdr.flow_journal")
    journal_module.EVENT_SCHEMA_VERSION = "role-graph-event/v1"
    journal_module.FlowJournal = FlowJournal
    journal_module.FlowJournalReader = FlowJournalReader
    journal_module.JournalError = JournalError
    spec = importlib.util.spec_from_file_location("emit_event", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    with mock.patch.dict(
        sys.modules, {"adapters.herdr.flow_journal": journal_module}
    ):
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    return module


class EmitEventTest(unittest.TestCase):
    def setUp(self) -> None:
        self.emitter = load_emitter()

    def require_emitter(self):
        self.assertIsNotNone(self.emitter, "emit_event.py is missing")
        return self.emitter

    def base_argv(self, journal: Path, *, event_id: str, kind: str) -> list[str]:
        return [
            "--journal",
            str(journal),
            "--workspace-id",
            "wK",
            "--run-id",
            "run-1",
            "--event-id",
            event_id,
            "--at",
            "2026-08-07T12:00:00Z",
            "--kind",
            kind,
            "--generation",
            "1",
        ]

    def invoke(self, argv: list[str]) -> tuple[int, dict]:
        emitter = self.require_emitter()
        output = io.StringIO()
        with redirect_stdout(output):
            code = emitter.main(argv)
        lines = output.getvalue().splitlines()
        self.assertEqual(len(lines), 1)
        return code, json.loads(lines[0])

    def test_emits_every_event_kind_with_machine_readable_output(self):
        assignment = json.dumps(
            {
                "id": "implementation-ui:g1",
                "role": "Implementation",
                "slot": "P2",
                "task": "Implement checkout UI",
            }
        )
        cases = {
            "CONTROL_DISPATCH": ["--source", assignment, "--target", assignment],
            "ARTIFACT_HANDOFF": [
                "--source",
                assignment,
                "--target",
                assignment,
                "--artifact",
                json.dumps({"path": "src/ui.tsx"}),
            ],
            "ASSIGNMENT_RESULT": [
                "--assignment",
                assignment,
                "--result",
                "PASS",
            ],
            "REWORK_ROUTE": [
                "--source",
                assignment,
                "--target",
                assignment,
                "--reason",
                "Fix the finding",
            ],
            "CONTROLLER_RECOVERED": ["--assignment", assignment],
            "RUN_TERMINAL": ["--result", "PASS"],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index, (kind, extra) in enumerate(cases.items()):
                with self.subTest(kind=kind):
                    journal = root / f"{index}.jsonl"
                    event_id = f"evt-{index}"
                    code, output = self.invoke(
                        self.base_argv(journal, event_id=event_id, kind=kind) + extra
                    )
                    self.assertEqual(code, 0)
                    self.assertEqual(
                        set(output), {"status", "eventId", "appended", "elapsedMs"}
                    )
                    self.assertEqual(output["status"], "ok")
                    self.assertEqual(output["eventId"], event_id)
                    self.assertIs(output["appended"], True)
                    self.assertIsInstance(output["elapsedMs"], float)

    def test_parses_assignment_json_into_the_event(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = Path(directory) / "events.jsonl"
            assignment = {
                "id": "independent-qc:g1",
                "role": "Independent QC",
                "slot": "P6",
                "agentSessionId": "session-6",
                "task": "Review candidate",
            }
            argv = self.base_argv(
                journal, event_id="evt-result", kind="ASSIGNMENT_RESULT"
            ) + ["--assignment", json.dumps(assignment), "--result", "PASS"]

            code, _ = self.invoke(argv)

            self.assertEqual(code, 0)
            event = json.loads(journal.read_text(encoding="utf-8"))
            self.assertEqual(event["assignment"], assignment)

    def test_validation_and_identity_failures_exit_two(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            missing_fields = self.base_argv(
                root / "missing.jsonl", event_id="evt-missing", kind="CONTROL_DISPATCH"
            )
            foreign_identity = self.base_argv(
                root / "foreign.jsonl", event_id="evt-foreign", kind="RUN_TERMINAL"
            ) + ["--result", "PASS"]

            for argv in (missing_fields, foreign_identity):
                with self.subTest(argv=argv):
                    code, output = self.invoke(argv)
                    self.assertEqual(code, 2)
                    self.assertEqual(output["status"], "error")
                    self.assertIs(output["appended"], False)

    def test_duplicate_ids_append_successfully_and_project_once(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = Path(directory) / "events.jsonl"
            argv = self.base_argv(
                journal, event_id="evt-terminal", kind="RUN_TERMINAL"
            ) + ["--result", "PASS"]

            first, _ = self.invoke(argv)
            second, _ = self.invoke(argv)

            self.assertEqual((first, second), (0, 0))
            reader = FlowJournalReader(journal, workspace_id="wK", run_id="run-1")
            self.assertEqual(
                [event["eventId"] for event in reader.read_new()], ["evt-terminal"]
            )


if __name__ == "__main__":
    unittest.main()
