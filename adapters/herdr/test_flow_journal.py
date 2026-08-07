import copy
import json
import tempfile
import unittest
from pathlib import Path

from adapters.herdr.flow_journal import (
    EVENT_KINDS,
    EVENT_SCHEMA_VERSION,
    FlowJournal,
    FlowJournalReader,
    JournalError,
    validate_event,
)


WORKSPACE_ID = "wK"
RUN_ID = "run-1"


def assignment(identifier="implementation-ui:g1", **overrides):
    value = {
        "id": identifier,
        "role": "Implementation",
        "slot": "P2",
        "task": "Implement checkout UI",
    }
    value.update(overrides)
    return value


def event(event_kind, **overrides):
    value = {
        "schemaVersion": EVENT_SCHEMA_VERSION,
        "eventId": f"evt-{event_kind.lower()}",
        "workspaceId": WORKSPACE_ID,
        "runId": RUN_ID,
        "at": "2026-08-07T01:02:03Z",
        "kind": event_kind,
        "generation": 1,
    }
    fields = {
        "CONTROL_DISPATCH": {
            "source": assignment("orchestrator", role="Orchestrator", slot="P1"),
            "target": assignment(),
        },
        "ARTIFACT_HANDOFF": {
            "source": assignment(),
            "target": assignment("integration:g1", role="Integration", slot="P5"),
            "artifact": {"commit": "abc123"},
        },
        "ASSIGNMENT_RESULT": {
            "assignment": assignment(),
            "result": "PASS",
        },
        "REWORK_ROUTE": {
            "source": assignment("independent-qc:g1", role="Independent QC", slot="P6"),
            "target": assignment("implementation-ui:g2"),
            "reason": "Browser assertion failed",
        },
        "CONTROLLER_RECOVERED": {
            "assignment": assignment(
                "orchestrator", role="Orchestrator", slot="P1"
            ),
        },
        "RUN_TERMINAL": {"result": "PASS"},
    }
    value.update(fields[event_kind])
    value.update(overrides)
    return value


class EventValidationTests(unittest.TestCase):
    def test_accepts_one_valid_event_for_every_kind_without_mutating_input(self):
        self.assertEqual(set(EVENT_KINDS), set(event_kind for event_kind in EVENT_KINDS))
        for event_kind in EVENT_KINDS:
            with self.subTest(kind=event_kind):
                value = event(event_kind)
                original = copy.deepcopy(value)

                validated = validate_event(
                    value, workspace_id=WORKSPACE_ID, run_id=RUN_ID
                )

                self.assertEqual(original, value)
                self.assertEqual(original, validated)
                self.assertIsNot(value, validated)

        dispatch = validate_event(
            event("CONTROL_DISPATCH", eventId="evt-dispatch-p2-g1"),
            workspace_id=WORKSPACE_ID,
            run_id=RUN_ID,
        )
        self.assertEqual("evt-dispatch-p2-g1", dispatch["eventId"])

    def test_rejects_missing_common_identity(self):
        for field in (
            "schemaVersion",
            "eventId",
            "workspaceId",
            "runId",
            "at",
            "kind",
            "generation",
        ):
            with self.subTest(field=field):
                value = event("CONTROL_DISPATCH")
                del value[field]
                with self.assertRaisesRegex(JournalError, field):
                    validate_event(
                        value, workspace_id=WORKSPACE_ID, run_id=RUN_ID
                    )

    def test_rejects_foreign_workspace_or_run(self):
        for field, foreign in (("workspaceId", "wOther"), ("runId", "run-other")):
            with self.subTest(field=field):
                with self.assertRaisesRegex(JournalError, field):
                    validate_event(
                        event("CONTROL_DISPATCH", **{field: foreign}),
                        workspace_id=WORKSPACE_ID,
                        run_id=RUN_ID,
                    )

    def test_rejects_unknown_kind_malformed_timestamp_and_generation(self):
        cases = (
            (event("CONTROL_DISPATCH", kind="UNKNOWN"), "kind"),
            (event("CONTROL_DISPATCH", at="not-a-time"), "at"),
            (event("CONTROL_DISPATCH", at="2026-08-07T01:02:03"), "at"),
            (event("CONTROL_DISPATCH", generation=0), "generation"),
            (event("CONTROL_DISPATCH", generation=True), "generation"),
        )
        for value, field in cases:
            with self.subTest(field=field, value=value[field]):
                with self.assertRaisesRegex(JournalError, field):
                    validate_event(
                        value, workspace_id=WORKSPACE_ID, run_id=RUN_ID
                    )

    def test_rejects_incomplete_assignment_descriptors(self):
        for descriptor_field in ("id", "role", "slot", "task"):
            with self.subTest(field=descriptor_field):
                source = assignment()
                del source[descriptor_field]
                with self.assertRaisesRegex(JournalError, descriptor_field):
                    validate_event(
                        event("CONTROL_DISPATCH", source=source),
                        workspace_id=WORKSPACE_ID,
                        run_id=RUN_ID,
                    )

        with self.assertRaisesRegex(JournalError, "agentSessionId"):
            validate_event(
                event(
                    "ASSIGNMENT_RESULT",
                    assignment=assignment(agentSessionId=""),
                ),
                workspace_id=WORKSPACE_ID,
                run_id=RUN_ID,
            )

    def test_rejects_unknown_result(self):
        for event_kind in ("ASSIGNMENT_RESULT", "RUN_TERMINAL"):
            for result in ("MAYBE", {"unexpected": True}):
                with self.subTest(kind=event_kind, result=result):
                    with self.assertRaisesRegex(JournalError, "result"):
                        validate_event(
                            event(event_kind, result=result),
                            workspace_id=WORKSPACE_ID,
                            run_id=RUN_ID,
                        )


class JournalAppendReadTests(unittest.TestCase):
    def test_append_is_canonical_and_reader_deduplicates_incrementally(self):
        value = event("CONTROL_DISPATCH", eventId="evt-dispatch-p2-g1")
        with tempfile.TemporaryDirectory() as directory:
            journal_path = Path(directory) / "flow-events.jsonl"
            journal = FlowJournal(
                journal_path, workspace_id=WORKSPACE_ID, run_id=RUN_ID
            )
            journal.append(value)
            journal.append(value)

            expected_line = json.dumps(
                value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            )
            self.assertEqual(
                expected_line + "\n" + expected_line + "\n",
                journal_path.read_text(encoding="utf-8"),
            )

            reader = FlowJournalReader(
                journal_path, workspace_id=WORKSPACE_ID, run_id=RUN_ID
            )
            self.assertEqual([value], reader.read_new())
            self.assertEqual([], reader.read_new())

            next_value = event("ASSIGNMENT_RESULT", eventId="evt-result-p2-g1")
            journal.append(next_value)
            self.assertEqual([next_value], reader.read_new())
            self.assertEqual([], reader.read_new())

    def test_two_writers_and_tied_timestamps_preserve_append_order(self):
        first = event(
            "CONTROL_DISPATCH",
            eventId="evt-first",
            at="2026-08-07T01:02:03Z",
        )
        second = event(
            "ARTIFACT_HANDOFF",
            eventId="evt-second",
            at="2026-08-07T01:02:03Z",
        )
        with tempfile.TemporaryDirectory() as directory:
            journal_path = Path(directory) / "flow-events.jsonl"
            writer_one = FlowJournal(
                journal_path, workspace_id=WORKSPACE_ID, run_id=RUN_ID
            )
            writer_two = FlowJournal(
                journal_path, workspace_id=WORKSPACE_ID, run_id=RUN_ID
            )

            writer_one.append(first)
            writer_two.append(second)

            reader = FlowJournalReader(
                journal_path, workspace_id=WORKSPACE_ID, run_id=RUN_ID
            )
            self.assertEqual(
                ["evt-first", "evt-second"],
                [item["eventId"] for item in reader.read_new()],
            )

    def test_restarted_reader_performs_full_recovery_scan(self):
        with tempfile.TemporaryDirectory() as directory:
            journal_path = Path(directory) / "flow-events.jsonl"
            journal = FlowJournal(
                journal_path, workspace_id=WORKSPACE_ID, run_id=RUN_ID
            )
            values = [
                event("CONTROL_DISPATCH", eventId="evt-1"),
                event("ASSIGNMENT_RESULT", eventId="evt-2"),
            ]
            for value in values:
                journal.append(value)

            first_reader = FlowJournalReader(
                journal_path, workspace_id=WORKSPACE_ID, run_id=RUN_ID
            )
            self.assertEqual(values, first_reader.read_new())
            self.assertEqual([], first_reader.read_new())

            restarted = FlowJournalReader(
                journal_path, workspace_id=WORKSPACE_ID, run_id=RUN_ID
            )
            self.assertEqual(values, restarted.read_new())

    def test_valid_prefix_plus_malformed_tail_raises_without_rewriting(self):
        with tempfile.TemporaryDirectory() as directory:
            journal_path = Path(directory) / "flow-events.jsonl"
            journal = FlowJournal(
                journal_path, workspace_id=WORKSPACE_ID, run_id=RUN_ID
            )
            first = event("CONTROL_DISPATCH", eventId="evt-valid")
            journal.append(first)
            reader = FlowJournalReader(
                journal_path, workspace_id=WORKSPACE_ID, run_id=RUN_ID
            )
            self.assertEqual([first], reader.read_new())

            with journal_path.open("ab") as handle:
                handle.write(b'{"eventId":"malformed"')
            before = journal_path.read_bytes()

            with self.assertRaisesRegex(JournalError, "malformed"):
                reader.read_new()

            self.assertEqual(before, journal_path.read_bytes())

    def test_writer_and_reader_reject_foreign_identity(self):
        value = event("CONTROL_DISPATCH")
        with tempfile.TemporaryDirectory() as directory:
            journal_path = Path(directory) / "flow-events.jsonl"
            with self.assertRaisesRegex(JournalError, "workspaceId"):
                FlowJournal(
                    journal_path, workspace_id="wOther", run_id=RUN_ID
                ).append(value)

            FlowJournal(
                journal_path, workspace_id=WORKSPACE_ID, run_id=RUN_ID
            ).append(value)
            with self.assertRaisesRegex(JournalError, "runId"):
                FlowJournalReader(
                    journal_path, workspace_id=WORKSPACE_ID, run_id="run-other"
                ).read_new()


if __name__ == "__main__":
    unittest.main()
