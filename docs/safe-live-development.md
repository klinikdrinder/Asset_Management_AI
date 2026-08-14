# KDI safe live development and deployment

Port 3000 is the last known-good production release. Treat its source, `.next`,
environment, process, and Scheduled Task as immutable during feature work. The
standard staging worktree is `.worktrees/staging`; it owns separate dependencies
and a separate `.next`, and its verified server listens only on 127.0.0.1:3001.

## Normal feature development

```text
Confirm /login on live port 3000
Develop and commit in the isolated staging worktree
Run scripts/build-kdi-candidate.ps1 from the staging worktree
Typecheck, dashboard tests, Python tests, build, and runtime acceptance run there
Keep the verified candidate on port 3001
Merge the clean candidate commit to main only at final deployment
Run scripts/deploy-kdi-candidate.ps1 -CandidateRoot <staging-worktree>
Refresh http://127.0.0.1:3000
```

The build script never stops the Scheduled Task, never kills port 3000, and
never writes to the live `.next`. A candidate receives a verification manifest
only after all required checks pass. Runtime acceptance covers authenticated
library/search, semantic search, thumbnail, preview, download, Supabase, and
Google Drive paths without indexing or modifying media data.

## Failed candidate

```text
Live stays unchanged
Fix the candidate in staging
Retry all checks
Deploy only after PASS
```

Do not restart production to diagnose candidate failures.

## Deployment and failed deployment

Deployment creates an immutable release worktree under `.kdi-runtime/releases`,
installs its own dependencies, copies the already verified candidate build, and
records the previous active dashboard. Only then does it update the active
pointer, restart the `KDI Media Library` task once, and check `/api/health`,
`/login`, and `/library`.

If activation or health verification fails, the deploy script immediately
restores the previous pointer and restarts the previous known-good release. It
does not leave production offline for debugging. A create-new deployment lock
prevents concurrent deployments. JSON-line logs are stored under
`.kdi-runtime/logs` and contain timestamps, commit/release identifiers, test and
build outcomes, restart/health results, and rollback outcome—never secrets.

Manual rollback command:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\rollback-kdi-release.ps1
```

Expected interruption is one Scheduled Task restart, normally a few seconds.
Literal zero downtime is not promised. A future optional improvement is a local
reverse proxy switching between two continuously running application ports.

## Safety rules for future Codex work

- Never run `next build` in the active release dashboard.
- Never remove or replace its `.next` during development.
- Never use port 3000 for candidate testing.
- Never deploy a dirty or unverified worktree.
- Never index, embed, copy Drive media, migrate data, or change production env
  as part of this workflow.
- Verify live health before candidate work and after the one final activation.
