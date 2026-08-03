# Active Session Selector Meta-Harness Plan

1. Implement workspace-local snapshot and presence publication with tests.
2. Implement presence TTL, active-first summaries, compact selector groups,
   and browser fixtures with tests.
3. Implement pane-and-session control-state matching plus session-mode launch
   with tests.
4. Integrate only accepted lane commits and run the complete verification set.
5. Evaluate the locked rubric with independent review, functional browser QC,
   layout QC, and operator-persona QC.
6. Route any failed criterion to its owning lane, increment that lane's
   generation, and repeat affected downstream gates up to three iterations.
7. On success, sync only `herdr-graph-viewer`, verify parity, commit, and push.
