import unittest

from adapters.herdr.observed_events import ObservationError, ObservationLedger


def node(node_id, status="running", assignee="P2", generation=1):
    value = {"id": node_id, "status": status, "assignee": assignee}
    if generation is not None:
        value["generation"] = generation
    return value


class InitialObservationTests(unittest.TestCase):
    def test_first_observation_emits_one_event_per_node_and_noop_repeats(self):
        ledger = ObservationLedger(limit=4)
        nodes = [node("orchestrator"), node("agent-b", status="pending")]

        events = ledger.observe(nodes, observed_at="2026-08-05T10:00:00Z")

        self.assertEqual(
            ["NODE_OBSERVED", "NODE_OBSERVED"], [event["kind"] for event in events]
        )
        self.assertEqual(
            [], ledger.observe(nodes, observed_at="2026-08-05T10:00:02Z")
        )

    def test_initial_events_carry_required_fields_and_utc_timestamp(self):
        ledger = ObservationLedger()
        events = ledger.observe(
            [node("orchestrator")], observed_at="2026-08-05T10:00:00Z"
        )
        event = events[0]

        for key in ("id", "at", "nodeId", "kind", "message"):
            self.assertIn(key, event)
        self.assertEqual("orchestrator", event["nodeId"])
        self.assertTrue(event["at"].endswith("Z"))
        self.assertEqual("observed-000001", event["id"])
        self.assertIn("running", event["message"])

    def test_generation_included_only_for_integer_generation(self):
        ledger = ObservationLedger()
        events = ledger.observe(
            [
                node("with-generation", generation=3),
                node("without-generation", generation=None),
                node("boolean-generation", generation=None),
            ],
            observed_at="2026-08-05T10:00:00Z",
        )
        by_id = {event["nodeId"]: event for event in events}

        self.assertEqual(3, by_id["with-generation"]["generation"])
        self.assertNotIn("generation", by_id["without-generation"])

    def test_default_observed_at_is_utc_z_timestamp(self):
        ledger = ObservationLedger()
        events = ledger.observe([node("orchestrator")])

        self.assertTrue(events[0]["at"].endswith("Z"))


class TransitionTests(unittest.TestCase):
    def setUp(self):
        self.ledger = ObservationLedger(limit=16)
        self.ledger.observe(
            [node("orchestrator", status="running", assignee="P1"), node("agent-b")],
            observed_at="2026-08-05T10:00:00Z",
        )

    def test_status_change_emits_one_event(self):
        events = self.ledger.observe(
            [
                node("orchestrator", status="passed", assignee="P1"),
                node("agent-b"),
            ],
            observed_at="2026-08-05T10:00:02Z",
        )

        self.assertEqual(1, len(events))
        self.assertEqual("NODE_STATUS_CHANGED", events[0]["kind"])
        self.assertEqual("orchestrator", events[0]["nodeId"])

    def test_assignee_change_emits_one_event(self):
        events = self.ledger.observe(
            [
                node("orchestrator", status="running", assignee="P1"),
                node("agent-b", assignee="P3"),
            ],
            observed_at="2026-08-05T10:00:02Z",
        )

        self.assertEqual(
            [("agent-b", "NODE_ASSIGNEE_CHANGED")],
            [(event["nodeId"], event["kind"]) for event in events],
        )

    def test_generation_only_change_emits_one_event_with_new_generation(self):
        events = self.ledger.observe(
            [
                node("orchestrator", status="running", assignee="P1", generation=2),
                node("agent-b"),
            ],
            observed_at="2026-08-05T10:00:02Z",
        )

        self.assertEqual(1, len(events))
        self.assertEqual("observed-000003", events[0]["id"])
        self.assertEqual("NODE_GENERATION_CHANGED", events[0]["kind"])
        self.assertEqual("orchestrator", events[0]["nodeId"])
        self.assertEqual(2, events[0]["generation"])
        self.assertIn("generation 2", events[0]["message"])

    def test_removed_node_emits_single_terminal_event(self):
        events = self.ledger.observe(
            [node("orchestrator", status="running", assignee="P1")],
            observed_at="2026-08-05T10:00:02Z",
        )

        self.assertEqual(
            [("agent-b", "NODE_REMOVED")],
            [(event["nodeId"], event["kind"]) for event in events],
        )
        follow_up = self.ledger.observe(
            [node("orchestrator", status="running", assignee="P1")],
            observed_at="2026-08-05T10:00:04Z",
        )
        self.assertEqual([], follow_up)

    def test_new_node_emits_observed_event(self):
        events = self.ledger.observe(
            [
                node("orchestrator", status="running", assignee="P1"),
                node("agent-b"),
                node("agent-c", status="pending"),
            ],
            observed_at="2026-08-05T10:00:02Z",
        )

        self.assertEqual(
            [("agent-c", "NODE_OBSERVED")],
            [(event["nodeId"], event["kind"]) for event in events],
        )

    def test_simultaneous_changes_order_by_node_id_then_kind(self):
        events = self.ledger.observe(
            [
                node("orchestrator", status="passed", assignee="P9"),
                node("agent-b", status="blocked"),
            ],
            observed_at="2026-08-05T10:00:02Z",
        )

        self.assertEqual(
            [
                ("agent-b", "NODE_STATUS_CHANGED"),
                ("orchestrator", "NODE_ASSIGNEE_CHANGED"),
                ("orchestrator", "NODE_STATUS_CHANGED"),
            ],
            [(event["nodeId"], event["kind"]) for event in events],
        )


class RetentionAndSafetyTests(unittest.TestCase):
    def test_retains_only_the_last_limit_events(self):
        ledger = ObservationLedger(limit=4)
        ledger.observe(
            [node(f"agent-{index}") for index in range(6)],
            observed_at="2026-08-05T10:00:00Z",
        )

        self.assertEqual(4, len(ledger.events))
        self.assertEqual(
            ["agent-2", "agent-3", "agent-4", "agent-5"],
            [event["nodeId"] for event in ledger.events],
        )

    def test_monotonic_ids_span_retained_and_evicted_events(self):
        ledger = ObservationLedger(limit=2)
        ledger.observe(
            [node("agent-a"), node("agent-b"), node("agent-c")],
            observed_at="2026-08-05T10:00:00Z",
        )

        self.assertEqual(
            ["observed-000002", "observed-000003"],
            [event["id"] for event in ledger.events],
        )

    def test_events_property_returns_defensive_copies(self):
        ledger = ObservationLedger()
        ledger.observe([node("orchestrator")], observed_at="2026-08-05T10:00:00Z")

        snapshot = ledger.events
        snapshot[0]["kind"] = "MUTATED"

        self.assertEqual("NODE_OBSERVED", ledger.events[0]["kind"])

    def test_rejects_non_positive_limit(self):
        with self.assertRaises(ObservationError):
            ObservationLedger(limit=0)
        with self.assertRaises(ObservationError):
            ObservationLedger(limit=-1)
        with self.assertRaises(ObservationError):
            ObservationLedger(limit=True)

    def test_rejects_malformed_node_id(self):
        ledger = ObservationLedger()
        with self.assertRaises(ObservationError):
            ledger.observe([{"status": "running"}])
        with self.assertRaises(ObservationError):
            ledger.observe([{"id": "", "status": "running"}])


if __name__ == "__main__":
    unittest.main()
