# Job 5.1 download-enforcement deployment

The Job 5 backend enforcement is located in `dashboard/app/media-service.ts`: downloads resolve the asset through RLS, then call service-only RPC `can_user_download_asset_for(p_user_id, p_asset_id)` and fail closed unless it returns exactly true. The route is `dashboard/app/api/media/[sourceFileId]/download/route.ts`.

Activating this code requires a Next.js release build and the repository's candidate/atomic release workflow. The current branch is `ai-search-v3-job1-safety`, commit `ae469af979826b3dbff02147347c22f66b076751`, with existing uncommitted Job 1–5 work preserved.

Deployment was not attempted. Job 5.1 explicitly requires stopping when pilot authorization is absent. This avoided bundling a production switch after the first readiness requirement failed. The live release was not edited or rebuilt; rollback was not required. Current health: `/login` 200, `/library` 307, unauthenticated fabricated download URL 401.

The backend implementation remains tested locally but is not active in the protected production release. Blocker 2 therefore remains unresolved.
