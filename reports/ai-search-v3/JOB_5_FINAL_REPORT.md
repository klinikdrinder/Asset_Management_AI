# KDI AI Search V3 — Job 5 final report

## Outcome

Central view, download, external-AI, and set-based authorization are applied. Asset RLS now propagates to derived data; search history remains owner-isolated; raw vectors/search documents remain backend-only. The media backend resolves previews/thumbnails through asset RLS and now requires the service-only per-user/per-asset decision for downloads. No frontend UI was changed.

## Preservation and tests

Counts remain exactly: assets 881, source files 890, sources 881, destinations 881, visual vectors 875, semantic index 20, text vectors 20, profiles 10, access controls 881, treatments 12, aliases 6, anatomy 25, actions 22, locations 11. Deep-intelligence and Job 4 production rows remain zero. V1/V2 definition hashes remain `6b179fcb951bf228d434b44baad56c38` and `14f4f1347d13fa2201ac6e20e7e5020b`.

Transactional RLS tests passed all requested general/restricted/clinical/direct-UUID/vector/document/history/mutation and independent-control cases, then rolled back. TypeScript passed; dashboard passed 240/240; Python passed 644 plus 74 subtests; dedicated backend permission tests passed 2/2; login is HTTP 200 and library remains protected at HTTP 307. No `.next` build or deployment ran.

## Operational blockers before Job 6

All 881 assets remain `external_ai_status=NOT_REVIEWED`; no external provider may process a pilot asset until an authorized review explicitly sets that asset to `ALLOWED`. The repository's per-asset download enforcement change is not active on the protected website until a separate reviewed backend deployment is approved. Neither condition was bypassed in Job 5.

Job 6 is therefore not ready for external-AI pilot processing or reliance on the new live download rule. Job 6 was not started.
