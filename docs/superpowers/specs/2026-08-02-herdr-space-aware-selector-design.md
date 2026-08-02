# Herdr Space-Aware Graph Selector Design

## Status

Approved for implementation on 2026-08-02 under the standing instruction to
auto-approve plans for this viewer work.

## Problem

The graph selector currently renders `<title> · <scopeId> / <runId>`. Herdr
scope IDs such as `herdr:wK` and `herdr:wP` are opaque, so a user cannot quickly
distinguish graphs from spaces such as `herdr-orchestrator` and `car-edge`.

## Goal

Show the live Herdr workspace label, described as the space name in the UI, at
the start of every saved graph option.

Expected examples:

- `herdr-orchestrator · Herdr graph viewer hardening`
- `car-edge · Herdr standard delivery`

The selected graph metadata continues to show `scopeId / runId` for exact
diagnostics.

## Data Contract

Add optional `spaceName` to `role-graph/v1` snapshots and graph summaries.
The launcher resolves it from the exact selected workspace entry returned by
`herdr workspace list` and passes it to the publisher. The publisher copies it
into every snapshot it emits.

The server persists and lists `spaceName` without querying Herdr. The browser
uses `spaceName` when present and falls back to `scopeId` for existing saved
snapshots. Scope and run remain the selection identity; display names never
participate in routing or lookup.

## Boundaries

- Do not derive a space name from repository or worktree paths.
- Do not let the browser or server call the Herdr CLI.
- Do not change `herdr-orchestrator`, install hooks, or alter pane placement.
- Do not migrate or rewrite existing snapshot ledgers.
- Do not address unrelated custom-manifest validation findings in this change.

## Failure Handling

The selected workspace must exist in the successful `herdr workspace list`
response and have a non-empty label. A missing or malformed label is a launcher
selection error before any pane mutation. Existing snapshots without
`spaceName` remain readable through the `scopeId` fallback.

## Verification

- Publisher tests prove `spaceName` is emitted.
- Launcher tests prove exact-workspace label selection, command propagation,
  and failure before pane mutation when the label is unusable.
- Store/server tests prove summaries retain `spaceName`.
- Frontend tests prove the display formatter prefers `spaceName` and falls back
  to `scopeId`.
- Browser smoke proves two spaces are visibly distinguishable in the selector.
- Full tests, build, browser smoke, installed-skill parity, and a read-only
  independent review must pass before delivery.
