# Job 5.2 download production deployment

## Artifact

- Backend: `dashboard/app/media-service.ts`
- Route: `dashboard/app/api/media/[sourceFileId]/download/route.ts`
- Authorization: service-only `can_user_download_asset_for(p_user_id, p_asset_id)`
- Candidate commit: `16d50eafef570438a80fa185de61dbed524b013c`
- Candidate: `candidate-16d50ea-20260819-162553`
- New immutable release: `16d50ea-20260819-163112`
- Previous retained release: `66817b0-20260817-165749`

The candidate contained only the seven-line backend authorization change. It passed typecheck, 240 dashboard tests, 192 candidate Python tests, Next production build, staging health, route smoke checks, and runtime acceptance.

The existing atomic deployment script prepared an immutable release, stopped only the verified production process tree, switched the release pointer, restarted through the Scheduled Task, and verified health/login/library/admin routes. Deployment passed at 2026-08-19T08:34:08Z. Rollback was not required and the previous release remains recorded.

Port 3000 stayed live throughout candidate preparation. The controlled switch took about 48.5 seconds from stop initiation to healthy status. No live `.next` directory was edited or deleted.

## D: relocation resume verification (2026-08-20)

- Authoritative Git root: `D:/Asset_Management_AI`; branch `ai-search-v3-job1-safety`; HEAD `4476f6768639aad4d187b822af38a625f2b24cde`.
- Scheduled Task `KDI Media Library` runs `D:\Asset_Management_AI\scripts\start-kdi-media-library-hidden.vbs` with D:-based working directory.
- Port 3000 runs clean worktree commit `4476f6768639aad4d187b822af38a625f2b24cde` from `D:\Asset_Management_AI\.worktrees\storage_migration_candidate\dashboard`.
- The live `media-service.ts` and download route are byte-equivalent to the authoritative repository implementation and retain the `can_user_download_asset_for` check before Drive access.
- No rebuild or production switch was required during this resume because the current D:-based production artifact already contains the deployed enforcement and passed live verification.
- Port 3000 remained available throughout inspection and testing. Rollback was not invoked.
- Relocation caveat: `current-release.txt` and `previous-release.txt` presently name the same verified D:-based worktree. Older immutable D:-based releases remain retained under `.kdi-runtime/releases`, but the pointer pair should be repaired in the next separately authorized deployment-maintenance window.
