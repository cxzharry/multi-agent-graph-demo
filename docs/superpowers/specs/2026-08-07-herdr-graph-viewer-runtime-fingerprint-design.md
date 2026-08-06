# Herdr Graph Viewer Runtime Fingerprint and Stale-Process Recovery Design

**Date:** 2026-08-07
**Status:** Approved

## Problem

The graph viewer launcher currently decides whether to reuse a publisher by
matching its command-line identity: script path, workspace, run, P1 binding,
endpoint, topology mode, and watch mode. It decides whether to reuse the viewer
server from its health service/schema/capabilities response.

Those checks prove that a process serves the right graph, but they do not prove
that the process loaded the current repository bytes. A publisher started
before an update can retain old Python modules in memory while its argv remains
identical to the current desired command. Likewise, a previously built Node
server can keep serving an old backend and frontend after source files change.

The observed production failure demonstrates the gap:

- the session publisher started before the truthful-relationship and observed-
  event commits;
- later invocations considered it reusable because its argv still matched;
- the stored graph continued to contain eight fabricated P1 control edges and
  zero lifecycle events, although current source emits zero session edges and a
  bounded event ledger.

Merge and skill synchronization cannot hot-reload already running Python or
Node processes. The launcher must make runtime byte identity part of reuse.

## Goals

1. Invoking `herdr-graph-viewer` after a repository or installed-skill update
   automatically replaces stale publisher and viewer-server processes.
2. An unchanged current runtime continues to use the existing fast reuse path.
3. Stale processes are restarted in their existing ordinary panes whenever the
   launcher can identify them unambiguously; updates must not create routine
   pane sprawl.
4. The launcher never runs two publishers for the same workspace, scope, run,
   and endpoint during replacement.
5. `ready` means the server and published snapshot both prove current runtime
   fingerprints, not merely that an old URL still responds.
6. Session publisher restart advances the persisted sequence safely and
   preserves bounded observed history when trustworthy history exists.
7. Existing custom manifests, manifestless selection, workspace isolation,
   installed-skill boundaries, and manual invocation behavior remain intact.

## Non-goals

- Automatically starting the viewer when a Herdr or agent session starts.
- Restarting unrelated Herdr panes, agents, workspaces, or processes.
- Treating Git commit identity as the runtime identity.
- Restarting healthy unchanged processes on every invocation.
- Adding a daemon, global hook, background updater, or new polling loop.
- Changing graph relationship inference, agent status mapping, or role naming.
- Changing `herdr-orchestrator` or any sibling installed skill.

## Chosen Architecture

### Deterministic content fingerprints

The launcher computes two SHA-256 fingerprints from repository-relative path
names and file bytes in deterministic sorted order. Paths are part of the hash
so a rename changes identity even when bytes do not.

The **publisher fingerprint** covers non-test Python runtime files directly
under `adapters/herdr/`, including the session publisher, control-state
publisher, lifecycle ledger, package initializer, and any future non-test
helper added to that directory.

The **viewer fingerprint** covers the runtime and build inputs used by the
server and browser application:

- `server.js`, `server/**/*.js`, and `shared/**/*.js`;
- `src/**`, `index.html`, and Vite/TypeScript configuration files;
- `package.json` and `package-lock.json`.

Documentation, tests, screenshots, fixtures, plans, and `node_modules` do not
affect runtime fingerprints. The calculation requires no Git repository and
therefore behaves identically in a source checkout and an installed snapshot.
Missing required runtime files remain a `missing_viewer` error before any pane
mutation.

### Publisher identity contract

Both publisher CLIs accept a launcher-supplied argument that is mandatory for
launcher-managed processes:

```text
--runtime-fingerprint <sha256>
```

The argument remains optional for backward-compatible direct/manual publisher
usage. An omitted value is reported as `unmanaged`; it can publish for manual
diagnosis but can never satisfy launcher reuse or readiness.

Each published snapshot includes the same optional top-level field:

```json
{"publisherFingerprint": "<sha256>"}
```

The existing `role-graph/v1` validator permits additive fields. It will also
validate `publisherFingerprint` as a non-empty string when the field is
present. Historical snapshots without the field remain readable.

Publisher discovery separates two questions:

1. Does this ordinary pane contain the publisher for the exact workspace/run/
   endpoint/topology identity?
2. Does its `--runtime-fingerprint` equal the desired publisher fingerprint?

The result is `reusable`, `stale`, or `missing`. A legacy process without the
argument is `stale`, never reusable. Discovery returns the stale pane so the
launcher can replace it instead of opening a second publisher pane.

### Viewer-server identity contract

The launcher starts the server through the npm wrapper with explicit forwarded,
process-visible arguments:

```text
npm run server -- --port <port> --runtime-fingerprint <sha256>
```

Host and persistence configuration remain environment variables. The arguments
are optional for backward-compatible direct development startup; omitted values
use the existing port behavior and an `unmanaged` fingerprint. `server.js`
validates supplied values and passes the fingerprint into the app.
`/api/health` adds:

```json
{"runtimeFingerprint": "<sha256>"}
```

Server probing distinguishes:

- `viewer-current`: exact service/schema/capabilities and fingerprint;
- `viewer-stale`: correct viewer service but missing or different fingerprint;
- `free`;
- `occupied`: an unrelated service or incompatible viewer.

New server processes expose port and fingerprint in `process-info` argv, so the
launcher can map a stale health response back to one exact ordinary pane.

For the one-time migration from legacy servers without process-visible port or
fingerprint arguments, the launcher may reuse a pane only when exactly one
ordinary pane in the current workspace has all of:

- label `graph-viewer-server`;
- foreground `node server.js` process;
- foreground cwd equal to the selected viewer repository.

Zero legacy candidates means the stale port is treated as occupied and the
launcher may use the next free port. Multiple candidates fail with an explicit
`ambiguous_stale_server` error before mutation. The launcher never inspects or
stops another workspace to recover a stale port.

### Replacement transaction

The existing per-workspace `fcntl` launcher lock encloses discovery,
replacement, startup, and readiness verification.

After discovering both components, replacement proceeds in this order:

1. Capture the latest exact `scopeId + runId` snapshot and its sequence.
2. If the publisher is stale, send `Ctrl+C` to its ordinary pane and wait for
   the shell to become ready.
3. If the server is stale, stop it in its identified ordinary pane and wait for
   the shell.
4. Start or rebuild the server in the same pane and require health with the
   desired viewer fingerprint.
5. Start the publisher in the same pane with the desired publisher fingerprint.
6. Require a new exact snapshot containing that publisher fingerprint before
   returning `ready`.

Only stale components restart. A current server can remain while a stale
publisher is replaced; a current publisher can continue heartbeating after a
stale server is replaced. If both are stale, the publisher stops first so it
does not publish into a server being rebuilt.

Pane-stop waits are bounded. A pane that does not return to a shell produces a
specific recovery error; the launcher does not stack a new process on top of
an unconfirmed old process.

### Snapshot continuity

Control-state mode already has an authoritative integer revision. Replacing a
stale publisher for the same revision supplies `--replace-current`, allowing
the current exact sequence to be replaced with a snapshot carrying current
topology and fingerprint.

Session mode has no control-state revision. Before starting a replacement, the
launcher reads the current exact snapshot sequence and passes the next sequence
floor to the session publisher. The first new snapshot must be strictly newer
than the previous persisted sequence.

The session publisher seeds its bounded observation ledger only from a current
snapshot with the exact scope/run identity and valid observed-event history.
If the prior snapshot has no observed history, as with the legacy failure, it
starts a fresh ledger and emits initial `NODE_OBSERVED` events. Invalid,
mismatched, or unavailable seed data is non-fatal; it cannot lower the sequence
floor or import events from another run.

Readiness for session mode requires both:

- `sequence >` the pre-replacement sequence when a publisher was restarted;
- `publisherFingerprint ==` the desired fingerprint.

This prevents the launcher from immediately accepting the stale snapshot that
was already stored before replacement.

### Return evidence

The launcher result retains the existing `server.reused` and
`publisher.reused` fields and adds concise runtime evidence:

```json
{
  "viewerFingerprint": "<sha256>",
  "publisherFingerprint": "<sha256>",
  "server": {"reused": false, "replaced": true},
  "publisher": {"reused": false, "replaced": true}
}
```

`replaced` is false for a newly created pane and for unchanged reuse. This is
operator evidence only; it does not alter graph selection or session presence.

## Error Handling

- A fingerprint calculation failure occurs before pane mutation.
- A legacy or mismatched publisher is stale, not reusable.
- An ambiguous legacy server fails before mutation rather than killing an
  arbitrary process.
- Failure to stop a stale component is terminal and does not start a duplicate.
- Failure to start a replacement leaves the pane visible for diagnosis; the
  launcher reports the exact component and pane.
- A server with the wrong fingerprint never satisfies readiness.
- A snapshot with the wrong or missing publisher fingerprint never satisfies
  post-replacement readiness.
- Existing behavior for stale/moved/closed panes, empty Herdr responses,
  invalid manifests, occupied ports, and P1 identity errors remains unchanged.

## Performance Contract

- Fingerprints are computed once per invocation under the launcher lock.
- Hashing is linear in the small runtime source set and does not enter the two-
  second publisher polling loop.
- Unchanged invocation reuses both processes without `npm ci`, build, restart,
  new panes, or additional snapshot churn.
- Only a stale viewer fingerprint triggers `npm ci` and the production build.
- Runtime fingerprints never include `node_modules`, generated `dist`, JSONL
  snapshots, receipts, screenshots, or documentation.

## Compatibility and Isolation

- Historical viewer servers without `runtimeFingerprint` are stale but remain
  discoverable for one-time same-pane migration.
- Historical snapshots without `publisherFingerprint` remain readable but
  cannot prove replacement readiness.
- Custom manifests remain authoritative; fingerprints describe code identity,
  not graph authorship.
- Discovery and mutation remain restricted to the caller's exact Herdr
  workspace and ordinary viewer panes.
- The viewer still starts only when the user invokes the skill.
- Installation synchronizes only `skills/herdr-graph-viewer/` after all gates;
  Claude and Codex installed bytes must remain identical.

## Verification

TDD must first reproduce the production failure: a process with exact legacy
argv but no runtime fingerprint is discovered as stale, replaced in its
existing pane, and not accompanied by a second publisher.

The focused matrix must also prove:

1. fingerprint calculation is deterministic, path-sensitive, and excludes
   docs, tests, generated output, and `node_modules`;
2. matching publisher identity plus matching fingerprint is reusable;
3. matching publisher identity with missing/different fingerprint is stale;
4. current viewer health is reused while stale health is replaced or safely
   skipped according to current-workspace pane evidence;
5. ambiguous legacy server discovery fails before any `send-keys`, split, or
   run command;
6. stale publisher stops before stale server, both panes return to shell, and
   replacements reuse those panes;
7. concurrent invokes remain serialized and do not duplicate either process;
8. control-state replacement supplies `--replace-current` and waits for the
   exact revision plus publisher fingerprint;
9. session replacement advances beyond the stored sequence and does not accept
   the old snapshot;
10. legacy session snapshot with zero events becomes zero-edge topology with
    initial observed events after replacement;
11. trustworthy bounded event history survives a session publisher restart;
12. unchanged current runtimes preserve the existing fast reuse path;
13. launcher, publisher, server, protocol, Vitest, build, and real browser smoke
    suites pass;
14. a live current-workspace upgrade replaces stale processes without opening
    extra panes and renders the new graph contract;
15. independent integration review and functional/design/persona QC bind to the
    exact candidate; installed Codex/Claude skill parity is exact.

## Acceptance Evidence for the Reported Failure

Against a persisted session snapshot shaped like the reported failure, the
post-launch exact snapshot must show:

- the same `scopeId` and P1 `runId`;
- a strictly newer sequence;
- current `publisherFingerprint`;
- `edges: []` and no fabricated failure route;
- non-empty initial observed events;
- P1 status derived independently from Herdr (`idle -> pending`,
  `working -> running`).

This separates the expected pending status of an idle orchestrator from the
incorrect stale-process relationships that prompted the change.
