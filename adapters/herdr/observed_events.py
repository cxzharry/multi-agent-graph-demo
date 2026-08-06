#!/usr/bin/env python3
"""A bounded, deterministic lifecycle ledger shared by both publishers.

The ledger compares a current node projection with the previous projection it
already holds and emits ordered, timestamped lifecycle events. It adds no new
process, hook, or polling interval; publishers feed it the nodes they already
build from their existing two-second polls.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone


DEFAULT_LIMIT = 64

# Deterministic ordering for simultaneous transitions on one node.
_KIND_ORDER = {
    "NODE_OBSERVED": 0,
    "NODE_ASSIGNEE_CHANGED": 1,
    "NODE_STATUS_CHANGED": 2,
    "NODE_GENERATION_CHANGED": 3,
    "NODE_REMOVED": 4,
}


class ObservationError(ValueError):
    """Raised when the ledger is misconfigured or given malformed nodes."""


class ObservationLedger:
    """Turn repeated node observations into bounded lifecycle events."""

    def __init__(self, limit: int = DEFAULT_LIMIT) -> None:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ObservationError("limit must be a positive integer")
        self._limit = limit
        self._events: list[dict] = []
        self._counter = 0
        self._previous: dict[str, dict] | None = None

    def observe(
        self,
        nodes: list[dict],
        observed_at: str | None = None,
    ) -> list[dict]:
        """Compare ``nodes`` with the previous projection and emit new events."""
        current = self._project(nodes)
        at = observed_at if isinstance(observed_at, str) and observed_at else _utc_now()

        if self._previous is None:
            transitions = [
                (node_id, "NODE_OBSERVED") for node_id in sorted(current)
            ]
        else:
            transitions = self._diff(self._previous, current)

        new_events = [
            self._build_event(kind, node_id, current.get(node_id) or self._previous[node_id], at)
            for node_id, kind in transitions
        ]

        self._previous = current
        if new_events:
            self._events.extend(new_events)
            if len(self._events) > self._limit:
                self._events = self._events[-self._limit :]
        return copy.deepcopy(new_events)

    @property
    def events(self) -> list[dict]:
        """Return defensive copies of the retained bounded history."""
        return copy.deepcopy(self._events)

    def _project(self, nodes: list[dict]) -> dict[str, dict]:
        projection: dict[str, dict] = {}
        for node in nodes:
            node_id = node.get("id") if isinstance(node, dict) else None
            if not isinstance(node_id, str) or not node_id:
                raise ObservationError("each node requires a non-empty string id")
            generation = node.get("generation")
            projection[node_id] = {
                "status": node.get("status"),
                "assignee": node.get("assignee"),
                "generation": generation
                if isinstance(generation, int) and not isinstance(generation, bool)
                else None,
            }
        return projection

    def _diff(
        self,
        previous: dict[str, dict],
        current: dict[str, dict],
    ) -> list[tuple[str, str]]:
        transitions: list[tuple[str, str]] = []
        for node_id, projection in current.items():
            prior = previous.get(node_id)
            if prior is None:
                transitions.append((node_id, "NODE_OBSERVED"))
                continue
            if projection["status"] != prior["status"]:
                transitions.append((node_id, "NODE_STATUS_CHANGED"))
            if projection["assignee"] != prior["assignee"]:
                transitions.append((node_id, "NODE_ASSIGNEE_CHANGED"))
            if projection["generation"] != prior["generation"]:
                transitions.append((node_id, "NODE_GENERATION_CHANGED"))
        for node_id in previous:
            if node_id not in current:
                transitions.append((node_id, "NODE_REMOVED"))
        transitions.sort(key=lambda item: (item[0], _KIND_ORDER[item[1]]))
        return transitions

    def _build_event(
        self,
        kind: str,
        node_id: str,
        projection: dict,
        at: str,
    ) -> dict:
        self._counter += 1
        event = {
            "id": f"observed-{self._counter:06d}",
            "at": at,
            "nodeId": node_id,
            "kind": kind,
            "message": _message(kind, node_id, projection),
        }
        generation = projection.get("generation")
        if isinstance(generation, int) and not isinstance(generation, bool):
            event["generation"] = generation
        return event


def _message(kind: str, node_id: str, projection: dict) -> str:
    status = projection.get("status") or "unknown"
    assignee = projection.get("assignee") or "unassigned"
    if kind == "NODE_OBSERVED":
        return f"Observed {node_id} as {status}"
    if kind == "NODE_STATUS_CHANGED":
        return f"{node_id} changed status to {status}"
    if kind == "NODE_ASSIGNEE_CHANGED":
        return f"{node_id} reassigned to {assignee}"
    if kind == "NODE_GENERATION_CHANGED":
        generation = projection.get("generation")
        if not isinstance(generation, int) or isinstance(generation, bool):
            generation = "unknown"
        return f"{node_id} changed to generation {generation}"
    if kind == "NODE_REMOVED":
        return f"{node_id} is no longer observed"
    return f"{node_id} {kind}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
