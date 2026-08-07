#!/usr/bin/env python3
"""Append one explicit semantic event to a graph flow journal."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any


SOURCE_REPO = Path(__file__).resolve().parents[3]
if not (SOURCE_REPO / "adapters/herdr").is_dir():
    SOURCE_REPO = Path("/Users/haido/multi-agent-graph-demo")
if str(SOURCE_REPO) not in sys.path:
    sys.path.insert(0, str(SOURCE_REPO))

from adapters.herdr.flow_journal import (  # noqa: E402
    EVENT_SCHEMA_VERSION,
    FlowJournal,
    JournalError,
)


def _json_object(value: str) -> dict[str, Any]:
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("JSON arguments must be objects")
    return parsed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--at", required=True)
    parser.add_argument("--kind", required=True)
    parser.add_argument("--generation", type=int, required=True)
    parser.add_argument("--source", type=_json_object)
    parser.add_argument("--target", type=_json_object)
    parser.add_argument("--assignment", type=_json_object)
    parser.add_argument("--result")
    parser.add_argument("--artifact", type=_json_object)
    parser.add_argument("--reason")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    started = time.perf_counter()
    event_id: str | None = None
    try:
        args = parse_args(argv)
        event_id = args.event_id
        event = {
            "schemaVersion": EVENT_SCHEMA_VERSION,
            "eventId": args.event_id,
            "workspaceId": args.workspace_id,
            "runId": args.run_id,
            "at": args.at,
            "kind": args.kind,
            "generation": args.generation,
        }
        for field in ("source", "target", "assignment", "result", "artifact", "reason"):
            value = getattr(args, field)
            if value is not None:
                event[field] = value
        journal = FlowJournal(
            args.journal.expanduser().resolve(),
            workspace_id=args.workspace_id,
            run_id=args.run_id,
        )
        journal.append(event)
    except (JournalError, OSError, ValueError, json.JSONDecodeError) as error:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        print(
            json.dumps(
                {
                    "status": "error",
                    "eventId": event_id,
                    "appended": False,
                    "elapsedMs": elapsed_ms,
                    "message": str(error),
                },
                separators=(",", ":"),
            )
        )
        return 2

    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    print(
        json.dumps(
            {
                "status": "ok",
                "eventId": event_id,
                "appended": True,
                "elapsedMs": elapsed_ms,
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
