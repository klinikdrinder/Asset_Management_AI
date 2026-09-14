# Job 5.2 live download security tests

| Case | Result | Evidence |
|---|---|---|
| Unauthenticated direct download | PASS | live production returned HTTP 401 with only `{"error":"Authentication required"}` |
| Unauthenticated preview | PASS | live production returned HTTP 401 |
| Direct fabricated UUID bypass | PASS | HTTP 401; no asset resolution or URL |
| Restricted metadata/storage leakage | PASS | denial contained no Drive URL, storage path, signed URL, credential, patient data, or asset metadata |
| View allowed / download denied | PASS (transactional integration) | active user + permitted asset + `can_download=false` produced view true/download false; transaction rolled back |
| Download allowed | PASS (transactional integration) | same fixture with user download and asset `download_allowed=true` produced true; transaction rolled back |
| Restricted asset | PASS (transactional integration) | `internal_usage_status=NOT_ALLOWED` denied both view and download; transaction rolled back |
| External AI unknown | PASS (transactional integration) | `NOT_REVIEWED` remained false; transaction rolled back |

No safe authenticated production HTTP session representing both view-only and download-enabled states was available. Accordingly those two cases were exercised against the live database authorization functions plus the production-compatible route binding test; no account or asset permission was persistently changed. The live unauthenticated/direct-route boundary was tested on the deployed production route.

## D: relocation resume verification (2026-08-20)

The relocated live process was rechecked without changing any account or asset permission:

| Check | Result |
|---|---|
| `/api/health` | PASS — HTTP 200 |
| `/login` | PASS — HTTP 200 |
| protected `/library` | PASS — HTTP 307 to login |
| unauthenticated fabricated-UUID preview | PASS — HTTP 401 |
| unauthenticated fabricated-UUID download | PASS — HTTP 401 |
| unauthenticated known-pilot-UUID download | PASS — HTTP 401 |
| denial-body leakage scan | PASS — no Drive URL, Google API URL, signed URL, service-account material, storage path, destination identifier, or patient marker |

The earlier transactional integration results for view-only denial and authorized download remain applicable: database functions, route binding, and live backend implementation are unchanged. No safe authenticated production HTTP fixture was available during the resume, so those two cases were not repeated over HTTP.
