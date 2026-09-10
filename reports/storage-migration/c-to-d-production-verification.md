# C: to D: production verification

Verification completed against the D:-based system on 2026-08-20.

- TypeScript typecheck: PASS.
- Dashboard tests: PASS, 240/240 (238 server/unit tests plus 2 client tests).
- Next.js 16.2.12 production build: PASS.
- Python tests: PASS, 646 tests plus 74 subtests.
- Supabase trusted-client preflight: PASS; project and approved-profile lookup reachable; secret exposure check passed.
- Google Drive: PASS; service account authenticated, KDI Master folder reachable, known destination metadata readable, and a 64-byte range returned HTTP 206.
- Port 3000: LISTENING from D:.
- `/api/health`: HTTP 200.
- `/api/version`: HTTP 200.
- `/login`: HTTP 200 and login form content present.
- `/library`: HTTP 307 to `/login?next=%2Flibrary` when unauthenticated.
- Unauthenticated media preview: HTTP 401.
- Unauthenticated download: HTTP 401.
- Filename/semantic/media/auth/download-security behavior: PASS via the dashboard suite and live protected-route checks.

Read-only production counts:

| Table | Count | Verification |
|---|---:|---|
| assets | 881 | live exact count |
| source_files | 890 | live exact count |
| asset_sources | 881 | live exact count |
| asset_destinations | 881 | live exact count |
| asset_visual_embeddings | 875 | live exact count |
| asset_semantic_index | 20 | live exact count |
| asset_embeddings | 20 | live exact count |
| asset_ai_profiles | 10 | latest D:-resident preservation evidence; live Data API read intentionally returns 403 |
| asset_access_control | 881 | live exact count |

No media was modified, no embeddings were regenerated, and no Google Drive original was modified.
